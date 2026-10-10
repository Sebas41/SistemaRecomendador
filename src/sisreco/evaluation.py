"""Métricas para los juicios manuales de relevancia."""

from __future__ import annotations

import numpy as np


def precision_at_k(relevances: list[int] | np.ndarray, k: int = 5, threshold: int = 1) -> float:
    if k <= 0:
        raise ValueError("k debe ser positivo")
    values = np.asarray(relevances[:k], dtype=float)
    if len(values) == 0:
        return 0.0
    return float(np.sum(values >= threshold) / k)


def ndcg_at_k(relevances: list[int] | np.ndarray, k: int = 5) -> float:
    if k <= 0:
        raise ValueError("k debe ser positivo")
    values = np.asarray(relevances[:k], dtype=float)
    if len(values) == 0:
        return 0.0
    discounts = np.log2(np.arange(2, len(values) + 2))
    dcg = float(np.sum((np.power(2, values) - 1) / discounts))
    ideal = np.sort(np.asarray(relevances, dtype=float))[::-1][:k]
    ideal_dcg = float(np.sum((np.power(2, ideal) - 1) / np.log2(np.arange(2, len(ideal) + 2))))
    return dcg / ideal_dcg if ideal_dcg else 0.0
