"""Recuperación densa, reordenamiento y referencia TF-IDF para recomendar artículos."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .settings import (
    EMBEDDING_BATCH_SIZE,
    RERANKER,
    RETRIEVER,
    TOP_K,
    RerankerSpec,
    RetrieverSpec,
    TFIDF_IDS,
    TFIDF_MATRIX,
    TFIDF_VECTORIZER,
)


def _keywords_text(keywords: Any) -> str:
    if isinstance(keywords, (list, tuple, np.ndarray)):
        return ", ".join(str(value) for value in keywords if value)
    return "" if keywords is None or (isinstance(keywords, float) and pd.isna(keywords)) else str(keywords)


def article_text(row: pd.Series | dict[str, Any]) -> str:
    """Texto indexado: título, palabras clave, topic y resumen.

    Las palabras clave y el topic resumen el tema con términos que el resumen a veces
    no usa. El campo no se incluye: es una categoría amplia que sirve para filtrar,
    no para distinguir artículos del mismo campo.
    """
    topic = row.get("topic")
    parts = [
        row.get("title", ""),
        _keywords_text(row.get("keywords")),
        "" if topic is None or pd.isna(topic) else str(topic),
        row.get("abstract", ""),
    ]
    return ". ".join(str(part).strip().rstrip(".") for part in parts if str(part).strip()) + "."


def build_query(description: str, keywords: str = "") -> str:
    """Une la descripción del proyecto con las palabras clave opcionales del estudiante."""
    description, keywords = description.strip(), keywords.strip()
    return f"{description}. Palabras clave: {keywords}" if keywords else description


def _best_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _model_kwargs(device: str) -> dict[str, Any]:
    # fp16 reduce a la mitad la memoria de la GPU; en CPU se mantiene fp32 por precisión y soporte.
    if device == "cpu":
        return {}
    import torch

    return {"torch_dtype": torch.float16}


@lru_cache(maxsize=2)
def load_retriever(spec: RetrieverSpec = RETRIEVER):
    from sentence_transformers import SentenceTransformer

    device = _best_device()
    model = SentenceTransformer(spec.model_name, device=device, model_kwargs=_model_kwargs(device))
    model.max_seq_length = spec.max_seq_length
    return model


@lru_cache(maxsize=2)
def load_reranker(spec: RerankerSpec = RERANKER):
    from sentence_transformers import CrossEncoder

    device = _best_device()
    return CrossEncoder(spec.model_name, device=device, max_length=spec.max_length, model_kwargs=_model_kwargs(device))


def encode_documents(catalog: pd.DataFrame, spec: RetrieverSpec = RETRIEVER, model: Any | None = None,
                     batch_size: int = EMBEDDING_BATCH_SIZE, show_progress_bar: bool = True) -> np.ndarray:
    """Codifica el texto indexado de cada artículo en vectores normalizados."""
    model = model or load_retriever(spec)
    documents = [f"{spec.document_prefix}{article_text(row)}" for _, row in catalog.iterrows()]
    # Agrupar textos de longitud parecida reduce el relleno dentro de cada lote.
    order = np.argsort([len(text) for text in documents])[::-1]
    vectors = model.encode([documents[i] for i in order], batch_size=batch_size, show_progress_bar=show_progress_bar,
                           normalize_embeddings=True, convert_to_numpy=True)
    result = np.empty_like(vectors, dtype=np.float32)
    result[order] = vectors
    return result


def _truncated_documents(catalog: pd.DataFrame, spec: RetrieverSpec, model: Any) -> int:
    tokenizer = model.tokenizer
    documents = [f"{spec.document_prefix}{article_text(row)}" for _, row in catalog.iterrows()]
    lengths = [len(ids) for ids in tokenizer(documents, truncation=False)["input_ids"]]
    return int(sum(length > spec.max_seq_length for length in lengths))


def model_revision(model_name: str) -> str | None:
    """Commit del modelo descargado en la caché local de Hugging Face, para el manifiesto."""
    try:
        from huggingface_hub import snapshot_download

        return Path(snapshot_download(model_name, local_files_only=True)).name
    except Exception:  # noqa: BLE001 — sin caché local la revisión simplemente no se registra.
        return None


def _manifest_path(spec: RetrieverSpec) -> Path:
    return spec.vectors_path.with_suffix(".json")


def save_vectors(catalog: pd.DataFrame, vectors: np.ndarray, spec: RetrieverSpec = RETRIEVER, model: Any | None = None) -> None:
    if vectors.shape[0] != len(catalog):
        raise ValueError("El número de vectores debe coincidir con el catálogo.")
    spec.vectors_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = spec.vectors_path.with_suffix(".npy.tmp")
    with temporary.open("wb") as target:
        np.save(target, vectors.astype(np.float32))
    temporary.replace(spec.vectors_path)
    revision = model_revision(spec.model_name)
    truncated = _truncated_documents(catalog, spec, model) if model is not None else None
    _manifest_path(spec).write_text(json.dumps({
        "model": spec.model_name,
        "revision": revision,
        "device": str(getattr(model, "device", "")),
        "max_seq_length": spec.max_seq_length,
        "query_prefix": spec.query_prefix,
        "document_prefix": spec.document_prefix,
        "indexed_text": "title. keywords. topic. abstract",
        "normalized": True,
        "shape": list(vectors.shape),
        "truncated_documents": truncated,
        "truncated_fraction": truncated / len(catalog) if truncated is not None else None,
        "catalog_ids": catalog["id"].tolist(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def load_vectors(catalog: pd.DataFrame, spec: RetrieverSpec = RETRIEVER) -> np.ndarray:
    manifest_path = _manifest_path(spec)
    if not spec.vectors_path.exists() or not manifest_path.exists():
        raise FileNotFoundError("Faltan los vectores. Ejecuta: python scripts/build_index.py")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("catalog_ids") != catalog["id"].tolist():
        raise ValueError("El índice semántico no coincide con el catálogo actual. Regenera el índice.")
    return np.load(spec.vectors_path, mmap_mode="r")


def encode_query(query: str, spec: RetrieverSpec, model: Any) -> np.ndarray:
    vector = model.encode([f"{spec.query_prefix}{query}"], normalize_embeddings=True, convert_to_numpy=True,
                          show_progress_bar=False)
    return np.asarray(vector, dtype=np.float32).reshape(-1)


def dense_scores(vectors: np.ndarray, query_vector: np.ndarray, positions: np.ndarray | None = None) -> np.ndarray:
    """Similitud coseno exacta; los vectores ya están normalizados, así que basta el producto punto."""
    selected = vectors if positions is None else vectors[positions]
    return np.asarray(selected @ query_vector, dtype=np.float32).reshape(-1)


def rerank_scores(query: str, passages: list[str], reranker: Any, batch_size: int = 16) -> np.ndarray:
    pairs = [(query, passage) for passage in passages]
    return np.asarray(reranker.predict(pairs, batch_size=batch_size, show_progress_bar=False), dtype=np.float32).reshape(-1)


def build_tfidf_index(catalog: pd.DataFrame) -> None:
    """Crea la referencia léxica en inglés con unigramas y bigramas."""
    english = catalog.loc[catalog["language"].eq("en")].copy()
    if english.empty:
        raise ValueError("El catálogo no contiene artículos en inglés para TF-IDF.")
    vectorizer = TfidfVectorizer(stop_words=list(ENGLISH_STOP_WORDS), ngram_range=(1, 2), max_features=30_000,
                                 sublinear_tf=True, dtype=np.float32)
    matrix = vectorizer.fit_transform(english.apply(article_text, axis=1).tolist())
    TFIDF_VECTORIZER.parent.mkdir(parents=True, exist_ok=True)
    import joblib
    from scipy.sparse import save_npz

    joblib.dump(vectorizer, TFIDF_VECTORIZER)
    save_npz(TFIDF_MATRIX, matrix)
    TFIDF_IDS.write_text(json.dumps(english["id"].tolist()), encoding="utf-8")


def _semantic_evidence(query: str, abstract: str, spec: RetrieverSpec, model: Any) -> str:
    """Oración del resumen más cercana a la consulta, para que el estudiante vea por qué se recomienda."""
    sentences = [part.strip() for part in abstract.replace("? ", "?\n").replace("! ", "!\n").replace(". ", ".\n").splitlines()
                 if len(part.split()) >= 8]
    if not sentences:
        return ""
    query_vector = encode_query(query, spec, model)
    sentence_vectors = model.encode([f"{spec.document_prefix}{sentence}" for sentence in sentences],
                                    normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    return sentences[int(np.argmax(np.asarray(sentence_vectors) @ query_vector))]


def _filter(catalog: pd.DataFrame, fields: list[str] | None, min_year: int | None, max_year: int | None,
            language: str) -> pd.DataFrame:
    candidates = catalog
    if fields:
        candidates = candidates[candidates["field"].isin(fields)]
    if min_year is not None:
        candidates = candidates[candidates["year"] >= min_year]
    if max_year is not None:
        candidates = candidates[candidates["year"] <= max_year]
    if language in {"en", "es"}:
        candidates = candidates[candidates["language"].eq(language)]
    return candidates


def recommend(catalog: pd.DataFrame, query: str, *, engine: str = "semantico", top_k: int = TOP_K,
              vectors: np.ndarray | None = None, retriever: Any | None = None, reranker: Any | None = None,
              retriever_spec: RetrieverSpec = RETRIEVER, reranker_spec: RerankerSpec | None = RERANKER,
              fields: list[str] | None = None, min_year: int | None = None, max_year: int | None = None,
              language: str = "Todos", generate_evidence: bool = True) -> pd.DataFrame:
    """Devuelve los top_k artículos más afines. Los puntajes ordenan; no son probabilidades ni miden calidad."""
    if len(query.split()) < 5:
        raise ValueError("Describe el proyecto con al menos cinco palabras.")
    if top_k <= 0:
        raise ValueError("La cantidad de resultados debe ser positiva.")
    if engine not in {"semantico", "tfidf"}:
        raise ValueError("Motor desconocido: selecciona semántico o TF-IDF.")
    candidates = _filter(catalog, fields, min_year, max_year, language)
    if engine == "tfidf":
        return _recommend_tfidf(candidates, query, top_k)
    if candidates.empty:
        return candidates.assign(score=pd.Series(dtype="float32"), retrieval_score=pd.Series(dtype="float32"),
                                 evidence=pd.Series(dtype="object"))

    retriever = retriever or load_retriever(retriever_spec)
    vectors = vectors if vectors is not None else load_vectors(catalog, retriever_spec)
    if vectors.shape[0] != len(catalog):
        raise ValueError("Los vectores no corresponden al catálogo.")
    positions = np.flatnonzero(catalog.index.isin(candidates.index)) if len(candidates) < len(catalog) else None
    scores = dense_scores(vectors, encode_query(query, retriever_spec, retriever), positions)
    shortlist = reranker_spec.candidates if reranker_spec is not None else top_k
    keep = min(max(top_k, shortlist), len(scores))
    best = np.argpartition(-scores, keep - 1)[:keep]
    best = best[np.argsort(-scores[best], kind="stable")]
    results = candidates.iloc[best].copy()
    results["retrieval_score"] = scores[best]
    results["score"] = results["retrieval_score"]
    if reranker_spec is not None:
        reranker = reranker or load_reranker(reranker_spec)
        results["score"] = rerank_scores(query, [article_text(row) for _, row in results.iterrows()], reranker)
        results = results.sort_values("score", ascending=False, kind="stable")
    # Top-k fijo: sin umbral, porque los puntajes del reordenador no están calibrados entre
    # consultas y un corte fijo deja listas vacías o incompletas.
    results = results.head(top_k).reset_index(drop=True)
    if generate_evidence:
        results["evidence"] = [_semantic_evidence(query, abstract, retriever_spec, retriever)
                               for abstract in results["abstract"].tolist()]
    else:
        results["evidence"] = ""
    return results


def _recommend_tfidf(candidates: pd.DataFrame, query: str, top_k: int) -> pd.DataFrame:
    import joblib
    from scipy.sparse import load_npz

    empty = candidates.iloc[0:0].assign(score=pd.Series(dtype="float32"), evidence=pd.Series(dtype="object"))
    if not all(path.exists() for path in (TFIDF_VECTORIZER, TFIDF_MATRIX, TFIDF_IDS)):
        raise FileNotFoundError("Falta el índice TF-IDF. Ejecuta: python scripts/build_index.py")
    vectorizer = joblib.load(TFIDF_VECTORIZER)
    matrix = load_npz(TFIDF_MATRIX)
    indexed_positions = {value: i for i, value in enumerate(json.loads(TFIDF_IDS.read_text(encoding="utf-8")))}
    candidates = candidates[candidates["language"].eq("en") & candidates["id"].isin(indexed_positions)]
    query_vector = vectorizer.transform([query])
    if candidates.empty or query_vector.nnz == 0:
        return empty
    scores = cosine_similarity(query_vector, matrix[[indexed_positions[value] for value in candidates["id"]]]).ravel()
    results = candidates.assign(score=scores.astype(np.float32))
    results = results.sort_values("score", ascending=False, kind="stable").head(top_k).reset_index(drop=True)
    results["evidence"] = ""
    return results
