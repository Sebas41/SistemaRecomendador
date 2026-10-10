#!/usr/bin/env python3
"""Calcula Precision@5 y nDCG@5 tras completar las etiquetas manuales."""

import json
import pandas as pd

from sisreco.evaluation import ndcg_at_k, precision_at_k
from sisreco.settings import ARTIFACTS_DIR


def main():
    candidates = ARTIFACTS_DIR / "evaluation_candidates.csv"
    ratings_path = ARTIFACTS_DIR / "evaluation_ratings.csv"
    key = ARTIFACTS_DIR / "evaluation_blind_key.json"
    if not candidates.exists() or not ratings_path.exists() or not key.exists():
        raise SystemExit("Genera candidatos con: python scripts/prepare_evaluation.py")
    rankings = pd.read_csv(candidates)
    ratings = pd.read_csv(ratings_path)
    if ratings["relevance"].isna().any() or (ratings["relevance"].astype(str).str.strip() == "").any():
        raise SystemExit("Completa la columna relevance de evaluation_ratings.csv con 0, 1 o 2.")
    ratings["relevance"] = pd.to_numeric(ratings["relevance"], errors="raise")
    if not ratings["relevance"].isin([0,1,2]).all():
        raise SystemExit("La relevancia solo puede ser 0, 1 o 2.")
    if ratings.duplicated(["profile_id", "article_id"]).any():
        raise SystemExit("Cada combinación de perfil y artículo debe tener una sola calificación.")
    labels = json.loads(key.read_text(encoding="utf-8"))
    frame = rankings.merge(
        ratings[["profile_id", "article_id", "relevance"]],
        on=["profile_id", "article_id"],
        how="left",
        validate="many_to_one",
    )
    if frame["relevance"].isna().any():
        raise SystemExit("Faltan calificaciones para algunos resultados ordenados.")
    frame["engine"] = frame["anonymous_engine"].map(labels)
    rows = []
    for (engine, language), group in frame.groupby(["engine","query_language"]):
        metrics = []
        for _, results in group.groupby("profile_id"):
            values = results.sort_values("rank")["relevance"].astype(int).tolist()
            metrics.append((precision_at_k(values,5),ndcg_at_k(values,5)))
        rows.append({"engine":engine,"language":language,"profiles":len(metrics),
            "precision_at_5":sum(x[0] for x in metrics)/len(metrics),
            "ndcg_at_5":sum(x[1] for x in metrics)/len(metrics)})
    report = pd.DataFrame(rows)
    report.to_csv(ARTIFACTS_DIR / "evaluation_metrics.csv",index=False)
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()
