from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import sisreco.openalex as openalex
from pathlib import Path

from sisreco.catalog import clean_abstract, clean_catalog, clean_text, prepare_texts
from sisreco.engine import _mmr_order, article_text, build_query, recommend
from sisreco.evaluation import intra_list_diversity, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
from sisreco.settings import RerankerSpec, RetrieverSpec
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


SPEC = RetrieverSpec("fake", max_seq_length=512, vectors_path=Path("unused.npy"))
RERANK = RerankerSpec("fake", max_length=512, candidates=10)


class FakeModel:
    def encode(self, inputs, **kwargs):
        if isinstance(inputs, str):
            inputs = [inputs]
        return np.asarray([[1.0, 0.0] if "solar" in text.lower() else [0.0, 1.0] for text in inputs], dtype=np.float32)


class FakeReranker:
    """Puntaje alto para pasajes con «business process» o «solar energy»; negativo para el resto."""

    def predict(self, pairs, **kwargs):
        return np.asarray([
            2.0 if any(term in passage.lower() for term in ("business process", "solar energy")) else -2.0
            for _, passage in pairs
        ], dtype=np.float32)


def run(catalog, query, vectors, **kwargs):
    kwargs.setdefault("reranker_spec", RERANK)
    kwargs.setdefault("reranker", FakeReranker())
    return recommend(catalog, query, vectors=vectors, retriever=FakeModel(), retriever_spec=SPEC,
                     generate_evidence=False, **kwargs)


def test_article_text_joins_title_keywords_topic_and_abstract_without_field():
    row = {"title": "Solar forecasting", "keywords": np.array(["solar", "machine learning"]), "topic": "Energy forecasting",
           "abstract": "We forecast solar output.", "field": "Energy"}
    assert article_text(row) == "Solar forecasting. solar, machine learning. Energy forecasting. We forecast solar output."


def test_build_query_appends_keywords_only_when_present():
    assert build_query("Quiero estudiar energía solar", "pronóstico, redes") == "Quiero estudiar energía solar. Palabras clave: pronóstico, redes"
    assert build_query("Quiero estudiar energía solar", "  ") == "Quiero estudiar energía solar"


def test_semantic_recommender_ranks_and_filters_articles():
    catalog = make_catalog().iloc[:2].reset_index(drop=True)
    results = run(catalog, "Research project about solar energy forecasting", np.asarray([[1, 0], [0, 1]], dtype=np.float32),
                  fields=["Energy"], min_year=2022, max_year=2022)
    assert results["id"].tolist() == ["W1"]
    assert np.isclose(results.iloc[0]["score"], 2.0)
    assert np.isclose(results.iloc[0]["retrieval_score"], 1.0)


def test_reranker_moves_the_pertinent_candidate_to_the_top():
    catalog = pd.DataFrame([
        {**make_catalog().iloc[0].to_dict(), "id": "building", "title": "AI for masonry architecture"},
        {**make_catalog().iloc[0].to_dict(), "id": "business", "title": "AI agents for enterprise business process architecture"},
    ])
    # El recuperador prefiere el artículo de mampostería; el reordenador debe corregirlo.
    results = run(catalog, "agentes de inteligencia artificial para arquitectura empresarial",
                  np.asarray([[0, 1], [1, 0]], dtype=np.float32))
    assert results["id"].tolist() == ["business", "building"]


def test_recommender_returns_fixed_top_k_even_when_reranker_scores_are_negative():
    catalog = pd.concat([make_catalog().iloc[[0]].assign(id=f"W{i}", title=f"Wind turbine study number {i}")
                         for i in range(12)], ignore_index=True)
    vectors = np.tile(np.asarray([[0, 1]], dtype=np.float32), (12, 1))
    results = run(catalog, "Research project about solar energy", vectors, top_k=10)
    assert len(results) == 10
    assert (results["score"] < 0).all()


def test_recommender_without_reranker_orders_by_cosine():
    catalog = make_catalog().iloc[:2].reset_index(drop=True)
    results = run(catalog, "Research project about solar energy", np.asarray([[0.6, 0.8], [1, 0]], dtype=np.float32),
                  reranker_spec=None, reranker=None)
    assert results["id"].tolist() == ["W2", "W1"]
    assert results["score"].equals(results["retrieval_score"])


def test_mmr_full_relevance_weight_preserves_relevance_order():
    order = _mmr_order(
        np.asarray([0.8, 0.95, 0.7]),
        np.asarray([[1, 0], [0.9, 0.1], [0, 1]], dtype=np.float32),
        relevance_weight=1.0,
    )
    assert order.tolist() == [1, 0, 2]


def test_mmr_selects_a_less_redundant_candidate():
    order = _mmr_order(
        np.asarray([0.95, 0.94, 0.7]),
        np.asarray([[1, 0], [0.99, 0.1], [0, 1]], dtype=np.float32),
        relevance_weight=0.5,
    )
    assert order[:2].tolist() == [0, 2]


