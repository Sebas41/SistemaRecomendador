from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import sisreco.openalex as openalex
from sisreco.catalog import clean_catalog
from sisreco.engine import recommend
from sisreco.evaluation import ndcg_at_k, precision_at_k
from sisreco.openalex import reconstruct_abstract, valid_work
from sisreco.scielo import journal_subjects, normalize_article, sample_offsets


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


def test_openalex_download_checkpoints_completed_fields(tmp_path, monkeypatch):
    fields = [{"id": f"https://openalex.org/fields/{index}", "display_name": f"Field {index}"}
              for index in range(26)]
    monkeypatch.setattr(openalex, "academic_fields", lambda session: fields)

    fail_once = True
    first_field_calls = 0

    def fake_field_records(field, **kwargs):
        nonlocal fail_once, first_field_calls
        field_number = field["id"].rsplit("/", 1)[-1]
        if field_number == "0":
            first_field_calls += 1
        if field_number == "1" and fail_once:
            fail_once = False
            raise RuntimeError("Simulated interrupted request")
        return [{
            "id": f"https://openalex.org/W{field_number}_{index}",
            "title": f"Research article {field_number} number {index}",
            "abstract_inverted_index": {"research": [0], "findings": [1], "matter": [2]},
            "publication_year": 2020,
            "authorships": [],
            "primary_topic": {"display_name": "Research", "field": {"id": field["id"]}},
            "keywords": [],
            "language": "en",
            "doi": None,
            "primary_location": {},
        } for index in range(100)]

    monkeypatch.setattr(openalex, "_field_sample_records", fake_field_records)
    output = tmp_path / "works.jsonl.gz"
    with pytest.raises(RuntimeError, match="Simulated interrupted request"):
        openalex.download_catalog(
            output, target_per_field=100, sample_size=100, max_attempts=1
        )

    assert openalex.download_catalog(
        output, target_per_field=100, sample_size=100, max_attempts=1
    ) == 2600
    assert first_field_calls == 1
    assert not list(tmp_path.glob("openalex_checkpoint_*"))


def test_openalex_reads_api_key_from_project_env_file(tmp_path, monkeypatch):
    module_path = tmp_path / "src" / "sisreco" / "openalex.py"
    module_path.parent.mkdir(parents=True)
    monkeypatch.setattr(openalex, "__file__", str(module_path))
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    (tmp_path / ".env").write_text('OPENALEX_API_KEY="local-test-key"\n', encoding="utf-8")
    assert openalex._api_key() == "local-test-key"


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


class FakeReranker:
    def predict(self, pairs, **kwargs):
        return np.asarray([
            2.0 if any(term in passage.lower() for term in ("business process", "solar energy")) else -2.0
            for _, passage in pairs
        ], dtype=np.float32)


def test_semantic_recommender_ranks_and_filters_articles():
    catalog = make_catalog().iloc[:2].reset_index(drop=True)
    embeddings = np.asarray([[1, 0], [0, 1]], dtype=np.float32)
    results = recommend(
        catalog,
        "Research project about solar energy forecasting",
        embeddings=embeddings,
        model=FakeModel(),
        reranker=FakeReranker(),
        fields=["Energy"],
        min_year=2022,
        max_year=2022,
        top_k=5,
        generate_evidence=False,
    )
    assert results["id"].tolist() == ["W1"]
    assert np.isclose(results.iloc[0]["score"], 2.0)
    assert np.isclose(results.iloc[0]["semantic_score"], 1.0)


def test_semantic_reranker_removes_polysemy_mismatch():
    catalog = pd.DataFrame([
        {**make_catalog().iloc[0].to_dict(), "id": "building", "title": "AI for masonry architecture", "abstract": "Masonry structural behavior in physical buildings."},
        {**make_catalog().iloc[0].to_dict(), "id": "business", "title": "AI agents for enterprise business process architecture", "abstract": "Enterprise software and business process automation."},
    ])
    vectors = np.asarray([[0, 1], [1, 0]], dtype=np.float32)
    results = recommend(
        catalog,
        "agentes de inteligencia artificial para arquitectura empresarial",
        embeddings=vectors,
        model=FakeModel(),
        reranker=FakeReranker(),
        generate_evidence=False,
    )
    assert results["id"].tolist() == ["business"]


def test_semantic_recommender_abstains_when_all_candidates_are_irrelevant():
    catalog = make_catalog().iloc[:1].reset_index(drop=True)
    vectors = np.asarray([[1, 0]], dtype=np.float32)
    class IrrelevantReranker:
        def predict(self, pairs, **kwargs):
            return np.full(len(pairs), -1.0, dtype=np.float32)

    results = recommend(
        catalog,
        "Research project about solar energy",
        embeddings=vectors,
        model=FakeModel(),
        reranker=IrrelevantReranker(),
        generate_evidence=False,
    )
    assert results.empty


