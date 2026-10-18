#!/usr/bin/env python3
"""Genera resultados ciegos para comparar motores de recuperación."""

import json
import random
from pathlib import Path
from time import perf_counter

import pandas as pd

from sisreco.engine import _load_reranker, _load_sentence_model, load_embeddings, recommend
from sisreco.evaluation_profiles import ALL_PROFILES, DEVELOPMENT_PROFILES, HELDOUT_PROFILES
from sisreco.settings import ARTIFACTS_DIR, CATALOG, DATA_MANIFEST, EMBEDDINGS_MANIFEST

ENGINES = ("e5", "semantico", "hibrido_sin_rerank", "hibrido")
OUTPUT = ARTIFACTS_DIR / "evaluation_v2_candidates.csv"
RATINGS = ARTIFACTS_DIR / "evaluation_v2_ratings.csv"
KEY = ARTIFACTS_DIR / "evaluation_v2_blind_key.json"
MANIFEST = ARTIFACTS_DIR / "evaluation_v2_manifest.json"


def main():
    catalog = pd.read_parquet(CATALOG)
    vectors = load_embeddings(catalog)
    model = _load_sentence_model(local_files_only=True)
    reranker = _load_reranker(local_files_only=True)
    labels = list("ABCD")
    random.Random(42).shuffle(labels)
    engine_labels = dict(zip(ENGINES, labels))
    rows = []
    for profile in ALL_PROFILES:
        split = "development" if profile in DEVELOPMENT_PROFILES else "heldout"
        for language in ("es", "en"):
            for engine_name in ENGINES:
                started = perf_counter()
                result = recommend(catalog, profile[language], engine=engine_name, top_k=10,
                    embeddings=vectors, model=model, reranker=reranker, generate_evidence=False)
                elapsed = perf_counter() - started
                for rank, (_, article) in enumerate(result.iterrows(), start=1):
                    rows.append({"split": split, "profile_id": profile["id"], "profile_area": profile["area"],
                        "query_language": language, "query": profile[language],
                        "anonymous_engine": engine_labels[engine_name], "rank": rank,
                        "article_id": article["id"], "title": article["title"], "abstract": article["abstract"],
                        "field": article["field"], "year": article["year"], "article_language": article["language"],
                        "url": article["url"], "latency_seconds": elapsed,
                        "result_count": len(result)})
                print(f"{profile['id']} {language} {engine_name}: {len(result)} resultados en {elapsed:.2f}s", flush=True)
    candidates = pd.DataFrame(rows)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(OUTPUT, index=False)
    blind_columns = ["split", "profile_id", "profile_area", "query_language", "query", "article_id", "title", "abstract", "field", "year", "article_language", "url"]
    ratings = candidates[blind_columns].drop_duplicates(["split", "profile_id", "query_language", "article_id"]).copy()
    ratings["relevance"] = ""
    ratings.to_csv(RATINGS, index=False)
    manifest = {"engines": engine_labels, "top_k": 10, "profiles": ALL_PROFILES,
                "catalog_records": len(catalog), "catalog_manifest": json.loads(DATA_MANIFEST.read_text()),
                "embedding_manifest": json.loads(EMBEDDINGS_MANIFEST.read_text()),
                "ratings_file": str(RATINGS), "candidate_file": str(OUTPUT)}
    KEY.write_text(json.dumps({label: engine for engine, label in engine_labels.items()}, indent=2), encoding="utf-8")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Revisión ciega: {RATINGS}")
    print(f"Resultados ordenados: {len(candidates)}; artículos únicos a calificar: {len(ratings)}")


if __name__ == "__main__":
    main()
