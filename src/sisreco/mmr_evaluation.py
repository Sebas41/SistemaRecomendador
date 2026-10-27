"""Preparación y puntuación de una evaluación pareada de diversidad MMR."""

from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

from .evaluation import intra_list_diversity, ndcg_at_k, precision_at_k

MMR_LAMBDAS = (1.0, 0.7, 0.5)
HUMAN_METRICS = ("precision_at_5", "precision_at_5_grade2", "ndcg_at_10", "ild_at_10")


def build_blind_rating_sheet(
    rankings: pd.DataFrame,
    catalog: pd.DataFrame,
    profiles: list[dict[str, Any]],
    *,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return a shuffled profile/article sheet and its separate lambda/rank key."""
    key = rankings[["profile_id", "query_language", "lambda", "rank", "article_id"]].copy()
    profile_map = {profile["profile_id"]: profile for profile in profiles}
    articles = catalog.set_index("id")
    sheet = (rankings[["profile_id", "article_id"]].drop_duplicates()
             .sample(frac=1, random_state=seed).sort_values("profile_id", kind="stable").reset_index(drop=True))
    sheet["profile_description_es"] = sheet["profile_id"].map(lambda pid: profile_map[pid]["es"])
    for column in ("title", "abstract", "year", "language", "source_database", "url"):
        sheet[column] = sheet["article_id"].map(articles[column])
    sheet["relevance"] = ""
    return sheet, key


def diversity_by_query(
    rankings: pd.DataFrame,
    catalog: pd.DataFrame,
    vectors: np.ndarray,
    *,
    top_k: int = 10,
) -> pd.DataFrame:
    """Calculate ILD on each lambda's top-k list using normalized catalog vectors."""
    positions = pd.Series(np.arange(len(catalog)), index=catalog["id"])
    rows = []
    groups = rankings.groupby(["lambda", "profile_id", "query_language"], sort=True)
    for (weight, profile_id, language), group in groups:
        ranked = group.sort_values("rank").head(top_k)
        row_positions = positions.reindex(ranked["article_id"])
        if row_positions.isna().any():
            raise ValueError("La evaluación contiene un artículo sin vector en el catálogo.")
        rows.append({
            "lambda": float(weight),
            "profile_id": profile_id,
            "query_language": language,
            "n_articles": len(ranked),
            "ild_at_10": intra_list_diversity(np.asarray(vectors[row_positions.to_numpy(dtype=int)])),
        })
    return pd.DataFrame(rows)


def paired_randomization(differences: np.ndarray, *, permutations: int = 100_000, seed: int = 42) -> float:
    """Two-sided paired sign-flip randomization p-value."""
    values = np.asarray(differences, dtype=np.float64)
    if values.size == 0:
        return float("nan")
    rng = np.random.default_rng(seed)
    observed = abs(float(values.mean()))
    signs = rng.choice((-1.0, 1.0), size=(permutations, len(values)))
    exceedances = np.abs((signs * values).mean(axis=1)) >= observed
    return float((int(exceedances.sum()) + 1) / (permutations + 1))


def score_mmr(
    rankings: pd.DataFrame,
    diversity: pd.DataFrame,
    ratings: pd.DataFrame,
    *,
    top_k: int = 10,
    permutations: int = 100_000,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute per-query human relevance, lambda summaries, and paired comparisons."""
    judgments = {
        profile_id: dict(zip(group["article_id"], group["relevance"].astype(int)))
        for profile_id, group in ratings.groupby("profile_id")
    }
    rows = []
    for (weight, profile_id, language), group in rankings.groupby(
        ["lambda", "profile_id", "query_language"], sort=True
    ):
        ranked = group.sort_values("rank")["article_id"].tolist()[:top_k]
        profile_judgments = judgments.get(profile_id, {})
        grades = [profile_judgments.get(article_id, 0) for article_id in ranked]
        rows.append({
            "lambda": float(weight),
            "profile_id": profile_id,
            "query_language": language,
            "precision_at_5": precision_at_k(grades, 5, threshold=1),
            "precision_at_5_grade2": precision_at_k(grades, 5, threshold=2),
            "ndcg_at_10": ndcg_at_k(ranked, profile_judgments, top_k),
        })
    per_query = pd.DataFrame(rows).merge(
        diversity, on=["lambda", "profile_id", "query_language"], how="left", validate="one_to_one"
    )
    all_summary = per_query.groupby("lambda")[list(HUMAN_METRICS)].mean().assign(query_language="todos")
    language_summary = per_query.groupby(["lambda", "query_language"])[list(HUMAN_METRICS)].mean().reset_index()
    summary = pd.concat([all_summary.reset_index(), language_summary], ignore_index=True)

    paired = per_query.pivot(index=["profile_id", "query_language"], columns="lambda", values=list(HUMAN_METRICS))
    comparisons = []
    weights = sorted(per_query["lambda"].unique(), reverse=True)
    for first, second in combinations(weights, 2):
        for metric in HUMAN_METRICS:
            differences = (paired[(metric, second)] - paired[(metric, first)]).dropna().to_numpy()
            comparisons.append({
                "metric": metric,
                "lambda_reference": first,
                "lambda_candidate": second,
                "queries": len(differences),
                "difference_candidate_minus_reference": float(differences.mean()) if len(differences) else float("nan"),
                "candidate_better": int((differences > 0).sum()),
                "ties": int((differences == 0).sum()),
                "candidate_worse": int((differences < 0).sum()),
                "p_value": paired_randomization(differences, permutations=permutations, seed=seed),
            })
    return per_query, summary, pd.DataFrame(comparisons)
