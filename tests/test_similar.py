"""Regresiones de recomendación por artículo y casos sin vocabulario."""

import numpy as np
import pandas as pd
import pytest

import sisreco.engine as engine


class FakeSemanticModel:
    def encode(self, inputs, **kwargs):
        if isinstance(inputs, str):
            inputs = [inputs]
        return np.asarray([[1.0, 0.0] if "solar" in value.lower() else [0.0, 1.0] for value in inputs], dtype=np.float32)


def small_catalog():
    return pd.DataFrame([
        dict(id="solar", title="Solar power forecasting", abstract="Solar energy weather forecasting",
             year=2022, language="en", field="Energy", doi="10.1234/solar", authors=["Ana Pérez"]),
        dict(id="wind", title="Wind energy prediction", abstract="Wind energy weather prediction",
             year=2023, language="en", field="Energy", doi=None, authors=["Luis Díaz"]),
        dict(id="spanish", title="Predicción de energía solar", abstract="Predicción energética",
             year=2024, language="es", field="Energy", doi=None, authors=[]),
        dict(id="health", title="Mobile diabetes care", abstract="Mobile diabetes patients health",
             year=2021, language="en", field="Medicine", doi=None, authors=[]),
    ], index=[30, 10, 80, 20])


def vectors():
    # Intentionally not normalized: cosine should ignore vector magnitude.
    return np.array([[3, 0], [4, 1], [2, 1], [.1, 8]], dtype=np.float32)


def test_similar_uses_seed_content_and_positional_alignment_without_models(monkeypatch):
    def no_model(*args, **kwargs):
        raise AssertionError("Item recommendations must reuse the existing vectors")
    monkeypatch.setattr(engine, "_load_sentence_model", no_model)
    monkeypatch.setattr(engine, "_load_reranker", no_model)
    c = small_catalog()
    first = engine.recommend_similar(c, "solar", embeddings=vectors(), top_k=10)
    assert first.id.tolist() == ["wind", "spanish", "health"]
    assert first.score.is_monotonic_decreasing
    assert first.iloc[0].score == pytest.approx(4 / np.sqrt(17))
    second = engine.recommend_similar(c, "health", embeddings=vectors(), top_k=2)
    assert second.id.tolist() == ["spanish", "wind"]
    assert c.index.tolist() == [30, 10, 80, 20]  # The caller's frame is not mutated.


def test_similar_excludes_seed_and_duplicate_doi_or_title():
    c = small_catalog().reset_index(drop=True)
    duplicate_doi = {**c.iloc[0].to_dict(), "id": "copy_doi", "title": "Alternate title",
                     "doi": "https://doi.org/10.1234/SOLAR"}
    duplicate_title = {**c.iloc[0].to_dict(), "id": "copy_title", "title": "SOLAR POWER—FORECASTING!", "doi": None}
    c = pd.concat([c, pd.DataFrame([duplicate_doi, duplicate_title])], ignore_index=True)
    v = np.vstack([vectors(), [3, 0], [3, 0]])
    result = engine.recommend_similar(c, "solar", embeddings=v, top_k=10)
    assert set(result.id) == {"wind", "spanish", "health"}


def test_similar_filters_and_returns_fewer_than_requested():
    c = small_catalog()
    result = engine.recommend_similar(c, "solar", embeddings=vectors(), fields=["Energy"],
                                      language="es", min_year=2023, max_year=2024, top_k=10)
    assert result.id.tolist() == ["spanish"]
    # Reference need not pass the candidate filters.
    empty = engine.recommend_similar(c, "solar", embeddings=vectors(), fields=["Medicine"], language="es")
    assert empty.empty
    assert {"score", "evidence"}.issubset(empty.columns)


@pytest.mark.parametrize("kwargs, message", [
    ({"article_id": "missing"}, "no existe"),
    ({"article_id": "solar", "top_k": 0}, "positiva"),
    ({"article_id": "solar", "min_year": 2024, "max_year": 2020}, "año inicial"),
    ({"article_id": "solar", "language": "xx"}, "Idioma desconocido"),
])
def test_similar_validates_inputs(kwargs, message):
    with pytest.raises(ValueError, match=message):
        engine.recommend_similar(small_catalog(), embeddings=vectors(), **kwargs)


