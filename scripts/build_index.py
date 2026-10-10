#!/usr/bin/env python3
"""Precalcula el índice semántico multilingüe y la referencia TF-IDF."""

from sisreco.engine import _load_sentence_model, build_tfidf_index, encode_documents, save_embeddings
from sisreco.settings import CATALOG as CATALOG_PATH


def main() -> None:
    if not CATALOG_PATH.exists():
        raise SystemExit("Falta el catálogo. Ejecuta primero: python scripts/download_data.py")
    import pandas as pd

    catalog = pd.read_parquet(CATALOG_PATH)
    model = _load_sentence_model()
    vectors = encode_documents(catalog, model=model)
    save_embeddings(catalog, vectors, model=model)
    build_tfidf_index(catalog)
    print(f"Índices preparados para {len(catalog):,} artículos.")


if __name__ == "__main__":
    main()
