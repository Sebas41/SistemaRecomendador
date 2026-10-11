"""Indexación semántica bilingüe y recomendación basada en contenido."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .settings import EMBEDDINGS, EMBEDDINGS_MANIFEST, EMBEDDING_BATCH_SIZE, MODEL_NAME, MODEL_REVISION, TFIDF_IDS, TFIDF_MATRIX, TFIDF_VECTORIZER


def article_text(row: pd.Series | dict[str, Any]) -> str:
    return f"{row.get('title', '')}. {row.get('abstract', '')}".strip()


def _load_sentence_model(model_name: str = MODEL_NAME):
    from sentence_transformers import SentenceTransformer
    import torch

    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    return SentenceTransformer(model_name, device=device)


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


def recommend(catalog: pd.DataFrame, query: str, *, engine: str = "semantico", top_k: int = 5, embeddings: np.ndarray | None = None, model: Any | None = None, fields: list[str] | None = None, min_year: int | None = None, max_year: int | None = None, language: str = "Todos", generate_evidence: bool = True) -> pd.DataFrame:
    """Ordena candidatos por coseno; la puntuación no es una probabilidad."""
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
        return candidates.assign(score=pd.Series(dtype="float32"), evidence=pd.Series(dtype="object"))

    if engine == "semantico":
        model = model or _load_sentence_model()
        vectors = embeddings if embeddings is not None else load_embeddings(catalog)
        if vectors.shape[0] != len(catalog):
            raise ValueError("Los vectores no corresponden al catálogo.")
        query_vector = model.encode([f"query: {query}"], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
        positions = catalog.reset_index(drop=True).reset_index(names="_position").set_index("id")["_position"]
        candidate_positions = positions.loc[candidates["id"].tolist()].to_numpy()
        scores = np.asarray(vectors[candidate_positions] @ np.asarray(query_vector).reshape(-1)).reshape(-1)
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
    candidates["score"] = scores.astype(np.float32)
    candidates = candidates.sort_values(["score", "year"], ascending=[False, False]).head(top_k).reset_index(drop=True)
    if engine == "semantico" and generate_evidence:
        model = model or _load_sentence_model()
        candidates["evidence"] = [_semantic_evidence(query, abstract, model) for abstract in candidates["abstract"].tolist()]
    else:
        candidates["evidence"] = ""
    return candidates


def recommend_pair(query: str, catalog: pd.DataFrame, top_k: int = 5, embeddings: np.ndarray | None = None, model: Any | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compara ambos motores usando los mismos candidatos en inglés."""
    semantic = recommend(catalog, query, engine="semantico", top_k=top_k, embeddings=embeddings, model=model, language="en")
    lexical = recommend(catalog, query, engine="tfidf", top_k=top_k, language="en")
    return semantic, lexical