def test_recommender_can_skip_reranker_and_keep_dense_scores():
    class RerankerMustNotRun:
        def predict(self, *_args, **_kwargs):
            raise AssertionError("Reranker should be skipped in low-memory fallback")

    catalog = make_catalog().iloc[:2].reset_index(drop=True)
    vectors = np.asarray([[1, 0], [0, 1]], dtype=np.float32)
    results = run(catalog, "Research project about solar energy", vectors,
                  reranker=RerankerMustNotRun(), rerank_enabled=False)

    assert results["id"].tolist() == ["W1", "W2"]
    assert results["score"].equals(results["retrieval_score"])


def test_recommender_rejects_short_queries_and_unknown_engines():
    catalog = make_catalog().iloc[:1].reset_index(drop=True)
    vectors = np.asarray([[1, 0]], dtype=np.float32)
    with pytest.raises(ValueError, match="cinco palabras"):
        run(catalog, "solar energy", vectors)
    with pytest.raises(ValueError, match="Motor desconocido"):
        run(catalog, "Research project about solar energy", vectors, engine="other")


def test_empty_filters_return_empty_result():
    catalog = make_catalog().iloc[:1].reset_index(drop=True)
    results = run(catalog, "Research project about solar energy", np.asarray([[1, 0]], dtype=np.float32), fields=["Medicine"])
    assert results.empty
    assert "score" in results.columns


def test_precision_counts_missing_positions_as_not_pertinent():
    assert precision_at_k([2, 0, 1, 0, 0], 5) == pytest.approx(0.4)
    assert precision_at_k([2, 1], 5) == pytest.approx(0.4)


def test_ndcg_ideal_uses_every_judgment_for_the_query():
    judgments = {"a": 1, "b": 2, "c": 2, "d": 0}
    # Una lista que solo recupera un artículo parcial no alcanza la nota máxima.
    assert ndcg_at_k(["a"], judgments, 5) == pytest.approx(1 / (3 + 3 / np.log2(3) + 1 / np.log2(4)))
    assert ndcg_at_k(["b", "c", "a"], judgments, 5) == pytest.approx(1.0)
    assert ndcg_at_k(["x", "y"], judgments, 5) == 0.0


def test_reciprocal_rank_and_recall_for_known_item():
    ranked = ["x", "y", "target", "z"]
    assert reciprocal_rank(ranked, "target", 10) == pytest.approx(1 / 3)
    assert reciprocal_rank(ranked, "target", 2) == 0.0
    assert recall_at_k(ranked, "target", 10) == 1.0
    assert recall_at_k(ranked, "target", 2) == 0.0


def test_intra_list_diversity_known_values():
    identical = np.asarray([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]])
    orthogonal = np.asarray([[1.0, 0.0], [0.0, 1.0]])
    assert intra_list_diversity(identical) == pytest.approx(0.0)
    assert intra_list_diversity(orthogonal) == pytest.approx(1.0)
    assert intra_list_diversity(identical[:1]) == 0.0


def test_metrics_validate_k():
    for metric, arguments in ((precision_at_k, ([1],)), (ndcg_at_k, (["a"], {"a": 1})), (reciprocal_rank, (["a"], "a")),
                              (recall_at_k, (["a"], "a"))):
        with pytest.raises(ValueError):
            metric(*arguments, 0)


def test_clean_abstract_removes_labels_and_trailing_notices_but_keeps_copyright_as_topic():
    assert clean_abstract("Abstract Results improved learning. " * 3 + "© 2017 Wiley Periodicals, Inc.").startswith("Results improved")
    assert "Wiley" not in clean_abstract("Results improved learning. " * 4 + "© 2017 Wiley Periodicals, Inc.")
    assert clean_abstract("RESUMEN: El estudio analiza el agua.") == "El estudio analiza el agua."
    topical = "The Law on Copyright and Related Rights is analysed in detail. " + "Further discussion follows. " * 10
    assert "Copyright" in clean_abstract(topical)
    assert clean_abstract("Findings hold. " * 6 + "(PsycInfo Database Record (c) 2021 APA, all rights reserved).").endswith("Findings hold.")


def test_clean_text_repairs_utf8_read_as_latin1():
    assert clean_text("objetivos estratÃ©gicos de la agenda") == "objetivos estratégicos de la agenda"


def test_prepare_texts_relabels_language_from_abstract_and_excludes_shared_abstracts():
    english = " ".join(["The study examines renewable energy policy and electricity markets in several countries."] * 10)
    frame = pd.DataFrame([
        {"id": "W1", "title": "Energía renovable", "abstract": english, "language": "es", "source_database": "OpenAlex"},
        {"id": "W2", "title": "Journal scope one", "abstract": "Shared journal description text " * 20, "language": "en", "source_database": "OpenAlex"},
        {"id": "W3", "title": "Journal scope two", "abstract": "Shared journal description text " * 20, "language": "en", "source_database": "OpenAlex"},
    ])
    kept, report = prepare_texts(frame)
    assert kept["id"].tolist() == ["W1"]
    assert kept.iloc[0]["language"] == "en"
    assert kept.iloc[0]["language_declared"] == "es"
    assert report["excluded"] == {"shared_abstract": 2}


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


def test_scielo_normalizes_articlemeta_json_fields():
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
