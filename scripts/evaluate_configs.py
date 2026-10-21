#!/usr/bin/env python3
"""Ejecuta las consultas de ítem conocido con las configuraciones comparadas.

Cada configuración cambia una sola cosa respecto de la que la precede:
A (referencia) multilingual-e5-small + reordenador mMARCO; B cambia el recuperador
por bge-m3 sin reordenador; C añade a B el reordenador bge-reranker-v2-m3 con 512
tokens; D amplía a 1.024 los tokens que lee ese reordenador; E arma la lista corta de C
fusionando la búsqueda densa con un índice léxico bilingüe. Todas se evalúan sin filtros
y con un top 10 fijo, igual que una búsqueda abierta en la app.
"""

import argparse
import json
import time

import pandas as pd

from sisreco.engine import (build_hybrid_index, encode_documents, load_hybrid_index, load_retriever, load_vectors, model_revision, recommend,
                            save_vectors)
from sisreco.settings import (ARTIFACTS_DIR, CATALOG, EVALUATION_DIR, HYBRID_RRF_K, RERANKER, RETRIEVER, TOP_K, RerankerSpec,
                              RetrieverSpec)

RUNS_DIR = ARTIFACTS_DIR / "evaluation"
# Cada configuración: (recuperador, reordenador o None, ¿fusiona el índice léxico bilingüe?).
CONFIGS = {
    "A": (
        RetrieverSpec("intfloat/multilingual-e5-small", max_seq_length=512, vectors_path=RUNS_DIR / "e5_small.npy",
                      query_prefix="query: ", document_prefix="passage: "),
        RerankerSpec("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", max_length=384, candidates=500),
        False,
    ),
    "B": (RETRIEVER, None, False),
    "C": (RETRIEVER, RERANKER, False),
    # D cambia solo la longitud que lee el reordenador: en C, los pares de más de 512 tokens
    # (42 % de las consultas) obtenían un MRR menor y concentraban sus fallos.
    "D": (RETRIEVER, RerankerSpec("BAAI/bge-reranker-v2-m3", max_length=1024, candidates=100), False),
    # E cambia solo la lista corta de C: fusiona por RRF el top 100 denso con el top 100 del
    # índice léxico bilingüe y reordena los 100 primeros de la fusión.
    "E": (RETRIEVER, RERANKER, True),
}
BATCH_SIZE = {"intfloat/multilingual-e5-small": 64}


def ensure_vectors(catalog: pd.DataFrame, spec: RetrieverSpec):
    try:
        return load_vectors(catalog, spec)
    except FileNotFoundError:
        model = load_retriever(spec)
        vectors = encode_documents(catalog, spec, model=model, batch_size=BATCH_SIZE.get(spec.model_name, 16))
        save_vectors(catalog, vectors, spec, model=model)
        return load_vectors(catalog, spec)


def ensure_lexical_index(catalog: pd.DataFrame):
    """El índice léxico bilingüe solo lo usa la configuración E; se construye al evaluarla."""
    try:
        return load_hybrid_index(catalog)
    except FileNotFoundError:
        build_hybrid_index(catalog)
        return load_hybrid_index(catalog)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs", nargs="+", choices=sorted(CONFIGS), default=sorted(CONFIGS))
    args = parser.parse_args()

    catalog = pd.read_parquet(CATALOG)
    queries = [json.loads(line) for line in (EVALUATION_DIR / "known_item.jsonl").read_text(encoding="utf-8").splitlines()]
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    for name in args.configs:
        retriever_spec, reranker_spec, lexical = CONFIGS[name]
        vectors = ensure_vectors(catalog, retriever_spec)
        lexical_index = ensure_lexical_index(catalog) if lexical else None
        retriever = load_retriever(retriever_spec)
        started = time.time()
        rows = []
        for query in queries:
            results = recommend(catalog, query["description"], top_k=TOP_K, vectors=vectors, retriever=retriever,
                                retriever_spec=retriever_spec, reranker_spec=reranker_spec,
                                lexical_index=lexical_index, generate_evidence=False)
            rows.extend({"query_id": query["query_id"], "rank": rank, "article_id": article_id, "score": float(score)}
                        for rank, (article_id, score) in enumerate(zip(results["id"], results["score"]), start=1))
        elapsed = time.time() - started
        pd.DataFrame(rows).to_csv(RUNS_DIR / f"run_{name}.csv", index=False)
        index_manifest = json.loads(retriever_spec.vectors_path.with_suffix(".json").read_text(encoding="utf-8"))
        (RUNS_DIR / f"run_{name}.json").write_text(json.dumps({
            "retriever": {"model": retriever_spec.model_name, "revision": index_manifest.get("revision"),
                          "max_seq_length": retriever_spec.max_seq_length, "query_prefix": retriever_spec.query_prefix,
                          "document_prefix": retriever_spec.document_prefix,
                          "truncated_fraction": index_manifest.get("truncated_fraction")},
            "reranker": None if reranker_spec is None else {"model": reranker_spec.model_name,
                                                            "revision": model_revision(reranker_spec.model_name),
                                                            "max_length": reranker_spec.max_length,
                                                            "candidates": reranker_spec.candidates},
            "lexical_fusion": {"method": "reciprocal rank fusion", "k": HYBRID_RRF_K} if lexical else None,
            "top_k": TOP_K,
            "seconds_per_query": elapsed / len(queries),
        }, indent=2), encoding="utf-8")
        print(f"Configuración {name}: {len(queries)} consultas en {elapsed:.0f} s ({elapsed / len(queries):.2f} s por consulta)")


if __name__ == "__main__":
    main()
