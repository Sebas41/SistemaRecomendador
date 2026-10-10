#!/usr/bin/env python3
"""Descarga la muestra balanceada y construye el catálogo Parquet."""

from sisreco.catalog import build_catalog
from sisreco.openalex import download_catalog
from sisreco.settings import RAW_CATALOG


def main() -> None:
    count = download_catalog()
    print(f"Descargados {count:,} registros de OpenAlex a {RAW_CATALOG}")
    catalog = build_catalog()
    print(f"Catálogo bilingüe limpio: {len(catalog):,} artículos.")
    print("Por campo:")
    print(catalog["field"].value_counts().to_string())
    print("\nPor idioma:")
    print(catalog["language"].value_counts().to_string())


if __name__ == "__main__":
    main()
