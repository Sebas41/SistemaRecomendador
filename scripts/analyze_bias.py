#!/usr/bin/env python3
"""Crea tablas de cobertura para el análisis de sesgos de Parte 3."""

import pandas as pd

from sisreco.settings import ARTIFACTS_DIR, CATALOG


def main():
    if not CATALOG.exists():
        raise SystemExit("Falta el catálogo. Ejecuta primero: python scripts/download_data.py")
    catalog = pd.read_parquet(CATALOG)
    fields = catalog.groupby("field",as_index=False).agg(
        articles=("id","count"),earliest_year=("year","min"),latest_year=("year","max")
    ).sort_values("articles",ascending=False)
    languages = catalog.groupby(["field","language"]).size().unstack(fill_value=0)
    sources = catalog.groupby("source_database",as_index=False).agg(
        articles=("id","count"),earliest_year=("year","min"),latest_year=("year","max")
    ).sort_values("articles",ascending=False)
    source_languages = catalog.groupby(["source_database","language"]).size().unstack(fill_value=0)
    source_fields = catalog.groupby(["source_database","field"]).size().unstack(fill_value=0)
    ARTIFACTS_DIR.mkdir(parents=True,exist_ok=True)
    fields.to_csv(ARTIFACTS_DIR / "bias_coverage_by_field.csv",index=False)
    languages.to_csv(ARTIFACTS_DIR / "bias_coverage_by_field_language.csv")
    sources.to_csv(ARTIFACTS_DIR / "bias_coverage_by_source.csv",index=False)
    source_languages.to_csv(ARTIFACTS_DIR / "bias_coverage_by_source_language.csv")
    source_fields.to_csv(ARTIFACTS_DIR / "bias_coverage_by_source_field.csv")
    print(fields.to_string(index=False))
    print(languages.to_string())
    print("\nCobertura por fuente:")
    print(sources.to_string(index=False))
    print("\nIdioma por fuente:")
    print(source_languages.to_string())


if __name__ == "__main__":
    main()
