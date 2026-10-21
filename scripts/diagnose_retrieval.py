#!/usr/bin/env python3
"""Registra las etapas de recuperación por perfil y verifica una muestra estratificada de vectores.

Para cada perfil de data/evaluation/topics.jsonl y cada configuración, guarda los
identificadores de la lista densa, la léxica y la fusionada (si aplica) y el top final, para
ver en qué etapa entra o sale cada artículo. La auditoría recodifica una muestra y la compara
con los vectores guardados: un coseno menor que 0,999 indica un índice desactualizado.
"""

import argparse
import json
from datetime import datetime, timezone
from time import perf_counter

import numpy as np
import pandas as pd

from evaluate_configs import CONFIGS, ensure_lexical_index
from sisreco.engine import encode_documents, load_retriever, load_vectors, recommend
from sisreco.settings import ARTIFACTS_DIR, CATALOG, DATA_MANIFEST, EVALUATION_DIR, RETRIEVER, SEED, TOP_K

PROFILES = [json.loads(line) for line in (EVALUATION_DIR / "topics.jsonl").read_text(encoding="utf-8").splitlines()]


def stratified_positions(catalog: pd.DataFrame, count: int = 100, seed: int = SEED) -> np.ndarray:
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
    fresh = encode_documents(sample, RETRIEVER, model=model, show_progress_bar=False)
    saved = np.asarray(vectors[positions])
    cosines = np.einsum("ij,ij->i", saved, fresh) / (np.linalg.norm(saved, axis=1) * np.linalg.norm(fresh, axis=1))
    records = []
    for (_, article), score in zip(sample.iterrows(), cosines):
        records.append({"id": article["id"], "source_database": article.get("source_database"),
                        "language": article["language"], "saved_vs_current_cosine": float(score)})
    return records


def query_diagnostics(catalog, configs: list[str], profile_ids: set[str]):
    rows = []
    columns = ["id", "title", "score", "retrieval_score"]
    for name in configs:
        retriever_spec, reranker_spec, lexical = CONFIGS[name]
        vectors = load_vectors(catalog, retriever_spec)
        retriever = load_retriever(retriever_spec, local_files_only=True)
        lexical_index = ensure_lexical_index(catalog) if lexical else None
        for profile in PROFILES:
            if profile["profile_id"] not in profile_ids:
                continue
            for language in ("es", "en"):
                details = {}
                started = perf_counter()
                result = recommend(catalog, profile[language], top_k=TOP_K, vectors=vectors, retriever=retriever,
                                   retriever_spec=retriever_spec, reranker_spec=reranker_spec, lexical_index=lexical_index,
                                   generate_evidence=False, diagnostics=details)
                dense_rank = {identifier: rank for rank, identifier in enumerate(details["dense_ids"], start=1)}
                records = result[columns].to_dict("records")
                for record in records:
                    record["dense_rank"] = dense_rank.get(record["id"])
                rows.append({"profile_id": profile["profile_id"], "language": language, "config": name,
                             "seconds": perf_counter() - started, "stages": details, "results": records})
                print(f"{profile['profile_id']} {language} {name}", flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--configs", nargs="+", choices=sorted(CONFIGS), default=["C"])
    parser.add_argument("--profile-id", action="append", choices=[item["profile_id"] for item in PROFILES],
                        help="Perfil para diagnosticar; por defecto, todos.")
    args = parser.parse_args()
    catalog = pd.read_parquet(CATALOG)
    vectors = load_vectors(catalog, RETRIEVER)
    model = load_retriever(RETRIEVER, local_files_only=True)
    audit = vector_audit(catalog, vectors, model, args.sample_size)
    minimum = min(row["saved_vs_current_cosine"] for row in audit)
    if minimum < .999:
        raise SystemExit("Se detectaron vectores que no coinciden con el índice guardado; regenera el índice antes de evaluar.")
    profile_ids = set(args.profile_id or [item["profile_id"] for item in PROFILES])
    output = {"executed_at_utc": datetime.now(timezone.utc).isoformat(),
              "catalog_sha256": json.loads(DATA_MANIFEST.read_text(encoding="utf-8"))["catalog_sha256"],
              "vector_audit_min_cosine": minimum, "vector_audit": audit,
              "queries": query_diagnostics(catalog, args.configs, profile_ids)}
    target = ARTIFACTS_DIR / "retrieval_diagnostics.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Diagnóstico guardado: {target}")


if __name__ == "__main__":
    main()
