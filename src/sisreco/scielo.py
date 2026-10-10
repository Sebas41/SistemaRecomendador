"""Descarga una muestra reproducible de artículos de SciELO ArticleMeta."""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from tqdm import tqdm

from .settings import (
    END_YEAR,
    MAX_ABSTRACT_WORDS,
    MAX_TITLE_WORDS,
    MIN_ABSTRACT_WORDS,
    RAW_SCIELO_CATALOG,
    RAW_SCIELO_SAMPLE_MANIFEST,
    SCIELO_API_BASE_URL,
    SCIELO_COLLECTIONS,
    SCIELO_PAGE_SIZE,
    SCIELO_PAGES_PER_COLLECTION,
    SCIELO_REQUEST_INTERVAL_SECONDS,
    SEED,
    START_YEAR,
)

_TAG_RE = re.compile(r"<[^>]+>")


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = html.unescape(_TAG_RE.sub(" ", value))
    return " ".join(text.split())


def _field_text(value: Any, language: str | None = None) -> str:
    """Lee un campo ArticleMeta multilingüe, que puede usar ``_`` o ``a``."""
    entries = _items(value)
    if not entries and isinstance(value, str):
        return _clean_text(value)
    if language:
        preferred = [entry for entry in entries if entry.get("l") == language]
        entries = preferred + [entry for entry in entries if entry not in preferred]
    for entry in entries:
        for key in ("_", "a", "t", "k"):
            candidate = _clean_text(entry.get(key))
            if candidate:
                return candidate
    return ""


def _field_values(value: Any) -> list[str]:
    values = []
    for entry in _items(value):
        text = ""
        for key in ("_", "k", "a", "t"):
            text = _clean_text(entry.get(key))
            if text:
                break
        if text and text.casefold() not in {"nd", "n/a"} and text not in values:
            values.append(text)
    return values


def _doi(value: Any) -> str | None:
    if not value:
        return None
    doi = str(value).strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    return doi or None


def _journal_subject(journal: dict[str, Any] | None) -> str:
    if not journal:
        return "Multidisciplinary / unclassified"
    return (
        _field_text(journal.get("v441"))
        or _field_text(journal.get("v440"))
        or "Multidisciplinary / unclassified"
    )


def journal_subjects(records: list[dict[str, Any]]) -> dict[str, str]:
    """Mapea ISSN a la categoría declarada en los metadatos de la revista."""
    result: dict[str, str] = {}
    for journal in records:
        subject = _journal_subject(journal)
        issns = journal.get("issns") or []
        if journal.get("code"):
            issns = [*issns, journal["code"]]
        issns.extend(entry.get("_") for entry in _items(journal.get("v400")))
        for issn in issns:
            if issn:
                result[str(issn).strip().casefold()] = subject
    return result


