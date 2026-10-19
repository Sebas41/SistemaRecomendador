#!/usr/bin/env python3
"""Calcula las métricas de ítem conocido, sus desgloses y la comparación pareada entre configuraciones."""

import argparse
import hashlib
import json
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from sisreco.engine import load_vectors
from sisreco.evaluation import intra_list_diversity, precision_at_k, recall_at_k, reciprocal_rank
from sisreco.settings import ARTIFACTS_DIR, CATALOG, EVALUATION_DIR, RETRIEVER, SEED, TOP_K

RUNS_DIR = ARTIFACTS_DIR / "evaluation"
REFERENCE = "A"


def load_runs(names: list[str]) -> dict[str, pd.DataFrame]:
    return {name: pd.read_csv(RUNS_DIR / f"run_{name}.csv") for name in names if (RUNS_DIR / f"run_{name}.csv").exists()}


def per_query(run: pd.DataFrame, queries: pd.DataFrame, catalog: pd.DataFrame, vectors: np.ndarray) -> pd.DataFrame:
    """Una fila por consulta con las métricas de ítem conocido, topic, diversidad y exposición."""
    topic = catalog.set_index("id")["topic"]
    language = catalog.set_index("id")["language"]
    source = catalog.set_index("id")["source_database"]
    position = pd.Series(np.arange(len(catalog)), index=catalog["id"])
    ranked = run.sort_values(["query_id", "rank"]).groupby("query_id")["article_id"].apply(list)
    rows = []
    for _, query in queries.iterrows():
        ids = ranked.get(query["query_id"], [])
        same_topic = [int(topic.get(item) == query["topic"]) for item in ids]
        others = [item for item in ids if item != query["article_id"]]
        rows.append({
            "query_id": query["query_id"],
            "rr": reciprocal_rank(ids, query["article_id"], TOP_K),
            "recall": recall_at_k(ids, query["article_id"], TOP_K),
            "rank_found": ids.index(query["article_id"]) + 1 if query["article_id"] in ids[:TOP_K] else None,
            # El topic de SciELO es su primera palabra clave, no un topic de OpenAlex.
            "topic_precision": precision_at_k(same_topic, TOP_K) if query["source_database"] == "OpenAlex" else np.nan,
            "ild": intra_list_diversity(vectors[position.loc[ids].to_numpy()]) if len(ids) > 1 else np.nan,
            "share_spanish": float(np.mean([language.get(item) == "es" for item in ids])) if ids else np.nan,
            "share_scielo": float(np.mean([source.get(item) == "SciELO" for item in ids])) if ids else np.nan,
            # Sin el artículo de origen: las consultas sobrerrepresentan el español a propósito y el
            # origen aparece casi siempre, así que incluirlo mediría el diseño de la muestra.
            "share_spanish_others": float(np.mean([language.get(item) == "es" for item in others])) if others else np.nan,
            "share_scielo_others": float(np.mean([source.get(item) == "SciELO" for item in others])) if others else np.nan,
        })
    return queries.merge(pd.DataFrame(rows), on="query_id")


