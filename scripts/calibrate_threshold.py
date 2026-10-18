#!/usr/bin/env python3
"""Selecciona un corte de puntuación usando solo el conjunto de desarrollo calificado."""

import json
import numpy as np
import pandas as pd

from sisreco.evaluation import ndcg_at_k, precision_at_k
from sisreco.settings import ARTIFACTS_DIR


def main():
    candidates = pd.read_csv(ARTIFACTS_DIR / "evaluation_v2_candidates.csv")
    ratings = pd.read_csv(ARTIFACTS_DIR / "evaluation_v2_ratings.csv", keep_default_na=False)
    if (ratings.relevance.astype(str).str.strip() == "").any():
        raise SystemExit("Completa las calificaciones humanas antes de calibrar el corte.")
    ratings["relevance"] = pd.to_numeric(ratings["relevance"], errors="raise")
    key = json.loads((ARTIFACTS_DIR / "evaluation_v2_blind_key.json").read_text())
    frame = candidates.merge(ratings[["split", "profile_id", "query_language", "article_id", "relevance"]],
        on=["split", "profile_id", "query_language", "article_id"], how="inner", validate="many_to_one")
    frame["engine"] = frame.anonymous_engine.map(key)
    frame = frame[(frame.split == "development") & frame.reranker_score.notna()].copy()
    if frame.empty:
        raise SystemExit("No hay puntuaciones de reordenador para calibrar.")
    thresholds = sorted(set(frame.reranker_score.tolist()))
    rows = []
    for threshold in thresholds:
        per_query = []
        for _, group in frame.groupby(["engine", "profile_id", "query_language"]):
            labels = group.loc[group.reranker_score >= threshold].sort_values("rank").relevance.astype(int).tolist()
            ideal = group.relevance.astype(int).tolist()
            per_query.append({"direct": precision_at_k(labels, 5, threshold=2),
                              "ndcg": ndcg_at_k(labels, 5, ideal_relevances=ideal),
                              "irrelevant": float(bool(labels) and labels[0] == 0), "count": len(labels)})
        values = pd.DataFrame(per_query)
        rows.append({"threshold": threshold, "precision_at_5_direct": values.direct.mean(),
                     "ndcg_at_5": values.ndcg.mean(), "first_result_irrelevant_rate": values.irrelevant.mean(),
                     "mean_results": values["count"].mean()})
    report = pd.DataFrame(rows).sort_values(["precision_at_5_direct", "ndcg_at_5", "first_result_irrelevant_rate"],
                                              ascending=[False, False, True])
    report.to_csv(ARTIFACTS_DIR / "threshold_calibration.csv", index=False)
    print(report.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