@pytest.mark.parametrize("query", [
    "agentes de inteligencia artificial para la arquitectura empresarial",
    "mobile applications for diabetes patient care",
])
def test_no_topic_can_bypass_the_relevance_filter(query):
    class NegativeReranker:
        def predict(self, pairs, **kwargs):
            return np.full(len(pairs), -1.0, dtype=np.float32)

    catalog = make_catalog().iloc[:1].copy()
    catalog.loc[0, "title"] = query
    result = recommend(catalog, query, embeddings=np.asarray([[1, 0]], dtype=np.float32),
                       model=FakeModel(), reranker=NegativeReranker(), generate_evidence=False)
    assert result.empty


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


def make_scielo_record():
    abstract = " ".join([
        "Este estudio analiza métodos de investigación aplicada, describe sus resultados y discute sus implicaciones para futuras investigaciones."
    ] * 9)
    return {
        "code": "S1234-56782024000100001",
        "collection": "col",
        "doi": "https://doi.org/10.1234/example.2024.01",
        "fulltexts": {"html": {"es": "http://www.scielo.org.co/scielo.php?pid=example"}},
        "article": {
            "v12": [{"l": "en", "_": "A study about applied scientific methods"}, {"l": "es", "_": "Estudio sobre métodos científicos aplicados"}],
            "v83": [{"l": "en", "_": "English abstract not selected"}, {"l": "es", "a": abstract}],
            "v40": [{"_": "es"}],
            "v65": [{"_": "20240500"}],
            "v35": [{"_": "1234-5678"}],
            "v10": [{"n": "Ana María", "s": "Pérez"}],
            "v85": [{"k": "metodología", "l": "es"}, {"_": "nd"}],
            "v30": [{"_": "Revista de Prueba"}],
            "v237": [{"_": "10.1234/example.2024.01"}],
        },
    }


def test_scielo_normalizes_legacy_articlemeta_fields():
    article = normalize_article(
        make_scielo_record(),
        journal_subject_by_issn={"1234-5678": "Health Sciences"},
        collection_names={"col": "Colombia"},
    )
    assert article is not None
    assert article["id"] == "SCIELO:col:S1234-56782024000100001"
    assert article["title"] == "Estudio sobre métodos científicos aplicados"
    assert article["year"] == 2024
    assert article["language"] == "es"
    assert article["field"] == "Health Sciences"
    assert article["authors"] == ["Ana María Pérez"]
    assert article["doi"] == "10.1234/example.2024.01"
    assert article["source_database"] == "SciELO"
    assert article["source_collection"] == "Colombia"
    assert article["url"].startswith("https://")


def test_scielo_journal_subjects_use_issn_and_articlemeta_classification():
    mapping = journal_subjects([{
        "code": "1234-5678",
        "issns": ["8765-4321"],
        "v441": [{"_": "Health Sciences"}],
    }])
    assert mapping == {"1234-5678": "Health Sciences", "8765-4321": "Health Sciences"}


def test_scielo_missing_language_is_inferred_by_catalog_cleaner():
    record = make_scielo_record()
    record["article"].pop("v40")
    record["article"]["v12"] = [record["article"]["v12"][1]]
    record["article"]["v83"] = [record["article"]["v83"][1]]
    normalized = normalize_article(record)
    cleaned = clean_catalog(pd.DataFrame([normalized]))
    assert cleaned.iloc[0]["language"] == "es"
    assert bool(cleaned.iloc[0]["language_inferred"])


def test_scielo_sample_offsets_are_reproducible_and_in_bounds():
    first = sample_offsets(total=12_345, page_size=100, pages_to_sample=5, seed=42)
    assert first == sample_offsets(total=12_345, page_size=100, pages_to_sample=5, seed=42)
    assert len(first) == 5
    assert len(first) == len(set(first))
    assert all(0 <= offset < 12_345 and offset % 100 == 0 for offset in first)


def test_clean_catalog_deduplicates_doi_url_and_plain_identifier():
    frame = make_catalog().iloc[:2].copy()
    frame.loc[frame.index[0], "doi"] = "https://doi.org/10.1234/shared"
    frame.loc[frame.index[1], "doi"] = "10.1234/shared"
    frame.loc[frame.index[1], "title"] = "A different solar forecasting study"
    cleaned = clean_catalog(frame)
    assert len(cleaned) == 1