def test_similar_rejects_misaligned_and_invalid_vectors():
    c = small_catalog()
    for bad in (np.ones((2, 2)), np.ones(4)):
        with pytest.raises(ValueError, match="vectores"):
            engine.recommend_similar(c, "solar", embeddings=bad)
    v = vectors(); v[0] = 0
    with pytest.raises(ValueError, match="vector válido"):
        engine.recommend_similar(c, "solar", embeddings=v)
    v = vectors(); v[1] = np.nan; v[2] = 0
    result = engine.recommend_similar(c, "solar", embeddings=v)
    assert result.id.tolist() == ["health"]


@pytest.fixture
def lexical_catalog(tmp_path, monkeypatch):
    for name, filename in [("TFIDF_VECTORIZER", "tfidf.joblib"), ("TFIDF_MATRIX", "tfidf.npz"), ("TFIDF_IDS", "ids.json")]:
        monkeypatch.setattr(engine, name, tmp_path / filename)
    c = small_catalog()
    engine.build_tfidf_index(c)
    return c


def test_tfidf_no_vocabulary_returns_empty_not_unscored_catalog(lexical_catalog):
    result = engine.recommend(lexical_catalog, "zzzzzz qqqqqq xxxxxx vvvvvv jjjjjj", engine="tfidf")
    assert result.empty


def test_tfidf_excludes_zero_score_candidates_after_filters(lexical_catalog):
    result = engine.recommend(lexical_catalog, "solar solar solar solar solar", engine="tfidf", fields=["Medicine"])
    assert result.empty
    result = engine.recommend(lexical_catalog, "solar solar solar solar solar", engine="tfidf")
    assert result.id.tolist() == ["solar"]
    assert np.isfinite(result.score).all()


def test_tfidf_rejects_outdated_index(lexical_catalog):
    changed = lexical_catalog.copy()
    changed.loc[30, "id"] = "new-id"
    with pytest.raises(ValueError, match="no coincide"):
        engine.recommend(changed, "solar solar solar solar solar", engine="tfidf")


def test_hybrid_index_and_rrf_recommendation(tmp_path, monkeypatch):
    c = small_catalog().copy()
    for name, filename in (("HYBRID_VECTORIZER", "hybrid.joblib"), ("HYBRID_MATRIX", "hybrid.npz"), ("HYBRID_MANIFEST", "hybrid.json")):
        monkeypatch.setattr(engine, name, tmp_path / filename)
    engine.build_hybrid_index(c)
    vectorizer, matrix, manifest = engine.load_hybrid_index(c)
    assert matrix.shape[0] == len(c)
    assert manifest["catalog_ids"] == c["id"].tolist()
    assert vectorizer.transform(["solar energy forecast"]).nnz > 0

    class StableReranker:
        def predict(self, pairs, **kwargs):
            return np.asarray([float(len(passage)) for _, passage in pairs])

    result = engine.recommend(
        c, "solar energy forecasting research project", engine="hibrido", top_k=2,
        embeddings=vectors(), model=FakeSemanticModel(), reranker=StableReranker(),
        generate_evidence=False, rerank_candidates=2,
    )
    assert len(result) == 2
    assert {"semantic_score", "lexical_score", "retrieval_score", "reranker_score", "score"} <= set(result.columns)
    assert result.score.is_monotonic_decreasing


def test_rrf_deduplicates_and_validates_weights():
    scores = engine.reciprocal_rank_fusion([["a", "a", "b"], ["b", "a"]], k=10)
    assert scores["a"] == pytest.approx(1 / 11 + 1 / 12)
    assert scores["b"] == pytest.approx(1 / 13 + 1 / 11)
    with pytest.raises(ValueError):
        engine.reciprocal_rank_fusion([["a"]], weights=[1, 1])


def test_hybrid_keeps_semantic_results_when_lexical_query_is_oov(tmp_path, monkeypatch):
    c = small_catalog().copy()
    for name, filename in (("HYBRID_VECTORIZER", "hybrid.joblib"), ("HYBRID_MATRIX", "hybrid.npz"), ("HYBRID_MANIFEST", "hybrid.json")):
        monkeypatch.setattr(engine, name, tmp_path / filename)
    engine.build_hybrid_index(c)
    result = engine.recommend(
        c, "zzzz qqqq xxxxx yyyyy vvvvv", engine="hibrido_sin_rerank", top_k=2,
        embeddings=vectors(), model=FakeSemanticModel(), generate_evidence=False,
    )
    assert len(result) == 2
