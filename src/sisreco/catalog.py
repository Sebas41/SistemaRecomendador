"""Normalización y validación del catálogo de artículos."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from langdetect import DetectorFactory, LangDetectException, detect

from .settings import CATALOG, DATA_MANIFEST, END_YEAR, MAX_ABSTRACT_WORDS, MIN_ABSTRACT_WORDS, MINIMUM_PER_FIELD, RAW_CATALOG, RAW_OPENALEX_SAMPLE_MANIFEST, RAW_SCIELO_CATALOG, RAW_SCIELO_SAMPLE_MANIFEST, START_YEAR

REQUIRED_COLUMNS = ["id", "title", "abstract", "authors", "year", "language", "field", "topic", "keywords", "doi", "url", "source", "source_database", "source_collection"]
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
    frame["source_database"] = frame["source_database"].fillna("OpenAlex").astype(str)
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
    frame["_doi_key"] = (
        frame["doi"].fillna("").astype(str).str.casefold().str.strip()
        .str.replace(r"^https?://(?:dx\.)?doi\.org/", "", regex=True)
        .str.replace(r"^doi:\s*", "", regex=True)
    )
    has_doi = frame["_doi_key"].ne("")
    frame = pd.concat([
        frame.loc[has_doi].drop_duplicates(subset="_doi_key", keep="first"),
        frame.loc[~has_doi],
    ], ignore_index=True)
    frame = frame.drop_duplicates(subset="title_key", keep="first")
    frame["year"] = frame["year"].astype(int)
    return frame.drop(columns=["title_key", "_doi_key"]).reset_index(drop=True)


# Patrones observados en los resúmenes de OpenAlex y SciELO: rótulos de sección,
# avisos editoriales, texto UTF-8 leído como Latin-1 y portadillas de Wiley que
# ocupan el lugar del resumen. El aviso exige un símbolo o una fórmula editorial
# para no confundirlo con artículos cuyo tema es el derecho de autor.
ABSTRACT_LABEL = re.compile(r"^\s*(?:abstract|resumen|summary|resumo)\b\s*[:.\-–]?\s*", re.IGNORECASE)
COPYRIGHT_NOTICE = re.compile(
    r"©|\bcopyright\s*(?:©|\(c\)|:|of\b)|\(c\)\s*\d{4}|\ball rights reserved\b"
    r"|\btodos los derechos reservados\b|\bpublication history\b",
    re.IGNORECASE,
)
LEADING_NOTICE = re.compile(r"^(?:©|copyright\b)[^.]{0,200}\.\s*", re.IGNORECASE)
MOJIBAKE = re.compile(r"Ã[\x80-\xbf]|â€")
FRONT_MATTER = re.compile(
    r"Volume \d+,? Issue|Search for more papers by this author|First published:|ChemInform Abstract",
    re.IGNORECASE,
)


def abstract_quality_flags(frame: pd.DataFrame) -> pd.DataFrame:
    """Marca los problemas de calidad del resumen que afectan el texto indexado."""
    abstract = frame["abstract"].fillna("").astype(str)
    words = abstract.str.split().str.len()
    return pd.DataFrame({
        "empty_or_short": words < MIN_ABSTRACT_WORDS,
        "label_prefix": abstract.str.contains(ABSTRACT_LABEL),
        "copyright": abstract.str.contains(COPYRIGHT_NOTICE),
        "mojibake": abstract.str.contains(MOJIBAKE) | frame["title"].fillna("").astype(str).str.contains(MOJIBAKE),
        "front_matter": abstract.str.contains(FRONT_MATTER),
        # Un mismo resumen en artículos distintos suele ser la descripción de la revista.
        "shared_abstract": abstract.duplicated(keep=False) & abstract.ne(""),
    }, index=frame.index)


def _repair_mojibake_word(word: str) -> str:
    # El texto UTF-8 decodificado como Windows-1252 se revierte byte a byte; los
    # bytes sin carácter en esa tabla quedaron como su código Latin-1.
    data = bytearray()
    for char in word:
        try:
            data += char.encode("cp1252")
        except UnicodeEncodeError:
            if ord(char) > 255:
                return word
            data.append(ord(char))
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return word


def clean_text(text: str) -> str:
    """Normaliza Unicode y espacios, y repara la codificación de un título o resumen."""
    text = unicodedata.normalize("NFC", str(text or ""))
    if MOJIBAKE.search(text):
        text = re.sub(r"\S+", lambda match: _repair_mojibake_word(match.group()) if MOJIBAKE.search(match.group()) else match.group(), text)
    return re.sub(r"\s+", " ", text).strip()


def clean_abstract(text: str) -> str:
    """Quita el rótulo inicial y el aviso editorial final, que no describen la investigación."""
    text = ABSTRACT_LABEL.sub("", clean_text(text), count=1)
    text = LEADING_NOTICE.sub("", text, count=1)
    match = COPYRIGHT_NOTICE.search(text, len(text) // 2)
    if match:
        start = match.start()
        # Un aviso entre paréntesis o corchetes se elimina completo.
        opening = max(text.rfind("(", 0, start), text.rfind("[", 0, start))
        if opening >= 0 and start - opening <= 80 and not re.search(r"[)\]]", text[opening:start]):
            start = opening
        text = text[:start]
    return text.strip(" ;,")


def _detect_language(text: str) -> str:
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def prepare_texts(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Limpia títulos y resúmenes, asigna el idioma del resumen y excluye textos que no describen el artículo.

    OpenAlex declara a menudo el idioma del título; el filtro de idioma y las
    métricas por idioma necesitan el idioma del resumen, que es lo que se lee y se indexa.
    """
    frame = frame.copy()
    flags = abstract_quality_flags(frame)
    original_abstract = frame["abstract"].astype(str)
    original_title = frame["title"].astype(str)
    frame["title"] = original_title.map(clean_text)
    frame["abstract"] = original_abstract.map(clean_abstract)
    frame["language_declared"] = frame["language"]
    frame["language"] = frame["abstract"].map(_detect_language)

    excluded = pd.Series("", index=frame.index)
    excluded[flags["front_matter"]] = "front_matter"
    excluded[flags["shared_abstract"] & excluded.eq("")] = "shared_abstract"
    too_short = frame["abstract"].str.split().str.len() < MIN_ABSTRACT_WORDS
    excluded[too_short & excluded.eq("")] = "short_after_cleaning"
    other_language = ~frame["language"].isin(["en", "es"])
    excluded[other_language & excluded.eq("")] = "language_not_en_es"
    modified = frame["abstract"].ne(original_abstract.str.replace(r"\s+", " ", regex=True).str.strip()) | frame["title"].ne(original_title)

    group = [frame["source_database"], frame["language_declared"]]
    report = {
        "records_in": int(len(frame)),
        "modified_text": int(modified.sum()),
        "modified_by_source_language": {f"{s}|{l}": int(n) for (s, l), n in modified.groupby(group).sum().items()},
        "relabelled_language": int((frame["language"].ne(frame["language_declared"]) & excluded.eq("")).sum()),
        "excluded": {reason: int(n) for reason, n in excluded[excluded.ne("")].value_counts().items()},
        "excluded_by_source_language": {
            f"{s}|{l}|{reason}": int(n)
            for (s, l, reason), n in excluded[excluded.ne("")].groupby([*group, excluded[excluded.ne("")]]).size().items()
        },
    }
    kept = frame.loc[excluded.eq("")].reset_index(drop=True)
    report["records_out"] = int(len(kept))
    return kept, report


