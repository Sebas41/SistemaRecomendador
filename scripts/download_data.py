#!/usr/bin/env python3
"""Descarga OpenAlex y SciELO, y construye el catálogo Parquet unificado."""

import argparse

from sisreco.catalog import build_catalog
from sisreco.openalex import download_catalog
from sisreco.scielo import download_scielo_catalog
from sisreco.settings import (
    FIELD_SAMPLE_SIZE,
    MAX_SAMPLE_ATTEMPTS,
    MINIMUM_CATALOG_SIZE,
    RAW_CATALOG,
    SCIELO_COLLECTIONS,
    SCIELO_PAGES_PER_COLLECTION,
    TARGET_PER_FIELD,
)


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
    parser.add_argument(
        "--openalex-target-per-field", type=int, default=TARGET_PER_FIELD,
        help=f"Artículos válidos objetivo por campo OpenAlex (por defecto: {TARGET_PER_FIELD}).",
    )
    parser.add_argument(
        "--openalex-sample-size", type=int, default=FIELD_SAMPLE_SIZE,
        help=f"Trabajos aleatorios por campo e intento (máximo API: 10000; por defecto: {FIELD_SAMPLE_SIZE}).",
    )
    parser.add_argument(
        "--openalex-max-attempts", type=int, default=MAX_SAMPLE_ATTEMPTS,
        help=f"Intentos con semillas sucesivas por campo (por defecto: {MAX_SAMPLE_ATTEMPTS}).",
    )
    parser.add_argument(
        "--minimum-catalog-size", type=int, default=MINIMUM_CATALOG_SIZE,
        help=f"Mínimo de registros limpios requerido al terminar (por defecto: {MINIMUM_CATALOG_SIZE}).",
    )
    args = parser.parse_args()

    if args.openalex_target_per_field <= 0:
        parser.error("--openalex-target-per-field debe ser positivo.")
    if not args.openalex_target_per_field <= args.openalex_sample_size <= 10_000:
        parser.error("--openalex-sample-size debe ser al menos el objetivo y no superar 10000.")
    if args.openalex_max_attempts <= 0 or args.scielo_pages_per_collection <= 0:
        parser.error("Los intentos y las páginas SciELO deben ser positivos.")
    if args.minimum_catalog_size < 0:
        parser.error("--minimum-catalog-size no puede ser negativo.")

    if "openalex" in args.sources:
        count = download_catalog(
            target_per_field=args.openalex_target_per_field,
            sample_size=args.openalex_sample_size,
            max_attempts=args.openalex_max_attempts,
        )
        print(f"Descargados {count:,} registros de OpenAlex a {RAW_CATALOG}")
    if "scielo" in args.sources:
        count = download_scielo_catalog(
            collections=tuple(args.scielo_collections),
            pages_per_collection=args.scielo_pages_per_collection,
        )
        print(f"Descargados {count:,} registros válidos de SciELO ArticleMeta.")
    catalog = build_catalog()
    print(f"Catálogo bilingüe limpio: {len(catalog):,} artículos.")
    if len(catalog) < args.minimum_catalog_size:
        raise SystemExit(
            f"El catálogo quedó bajo el mínimo solicitado ({len(catalog):,}/"
            f"{args.minimum_catalog_size:,}). Aumenta --scielo-pages-per-collection "
            "o --openalex-target-per-field y repite la descarga."
        )
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
