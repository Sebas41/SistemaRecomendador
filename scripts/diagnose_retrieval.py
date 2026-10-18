#!/usr/bin/env python3
"""Registra etapas de recuperación y verifica una muestra estratificada de vectores."""

import argparse
import json
from datetime import datetime, timezone
from time import perf_counter

import numpy as np
import pandas as pd

from sisreco.engine import _load_reranker, _load_sentence_model, encode_documents, load_embeddings, recommend
from sisreco.evaluation_profiles import ALL_PROFILES
from sisreco.settings import ARTIFACTS_DIR, CATALOG, DATA_MANIFEST, EMBEDDINGS_MANIFEST

ENGINES = ("e5", "semantico", "hibrido_sin_rerank", "hibrido")


def stratified_positions(catalog: pd.DataFrame, count: int = 100, seed: int = 42) -> np.ndarray:
    """Muestra posiciones reproducibles que preservan combinaciones fuente-idioma."""
    if count <= 0:
        raise ValueError("La muestra debe ser positiva.")
    rng = np.random.default_rng(seed)
    groups = catalog.fillna({"source_database": "Unknown", "language": "unknown"}).groupby(["source_database", "language"], sort=True)
    selected: list[int] = []
    for _, frame in groups:
        selected.append(int(rng.choice(frame.index.to_numpy())))
    available = np.setdiff1d(catalog.index.to_numpy(), np.asarray(selected), assume_unique=False)
    remaining = min(count - len(selected), len(available))
    if remaining > 0:
        selected.extend(rng.choice(available, size=remaining, replace=False).astype(int).tolist())
    return np.asarray(sorted(selected[:count]), dtype=int)


def vector_audit(catalog, vectors, model, count: int):
    positions = stratified_positions(catalog, count=count)
    sample = catalog.iloc[positions]
    fresh = encode_documents(sample, model=model, show_progress_bar=False)
    saved = np.asarray(vectors[positions])
    cosines = np.einsum("ij,ij->i", saved, fresh) / (np.linalg.norm(saved, axis=1) * np.linalg.norm(fresh, axis=1))
    records = []
    for (_, article), score in zip(sample.iterrows(), cosines):
        records.append({"id": article["id"], "source_database": article.get("source_database"),
                        "language": article["language"], "saved_vs_current_cosine": float(score)})
    return records


def query_diagnostics(catalog, vectors, model, reranker, profile_ids: set[str]):
    rows = []
    columns = ["id", "title", "score", "semantic_score", "lexical_score", "retrieval_score", "reranker_score"]
    for profile in ALL_PROFILES:
        if profile["id"] not in profile_ids:
            continue
        for language in ("es", "en"):
            for engine in ENGINES:
                details = {}
                started = perf_counter()
                result = recommend(catalog, profile[language], engine=engine, top_k=10, embeddings=vectors,
                    model=model, reranker=reranker, generate_evidence=False, diagnostics=details)
                existing = [column for column in columns if column in result]
                rows.append({"profile_id": profile["id"], "language": language, "engine": engine,
                    "seconds": perf_counter() - started, "stages": details,
                    "results": result[existing].replace({np.nan: None}).to_dict("records")})
                print(f"{profile['id']} {language} {engine}", flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--profile-id", action="append", choices=[item["id"] for item in ALL_PROFILES],
                        help="Perfil para diagnosticar; por defecto usa los ocho de desarrollo.")
    args = parser.parse_args()
    catalog = pd.read_parquet(CATALOG)
    vectors = load_embeddings(catalog)
    model = _load_sentence_model(local_files_only=True)
    reranker = _load_reranker(local_files_only=True)
    profile_ids = set(args.profile_id or [item["id"] for item in ALL_PROFILES[:8]])
    output = {"executed_at_utc": datetime.now(timezone.utc).isoformat(),
              "catalog_manifest": json.loads(DATA_MANIFEST.read_text()),
              "embedding_manifest": json.loads(EMBEDDINGS_MANIFEST.read_text()),
              "vector_audit": vector_audit(catalog, vectors, model, args.sample_size),
              "queries": query_diagnostics(catalog, vectors, model, reranker, profile_ids)}
    output["vector_audit_min_cosine"] = min(row["saved_vs_current_cosine"] for row in output["vector_audit"])
    if output["vector_audit_min_cosine"] < .999:
        raise SystemExit("Se detectaron vectores que no coinciden con el índice guardado; no continúes con experimentos.")
    target = ARTIFACTS_DIR / "retrieval_diagnostics.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Diagnóstico guardado: {target}")


if __name__ == "__main__":
    main()