def _read_raw_jsonl(path: Path) -> pd.DataFrame:
    import gzip

    rows = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def _raw_frames(raw_path: Path | None = RAW_CATALOG) -> tuple[list[Path], list[pd.DataFrame]]:
    raw_paths = [path for path in (raw_path, RAW_SCIELO_CATALOG) if path and path.exists()]
    if not raw_paths:
        raise FileNotFoundError(
            "No se encontró un catálogo crudo. Ejecuta: python scripts/download_data.py"
        )
    return raw_paths, [_read_raw_jsonl(path) for path in raw_paths]


def load_catalog_before_text_cleaning(raw_path: Path | None = RAW_CATALOG) -> pd.DataFrame:
    """Reconstruye el catálogo desde los archivos crudos sin limpiar los textos, para el EDA."""
    _, frames = _raw_frames(raw_path)
    return clean_catalog(pd.concat(frames, ignore_index=True))


def build_catalog(raw_path: Path | None = RAW_CATALOG, output_path: Path = CATALOG) -> pd.DataFrame:
    raw_paths, frames = _raw_frames(raw_path)
    frame = pd.concat(frames, ignore_index=True)
    cleaned, text_report = prepare_texts(clean_catalog(frame))
    openalex = cleaned[cleaned["source_database"].eq("OpenAlex")]
    field_counts = openalex["field"].value_counts().to_dict()
    underfilled = {field: n for field, n in field_counts.items() if n < MINIMUM_PER_FIELD}
    if underfilled:
        raise ValueError(f"Hay campos con menos de {MINIMUM_PER_FIELD} artículos: {underfilled}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_parquet(output_path, index=False)
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    raw_sources = []
    for path, raw_frame in zip(raw_paths, frames):
        source_name = (
            str(raw_frame["source_database"].dropna().mode().iloc[0])
            if "source_database" in raw_frame and not raw_frame["source_database"].dropna().empty
            else "SciELO" if "scielo" in path.name.casefold()
            else "OpenAlex"
        )
        raw_sources.append({
            "source": source_name,
            "file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "records": int(len(raw_frame)),
        })
    manifest = {
        "source": "OpenAlex Works API and SciELO ArticleMeta API",
        "source_license": {
            "OpenAlex": "CC0",
            "SciELO": "Article metadata; article-level reuse terms may vary by publication",
        },
        # La fecha de extracción es la de la descarga; reconstruir el catálogo no la cambia.
        "retrieved_at_utc": (
            json.loads(RAW_OPENALEX_SAMPLE_MANIFEST.read_text(encoding="utf-8")).get("retrieved_at_utc")
            if RAW_OPENALEX_SAMPLE_MANIFEST.exists() else None
        ),
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": raw_path.name if raw_path and raw_path.exists() else None,
        "source_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest() if raw_path and raw_path.exists() else None,
        "raw_sources": raw_sources,
        "scielo_sampling": (
            json.loads(RAW_SCIELO_SAMPLE_MANIFEST.read_text(encoding="utf-8"))
            if RAW_SCIELO_CATALOG in raw_paths and RAW_SCIELO_SAMPLE_MANIFEST.exists() else None
        ),
        "openalex_sampling": (
            json.loads(RAW_OPENALEX_SAMPLE_MANIFEST.read_text(encoding="utf-8"))
            if RAW_CATALOG in raw_paths and RAW_OPENALEX_SAMPLE_MANIFEST.exists() else None
        ),
        "catalog_file": output_path.name,
        "catalog_sha256": digest,
        "filters": {
            "type": "article",
            "publication_year": f"{START_YEAR}-{END_YEAR}",
            "scielo_processing_date": f"{START_YEAR}-01-01 to {END_YEAR}-12-31",
            "abstract_words": f"{MIN_ABSTRACT_WORDS}-{MAX_ABSTRACT_WORDS}",
            "title_words": "3-100",
            "languages": ["en", "es"],
            "retracted": "OpenAlex records marked retracted are excluded; SciELO status is not consistently provided by ArticleMeta",
        },
        "records": int(len(cleaned)),
        "raw_records": int(len(frame)),
        "valid_records": int(len(cleaned)),
        "discarded_during_cleaning": int(len(frame) - len(cleaned)),
        "text_cleaning": text_report,
        "inferred_language_records": int(cleaned["language_inferred"].sum()),
        "by_field": {str(k): int(v) for k, v in field_counts.items()},
        "by_language": {str(k): int(v) for k, v in cleaned["language"].value_counts().items()},
        "by_source": {str(k): int(v) for k, v in cleaned["source_database"].value_counts().items()},
        "by_source_language": {
            f"{source}|{language}": int(count)
            for (source, language), count in cleaned.groupby(["source_database", "language"]).size().items()
        },
        "by_source_field": {
            f"{source}|{field}": int(count)
            for (source, field), count in cleaned.groupby(["source_database", "field"]).size().items()
        },
        "scielo_field_note": "SciELO field labels follow the journal's ArticleMeta classification; they are not mapped to OpenAlex's 26 fields.",
        "language_detection": "language is detected with langdetect (seed 42) on the cleaned abstract; language_declared keeps the source metadata. Abstracts outside English and Spanish are excluded.",
    }
    DATA_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    DATA_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned
