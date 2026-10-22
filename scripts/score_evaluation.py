#!/usr/bin/env python3
"""Calcula P@5 y nDCG@5 con los juicios humanos de la hoja ciega y compara las configuraciones."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from sisreco.evaluation import ndcg_at_k, precision_at_k
from sisreco.settings import ARTIFACTS_DIR, SEED

TOP_RATED = 5
PERMUTATIONS = 100_000
METRICS = ["precision_at_5", "precision_at_5_grade2", "ndcg_at_5"]


def paired_randomization(differences: np.ndarray, permutations: int = PERMUTATIONS, seed: int = SEED) -> float:
    """p bilateral de la prueba de aleatorización pareada: invierte al azar el signo de cada diferencia."""
    rng = np.random.default_rng(seed)
    observed = abs(differences.mean())
    signs = rng.choice([-1.0, 1.0], size=(permutations, len(differences)))
    return float(((np.abs((signs * differences).mean(axis=1)) >= observed).sum() + 1) / (permutations + 1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings", type=Path, default=ARTIFACTS_DIR / "human_ratings.csv",
                        help="Hoja calificada (por ejemplo artifacts/human_ratings_JC.csv).")
    parser.add_argument("--reference", default="A")
    parser.add_argument("--chosen", default="C")
    args = parser.parse_args()
    ratings_path, key_path = args.ratings, ARTIFACTS_DIR / "human_ratings_key.csv"
    if not ratings_path.exists() or not key_path.exists():
        raise SystemExit("Genera la hoja con: python scripts/prepare_evaluation.py --chosen <configuración>")
    ratings = pd.read_csv(ratings_path)
    if ratings["relevance"].isna().any() or (ratings["relevance"].astype(str).str.strip() == "").any():
        raise SystemExit(f"Completa la columna relevance de {ratings_path.name} con 0, 1 o 2.")
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
        per_profile.groupby("config")[METRICS].mean().assign(query_language="todos"),
        per_profile.groupby(["config", "query_language"])[METRICS].mean().reset_index("query_language"),
    ]).reset_index()
    summary.to_csv(ARTIFACTS_DIR / "human_metrics.csv", index=False)
    print(f"Hoja: {ratings_path.name} · {len(ratings)} juicios · distribución {ratings['relevance'].value_counts().sort_index().to_dict()}")
    print(summary.round(3).to_string(index=False))

    # Comparación pareada por consulta (perfil × idioma): misma consulta, dos configuraciones.
    paired = per_profile.pivot_table(index=["profile_id", "query_language"], columns="config", values=METRICS)
    comparison = []
    for metric in METRICS:
        differences = (paired[(metric, args.chosen)] - paired[(metric, args.reference)]).to_numpy()
        comparison.append({"metric": metric, "reference": args.reference, "chosen": args.chosen,
                           "queries": len(differences), "difference": differences.mean(),
                           "chosen_better": int((differences > 0).sum()), "ties": int((differences == 0).sum()),
                           "chosen_worse": int((differences < 0).sum()), "p_value": paired_randomization(differences)})
    comparison = pd.DataFrame(comparison)
    comparison.to_csv(ARTIFACTS_DIR / "human_comparison.csv", index=False)
    print(comparison.round(4).to_string(index=False))
    by_profile = per_profile.pivot_table(index="profile_id", columns="config", values=["precision_at_5", "ndcg_at_5"])
    by_profile.to_csv(ARTIFACTS_DIR / "human_metrics_by_profile.csv")
    print(by_profile.round(2).to_string())


if __name__ == "__main__":
    main()
