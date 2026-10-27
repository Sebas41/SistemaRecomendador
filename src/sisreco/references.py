"""Exportación de referencias bibliográficas."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _clean_field(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def export_ris(articles: pd.DataFrame) -> str:
    """Serializa los metadatos bibliográficos disponibles como referencias RIS."""
    records: list[str] = []
    for _, article in articles.iterrows():
        records.append("TY  - JOUR")
        title = _clean_field(article.get("title"))
        if title:
            records.append(f"TI  - {title}")

        authors = article.get("authors")
        if isinstance(authors, (list, tuple, np.ndarray)):
            records.extend(f"AU  - {cleaned}" for author in authors if (cleaned := _clean_field(author)))

        year = article.get("year")
        if pd.notna(year):
            records.append(f"PY  - {int(year)}")

        doi = _clean_field(article.get("doi"))
        if doi:
            doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
            records.append(f"DO  - {doi}")

        url = _clean_field(article.get("url")) or (f"https://doi.org/{doi}" if doi else "")
        if url:
            records.append(f"UR  - {url}")

        keywords = article.get("keywords")
        if isinstance(keywords, (list, tuple, np.ndarray)):
            records.extend(f"KW  - {cleaned}" for keyword in keywords if (cleaned := _clean_field(keyword)))

        abstract = _clean_field(article.get("abstract"))
        if abstract:
            records.append(f"AB  - {abstract}")
        records.extend(("ER  -", ""))

    return "\n".join(records)
