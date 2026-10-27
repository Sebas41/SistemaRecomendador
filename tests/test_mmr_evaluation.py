import numpy as np
import pandas as pd

from sisreco.mmr_evaluation import build_blind_rating_sheet, diversity_by_query, score_mmr


def sample_data():
    catalog = pd.DataFrame([
        dict(id="a", title="Solar methods", abstract="Solar energy forecasting study.", year=2022,
             language="en", source_database="OpenAlex", url="https://example.org/a"),
        dict(id="b", title="Solar forecasting", abstract="Solar output prediction study.", year=2023,
             language="en", source_database="OpenAlex", url="https://example.org/b"),
        dict(id="c", title="Health services", abstract="Hospital care and patient outcomes.", year=2024,
             language="en", source_database="SciELO", url="https://example.org/c"),
    ])
    rankings = pd.DataFrame([
        ("P01_en", "P01", "en", 1.0, 1, "a", .9),
        ("P01_en", "P01", "en", 1.0, 2, "b", .8),
        ("P01_en", "P01", "en", .7, 1, "a", .9),
        ("P01_en", "P01", "en", .7, 2, "c", .7),
        ("P01_en", "P01", "en", .5, 1, "c", .7),
        ("P01_en", "P01", "en", .5, 2, "b", .8),
    ], columns=["query_id", "profile_id", "query_language", "lambda", "rank", "article_id", "score"])
    vectors = np.asarray([[1, 0], [.99, .1], [0, 1]], dtype=np.float32)
    profiles = [{"profile_id": "P01", "es": "Proyecto de pronóstico de energía solar"}]
    return catalog, rankings, vectors, profiles


def test_blind_rating_sheet_deduplicates_articles_and_hides_lambda():
    catalog, rankings, _vectors, profiles = sample_data()

    sheet, key = build_blind_rating_sheet(rankings, catalog, profiles, seed=42)

    assert set(sheet["article_id"]) == {"a", "b", "c"}
    assert sheet[["profile_id", "article_id"]].duplicated().sum() == 0
    assert "lambda" not in sheet.columns
    assert "rank" not in sheet.columns
    assert set(key["lambda"]) == {1.0, 0.7, 0.5}
    assert (sheet["relevance"] == "").all()


def test_diversity_by_query_uses_the_top_k_vectors():
    catalog, rankings, vectors, _profiles = sample_data()

    measured = diversity_by_query(rankings, catalog, vectors, top_k=2)
    by_lambda = measured.set_index("lambda")["ild_at_10"]

    assert by_lambda[1.0] < 0.01
    assert by_lambda[0.7] > 0.99
    assert by_lambda[0.5] > 0.89


def test_score_mmr_computes_human_metrics_and_paired_comparisons():
    catalog, rankings, vectors, _profiles = sample_data()
    diversity = diversity_by_query(rankings, catalog, vectors, top_k=2)
    ratings = pd.DataFrame([
        ("P01", "a", 2),
        ("P01", "b", 0),
        ("P01", "c", 1),
    ], columns=["profile_id", "article_id", "relevance"])

    per_query, summary, comparisons = score_mmr(
        rankings, diversity, ratings, top_k=2, permutations=100, seed=42
    )

    assert len(per_query) == 3
    assert per_query.set_index("lambda").loc[1.0, "precision_at_5"] == .2
    assert per_query.set_index("lambda").loc[0.7, "precision_at_5_grade2"] == .2
    assert set(summary["query_language"]) == {"todos", "en"}
    assert len(comparisons) == 3 * 4
    assert comparisons["p_value"].between(0, 1).all()
