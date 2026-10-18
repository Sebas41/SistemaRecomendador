#!/usr/bin/env python3
"""Precalcula índices semántico, léxico híbrido y TF-IDF de referencia."""

import argparse

from sisreco.engine import (
    _load_reranker,
    _load_sentence_model,
    build_tfidf_index,
    build_hybrid_index,
    encode_documents,
    save_embeddings,
)
from sisreco.settings import CATALOG as CATALOG_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hybrid-only", action="store_true",
                        help="Reconstruye el índice léxico híbrido sin recodificar E5.")
    args = parser.parse_args()
    if not CATALOG_PATH.exists():
        raise SystemExit("Falta el catálogo. Ejecuta primero: python scripts/download_data.py")
    import pandas as pd

    catalog = pd.read_parquet(CATALOG_PATH)
    build_hybrid_index(catalog)
    if args.hybrid_only:
        print(f"Índice híbrido preparado para {len(catalog):,} artículos.")
        return
    model = _load_sentence_model()
    vectors = encode_documents(catalog, model=model)
    save_embeddings(catalog, vectors, model=model)
    build_tfidf_index(catalog)
    _load_reranker()  # Descarga el reranker durante la preparación para usar la app sin conexión.
    print(f"Índices y reranker preparados para {len(catalog):,} artículos.")


if __name__ == "__main__":
    main()
