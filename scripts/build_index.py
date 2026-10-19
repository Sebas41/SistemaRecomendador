#!/usr/bin/env python3
"""Precalcula los vectores bge-m3, el índice léxico bilingüe y la referencia TF-IDF."""

import argparse

import pandas as pd

from sisreco.engine import (
    build_hybrid_index,
    build_tfidf_index,
    encode_documents,
    load_reranker,
    load_retriever,
    save_vectors,
)
from sisreco.settings import CATALOG, RERANKER, RETRIEVER


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lexical-only", action="store_true",
                        help="Reconstruye solo los índices léxicos, sin recodificar el catálogo con bge-m3 (unos 70 minutos en GPU).")
    args = parser.parse_args()
    if not CATALOG.exists():
        raise SystemExit("Falta el catálogo. Ejecuta primero: python scripts/download_data.py")

    catalog = pd.read_parquet(CATALOG)
    build_tfidf_index(catalog)
    build_hybrid_index(catalog)
    if args.lexical_only:
        print(f"Índices léxicos preparados para {len(catalog):,} artículos.")
        return
    model = load_retriever(RETRIEVER)
    save_vectors(catalog, encode_documents(catalog, RETRIEVER, model=model), RETRIEVER, model=model)
    load_reranker(RERANKER)  # Descarga el reordenador durante la preparación para usar la app sin conexión.
    print(f"Vectores, índices léxicos y reordenador preparados para {len(catalog):,} artículos.")


if __name__ == "__main__":
    main()