def summarize(table: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    aggregations = {"queries": ("query_id", "count"), "mrr_at_10": ("rr", "mean"), "recall_at_10": ("recall", "mean"),
                    "topic_precision_at_10": ("topic_precision", "mean"), "ild_at_10": ("ild", "mean"),
                    "share_spanish_top10": ("share_spanish", "mean"), "share_scielo_top10": ("share_scielo", "mean")}
    if by:
        return table.groupby(by).agg(**aggregations).reset_index()
    return pd.DataFrame({name: [table[column].agg(function)] for name, (column, function) in aggregations.items()})


def ranx_check(run: pd.DataFrame, queries: pd.DataFrame, table: pd.DataFrame) -> dict:
    """Recalcula MRR y Recall con ranx para verificar la implementación propia."""
    from ranx import Qrels, Run, evaluate

    qrels = Qrels({row["query_id"]: {row["article_id"]: 1} for _, row in queries.iterrows()})
    scores = {query_id: {row["article_id"]: float(TOP_K + 1 - row["rank"]) for _, row in group.iterrows()}
              for query_id, group in run.groupby("query_id")}
    for query_id in queries["query_id"]:
        scores.setdefault(query_id, {})
    result = evaluate(qrels, Run(scores), [f"mrr@{TOP_K}", f"recall@{TOP_K}"])
    return {"ranx_mrr": float(result[f"mrr@{TOP_K}"]), "own_mrr": float(table["rr"].mean()),
            "ranx_recall": float(result[f"recall@{TOP_K}"]), "own_recall": float(table["recall"].mean())}


def compare(runs: dict[str, pd.DataFrame], queries: pd.DataFrame) -> pd.DataFrame:
    """Prueba de aleatorización pareada de Fisher sobre MRR@10 y Recall@10."""
    from ranx import Qrels, Run, compare as ranx_compare

    qrels = Qrels({row["query_id"]: {row["article_id"]: 1} for _, row in queries.iterrows()})
    ranx_runs = []
    for name, run in runs.items():
        scores = {query_id: {row["article_id"]: float(TOP_K + 1 - row["rank"]) for _, row in group.iterrows()}
                  for query_id, group in run.groupby("query_id")}
        for query_id in queries["query_id"]:
            scores.setdefault(query_id, {})
        ranx_runs.append(Run(scores, name=name))
    report = ranx_compare(qrels, ranx_runs, metrics=[f"mrr@{TOP_K}", f"recall@{TOP_K}"], stat_test="fisher",
                          max_p=0.05, random_seed=SEED, n_permutations=100_000)
    rows = []
    for first in report.model_names:
        for second in report.model_names:
            if first >= second:
                continue
            for metric in report.metrics:
                rows.append({"config_a": first, "config_b": second, "metric": metric,
                             "score_a": report.results[first][metric], "score_b": report.results[second][metric],
                             "difference": report.results[second][metric] - report.results[first][metric],
                             "p_value": report.comparisons[(first, second)][metric]["p_value"]})
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs", nargs="+", default=["A", "B", "C"])
    args = parser.parse_args()
    warnings.filterwarnings("ignore", category=Warning, module="ranx")

    catalog = pd.read_parquet(CATALOG)
    queries = pd.DataFrame([json.loads(line) for line in (EVALUATION_DIR / "known_item.jsonl").read_text(encoding="utf-8").splitlines()])
    # Un mismo espacio de vectores para todas las configuraciones: así la diversidad es comparable.
    vectors = load_vectors(catalog, RETRIEVER)
    runs = load_runs(args.configs)
    tables, overall, breakdowns, checks = {}, [], [], []
    for name, run in runs.items():
        table = per_query(run, queries, catalog, vectors).assign(config=name)
        tables[name] = table
        summary = summarize(table).assign(config=name)
        by_language = table.groupby("query_language")["rr"].mean()
        summary["mrr_gap_es_en"] = abs(by_language.get("es", np.nan) - by_language.get("en", np.nan))
        overall.append(summary)
        for column in ("query_language", "article_language", "source_database"):
            breakdowns.append(summarize(table, [column]).rename(columns={column: "group"}).assign(config=name, dimension=column))
        breakdowns.append(summarize(table, ["query_language", "article_language"]).assign(
            config=name, dimension="query_language×article_language",
            group=lambda frame: frame["query_language"] + "→" + frame["article_language"]).drop(columns=["query_language", "article_language"]))
        checks.append({"config": name, **ranx_check(run, queries, table)})

    pd.concat(tables.values()).to_csv(RUNS_DIR / "known_item_per_query.csv", index=False)
    catalog_share = {"es": float(catalog["language"].eq("es").mean()), "SciELO": float(catalog["source_database"].eq("SciELO").mean())}
    exposure = (pd.concat(tables.values()).groupby(["config", "query_language"])[["share_spanish_others", "share_scielo_others"]]
                .mean().reset_index())
    exposure["catalog_share_spanish"] = catalog_share["es"]
    exposure["catalog_share_scielo"] = catalog_share["SciELO"]
    exposure["ratio_spanish"] = exposure["share_spanish_others"] / catalog_share["es"]
    exposure["ratio_scielo"] = exposure["share_scielo_others"] / catalog_share["SciELO"]
    exposure.to_csv(ARTIFACTS_DIR / "evaluation_exposure.csv", index=False)
    print(exposure.round(3).to_string(index=False))
    overall_frame = pd.concat(overall)[["config", "queries", "mrr_at_10", "recall_at_10", "mrr_gap_es_en", "topic_precision_at_10",
                                        "ild_at_10", "share_spanish_top10", "share_scielo_top10"]]
    overall_frame.to_csv(ARTIFACTS_DIR / "evaluation_metrics.csv", index=False)
    breakdown_frame = pd.concat(breakdowns)
    breakdown_frame = breakdown_frame[["config", "dimension", "group"] + [c for c in breakdown_frame.columns if c not in {"config", "dimension", "group"}]]
    breakdown_frame.to_csv(ARTIFACTS_DIR / "evaluation_breakdown.csv", index=False)
    pd.DataFrame(checks).to_csv(RUNS_DIR / "ranx_check.csv", index=False)
    print(overall_frame.round(3).to_string(index=False))
    print(pd.DataFrame(checks).round(4).to_string(index=False))
    if len(runs) > 1:
        comparison = compare(runs, queries)
        comparison.to_csv(ARTIFACTS_DIR / "evaluation_comparison.csv", index=False)
        print(comparison.round(4).to_string(index=False))
    catalog_manifest = json.loads((CATALOG.parent / "dataset_manifest.json").read_text(encoding="utf-8"))
    (ARTIFACTS_DIR / "evaluation_manifest.json").write_text(json.dumps({
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_sha256": catalog_manifest["catalog_sha256"],
        "known_item_sha256": hashlib.sha256((EVALUATION_DIR / "known_item.jsonl").read_bytes()).hexdigest(),
        "queries": int(len(queries)),
        "top_k": TOP_K,
        "seed": SEED,
        "filters": "none",
        "statistical_test": "paired randomization (Fisher), 100,000 permutations, ranx.compare; p-values carry Monte Carlo error of about ±0.001",
        "diversity_vectors": RETRIEVER.model_name,
        "configs": {name: json.loads((RUNS_DIR / f"run_{name}.json").read_text(encoding="utf-8"))
                    for name in runs if (RUNS_DIR / f"run_{name}.json").exists()},
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
