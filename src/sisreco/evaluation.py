"""Métricas de ordenamiento para juicios de relevancia y consultas de ítem conocido."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np


def _check_k(k: int) -> None:
    if k <= 0:
        raise ValueError("k debe ser positivo")


def precision_at_k(relevances: Sequence[int] | np.ndarray, k: int = 5, threshold: int = 1) -> float:
    """Fracción de los k primeros puestos con relevancia ≥ threshold; un puesto vacío cuenta como no pertinente."""
    _check_k(k)
    values = np.asarray(relevances[:k], dtype=float)
    return float(np.sum(values >= threshold) / k)


def dcg(relevances: Sequence[float] | np.ndarray, k: int) -> float:
    """DCG con ganancia exponencial (2^rel − 1), equivalente a `ndcg_burges` de ranx.

    Con juicios 0/1/2, la ganancia exponencial vale 3 para un artículo directamente
    pertinente y 1 para uno parcial: premia más poner arriba lo que sí responde al proyecto.
    """
    values = np.asarray(relevances[:k], dtype=float)
    if values.size == 0:
        return 0.0
    discounts = np.log2(np.arange(2, values.size + 2))
    return float(np.sum((np.power(2, values) - 1) / discounts))


def ndcg_at_k(ranked_ids: Sequence[str], judgments: Mapping[str, int], k: int = 5) -> float:
    """nDCG@k de una lista ordenada frente a todos los juicios disponibles para la consulta.

    El DCG ideal ordena todos los artículos juzgados para la consulta, no solo los que
    devolvió la lista evaluada: así una configuración que no recupera los artículos más
    pertinentes no puede obtener la nota máxima.
    """
    _check_k(k)
    gains = [judgments.get(item, 0) for item in ranked_ids[:k]]
    ideal = dcg(sorted(judgments.values(), reverse=True), k)
    return dcg(gains, k) / ideal if ideal else 0.0


def reciprocal_rank(ranked_ids: Sequence[str], relevant: str | set[str], k: int = 10) -> float:
    """1/posición del primer artículo pertinente dentro del top k; 0 si no aparece."""
    _check_k(k)
    relevant = {relevant} if isinstance(relevant, str) else relevant
    for position, item in enumerate(ranked_ids[:k], start=1):
        if item in relevant:
            return 1.0 / position
    return 0.0


def recall_at_k(ranked_ids: Sequence[str], relevant: str | set[str], k: int = 10) -> float:
    """Fracción de los artículos pertinentes que aparece en el top k."""
    _check_k(k)
    relevant = {relevant} if isinstance(relevant, str) else relevant
    if not relevant:
        return 0.0
    return len(relevant & set(ranked_ids[:k])) / len(relevant)


def intra_list_diversity(vectors: np.ndarray) -> float:
    """ILD: 1 − coseno medio entre todos los pares de la lista; los vectores deben estar normalizados."""
    vectors = np.asarray(vectors, dtype=np.float64)
    count = len(vectors)
    if count < 2:
        return 0.0
    similarities = vectors @ vectors.T
    upper = similarities[np.triu_indices(count, k=1)]
    return float(1.0 - upper.mean())
