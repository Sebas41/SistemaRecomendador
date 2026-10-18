#!/usr/bin/env python3
"""Ejecuta configuraciones de ranking sin modificar juicios humanos."""

import argparse
import json
from time import perf_counter

import pandas as pd

from sisreco.engine import _load_reranker, _load_sentence_model, load_embeddings, recommend
from sisreco.evaluation_profiles import DEVELOPMENT_PROFILES
from sisreco.settings import ARTIFACTS_DIR, CATALOG, DATA_MANIFEST

CONFIGURATIONS = {
    "e5": {"engine": "e5"},
    "current": {"engine": "semantico", "rerank_candidates": 500, "rerank_passage": "enriched"},
    "hybrid_no_rerank": {"engine": "hibrido_sin_rerank"},
}
for candidate_count in (50, 100, 500):
    for passage in ("text", "enriched"):
        for weight in (.25, .50, .75):
            CONFIGURATIONS[f"hybrid_{candidate_count}_{passage}_{weight:.2f}"] = {
                "engine": "hibrido", "rerank_candidates": candidate_count,
                "rerank_passage": passage, "rerank_weight": weight,
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", action="append", choices=sorted(CONFIGURATIONS),
                        help="Configuración que se ejecuta; por defecto se ejecutan las tres referencias.")
    parser.add_argument("--profile-id", action="append", choices=[item["id"] for item in DEVELOPMENT_PROFILES])
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()
    if args.top_k <= 0:
        raise SystemExit("--top-k debe ser positivo")
    configurations = args.configuration or ["e5", "current", "hybrid_no_rerank"]
    profiles = [item for item in DEVELOPMENT_PROFILES if not args.profile_id or item["id"] in args.profile_id]
    catalog = pd.read_parquet(CATALOG)
    vectors = load_embeddings(catalog)
    model = _load_sentence_model(local_files_only=True)
    reranker = _load_reranker(local_files_only=True)
    rows = []
    for profile in profiles:
        for language in ("es", "en"):
            for name in configurations:
                options = CONFIGURATIONS[name]
                started = perf_counter()
                result = recommend(catalog, profile[language], top_k=args.top_k, embeddings=vectors,
                    model=model, reranker=reranker, generate_evidence=False, **options)
                seconds = perf_counter() - started
                for rank, (_, article) in enumerate(result.iterrows(), 1):
                    rows.append({"profile_id": profile["id"], "query_language": language,
                        "configuration": name, "rank": rank, "article_id": article["id"],
                        "title": article["title"], "score": article["score"],
                        "latency_seconds": seconds, "result_count": len(result)})
                print(f"{profile['id']} {language} {name}: {len(result)} en {seconds:.2f}s", flush=True)
    output = ARTIFACTS_DIR / "ranking_experiments.csv"
    pd.DataFrame(rows).to_csv(output, index=False)
    manifest = {"configurations": {name: CONFIGURATIONS[name] for name in configurations},
                "top_k": args.top_k, "catalog_manifest": json.loads(DATA_MANIFEST.read_text()),
                "profiles": profiles}
    (ARTIFACTS_DIR / "ranking_experiments_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
