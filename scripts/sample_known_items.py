#!/usr/bin/env python3
"""Selecciona los artículos de origen de las consultas de ítem conocido.

La muestra se estratifica por fuente, idioma y campo porque el catálogo es
desbalanceado: con un muestreo proporcional, el español (5,3 %) y SciELO (3,3 %)
tendrían muy pocos casos para medir su desempeño por separado.
"""

import re

import numpy as np
import pandas as pd

from sisreco.catalog import abstract_quality_flags
from sisreco.settings import CATALOG, EVALUATION_DIR, SEED

# Casos por grupo: 6 por campo de OpenAlex en inglés y 20 artículos en español por fuente.
OPENALEX_EN_PER_FIELD = 6
SCIELO_EN = 4
SPANISH_PER_SOURCE = 20
# Campos donde el español no llega al 1 % del catálogo: no hay casos suficientes como origen.
MIN_SPANISH_SHARE = 0.01


# Títulos de piezas que no reportan una investigación: una descripción de proyecto de
# grado no puede corresponder a una nota editorial, un obituario o la reseña de un libro.
NON_RESEARCH_TITLE = re.compile(
    r"^(?:note of thanks|editorial\b|erratum|corrigendum|in memoriam|obituary|"
    r"reseña\b|nota editorial|presentación del número)|"
    r"\breseña de\b|\bbook review\b|,\s*\d+\s*vol\.|\bpágs\.",
    re.IGNORECASE,
)


def eligible_sources(catalog: pd.DataFrame) -> pd.DataFrame:
    """Excluye artículos con texto residual de plantilla, sin topic, que no reportan investigación o con títulos casi duplicados."""
    flags = abstract_quality_flags(catalog)
    # Títulos que solo difieren en números o en "parte" (p. ej., Parte 1 y Parte 2) tienen
    # un artículo gemelo igual de correcto, que la métrica contaría como error.
    title_key = catalog["title"].str.casefold().str.replace(r"\b(?:part|parte)\b|\d+|[^\w\s]", "", regex=True).str.split().str.join(" ")
    near_duplicate = title_key.duplicated(keep=False)
    valid = (
        ~flags.any(axis=1)
        & catalog["topic"].notna()
        & catalog["topic"].ne("")
        & ~near_duplicate
        & ~catalog["title"].str.contains(NON_RESEARCH_TITLE)
    )
    return catalog.loc[valid]


def _round_robin(frame: pd.DataFrame, total: int, rng: np.random.Generator) -> pd.DataFrame:
    """Reparte la muestra entre los campos disponibles para no concentrarla en los más grandes."""
    groups = {field: group.sample(frac=1, random_state=int(rng.integers(1 << 31))) for field, group in frame.groupby("field")}
    order = list(groups)
    rng.shuffle(order)
    chosen, position = [], {field: 0 for field in order}
    while len(chosen) < total:
        for field in order:
            if len(chosen) == total:
                break
            if position[field] < len(groups[field]):
                chosen.append(groups[field].iloc[position[field]])
                position[field] += 1
    return pd.DataFrame(chosen)


def main() -> None:
    rng = np.random.default_rng(SEED)
    catalog = pd.read_parquet(CATALOG)
    pool = eligible_sources(catalog)
    spanish_share = catalog.groupby("field")["language"].apply(lambda s: s.eq("es").mean())
    spanish_fields = spanish_share[spanish_share >= MIN_SPANISH_SHARE].index

    openalex, scielo = pool[pool["source_database"].eq("OpenAlex")], pool[pool["source_database"].eq("SciELO")]
    parts = [
        openalex[openalex["language"].eq("en")].groupby("field", group_keys=False)
        .apply(lambda g: g.sample(OPENALEX_EN_PER_FIELD, random_state=SEED)),
        scielo[scielo["language"].eq("en")].sample(SCIELO_EN, random_state=SEED),
        _round_robin(openalex[openalex["language"].eq("es") & openalex["field"].isin(spanish_fields)], SPANISH_PER_SOURCE, rng),
        _round_robin(scielo[scielo["language"].eq("es")], SPANISH_PER_SOURCE, rng),
    ]
    sample = pd.concat(parts, ignore_index=True)
    # groupby().apply omite la columna de agrupación; se recupera del catálogo.
    sample["field"] = sample["id"].map(catalog.set_index("id")["field"])
    # La mitad de las consultas de cada grupo se redacta en español y la otra en inglés,
    # sin importar el idioma del artículo, para medir también la búsqueda entre idiomas.
    sample["group"] = sample["source_database"] + "|" + sample["language"]
    sample = sample.sample(frac=1, random_state=SEED).reset_index(drop=True)
    sample["query_language"] = sample.groupby("group").cumcount().map(lambda i: "es" if i % 2 == 0 else "en")
    sample["query_id"] = [f"K{index:03d}" for index in range(1, len(sample) + 1)]
    columns = ["query_id", "id", "query_language", "source_database", "language", "field", "topic", "title"]
    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    sample[columns].rename(columns={"id": "article_id", "language": "article_language"}).to_csv(
        EVALUATION_DIR / "known_item_sources.csv", index=False
    )
    print(sample.groupby(["source_database", "language", "query_language"]).size().to_string())
    print(f"{len(sample)} artículos de origen en {sample['field'].nunique()} campos.")


if __name__ == "__main__":
    main()
