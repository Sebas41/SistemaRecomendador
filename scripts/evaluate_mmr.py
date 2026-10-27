#!/usr/bin/env python3
"""Genera rankings MMR, ILD@10 y una hoja ciega de pertinencia humana.

Ejecuta los 10 perfiles bilingües de data/evaluation/topics.jsonl con lambda=1, 0.7 y 0.5.
Los tres valores comparten el recuperador, los vectores, el reranker y su shortlist de 100.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pandas as pd

from sisreco.engine import load_reranker, load_retriever, load_vectors, recommend
from sisreco.mmr_evaluation import MMR_LAMBDAS, build_blind_rating_sheet, diversity_by_query
from sisreco.settings import ARTIFACTS_DIR, CATALOG, EVALUATION_DIR, RERANKER, RETRIEVER, SEED, TOP_K

MMR_DIR = ARTIFACTS_DIR / "mmr"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-ids", nargs="+", help="Limita la corrida a perfiles como P01 P03.")
    args = parser.parse_args()

    if not CATALOG.exists():
        raise SystemExit("Falta el catálogo. Ejecuta primero: python scripts/download_data.py")
    profiles_path = EVALUATION_DIR / "topics.jsonl"
    if not profiles_path.exists():
        raise SystemExit(f"Faltan los perfiles de evaluación: {profiles_path}")

    catalog = pd.read_parquet(CATALOG)
    profiles = [json.loads(line) for line in profiles_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.profile_ids:
        requested = set(args.profile_ids)
        profiles = [profile for profile in profiles if profile["profile_id"] in requested]
        missing = requested - {profile["profile_id"] for profile in profiles}
        if missing:
            raise SystemExit(f"Perfiles desconocidos: {', '.join(sorted(missing))}")
    if not profiles:
        raise SystemExit("No hay perfiles para evaluar.")

    print("Cargando catálogo, vectores y modelos. No se reconstruye el índice.")
    vectors = load_vectors(catalog, RETRIEVER)
    retriever = load_retriever(RETRIEVER)
    reranker = load_reranker(RERANKER)

    ranking_rows = []
    total = len(profiles) * 2 * len(MMR_LAMBDAS)
    completed = 0
    for profile in profiles:
        for language in ("es", "en"):
            query_id = f"{profile['profile_id']}_{language}"
            for weight in MMR_LAMBDAS:
                results = recommend(
                    catalog,
                    profile[language],
                    top_k=TOP_K,
                    vectors=vectors,
                    retriever=retriever,
                    reranker=reranker,
                    diversity_lambda=weight,
                    generate_evidence=False,
                )
                ranking_rows.extend({
                    "query_id": query_id,
                    "profile_id": profile["profile_id"],
                    "query_language": language,
                    "lambda": weight,
                    "rank": rank,
                    "article_id": str(row.id),
                    "score": float(row.score),
                } for rank, row in enumerate(results.itertuples(index=False), start=1))
                completed += 1
                print(f"[{completed}/{total}] {query_id}, lambda={weight:g}")

    rankings = pd.DataFrame(ranking_rows)
    diversity = diversity_by_query(rankings, catalog, vectors, top_k=TOP_K)
    ratings, key = build_blind_rating_sheet(rankings, catalog, profiles, seed=SEED)

    MMR_DIR.mkdir(parents=True, exist_ok=True)
    rankings.to_csv(MMR_DIR / "rankings_key.csv", index=False, encoding="utf-8")
    diversity.to_csv(MMR_DIR / "diversity.csv", index=False, encoding="utf-8")
    ratings.to_csv(MMR_DIR / "human_ratings.csv", index=False, encoding="utf-8")
    key.to_csv(MMR_DIR / "human_ratings_key.csv", index=False, encoding="utf-8")
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_rows": len(catalog),
        "profiles": [profile["profile_id"] for profile in profiles],
        "query_languages": ["es", "en"],
        "lambdas": list(MMR_LAMBDAS),
        "top_k": TOP_K,
        "candidate_shortlist": RERANKER.candidates,
        "retriever": RETRIEVER.model_name,
        "reranker": RERANKER.model_name,
        "rating_unit": "one grade per profile/article, reused across languages and lambdas",
    }
    (MMR_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nListas: {len(rankings)} · ILD por consulta: {len(diversity)}")
    print(f"Artículos únicos para calificar: {len(ratings)}")
    print(f"Completa la columna relevance en {MMR_DIR / 'human_ratings.csv'} con 0, 1 o 2.")
    print("No abras human_ratings_key.csv hasta terminar la calificación ciega.")


if __name__ == "__main__":
    main()
