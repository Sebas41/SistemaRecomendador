import numpy as np
import pandas as pd

from sisreco.references import export_ris


def test_export_ris_includes_available_bibliographic_fields():
    articles = pd.DataFrame([{
        "title": "Solar forecasting methods",
        "authors": ["Ana Pérez", "Luis Díaz"],
        "year": 2024,
        "doi": "https://doi.org/10.1234/example",
        "url": "https://example.org/article",
        "keywords": np.asarray(["solar energy", "forecasting"]),
        "abstract": "We compare forecasting methods.\nResults improve accuracy.",
    }])

    ris = export_ris(articles)

    assert "TY  - JOUR" in ris
    assert "TI  - Solar forecasting methods" in ris
    assert "AU  - Ana Pérez" in ris
    assert "AU  - Luis Díaz" in ris
    assert "PY  - 2024" in ris
    assert "DO  - 10.1234/example" in ris
    assert "UR  - https://example.org/article" in ris
    assert "KW  - solar energy" in ris
    assert "KW  - forecasting" in ris
    assert "AB  - We compare forecasting methods. Results improve accuracy." in ris
    assert ris.rstrip().endswith("ER  -")


def test_export_ris_omits_missing_fields_and_builds_url_from_doi():
    articles = pd.DataFrame([{
        "title": "A short reference",
        "authors": [],
        "year": np.nan,
        "doi": "10.5678/reference",
        "url": None,
        "keywords": None,
        "abstract": None,
    }])

    ris = export_ris(articles)

    assert "TI  - A short reference" in ris
    assert "DO  - 10.5678/reference" in ris
    assert "UR  - https://doi.org/10.5678/reference" in ris
    assert "AU  -" not in ris
    assert "PY  -" not in ris
    assert "KW  -" not in ris
    assert "AB  -" not in ris
