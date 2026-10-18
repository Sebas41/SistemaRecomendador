#!/usr/bin/env python3
"""Resume la revisión humana de artículos similares sin mezclarla con las consultas."""

import pandas as pd

from sisreco.evaluation import ndcg_at_k, precision_at_k
from sisreco.settings import ARTIFACTS_DIR


def main():
    ratings = pd.read_csv(ARTIFACTS_DIR / "similarity_evaluation_ratings.csv", keep_default_na=False)
    if (ratings.relevance.astype(str).str.strip() == "").any():
        raise SystemExit("Completa relevance con 0, 1 o 2 antes de calcular métricas.")
    ratings["relevance"] = pd.to_numeric(ratings.relevance, errors="raise")
    rows = []
    for area, group in ratings.groupby("area"):
        labels = group.sort_values("rank").relevance.astype(int).tolist()
        rows.append({"area": area, "precision_at_5_direct": precision_at_k(labels, 5, threshold=2),
                     "precision_at_5_broad": precision_at_k(labels, 5, threshold=1), "ndcg_at_5": ndcg_at_k(labels, 5)})
    report = pd.DataFrame(rows)
    report.to_csv(ARTIFACTS_DIR / "similarity_evaluation_metrics.csv", index=False)
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()
