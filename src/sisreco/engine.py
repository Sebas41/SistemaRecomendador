"""Indexación semántica bilingüe y recomendación basada en contenido."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .settings import (
    EMBEDDINGS,
    EMBEDDINGS_MANIFEST,
    EMBEDDING_BATCH_SIZE,
    MIN_RERANK_SCORE,
    MODEL_NAME,
    MODEL_REVISION,
    RERANKER_MODEL_NAME,
    RERANK_CANDIDATES,
    TFIDF_IDS,
    TFIDF_MATRIX,
    TFIDF_VECTORIZER,
)


def article_text(row: pd.Series | dict[str, Any]) -> str:
    return f"{row.get('title', '')}. {row.get('abstract', '')}".strip()


def _best_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@lru_cache(maxsize=1)
def _load_sentence_model(model_name: str = MODEL_NAME):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=_best_device())


@lru_cache(maxsize=1)
def _load_reranker(model_name: str = RERANKER_MODEL_NAME):
    """Carga el modelo multilingüe que revisa la lista corta de candidatos."""
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name, device=_best_device(), max_length=384)


def encode_documents(catalog: pd.DataFrame, model: Any | None = None, batch_size: int = EMBEDDING_BATCH_SIZE, show_progress_bar: bool = True) -> np.ndarray:
    """Codifica título y resumen localmente, con el prefijo passage del modelo."""
    model = model or _load_sentence_model()
    documents = [f"passage: {article_text(row)}" for _, row in catalog.iterrows()]
    vectors = model.encode(documents, batch_size=batch_size, show_progress_bar=show_progress_bar, normalize_embeddings=True, convert_to_numpy=True)
    return np.asarray(vectors, dtype=np.float32)


def _model_provenance(model: Any | None, catalog: pd.DataFrame) -> dict[str, Any]:
    truncated = None
    revision = MODEL_REVISION
    if model is not None:
        tokenizer = getattr(model, "tokenizer", None)
        if tokenizer is not None:
            documents = [f"passage: {article_text(row)}" for _, row in catalog.iterrows()]
            truncated = 0
            original_limit = tokenizer.model_max_length
            try:
                tokenizer.model_max_length = 10**9
                for start in range(0, len(documents), EMBEDDING_BATCH_SIZE):
                    batch = tokenizer(
                        documents[start:start + EMBEDDING_BATCH_SIZE],
                        add_special_tokens=True,
                        truncation=False,
                        padding=False,
                    )["input_ids"]
                    truncated += sum(len(tokens) > 512 for tokens in batch)
            finally:
                tokenizer.model_max_length = original_limit
        for module in getattr(model, "_modules", {}).values():
            auto_model = getattr(module, "auto_model", None)
            commit = getattr(getattr(auto_model, "config", None), "_commit_hash", None)
            if commit:
                revision = commit
                break
    if revision == MODEL_REVISION:
        try:
            from huggingface_hub import try_to_load_from_cache

            cached_config = try_to_load_from_cache(MODEL_NAME, "config.json")
            if isinstance(cached_config, str):
                for parent in Path(cached_config).parents:
                    if parent.parent.name == "snapshots":
                        revision = parent.name
                        break
        except (ImportError, OSError):
            pass
    return {"model_revision": revision, "truncated_documents": truncated}


def save_embeddings(catalog: pd.DataFrame, embeddings: np.ndarray, model: Any | None = None) -> None:
    EMBEDDINGS.parent.mkdir(parents=True, exist_ok=True)
    if embeddings.shape[0] != len(catalog):
        raise ValueError("El número de vectores debe coincidir con el catálogo.")
    vector_tmp = EMBEDDINGS.with_suffix(".npy.tmp")
    with vector_tmp.open("wb") as target:
        np.save(target, embeddings)
    vector_tmp.replace(EMBEDDINGS)
    provenance = _model_provenance(model, catalog)
    manifest_tmp = EMBEDDINGS_MANIFEST.with_suffix(".json.tmp")
    manifest_tmp.write_text(json.dumps({
        "model": MODEL_NAME,
        "revision": provenance["model_revision"],
        "device": str(getattr(model, "device", "cpu")),
        "normalized": True,
        "shape": list(embeddings.shape),
        "catalog_ids": catalog["id"].tolist(),
        "prefix_document": "passage: ",
        "max_tokens": 512,
        "long_document_policy": "The model truncates text beyond 512 tokens.",
        "truncated_documents": provenance["truncated_documents"],
        "truncated_fraction": (
            provenance["truncated_documents"] / len(catalog)
            if provenance["truncated_documents"] is not None and len(catalog) else None
        ),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_tmp.replace(EMBEDDINGS_MANIFEST)


def load_embeddings(catalog: pd.DataFrame) -> np.ndarray:
    if not EMBEDDINGS.exists() or not EMBEDDINGS_MANIFEST.exists():
        raise FileNotFoundError("Faltan los vectores. Ejecuta: python scripts/build_index.py")
    manifest = json.loads(EMBEDDINGS_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("catalog_ids") != catalog["id"].tolist():
        raise ValueError("El índice semántico no coincide con el catálogo actual. Regenera el índice.")
    vectors = np.load(EMBEDDINGS, mmap_mode="r")
    if vectors.shape[0] != len(catalog):
        raise ValueError("La cantidad de vectores no coincide con el catálogo.")
    return vectors


def build_tfidf_index(catalog: pd.DataFrame) -> None:
    """Crea la referencia inglesa con unigramas y bigramas."""
    english = catalog.loc[catalog["language"].eq("en")].copy()
    if english.empty:
        raise ValueError("El catálogo no contiene artículos en inglés para TF-IDF.")
    vectorizer = TfidfVectorizer(stop_words=list(ENGLISH_STOP_WORDS), ngram_range=(1, 2), max_features=30_000, sublinear_tf=True, dtype=np.float32)
    matrix = vectorizer.fit_transform(english.apply(article_text, axis=1).tolist())
    TFIDF_VECTORIZER.parent.mkdir(parents=True, exist_ok=True)
    import joblib
    from scipy.sparse import save_npz

    joblib.dump(vectorizer, TFIDF_VECTORIZER)
    save_npz(TFIDF_MATRIX, matrix)
    TFIDF_IDS.write_text(json.dumps(english["id"].tolist()), encoding="utf-8")


def _semantic_evidence(query: str, abstract: str, model: Any) -> str:
    sentences = [part.strip() for part in abstract.replace("? ", "?\n").replace("! ", "!\n").replace(". ", ".\n").splitlines() if len(part.split()) >= 8]
    if not sentences:
        return ""
    query_vector = model.encode(f"query: {query}", normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    sentence_vectors = model.encode([f"passage: {sentence}" for sentence in sentences], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    scores = np.asarray(sentence_vectors) @ np.asarray(query_vector).reshape(-1)
    return sentences[int(np.argmax(scores))]


def _reranker_passage(article: pd.Series) -> str:
    keywords = article.get("keywords", [])
    if isinstance(keywords, (list, tuple, np.ndarray)):
        keyword_text = ", ".join(str(value) for value in keywords if value)
    else:
        keyword_text = str(keywords or "")
    topic = article.get("topic")
    topic_text = "" if topic is None or pd.isna(topic) else str(topic)
    return (
        f"Title: {article.get('title', '')}. "
        f"Field: {article.get('field', '')}. Topic: {topic_text}. "
        f"Keywords: {keyword_text}. "
        f"Abstract: {article.get('abstract', '')}"
    )


def _empty_results(candidates: pd.DataFrame, *, semantic: bool = False) -> pd.DataFrame:
    result = candidates.copy()
    result["score"] = pd.Series(dtype="float32")
    if semantic:
        result["semantic_score"] = pd.Series(dtype="float32")
    result["evidence"] = pd.Series(dtype="object")
    return result


_QUERY_CONCEPTS = {
    "ai_agents": (
        "agentes de IA",
        re.compile(
            r"\b(?:agentes?\s+de\s+(?:inteligencia\s+artificial|ia)|"
            r"(?:artificial\s+intelligence|ai)\s+agents?|agentic\s+ai|"
            r"autonomous\s+(?:ai\s+)?agents?)\b"
        ),
    ),
    "enterprise_architecture": (
        "arquitectura empresarial",
        re.compile(
            r"\b(?:arquitectura\s+empresarial|arquitectura\s+de\s+empresa|"
            r"enterprise\s+architecture|enterprise\s+architect(?:ure)?|"
            r"business\s+architecture)\b"
        ),
    ),
}


def _normalize_concept_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _query_concepts(query: str) -> list[str]:
    normalized = _normalize_concept_text(query)
    return [key for key, (_, pattern) in _QUERY_CONCEPTS.items() if pattern.search(normalized)]


def _article_concepts(article: pd.Series, concept_ids: list[str]) -> list[str]:
    parts = [article.get("title", ""), article.get("abstract", ""), article.get("topic", "")]
    keywords = article.get("keywords", [])
    if isinstance(keywords, (list, tuple, np.ndarray)):
        parts.extend(keywords)
    else:
        parts.append(keywords)
    text = _normalize_concept_text(" ".join(str(part) for part in parts if isinstance(part, str)))
    return [key for key in concept_ids if _QUERY_CONCEPTS[key][1].search(text)]


def recommend(catalog: pd.DataFrame, query: str, *, engine: str = "semantico", top_k: int = 5, embeddings: np.ndarray | None = None, model: Any | None = None, reranker: Any | None = None, fields: list[str] | None = None, min_year: int | None = None, max_year: int | None = None, language: str = "Todos", generate_evidence: bool = True) -> pd.DataFrame:
    """Recupera candidatos y los ordena por relevancia; los puntajes no son probabilidades."""
    if len(query.split()) < 5:
        raise ValueError("Describe el proyecto con al menos cinco palabras.")
    if top_k <= 0:
        raise ValueError("La cantidad de resultados debe ser positiva.")
    if engine not in {"semantico", "tfidf"}:
        raise ValueError("Motor desconocido: selecciona semántico o TF-IDF.")
    candidates = catalog.copy()
    if fields:
        candidates = candidates[candidates["field"].isin(fields)]
    if min_year is not None:
        candidates = candidates[candidates["year"] >= min_year]
    if max_year is not None:
        candidates = candidates[candidates["year"] <= max_year]
    if language in {"en", "es"}:
        candidates = candidates[candidates["language"].eq(language)]
    if candidates.empty:
        return _empty_results(candidates, semantic=engine == "semantico")

    if engine == "semantico":
        model = model or _load_sentence_model()
        vectors = embeddings if embeddings is not None else load_embeddings(catalog)
        if vectors.shape[0] != len(catalog):
            raise ValueError("Los vectores no corresponden al catálogo.")
        query_vector = model.encode([f"query: {query}"], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
        positions = catalog.reset_index(drop=True).reset_index(names="_position").set_index("id")["_position"]
        candidate_positions = positions.loc[candidates["id"].tolist()].to_numpy()
        semantic_scores = np.asarray(
            vectors[candidate_positions] @ np.asarray(query_vector).reshape(-1)
        ).reshape(-1)
        candidates = candidates.copy()
        candidates["semantic_score"] = semantic_scores.astype(np.float32)
        concept_ids = _query_concepts(query)
        if len(concept_ids) > 1:
            matched = candidates.apply(
                lambda article: _article_concepts(article, concept_ids), axis=1
            )
            direct = matched.map(lambda article_concepts: len(article_concepts) == len(concept_ids))
            if direct.any():
                candidates = candidates.loc[direct].copy()
                matched = matched.loc[direct]
                candidates["match_scope"] = "direct"
            else:
                partial = matched.map(bool)
                if not partial.any():
                    empty = _empty_results(candidates.iloc[0:0], semantic=True)
                    empty["match_scope"] = pd.Series(dtype="object")
                    empty.attrs["match_scope"] = "none"
                    return empty
                candidates = candidates.loc[partial].copy()
                matched = matched.loc[partial]
                candidates["match_scope"] = "partial"
            candidates["matched_concepts"] = matched.map(
                lambda article_concepts: [
                    _QUERY_CONCEPTS[concept_id][0] for concept_id in article_concepts
                ]
            )
        candidates = candidates.sort_values(
            ["semantic_score", "year"], ascending=[False, False]
        ).head(max(top_k, RERANK_CANDIDATES)).copy()

        reranker = reranker or _load_reranker()
        pairs = [
            (query, _reranker_passage(article))
            for _, article in candidates.iterrows()
        ]
        scores = np.asarray(
            reranker.predict(pairs, batch_size=32, show_progress_bar=False)
        ).reshape(-1)
        candidates["score"] = scores.astype(np.float32)
        # A recognized multi-concept query has an explicit coverage check. Keep
        # its direct or clearly labelled partial matches even when the raw
        # cross-encoder score is negative; those scores are not calibrated.
        if len(concept_ids) <= 1:
            candidates = candidates[candidates["score"] >= MIN_RERANK_SCORE]
        if candidates.empty:
            return _empty_results(candidates, semantic=True)
    else:
        import joblib
        from scipy.sparse import load_npz

        if not all(path.exists() for path in (TFIDF_VECTORIZER, TFIDF_MATRIX, TFIDF_IDS)):
            raise FileNotFoundError("Falta el índice TF-IDF. Ejecuta: python scripts/build_index.py")
        vectorizer = joblib.load(TFIDF_VECTORIZER)
        matrix = load_npz(TFIDF_MATRIX)
        indexed_ids = json.loads(TFIDF_IDS.read_text(encoding="utf-8"))
        indexed_positions = {value: i for i, value in enumerate(indexed_ids)}
        candidates = candidates[candidates["language"].eq("en")]
        candidates = candidates[candidates["id"].isin(indexed_positions)]
        if candidates.empty:
            return candidates.assign(score=pd.Series(dtype="float32"), evidence=pd.Series(dtype="object"))
        query_vector = vectorizer.transform([query])
        if query_vector.nnz == 0:
            return candidates.assign(score=pd.Series(dtype="float32"), evidence=pd.Series(dtype="object"))
        positions = [indexed_positions[value] for value in candidates["id"]]
        scores = cosine_similarity(query_vector, matrix[positions]).ravel()

    candidates = candidates.copy()
    if engine == "tfidf":
        candidates["score"] = scores.astype(np.float32)
    candidates = candidates.sort_values(["score", "year"], ascending=[False, False])
    if engine == "semantico" and candidates.get("match_scope", pd.Series(dtype="object")).eq("partial").any():
        # If no article covers every detected concept, distribute the short
        # list across the concepts instead of letting one partial match type
        # crowd out the others.
        selected_indices: list[Any] = []
        concept_ids = _query_concepts(query)
        ranked = candidates.reset_index(drop=True)
        for offset in range(top_k):
            concept_id = concept_ids[offset % len(concept_ids)]
            label = _QUERY_CONCEPTS[concept_id][0]
            for index, row in ranked.iterrows():
                if index not in selected_indices and label in row["matched_concepts"]:
                    selected_indices.append(index)
                    break
        selected_indices.extend(index for index in ranked.index if index not in selected_indices)
        candidates = ranked.loc[selected_indices]
    candidates = candidates.head(top_k).reset_index(drop=True)
    if engine == "semantico" and generate_evidence:
        model = model or _load_sentence_model()
        candidates["evidence"] = [_semantic_evidence(query, abstract, model) for abstract in candidates["abstract"].tolist()]
    else:
        candidates["evidence"] = ""
    return candidates


def recommend_pair(query: str, catalog: pd.DataFrame, top_k: int = 5, embeddings: np.ndarray | None = None, model: Any | None = None, reranker: Any | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compara ambos motores usando los mismos candidatos en inglés."""
    semantic = recommend(catalog, query, engine="semantico", top_k=top_k, embeddings=embeddings, model=model, reranker=reranker, language="en")
    lexical = recommend(catalog, query, engine="tfidf", top_k=top_k, language="en")
    return semantic, lexical
