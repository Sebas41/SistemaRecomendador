#!/usr/bin/env python3
"""Calcula P@5 y nDCG@5 con los juicios humanos de la hoja ciega."""

import pandas as pd

from sisreco.evaluation import ndcg_at_k, precision_at_k
from sisreco.settings import ARTIFACTS_DIR

TOP_RATED = 5


def main() -> None:
    ratings_path, key_path = ARTIFACTS_DIR / "human_ratings.csv", ARTIFACTS_DIR / "human_ratings_key.csv"
    if not ratings_path.exists() or not key_path.exists():
        raise SystemExit("Genera la hoja con: python scripts/prepare_evaluation.py --chosen <configuración>")
    ratings = pd.read_csv(ratings_path)
    if ratings["relevance"].isna().any() or (ratings["relevance"].astype(str).str.strip() == "").any():
        raise SystemExit("Completa la columna relevance de human_ratings.csv con 0, 1 o 2.")
    ratings["relevance"] = pd.to_numeric(ratings["relevance"], errors="raise").astype(int)
    if not ratings["relevance"].isin([0, 1, 2]).all():
        raise SystemExit("La relevancia solo puede ser 0, 1 o 2.")
    if ratings.duplicated(["profile_id", "article_id"]).any():
        raise SystemExit("Cada combinación de perfil y artículo debe tener una sola calificación.")

    # Los juicios son por perfil: valen para la consulta en español y en inglés.
    judgments = {profile: dict(zip(group["article_id"], group["relevance"])) for profile, group in ratings.groupby("profile_id")}
    rankings = pd.read_csv(key_path)
    rows = []
    for (config, language, profile), group in rankings.groupby(["config", "query_language", "profile_id"]):
        ranked = group.sort_values("rank")["article_id"].tolist()
        grades = [judgments[profile].get(article, 0) for article in ranked]
        rows.append({"config": config, "query_language": language, "profile_id": profile,
                     "precision_at_5": precision_at_k(grades, TOP_RATED, threshold=1),
                     "precision_at_5_grade2": precision_at_k(grades, TOP_RATED, threshold=2),
                     "ndcg_at_5": ndcg_at_k(ranked, judgments[profile], TOP_RATED)})
    per_profile = pd.DataFrame(rows)
    per_profile.to_csv(ARTIFACTS_DIR / "human_metrics_per_profile.csv", index=False)
    summary = pd.concat([
        per_profile.groupby("config")[["precision_at_5", "precision_at_5_grade2", "ndcg_at_5"]].mean().assign(query_language="todos"),
        per_profile.groupby(["config", "query_language"])[["precision_at_5", "precision_at_5_grade2", "ndcg_at_5"]].mean()
        .reset_index("query_language"),
    ]).reset_index()
    summary.to_csv(ARTIFACTS_DIR / "human_metrics.csv", index=False)
    print(summary.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
