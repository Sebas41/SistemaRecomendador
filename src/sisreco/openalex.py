"""Descarga reproducible de metadatos de OpenAlex por campo académico."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
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
    RAW_OPENALEX_SAMPLE_MANIFEST,
    SEED,
    START_YEAR,
    TARGET_PER_FIELD,
)

SELECT_FIELDS = (
    "id,title,abstract_inverted_index,publication_year,authorships,"
    "primary_topic,keywords,language,doi,primary_location,is_retracted,type"
)


def _api_key() -> str | None:
    """Lee la clave del entorno o del .env local ignorado por Git."""
    key = os.getenv("OPENALEX_API_KEY")
    if key:
        return key.strip()
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "OPENALEX_API_KEY":
            return value.strip().strip("\"'") or None
    return None


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
    last_error: Exception | None = None
    for attempt in range(5):
        api_key = _api_key()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        try:
            response = session.get(url, params=params, headers=headers, timeout=(10, 90))
        except requests.RequestException as error:
            last_error = error
            time.sleep(min(2**attempt, 30))
            continue
        if response.status_code == 429 and "Insufficient budget" in response.text:
            raise RuntimeError(
                "OpenAlex agotó la cuota diaria compartida para solicitudes sin clave. "
                "Configura OPENALEX_API_KEY o espera al reinicio diario y vuelve a ejecutar; "
                "los campos ya guardados en el checkpoint se reutilizarán."
            )
        if response.status_code == 429 or response.status_code >= 500:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = min(float(retry_after), 60) if retry_after else min(2**attempt, 30)
            except ValueError:
                delay = min(2**attempt, 30)
            time.sleep(delay)
            continue
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as error:
            last_error = error
            time.sleep(min(2**attempt, 30))
    raise RuntimeError(f"OpenAlex no respondió después de cinco intentos: {url}") from last_error


def academic_fields(session: requests.Session) -> list[dict[str, str]]:
    """Obtiene los campos actuales de OpenAlex en vez de codificar sus IDs."""
    params: dict[str, Any] = {"per_page": 100, "select": "id,display_name"}
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
        "sample": min(sample_size, 10_000),
        "seed": seed,
        "per_page": PAGE_SIZE,
        "select": SELECT_FIELDS,
    }
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
    sample_size: int = FIELD_SAMPLE_SIZE,
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
                sample = fetch_field_sample(
                    field["id"], SEED + attempt, sample_size=sample_size, session=session
                )
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


def _field_sample_records(
    field: dict[str, str],
    *,
    target_per_field: int,
    sample_size: int,
    max_attempts: int,
    session: requests.Session,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for attempt in range(max_attempts):
        if len(records) >= target_per_field:
            break
        sample = fetch_field_sample(
            field["id"], SEED + attempt, sample_size=sample_size, session=session
        )
        for work in sample:
            work_id = work.get("id")
            if not work_id or work_id in seen:
                continue
            seen.add(work_id)
            records.append(work)
            if len(records) >= target_per_field:
                break
    if len(records) < MINIMUM_PER_FIELD:
        raise RuntimeError(
            f"El campo {field['display_name']} solo produjo {len(records)} artículos válidos; "
            f"se requieren al menos {MINIMUM_PER_FIELD}. Ajusta filtros o consulta OpenAlex."
        )
    return records


def download_catalog(
    output_path: Path = RAW_CATALOG,
    *,
    target_per_field: int = TARGET_PER_FIELD,
    sample_size: int = FIELD_SAMPLE_SIZE,
    max_attempts: int = MAX_SAMPLE_ATTEMPTS,
) -> int:
    """Escribe los registros en JSONL comprimido sin cargar todo en memoria."""
    if target_per_field <= 0 or sample_size < target_per_field:
        raise ValueError("sample_size debe ser mayor o igual a target_per_field positivo.")
    if sample_size > 10_000:
        raise ValueError("OpenAlex limita cada muestra a 10.000 trabajos.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    title_keys: set[str] = set()
    dois: set[str] = set()
    per_field: dict[str, int] = {}
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    run_key = hashlib.sha256(
        f"{SEED}|{START_YEAR}|{END_YEAR}|{target_per_field}|{sample_size}|{max_attempts}".encode()
    ).hexdigest()[:12]
    checkpoint_dir = output_path.parent / f"openalex_checkpoint_{run_key}"
    try:
        with requests.Session() as session:
            session.headers.update({"User-Agent": "SisReco-Tesis/0.2 (educational project)"})
            fields = academic_fields(session)
            if len(fields) != 26:
                raise RuntimeError(f"Se esperaban 26 campos de OpenAlex y se encontraron {len(fields)}.")
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            field_paths = []
            for field in tqdm(fields, desc="Campos académicos"):
                field_path = checkpoint_dir / f"{field['id'].rsplit('/', 1)[-1]}.jsonl.gz"
                field_paths.append((field, field_path))
                if field_path.exists():
                    continue
                works = _field_sample_records(
                    field,
                    target_per_field=target_per_field,
                    sample_size=sample_size,
                    max_attempts=max_attempts,
                    session=session,
                )
                temporary = field_path.with_suffix(".gz.tmp")
                with gzip.open(temporary, "wt", encoding="utf-8") as checkpoint:
                    for work in works:
                        checkpoint.write(json.dumps(work, ensure_ascii=False) + "\n")
                temporary.replace(field_path)

        with gzip.open(tmp_path, "wt", encoding="utf-8") as stream:
            for field, field_path in field_paths:
                with gzip.open(field_path, "rt", encoding="utf-8") as checkpoint:
                    for line in checkpoint:
                        if not line.strip():
                            continue
                        work = json.loads(line)
                        field_name = field["display_name"]
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
                        per_field[field_name] = per_field.get(field_name, 0) + 1
        tmp_path.replace(output_path)
        manifest_path = (
            RAW_OPENALEX_SAMPLE_MANIFEST
            if output_path == RAW_CATALOG
            else output_path.with_name("openalex_sample_manifest.json")
        )
        manifest_path.write_text(json.dumps({
            "source": "OpenAlex Works API",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "publication_year_filter": f"{START_YEAR}-{END_YEAR}",
            "seed": SEED,
            "sample_size_per_field_per_attempt": sample_size,
            "target_valid_records_per_field": target_per_field,
            "max_attempts": max_attempts,
            "valid_records_written": written,
            "records_by_field": per_field,
            "catalog_file": output_path.name,
            "catalog_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.rmtree(checkpoint_dir, ignore_errors=True)
    finally:
        tmp_path.unlink(missing_ok=True)
    return written
