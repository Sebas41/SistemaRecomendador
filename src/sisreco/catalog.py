"""Normalización y validación del catálogo de artículos."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from langdetect import DetectorFactory, LangDetectException, detect

from .settings import CATALOG, DATA_MANIFEST, END_YEAR, MAX_ABSTRACT_WORDS, MIN_ABSTRACT_WORDS, MINIMUM_PER_FIELD, RAW_CATALOG, START_YEAR

REQUIRED_COLUMNS = ["id", "title", "abstract", "authors", "year", "language", "field", "topic", "keywords", "doi", "url", "source"]
DetectorFactory.seed = 42


def clean_catalog(frame: pd.DataFrame) -> pd.DataFrame:
    """Aplica reglas de calidad y elimina duplicados por ID, DOI y título."""
    frame = frame.copy()
    for name in REQUIRED_COLUMNS:
        if name not in frame.columns:
            frame[name] = None
    frame["title"] = frame["title"].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    frame["abstract"] = frame["abstract"].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    frame["field"] = frame["field"].fillna("Campo no disponible").astype(str)
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
    frame["language"] = frame["language"].fillna("unknown").astype(str).str.lower()
    inferred = frame["language"].isin(["", "none", "nan", "unknown"])
    frame["language_inferred"] = inferred

    def detect_language(text: str) -> str:
        try:
            return detect(text)
        except LangDetectException:
            return "unknown"

    frame.loc[inferred, "language"] = frame.loc[inferred, "abstract"].map(detect_language)
    frame["title_key"] = frame["title"].str.casefold().str.replace(r"[^\w]+", " ", regex=True).str.strip()
    title_words = frame["title"].str.split().str.len()
    abstract_words = frame["abstract"].str.split().str.len()
    valid = (
        (title_words >= 3)
        & (title_words <= 100)
        & (abstract_words >= MIN_ABSTRACT_WORDS)
        & (abstract_words <= MAX_ABSTRACT_WORDS)
        & frame["year"].between(START_YEAR, END_YEAR)
        & frame["field"].ne("Campo no disponible")
        & frame["language"].isin(["en", "es"])
    )
    frame = frame.loc[valid].copy()
    frame = frame.drop_duplicates(subset="id", keep="first")
    # Missing DOI means the deduplication key is unknown, not shared by every such article.
    frame["_doi_key"] = frame["doi"].fillna("").astype(str).str.casefold().str.strip()
    has_doi = frame["_doi_key"].ne("")
    frame = pd.concat([
        frame.loc[has_doi].drop_duplicates(subset="_doi_key", keep="first"),
        frame.loc[~has_doi],
    ], ignore_index=True)
    frame = frame.drop_duplicates(subset="title_key", keep="first")
    frame["year"] = frame["year"].astype(int)
    return frame.drop(columns=["title_key", "_doi_key"]).reset_index(drop=True)


def _read_raw_jsonl(path: Path) -> pd.DataFrame:
    import gzip

    rows = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def build_catalog(raw_path: Path = RAW_CATALOG, output_path: Path = CATALOG) -> pd.DataFrame:
    if not raw_path.exists():
        raise FileNotFoundError(f"No existe {raw_path}. Ejecuta: python scripts/download_data.py")
    frame = _read_raw_jsonl(raw_path)
    cleaned = clean_catalog(frame)
    field_counts = cleaned["field"].value_counts().to_dict()
    underfilled = {field: n for field, n in field_counts.items() if n < MINIMUM_PER_FIELD}
    if underfilled:
        raise ValueError(f"Hay campos con menos de {MINIMUM_PER_FIELD} artículos: {underfilled}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_parquet(output_path, index=False)
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    manifest = {
        "source": "OpenAlex Works API (https://api.openalex.org/works)",
        "source_license": "CC0",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": raw_path.name,
        "source_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "catalog_file": output_path.name,
        "catalog_sha256": digest,
        "filters": {
            "type": "article",
            "publication_year": f"{START_YEAR}-{END_YEAR}",
            "abstract_words": f"{MIN_ABSTRACT_WORDS}-{MAX_ABSTRACT_WORDS}",
            "title_words": "3-100",
            "languages": ["en", "es"],
            "retracted": False,
        },
        "records": int(len(cleaned)),
        "raw_records": int(len(frame)),
        "valid_records": int(len(cleaned)),
        "discarded_during_cleaning": int(len(frame) - len(cleaned)),
        "inferred_language_records": int(cleaned["language_inferred"].sum()),
        "by_field": {str(k): int(v) for k, v in field_counts.items()},
        "by_language": {str(k): int(v) for k, v in cleaned["language"].value_counts().items()},
        "language_detection": "OpenAlex language metadata; langdetect is used only when that metadata is missing.",
    }
    DATA_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    DATA_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned
