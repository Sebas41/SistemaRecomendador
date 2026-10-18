#!/usr/bin/env python3
"""Guarda ejemplos reales sin conexión; no asigna relevancia ni sobrescribe juicios."""

import argparse
import json
from time import perf_counter
from pathlib import Path

import pandas as pd

from sisreco.engine import (
    _load_reranker, _load_sentence_model, load_embeddings, recommend, recommend_similar,
)
from sisreco.settings import ARTIFACTS_DIR, CATALOG, DATA_MANIFEST

QUERIES = [
    "agentes de inteligencia artificial para la arquitectura empresarial",
    "machine learning for solar energy generation forecasting",
    "aplicaciones móviles para el autocuidado de pacientes con diabetes",
    "digital documentation and preservation of indigenous languages",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article-id", action="append", help="Evaluar similares a este ID; se puede repetir. Omite las búsquedas por texto.")
    parser.add_argument("--output", type=Path, default=ARTIFACTS_DIR / "recommendation_examples.json")
    args = parser.parse_args()
    catalog = pd.read_parquet(CATALOG)
    vectors = load_embeddings(catalog)
    report = {"catalog_records": len(catalog), "queries": [], "similar": [],
              "note": "Ejemplos de funcionamiento. No son una evaluación humana de pertinencia."}
    if DATA_MANIFEST.exists():
        report["catalog_sha256"] = json.loads(DATA_MANIFEST.read_text())["catalog_sha256"]
    seed_ids = list(args.article_id or [])
    if not seed_ids:
        model = _load_sentence_model(local_files_only=True)
        reranker = _load_reranker(local_files_only=True)
        for query in QUERIES:
            started = perf_counter()
            results = recommend(catalog, query, embeddings=vectors, model=model,
                                reranker=reranker, generate_evidence=False)
            report["queries"].append(dict(query=query, seconds=round(perf_counter() - started, 3),
                results=results[["id", "title", "score"]].to_dict("records")))
            if not results.empty:
                seed_ids.append(results.iloc[0]["id"])
            print(f"Búsqueda: {len(results)} resultados — {query}", flush=True)
    for seed_id in dict.fromkeys(seed_ids):
        started = perf_counter()
        results = recommend_similar(catalog, seed_id, embeddings=vectors)
        elapsed = round(perf_counter() - started, 3)
        seed = catalog.loc[catalog["id"].eq(seed_id)].iloc[0]
        assert seed_id not in results["id"].tolist()
        assert results["id"].is_unique and results["score"].is_monotonic_decreasing
        report["similar"].append(dict(seed_id=seed_id, seed_title=seed["title"], seconds=elapsed,
            results=results[["id", "title", "score"]].to_dict("records")))
        print(f"Similares: {len(results)} resultados en {elapsed}s — {seed['title']}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Ejemplos guardados en {args.output}")


if __name__ == "__main__":
    main()
