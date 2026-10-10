from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sisreco.catalog import clean_catalog
from sisreco.engine import recommend
from sisreco.evaluation import ndcg_at_k, precision_at_k
from sisreco.openalex import reconstruct_abstract, valid_work


def test_reconstruct_abstract_respects_positions():
    assert reconstruct_abstract({"world": [1], "Hello": [0], "again": [2]}) == "Hello world again"


def test_valid_work_rejects_short_title_and_abstract():
    assert not valid_work({
        "title": "A Short Title",
        "abstract_inverted_index": {"word": [0]},
        "publication_year": 2021,
        "type": "article",
        "is_retracted": False,
        "primary_topic": {"field": {"id": "fields/1"}},
    })


def make_catalog():
    abstract = " ".join(["Renewable energy forecasting research examines solar production, weather features, and electricity systems in cities around the world."] * 8)
    return pd.DataFrame([
        {"id": "W1", "title": "Solar energy forecasting models", "abstract": abstract, "authors": ["A. Author"], "year": 2022, "language": "en", "field": "Energy", "topic": "Forecasting", "keywords": [], "doi": "doi:one", "url": "https://example.com/1", "source": "Journal"},
        {"id": "W2", "title": "Predicción solar con aprendizaje automático", "abstract": abstract + " " + " ".join(["El análisis compara métodos de predicción energética renovable mediante información meteorológica y redes eléctricas."] * 5), "authors": [], "year": 2023, "language": "es", "field": "Energy", "topic": "Forecasting", "keywords": [], "doi": None, "url": None, "source": None},
        {"id": "W3", "title": "Solar energy forecasting models", "abstract": abstract, "authors": [], "year": 2020, "language": "en", "field": "Energy", "topic": "Forecasting", "keywords": [], "doi": "doi:duplicate", "url": None, "source": None},
        {"id": "W4", "title": "Paneles solares rurales colombianos", "abstract": abstract + " " + " ".join(["La investigación analiza sistemas fotovoltaicos sostenibles en comunidades de América Latina."] * 5), "authors": [], "year": 2024, "language": "es", "field": "Energy", "topic": "Forecasting", "keywords": [], "doi": None, "url": None, "source": None},
    ])


def test_clean_catalog_removes_duplicate_titles():
    cleaned = clean_catalog(make_catalog())
    assert cleaned["id"].tolist() == ["W1", "W2", "W4"]


class FakeModel:
    def encode(self, inputs, **kwargs):
        if isinstance(inputs, str):
            inputs = [inputs]
        vectors = []
        for text in inputs:
            vectors.append([1.0, 0.0] if "solar" in text.lower() else [0.0, 1.0])
        return np.asarray(vectors, dtype=np.float32)


def test_semantic_recommender_ranks_and_filters_articles():
    catalog = make_catalog().iloc[:2].reset_index(drop=True)
    embeddings = np.asarray([[1, 0], [0, 1]], dtype=np.float32)
    results = recommend(
        catalog,
        "Research project about solar energy forecasting",
        embeddings=embeddings,
        model=FakeModel(),
        fields=["Energy"],
        min_year=2022,
        max_year=2022,
        top_k=5,
        generate_evidence=False,
    )
    assert results["id"].tolist() == ["W1"]
    assert np.isclose(results.iloc[0]["score"], 1.0)


def test_recommender_rejects_short_queries_and_unknown_engines():
    catalog = make_catalog().iloc[:1].reset_index(drop=True)
    vectors = np.asarray([[1, 0]], dtype=np.float32)
    with pytest.raises(ValueError, match="cinco palabras"):
        recommend(catalog, "solar energy", embeddings=vectors, model=FakeModel())
    with pytest.raises(ValueError, match="Motor desconocido"):
        recommend(catalog, "Research project about solar energy", engine="other", embeddings=vectors, model=FakeModel())


def test_empty_filters_return_empty_result():
    catalog = make_catalog().iloc[:1].reset_index(drop=True)
    vectors = np.asarray([[1, 0]], dtype=np.float32)
    results = recommend(catalog, "Research project about solar energy", embeddings=vectors, model=FakeModel(), fields=["Medicine"])
    assert results.empty
    assert "score" in results.columns


def test_ranking_metrics():
    assert precision_at_k([2, 0, 1, 0, 0], 5) == pytest.approx(0.4)
    assert ndcg_at_k([2, 1, 0], 3) == pytest.approx(1.0)
    assert ndcg_at_k([0, 2], 2) < 1.0


def test_metrics_validate_k():
    with pytest.raises(ValueError):
        precision_at_k([1], 0)
    with pytest.raises(ValueError):
        ndcg_at_k([1], 0)
