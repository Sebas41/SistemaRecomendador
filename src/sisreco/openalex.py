"""Descarga reproducible de metadatos de OpenAlex por campo académico."""

from __future__ import annotations

import gzip
import json
import os
import time
from pathlib import Path
from typing import Any, Iterator

import requests
from tqdm import tqdm

from .settings import (
    END_YEAR,
    FIELD_SAMPLE_SIZE,
    MAX_ABSTRACT_WORDS,
    MAX_SAMPLE_ATTEMPTS,
    MAX_TITLE_WORDS,
    MIN_ABSTRACT_WORDS,
    MINIMUM_PER_FIELD,
    OPENALEX_BASE_URL,
    PAGE_SIZE,
    RAW_CATALOG,
    SEED,
    START_YEAR,
    TARGET_PER_FIELD,
)

SELECT_FIELDS = (
    "id,title,abstract_inverted_index,publication_year,authorships,"
    "primary_topic,keywords,language,doi,primary_location,is_retracted,type"
)


def reconstruct_abstract(index: dict[str, list[int]] | None) -> str:
    """Reconstruye el texto desde el índice posición-token de OpenAlex."""
    if not index:
        return ""
    positions: dict[int, str] = {}
    for token, offsets in index.items():
        for offset in offsets:
            positions[offset] = token
    return " ".join(positions[position] for position in sorted(positions))


def valid_work(work: dict[str, Any]) -> bool:
    """Aplica las reglas mínimas de calidad acordadas para un registro."""
    if work.get("is_retracted") is True or work.get("type") != "article":
        return False
    title = " ".join((work.get("title") or "").split())
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    title_words = title.split()
    abstract_words = abstract.split()
    return (
        len(title_words) >= 3
        and len(title_words) <= MAX_TITLE_WORDS
        and MIN_ABSTRACT_WORDS <= len(abstract_words) <= MAX_ABSTRACT_WORDS
        and START_YEAR <= (work.get("publication_year") or 0) <= END_YEAR
        and bool(work.get("primary_topic", {}).get("field", {}).get("id"))
    )


def _get_json(url: str, params: dict[str, Any], session: requests.Session) -> dict[str, Any]:
    for attempt in range(5):
        response = session.get(url, params=params, timeout=(10, 90))
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(min(2**attempt, 30))
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"OpenAlex no respondió después de cinco intentos: {url}")


def academic_fields(session: requests.Session) -> list[dict[str, str]]:
    """Obtiene los campos actuales de OpenAlex en vez de codificar sus IDs."""
    params: dict[str, Any] = {"per_page": 100, "select": "id,display_name"}
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    response = _get_json(f"{OPENALEX_BASE_URL}/fields", params, session)
    return [
        {"id": entry["id"], "display_name": entry["display_name"]}
        for entry in response.get("results", [])
    ]


def fetch_field_sample(
    field_id: str,
    seed: int,
    sample_size: int = FIELD_SAMPLE_SIZE,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Obtiene una muestra reproducible, sin ordenarla por citas."""
    own_session = session is None
    session = session or requests.Session()
    params: dict[str, Any] = {
        "filter": (
            f"primary_topic.field.id:{field_id},type:article,"
            f"has_abstract:true,publication_year:{START_YEAR}-{END_YEAR},is_retracted:false"
        ),
        "sample": sample_size,
        "seed": seed,
        "per_page": PAGE_SIZE,
        "select": SELECT_FIELDS,
    }
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    try:
        records = []
        pages = (sample_size + PAGE_SIZE - 1) // PAGE_SIZE
        for page in range(1, pages + 1):
            body = _get_json(f"{OPENALEX_BASE_URL}/works", {**params, "page": page}, session)
            records.extend(work for work in body.get("results", []) if valid_work(work))
        return records
    finally:
        if own_session:
            session.close()


def iter_sampled_records(
    target_per_field: int = TARGET_PER_FIELD,
    max_attempts: int = MAX_SAMPLE_ATTEMPTS,
) -> Iterator[tuple[dict[str, Any], str]]:
    """Produce registros únicos, con representación de cada campo."""
    with requests.Session() as session:
        session.headers.update({"User-Agent": "SisReco-Tesis/0.1 (educational project)"})
        fields = academic_fields(session)
        if len(fields) != 26:
            raise RuntimeError(f"Se esperaban 26 campos de OpenAlex y se encontraron {len(fields)}.")
        for field in tqdm(fields, desc="Campos académicos"):
            seen: set[str] = set()
            kept = 0
            for attempt in range(max_attempts):
                if kept >= target_per_field:
                    break
                sample = fetch_field_sample(field["id"], SEED + attempt, session=session)
                for work in sample:
                    work_id = work.get("id")
                    if not work_id or work_id in seen:
                        continue
                    seen.add(work_id)
                    yield work, field["display_name"]
                    kept += 1
                    if kept >= target_per_field:
                        break
            if kept < MINIMUM_PER_FIELD:
                raise RuntimeError(
                    f"El campo {field['display_name']} solo produjo {kept} artículos válidos; "
                    f"se requieren al menos {MINIMUM_PER_FIELD}. Ajusta filtros o consulta OpenAlex."
                )


def download_catalog(output_path: Path = RAW_CATALOG) -> int:
    """Escribe los registros en JSONL comprimido sin cargar todo en memoria."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    title_keys: set[str] = set()
    dois: set[str] = set()
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with gzip.open(tmp_path, "wt", encoding="utf-8") as stream:
            for work, field_name in iter_sampled_records():
                title_key = " ".join((work.get("title") or "").casefold().split())
                doi = (work.get("doi") or "").casefold()
                if title_key in title_keys or (doi and doi in dois):
                    continue
                title_keys.add(title_key)
                if doi:
                    dois.add(doi)
                authors = [
                    author.get("author", {}).get("display_name", "")
                    for author in work.get("authorships", [])
                    if author.get("author", {}).get("display_name")
                ]
                topic = work.get("primary_topic") or {}
                location = work.get("primary_location") or {}
                source = location.get("source") or {}
                record = {
                    "id": work.get("id", ""),
                    "title": " ".join((work.get("title") or "").split()),
                    "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
                    "authors": authors,
                    "year": work.get("publication_year"),
                    "language": work.get("language"),
                    "field": field_name,
                    "topic": topic.get("display_name"),
                    "keywords": [k.get("display_name", "") for k in work.get("keywords", [])],
                    "doi": work.get("doi"),
                    "url": location.get("landing_page_url") or work.get("doi"),
                    "source": source.get("display_name"),
                    "source_database": "OpenAlex",
                    "source_collection": None,
                }
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1
        tmp_path.replace(output_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return written
