#!/usr/bin/env python3
"""Calcula pertinencia humana y comparaciones pareadas para la evaluación MMR."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sisreco.mmr_evaluation import score_mmr
from sisreco.settings import ARTIFACTS_DIR

MMR_DIR = ARTIFACTS_DIR / "mmr"


def load_ratings(path: Path, key: pd.DataFrame) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Falta la hoja calificada: {path}")
    ratings = pd.read_csv(path)
    required = {"profile_id", "article_id", "relevance"}
    if not required.issubset(ratings.columns):
        raise SystemExit(f"La hoja debe incluir estas columnas: {', '.join(sorted(required))}")
    if ratings.duplicated(["profile_id", "article_id"]).any():
        raise SystemExit("Cada artículo se debe calificar una sola vez por perfil.")
    try:
        numeric = pd.to_numeric(ratings["relevance"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise SystemExit("Completa relevance solo con 0, 1 o 2.") from exc
    if numeric.isna().any() or not numeric.isin([0, 1, 2]).all():
        raise SystemExit("Completa relevance solo con 0, 1 o 2.")
    ratings["relevance"] = numeric.astype(int)

    expected = key[["profile_id", "article_id"]].drop_duplicates()
    comparison = expected.merge(ratings[["profile_id", "article_id"]], how="outer", indicator=True)
    missing = int(comparison["_merge"].eq("left_only").sum())
    unexpected = int(comparison["_merge"].eq("right_only").sum())
    if missing or unexpected:
        raise SystemExit(f"La hoja no coincide con la llave: faltan {missing} juicios y sobran {unexpected}.")
    return ratings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings", type=Path, default=MMR_DIR / "human_ratings.csv",
                        help="Hoja completada después de la calificación ciega.")
    parser.add_argument("--permutations", type=int, default=100_000,
                        help="Permutaciones para las comparaciones pareadas (predeterminado: 100000).")
    args = parser.parse_args()
    if args.permutations <= 0:
        raise SystemExit("--permutations debe ser positivo.")

    rankings_path = MMR_DIR / "rankings_key.csv"
    diversity_path = MMR_DIR / "diversity.csv"
    key_path = MMR_DIR / "human_ratings_key.csv"
    for path in (rankings_path, diversity_path, key_path):
        if not path.exists():
            raise SystemExit(f"Falta {path.name}. Ejecuta primero: python scripts/evaluate_mmr.py")

    rankings = pd.read_csv(rankings_path)
    diversity = pd.read_csv(diversity_path)
    key = pd.read_csv(key_path)
    ratings = load_ratings(args.ratings, key)
    per_query, summary, comparisons = score_mmr(
        rankings, diversity, ratings, permutations=args.permutations
    )
    per_query.to_csv(MMR_DIR / "human_metrics_per_query.csv", index=False)
    summary.to_csv(MMR_DIR / "human_metrics_summary.csv", index=False)
    comparisons.to_csv(MMR_DIR / "human_metrics_comparison.csv", index=False)
    query_count = len(per_query[["profile_id", "query_language"]].drop_duplicates())
    print(f"Juicios: {len(ratings)} · consultas perfil/idioma: {query_count}")
    print("\nPromedios por lambda (las filas 'todos' agrupan ambos idiomas):")
    print(summary.round(3).to_string(index=False))
    print("\nDiferencias pareadas (lambda candidata menos lambda de referencia):")
    print(comparisons.round(4).to_string(index=False))
    print(f"\nResultados guardados en {MMR_DIR}")


if __name__ == "__main__":
    main()
