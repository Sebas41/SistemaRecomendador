#!/usr/bin/env python3
"""Prepara ocho listas ciegas para evaluar artículos similares por contenido."""

import json
from time import perf_counter

import pandas as pd

from sisreco.engine import load_embeddings, recommend_similar
from sisreco.settings import ARTIFACTS_DIR, CATALOG, DATA_MANIFEST

SEEDS = {
    "arquitectura_empresarial": "https://openalex.org/W4410618283",
    "energia_solar": "https://openalex.org/W7116704433",
    "diabetes": "https://openalex.org/W3003081363",
    "educacion": "https://openalex.org/W4409339975",
    "agua": "https://openalex.org/W7115166932",
    "credito": "https://openalex.org/W4416063149",
    "lenguas_indigenas": "https://openalex.org/W7118813419",
    "agricultura": "https://openalex.org/W4386307387",
}


def main():
    catalog = pd.read_parquet(CATALOG)
    vectors = load_embeddings(catalog)
    rows = []
    for area, seed_id in SEEDS.items():
        seed = catalog.loc[catalog["id"].eq(seed_id)].iloc[0]
        started = perf_counter()
        results = recommend_similar(catalog, seed_id, embeddings=vectors, top_k=5)
        seconds = perf_counter() - started
        for rank, (_, article) in enumerate(results.iterrows(), 1):
            rows.append({"area": area, "seed_id": seed_id, "seed_title": seed["title"],
                         "rank": rank, "article_id": article["id"], "title": article["title"],
                         "abstract": article["abstract"], "field": article["field"],
                         "year": article["year"], "language": article["language"], "url": article["url"],
                         "similarity": article["score"], "latency_seconds": seconds})
        print(f"{area}: {len(results)} resultados en {seconds:.2f}s", flush=True)
    results = pd.DataFrame(rows)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(ARTIFACTS_DIR / "similarity_evaluation_candidates.csv", index=False)
    ratings = results.drop(columns=["similarity", "latency_seconds"]).copy()
    ratings["relevance"] = ""
    ratings.to_csv(ARTIFACTS_DIR / "similarity_evaluation_ratings.csv", index=False)
    manifest = {"seeds": SEEDS, "catalog_manifest": json.loads(DATA_MANIFEST.read_text()), "top_k": 5}
    (ARTIFACTS_DIR / "similarity_evaluation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Revisión de similares: {ARTIFACTS_DIR / 'similarity_evaluation_ratings.csv'}")


if __name__ == "__main__":
    main()
