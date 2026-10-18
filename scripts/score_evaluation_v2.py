#!/usr/bin/env python3
"""Calcula métricas de la evaluación ciega v2 cuando existen juicios humanos."""

import json
import numpy as np
import pandas as pd

from sisreco.evaluation import ndcg_at_k, precision_at_k
from sisreco.settings import ARTIFACTS_DIR


def main():
    candidates = pd.read_csv(ARTIFACTS_DIR / "evaluation_v2_candidates.csv")
    ratings = pd.read_csv(ARTIFACTS_DIR / "evaluation_v2_ratings.csv", keep_default_na=False)
    if (ratings["relevance"].astype(str).str.strip() == "").any():
        raise SystemExit("Completa relevance con 0, 1 o 2 antes de calcular métricas.")
    ratings["relevance"] = pd.to_numeric(ratings["relevance"], errors="raise")
    if not ratings["relevance"].isin([0, 1, 2]).all():
        raise SystemExit("La relevancia solo admite 0, 1 o 2.")
    key = json.loads((ARTIFACTS_DIR / "evaluation_v2_blind_key.json").read_text())
    keys = ["split", "profile_id", "query_language", "article_id"]
    frame = candidates.merge(ratings[keys + ["relevance"]], on=keys, how="left", validate="many_to_one")
    if frame["relevance"].isna().any():
        raise SystemExit("Faltan juicios para resultados presentados por un motor.")
    frame["engine"] = frame["anonymous_engine"].map(key)
    rows = []
    group_columns = ["split", "engine", "query_language"]
    for group_key, group in frame.groupby(group_columns):
        per_query = []
        for (_, profile_id, language), ranked in group.groupby(["split", "profile_id", "query_language"]):
            all_labels = frame[(frame["profile_id"] == profile_id) & (frame["query_language"] == language)]["relevance"].tolist()
            labels = ranked.sort_values("rank")["relevance"].astype(int).tolist()
            per_query.append({"precision_direct": precision_at_k(labels, 5, threshold=2),
                              "precision_broad": precision_at_k(labels, 5, threshold=1),
                              "ndcg": ndcg_at_k(labels, 5, ideal_relevances=all_labels),
                              "first_irrelevant": float(bool(labels) and labels[0] == 0),
                              "empty": 0.0, "count": len(labels),
                              "latency": ranked["latency_seconds"].iloc[0]})
        values = pd.DataFrame(per_query)
        rows.append(dict(zip(group_columns, group_key)) | {
            "queries": len(values), "precision_at_5_direct": values.precision_direct.mean(),
            "precision_at_5_broad": values.precision_broad.mean(), "ndcg_at_5": values.ndcg.mean(),
            "first_result_irrelevant_rate": values.first_irrelevant.mean(),
            "empty_rate": values.empty.mean(), "mean_results": values["count"].mean(),
            "latency_p95_seconds": float(np.quantile(values.latency, .95)),
        })
    report = pd.DataFrame(rows).sort_values(group_columns)
    report.to_csv(ARTIFACTS_DIR / "evaluation_v2_metrics.csv", index=False)
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()