def normalize_article(
    record: dict[str, Any],
    journal_subject_by_issn: dict[str, str] | None = None,
    collection_names: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Convierte un registro ArticleMeta al esquema común del catálogo."""
    article = record.get("article") or {}
    if not isinstance(article, dict):
        return None

    language = _field_text(article.get("v40")).lower() or "unknown"
    title = _field_text(article.get("v12"), language)
    abstract = _field_text(article.get("v83"), language)
    date = _field_text(article.get("v65"))
    year_text = str(record.get("publication_year") or date)[:4]
    try:
        year = int(year_text)
    except (TypeError, ValueError):
        return None
    title_words = title.split()
    abstract_words = abstract.split()
    if (
        len(title_words) < 3
        or len(title_words) > MAX_TITLE_WORDS
        or not MIN_ABSTRACT_WORDS <= len(abstract_words) <= MAX_ABSTRACT_WORDS
        or not START_YEAR <= year <= END_YEAR
        or language not in {"en", "es", "unknown"}
    ):
        return None

    collection = str(record.get("collection") or "unknown")
    article_code = str(record.get("code") or _field_text(article.get("v880")))
    if not article_code:
        return None
    issn = _field_text(article.get("v35")).casefold()
    subject = (journal_subject_by_issn or {}).get(
        issn, "Multidisciplinary / unclassified"
    )
    doi = _doi(record.get("doi") or _field_text(article.get("v237")))
    fulltexts = record.get("fulltexts") or {}
    language_links = fulltexts.get("html") or {}
    url = language_links.get(language) if isinstance(language_links, dict) else None
    if not url and doi:
        url = f"https://doi.org/{doi}"
    if url:
        url = str(url).replace("http://", "https://", 1)
    authors = []
    for author in _items(article.get("v10")):
        name = " ".join(
            part for part in (_clean_text(author.get("n")), _clean_text(author.get("s"))) if part
        )
        if name:
            authors.append(name)
    keywords = _field_values(article.get("v85"))
    topic = _field_text(article.get("v854")) or (keywords[0] if keywords else None)
    collection_label = (collection_names or {}).get(collection, collection)
    journal = _field_text(article.get("v30")) or "Revista no disponible"
    return {
        "id": f"SCIELO:{collection}:{article_code}",
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "year": year,
        "language": language,
        "field": subject,
        "topic": topic,
        "keywords": keywords,
        "doi": doi,
        "url": url,
        "source": journal,
        "source_database": "SciELO",
        "source_collection": collection_label,
    }


def _get_json(
    session: requests.Session,
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> Any:
    url = urljoin(f"{SCIELO_API_BASE_URL.rstrip('/')}/", endpoint.lstrip("/"))
    for attempt in range(5):
        response = session.get(url, params=params or {}, timeout=(10, 60))
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(min(2**attempt, 30))
            continue
        response.raise_for_status()
        time.sleep(SCIELO_REQUEST_INTERVAL_SECONDS)
        return response.json()
    raise RuntimeError(f"SciELO ArticleMeta no respondió después de cinco intentos: {url}")


def _collection_metadata(session: requests.Session) -> dict[str, str]:
    data = _get_json(session, "collection/identifiers")
    result = {}
    for item in data if isinstance(data, list) else []:
        code = item.get("code") or item.get("acron")
        names = item.get("name") or {}
        if code:
            result[str(code)] = str(names.get("es") or names.get("en") or code)
    return result


def sample_offsets(total: int, page_size: int, pages_to_sample: int, seed: int) -> list[int]:
    """Elige páginas reproducibles sin ordenar los trabajos por citas."""
    page_count = (total + page_size - 1) // page_size
    count = min(page_count, pages_to_sample)
    page_numbers = random.Random(seed).sample(range(page_count), count)
    return sorted(number * page_size for number in page_numbers)


def iter_scielo_records(
    *,
    collections: tuple[str, ...] = SCIELO_COLLECTIONS,
    pages_per_collection: int = SCIELO_PAGES_PER_COLLECTION,
    session: requests.Session | None = None,
    page_log: list[dict[str, Any]] | None = None,
) -> Any:
    """Muestrea páginas por colección y normaliza los artículos válidos."""
    if pages_per_collection <= 0:
        raise ValueError("pages_per_collection debe ser positivo.")
    owns_session = session is None
    session = session or requests.Session()
    session.headers.update({"User-Agent": "CienciaATuTesis/0.2 (proyecto académico)"})
    try:
        available = _collection_metadata(session)
        unknown_collections = sorted(set(collections) - set(available))
        if unknown_collections:
            raise ValueError(f"SciELO no reconoce estas colecciones: {unknown_collections}")
        collection_names = {code: available.get(code, code) for code in collections}
        rng = random.Random(SEED)
        for collection in tqdm(collections, desc="Colecciones SciELO"):
            journals = _get_json(session, "journal/", {"collection": collection})
            subjects = journal_subjects(journals if isinstance(journals, list) else [])
            params = {
                "collection": collection,
                "from": f"{START_YEAR}-01-01",
                "until": f"{END_YEAR}-12-31",
                "limit": 1,
                "offset": 0,
                "fmt": "json",
                "body": "false",
            }
            initial = _get_json(session, "articles/", params)
            total = int((initial.get("meta") or {}).get("total", 0))
            offsets = sample_offsets(
                total,
                SCIELO_PAGE_SIZE,
                pages_per_collection,
                rng.randint(0, 2**32 - 1),
            )
            for offset in offsets:
                if page_log is not None:
                    page_log.append({
                        "collection": collection,
                        "offset": offset,
                        "page_size": SCIELO_PAGE_SIZE,
                        "available_records": total,
                    })
                page = _get_json(
                    session,
                    "articles/",
                    {**params, "limit": SCIELO_PAGE_SIZE, "offset": offset},
                )
                for item in page.get("objects", []):
                    normalized = normalize_article(item, subjects, collection_names)
                    if normalized:
                        yield normalized
    finally:
        if owns_session:
            session.close()


def download_scielo_catalog(
    output_path: Path = RAW_SCIELO_CATALOG,
    *,
    collections: tuple[str, ...] = SCIELO_COLLECTIONS,
    pages_per_collection: int = SCIELO_PAGES_PER_COLLECTION,
) -> int:
    """Escribe artículos SciELO normalizados a JSONL comprimido."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    count = 0
    page_log: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()
    try:
        with gzip.open(tmp_path, "wt", encoding="utf-8") as target:
            for article in iter_scielo_records(
                collections=collections,
                pages_per_collection=pages_per_collection,
                page_log=page_log,
            ):
                title_key = " ".join(article["title"].casefold().split())
                doi_key = (article.get("doi") or "").casefold().strip()
                if (
                    article["id"] in seen_ids
                    or (doi_key and doi_key in seen_dois)
                    or title_key in seen_titles
                ):
                    continue
                seen_ids.add(article["id"])
                seen_titles.add(title_key)
                if doi_key:
                    seen_dois.add(doi_key)
                target.write(json.dumps(article, ensure_ascii=False) + "\n")
                count += 1
        tmp_path.replace(output_path)
        manifest_path = (
            RAW_SCIELO_SAMPLE_MANIFEST
            if output_path == RAW_SCIELO_CATALOG
            else output_path.with_name("scielo_sample_manifest.json")
        )
        manifest_path.write_text(json.dumps({
            "source": "SciELO ArticleMeta REST API",
            "api_base_url": SCIELO_API_BASE_URL,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "publication_year_filter": f"{START_YEAR}-{END_YEAR}",
            "api_processing_date_filter": {
                "from": f"{START_YEAR}-01-01",
                "until": f"{END_YEAR}-12-31",
            },
            "seed": SEED,
            "pages_per_collection": pages_per_collection,
            "page_size": SCIELO_PAGE_SIZE,
            "collections": list(collections),
            "sampled_pages": page_log,
            "valid_records_written": count,
            "catalog_file": output_path.name,
            "catalog_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        tmp_path.unlink(missing_ok=True)
    return count
