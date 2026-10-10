#!/usr/bin/env python3
"""Descarga OpenAlex y SciELO, y construye el catálogo Parquet unificado."""

import argparse

from sisreco.catalog import build_catalog
from sisreco.openalex import download_catalog
from sisreco.scielo import download_scielo_catalog
from sisreco.settings import RAW_CATALOG, SCIELO_COLLECTIONS, SCIELO_PAGES_PER_COLLECTION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sources", nargs="+", choices=("openalex", "scielo"),
        default=("openalex", "scielo"),
        help="Fuentes que se descargan (por defecto: ambas).",
    )
    parser.add_argument(
        "--scielo-pages-per-collection", type=int,
        default=SCIELO_PAGES_PER_COLLECTION,
        help=f"Páginas aleatorias por colección SciELO (por defecto: {SCIELO_PAGES_PER_COLLECTION}).",
    )
    parser.add_argument(
        "--scielo-collections", nargs="+", default=SCIELO_COLLECTIONS,
        help="Códigos de colección SciELO que se muestrean.",
    )
    args = parser.parse_args()

    if "openalex" in args.sources:
        count = download_catalog()
        print(f"Descargados {count:,} registros de OpenAlex a {RAW_CATALOG}")
    if "scielo" in args.sources:
        count = download_scielo_catalog(
            collections=tuple(args.scielo_collections),
            pages_per_collection=args.scielo_pages_per_collection,
        )
        print(f"Descargados {count:,} registros válidos de SciELO ArticleMeta.")
    catalog = build_catalog()
    print(f"Catálogo bilingüe limpio: {len(catalog):,} artículos.")
    print("Por fuente:")
    print(catalog["source_database"].value_counts().to_string())
    print("\nPor campo OpenAlex:")
    print(catalog.loc[catalog["source_database"].eq("OpenAlex"), "field"].value_counts().to_string())
    print("\nPor clasificación SciELO:")
    print(catalog.loc[catalog["source_database"].eq("SciELO"), "field"].value_counts().to_string())
    print("\nPor idioma:")
    print(catalog["language"].value_counts().to_string())


if __name__ == "__main__":
    main()
