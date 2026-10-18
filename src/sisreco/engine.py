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
    HYBRID_MANIFEST,
    HYBRID_MATRIX,
    HYBRID_MAX_FEATURES,
    HYBRID_RRF_K,
    HYBRID_VECTORIZER,
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


def _lexical_normalize(value: Any) -> str:
    """Normaliza texto para el índice léxico multilingüe sin traducirlo."""
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", text).strip()


def hybrid_text(row: pd.Series | dict[str, Any]) -> str:
    """Da más peso al título y conserva resumen y palabras clave disponibles."""
    keywords = row.get("keywords", [])
    if isinstance(keywords, (list, tuple, np.ndarray)):
        keywords = " ".join(str(value) for value in keywords if value)
    return _lexical_normalize(
        f"{row.get('title', '')} {row.get('title', '')} "
        f"{row.get('abstract', '')} {keywords}"
    )


def _best_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@lru_cache(maxsize=1)
def _load_sentence_model(model_name: str = MODEL_NAME, *, local_files_only: bool = False):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=_best_device(), local_files_only=local_files_only)


@lru_cache(maxsize=1)
def _load_reranker(model_name: str = RERANKER_MODEL_NAME, *, local_files_only: bool = False):
    """Carga el modelo multilingüe que revisa la lista corta de candidatos."""
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name, device=_best_device(), max_length=384, local_files_only=local_files_only)


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


def build_hybrid_index(catalog: pd.DataFrame) -> None:
    """Crea el índice léxico bilingüe usado por la recuperación combinada."""
    if catalog.empty:
        raise ValueError("No se puede indexar un catálogo vacío.")
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2), max_features=HYBRID_MAX_FEATURES, min_df=2,
        max_df=0.95, sublinear_tf=True, dtype=np.float32,
    )
    matrix = vectorizer.fit_transform(catalog.apply(hybrid_text, axis=1).tolist())
    HYBRID_VECTORIZER.parent.mkdir(parents=True, exist_ok=True)
    import joblib
    from scipy.sparse import save_npz

    joblib.dump(vectorizer, HYBRID_VECTORIZER)
    save_npz(HYBRID_MATRIX, matrix)
    HYBRID_MANIFEST.write_text(json.dumps({
        "catalog_ids": catalog["id"].tolist(), "ngram_range": [1, 2],
        "max_features": HYBRID_MAX_FEATURES, "min_df": 2, "max_df": 0.95,
        "sublinear_tf": True, "normalization": "casefold_and_strip_accents",
        "document": "title twice, abstract, keywords",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def load_hybrid_index(catalog: pd.DataFrame):
    """Carga el índice léxico y rechaza artefactos de otro catálogo."""
    if not all(path.exists() for path in (HYBRID_VECTORIZER, HYBRID_MATRIX, HYBRID_MANIFEST)):
        raise FileNotFoundError("Falta el índice híbrido. Ejecuta: python scripts/build_index.py --hybrid-only")
    import joblib
    from scipy.sparse import load_npz

    manifest = json.loads(HYBRID_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("catalog_ids") != catalog["id"].tolist():
        raise ValueError("El índice híbrido no coincide con el catálogo actual. Regenera el índice.")
    matrix = load_npz(HYBRID_MATRIX)
    if matrix.shape[0] != len(catalog):
        raise ValueError("La cantidad de filas del índice híbrido no coincide con el catálogo.")
    return joblib.load(HYBRID_VECTORIZER), matrix, manifest


def reciprocal_rank_fusion(rankings: list[list[str]], *, k: int = HYBRID_RRF_K,
                           weights: list[float] | None = None) -> dict[str, float]:
    """Fusiona rankings por posición; conserva el mejor resultado en duplicados."""
    if k <= 0:
        raise ValueError("La constante RRF debe ser positiva.")
    weights = weights or [1.0] * len(rankings)
    if len(weights) != len(rankings) or any(weight < 0 for weight in weights):
        raise ValueError("Los pesos RRF deben ser no negativos y corresponder a cada ranking.")
    scores: dict[str, float] = {}
    for ranking, weight in zip(rankings, weights):
        seen: set[str] = set()
        for rank, identifier in enumerate(ranking, start=1):
            if identifier in seen:
                continue
            seen.add(identifier)
            scores[identifier] = scores.get(identifier, 0.0) + weight / (k + rank)
    return scores


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
    result = candidates.iloc[0:0].copy()
    result["score"] = pd.Series(dtype="float32")
    if semantic:
        result["semantic_score"] = pd.Series(dtype="float32")
    result["evidence"] = pd.Series(dtype="object")
    return result


def _filter_catalog(catalog: pd.DataFrame, *, fields: list[str] | None = None,
                    min_year: int | None = None, max_year: int | None = None,
                    language: str = "Todos") -> pd.DataFrame:
    if min_year is not None and max_year is not None and min_year > max_year:
        raise ValueError("El año inicial no puede ser posterior al año final.")
    if language not in {"Todos", "en", "es"}:
        raise ValueError("Idioma desconocido: selecciona Todos, en o es.")
    mask = np.ones(len(catalog), dtype=bool)
    if fields:
        mask &= catalog["field"].isin(fields).to_numpy()
    if min_year is not None:
        mask &= catalog["year"].ge(min_year).to_numpy()
    if max_year is not None:
        mask &= catalog["year"].le(max_year).to_numpy()
    if language != "Todos":
        mask &= catalog["language"].eq(language).to_numpy()
    return catalog.loc[mask].copy()


def _validate_vectors(catalog: pd.DataFrame, vectors: np.ndarray) -> None:
    if vectors.ndim != 2 or vectors.shape[0] != len(catalog) or vectors.shape[1] == 0:
        raise ValueError("Los vectores no corresponden al catálogo.")
    if not catalog["id"].is_unique:
        raise ValueError("El catálogo contiene identificadores duplicados.")


def _title_key(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", text).strip()


def _doi_key(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.casefold().strip())


def recommend_similar(catalog: pd.DataFrame, article_id: str, *, top_k: int = 5,
                      embeddings: np.ndarray | None = None, fields: list[str] | None = None,
                      min_year: int | None = None, max_year: int | None = None,
                      language: str = "Todos") -> pd.DataFrame:
    """Recomienda por contenido a partir de un artículo, sin volver a ejecutar los modelos.

    Usa coseno entre vectores de título y resumen. Excluye el artículo de referencia
    y sus duplicados por DOI o título; la cercanía no garantiza pertinencia científica.
    """
    if top_k <= 0:
        raise ValueError("La cantidad de resultados debe ser positiva.")
    frame = catalog.reset_index(drop=True)
    seed_positions = np.flatnonzero(frame["id"].eq(article_id).to_numpy())
    if len(seed_positions) != 1:
        raise ValueError("El artículo seleccionado no existe o su identificador está duplicado.")
    vectors = embeddings if embeddings is not None else load_embeddings(catalog)
    _validate_vectors(catalog, vectors)
    seed_position = int(seed_positions[0])
    seed = frame.iloc[seed_position]
    seed_vector = np.asarray(vectors[seed_position], dtype=np.float32)
    seed_norm = float(np.linalg.norm(seed_vector))
    if not np.isfinite(seed_norm) or seed_norm == 0:
        raise ValueError("El artículo seleccionado no tiene un vector válido. Regenera el índice.")
    candidates = _filter_catalog(frame, fields=fields, min_year=min_year,
                                 max_year=max_year, language=language)
    candidates = candidates[candidates["id"].ne(article_id)]
    doi = _doi_key(seed.get("doi"))
    title = _title_key(seed.get("title"))
    if doi and "doi" in candidates:
        candidates = candidates[candidates["doi"].map(_doi_key).ne(doi)]
    if title:
        candidates = candidates[candidates["title"].map(_title_key).ne(title)]
    if candidates.empty:
        return _empty_results(candidates)

    # Compute over the full matrix once, avoiding a large advanced-index copy.
    norms = np.sqrt(np.einsum("ij,ij->i", vectors, vectors))
    denominator = norms * seed_norm
    with np.errstate(invalid="ignore", divide="ignore"):
        cosine = np.asarray(vectors @ seed_vector) / denominator
    scores = cosine[candidates.index.to_numpy()]
    valid = np.isfinite(scores) & (scores > 0)
    candidates = candidates.loc[valid].copy()
    candidates["score"] = np.clip(scores[valid], -1, 1).astype(np.float32)
    candidates = candidates.sort_values(
        ["score", "year", "id"], ascending=[False, False, True], kind="stable"
    ).head(top_k).reset_index(drop=True)
    candidates["evidence"] = ""
    candidates["seed_id"] = article_id
    candidates.attrs["recommendation_mode"] = "similar"
    return candidates


def recommend(catalog: pd.DataFrame, query: str, *, engine: str = "semantico", top_k: int = 5,
              embeddings: np.ndarray | None = None, model: Any | None = None,
              reranker: Any | None = None, fields: list[str] | None = None,
              min_year: int | None = None, max_year: int | None = None,
              language: str = "Todos", generate_evidence: bool = True,
              rerank_candidates: int = RERANK_CANDIDATES,
              rerank_weight: float = 0.5, rerank_passage: str = "enriched",
              diagnostics: dict[str, Any] | None = None) -> pd.DataFrame:
    """Recupera candidatos y los ordena por relevancia; los puntajes no son probabilidades."""
    if len(query.split()) < 5:
        raise ValueError("Describe el proyecto con al menos cinco palabras.")
    if top_k <= 0:
        raise ValueError("La cantidad de resultados debe ser positiva.")
    valid_engines = {"e5", "semantico", "tfidf", "hibrido", "hibrido_sin_rerank"}
    if engine not in valid_engines:
        raise ValueError("Motor desconocido: selecciona e5, semántico, híbrido o TF-IDF.")
    if rerank_candidates <= 0:
        raise ValueError("La cantidad de candidatos del reordenador debe ser positiva.")
    if not 0 <= rerank_weight <= 1:
        raise ValueError("El peso del reordenador debe estar entre cero y uno.")
    if rerank_passage not in {"enriched", "text"}:
        raise ValueError("El pasaje del reordenador debe ser enriched o text.")
    candidates = _filter_catalog(catalog, fields=fields, min_year=min_year,
                                 max_year=max_year, language=language)
    if candidates.empty:
        return _empty_results(candidates, semantic=engine != "tfidf")

    if engine in {"e5", "semantico", "hibrido", "hibrido_sin_rerank"}:
        model = model or _load_sentence_model()
        vectors = embeddings if embeddings is not None else load_embeddings(catalog)
        _validate_vectors(catalog, vectors)
        query_vector = model.encode([f"query: {query}"], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
        positions = catalog.reset_index(drop=True).reset_index(names="_position").set_index("id")["_position"]
        candidate_positions = positions.loc[candidates["id"].tolist()].to_numpy()
        semantic_scores = np.asarray(
            vectors[candidate_positions] @ np.asarray(query_vector).reshape(-1)
        ).reshape(-1)
        candidates = candidates.copy().assign(semantic_score=semantic_scores.astype(np.float32))
        semantic_order = candidates.sort_values(["semantic_score", "year", "id"], ascending=[False, False, True], kind="stable")
        semantic_order["semantic_rank"] = np.arange(1, len(semantic_order) + 1)
        if engine in {"hibrido", "hibrido_sin_rerank"}:
            vectorizer, matrix, _ = load_hybrid_index(catalog)
            lexical_query = vectorizer.transform([_lexical_normalize(query)])
            if lexical_query.nnz:
                lexical_scores = cosine_similarity(lexical_query, matrix[candidate_positions]).ravel()
                lexical = candidates.assign(lexical_score=lexical_scores.astype(np.float32))
                lexical = lexical[lexical["lexical_score"] > 0].sort_values(
                    ["lexical_score", "year", "id"], ascending=[False, False, True], kind="stable"
                ).head(rerank_candidates)
            else:
                lexical = candidates.iloc[0:0].copy().assign(lexical_score=pd.Series(dtype="float32"))
            semantic_shortlist = semantic_order.head(rerank_candidates)
            fused = reciprocal_rank_fusion(
                [semantic_shortlist["id"].tolist(), lexical["id"].tolist()]
            )
            candidates = candidates[candidates["id"].isin(fused)].copy()
            candidates["retrieval_score"] = candidates["id"].map(fused).astype(np.float32)
            candidates["semantic_rank"] = candidates["id"].map(semantic_order.set_index("id")["semantic_rank"])
            candidates["lexical_score"] = candidates["id"].map(lexical.set_index("id")["lexical_score"])
            candidates = candidates.sort_values(["retrieval_score", "year", "id"], ascending=[False, False, True], kind="stable")
            if diagnostics is not None:
                diagnostics.update({"semantic_candidate_ids": semantic_shortlist["id"].tolist(),
                                    "lexical_candidate_ids": lexical["id"].tolist(),
                                    "lexical_query_has_terms": bool(lexical_query.nnz),
                                    "retrieval_candidate_ids": candidates["id"].tolist()})
        else:
            candidates = semantic_order.head(rerank_candidates).copy()
            candidates["retrieval_score"] = candidates["semantic_score"]
            if diagnostics is not None:
                diagnostics.update({"semantic_candidate_ids": candidates["id"].tolist(),
                                    "retrieval_candidate_ids": candidates["id"].tolist()})

        if engine in {"semantico", "hibrido"}:
            reranker = reranker or _load_reranker()
            passage = _reranker_passage if rerank_passage == "enriched" else article_text
            pairs = [(query, passage(article)) for _, article in candidates.iterrows()]
            rerank_scores = np.asarray(reranker.predict(pairs, batch_size=32, show_progress_bar=False)).reshape(-1)
            candidates["reranker_score"] = rerank_scores.astype(np.float32)
            candidates = candidates[candidates["reranker_score"] >= MIN_RERANK_SCORE].copy()
            if candidates.empty:
                return _empty_results(candidates, semantic=True)
            rerank_order = candidates.sort_values(["reranker_score", "year", "id"], ascending=[False, False, True], kind="stable")
            if engine == "hibrido":
                fused = reciprocal_rank_fusion(
                    [candidates.sort_values(["retrieval_score", "year", "id"], ascending=[False, False, True])["id"].tolist(),
                     rerank_order["id"].tolist()],
                    weights=[1 - rerank_weight, rerank_weight],
                )
                candidates["score"] = candidates["id"].map(fused).astype(np.float32)
            else:
                candidates["score"] = candidates["reranker_score"]
            if diagnostics is not None:
                diagnostics.update({"reranked_candidate_ids": rerank_order["id"].tolist(),
                                    "excluded_negative_ids": [],
                                    "reranker_passage": rerank_passage})
        else:
            candidates["score"] = candidates["retrieval_score"] if engine == "hibrido_sin_rerank" else candidates["semantic_score"]
    else:
        import joblib
        from scipy.sparse import load_npz

        if not all(path.exists() for path in (TFIDF_VECTORIZER, TFIDF_MATRIX, TFIDF_IDS)):
            raise FileNotFoundError("Falta el índice TF-IDF. Ejecuta: python scripts/build_index.py")
        vectorizer = joblib.load(TFIDF_VECTORIZER)
        matrix = load_npz(TFIDF_MATRIX)
        indexed_ids = json.loads(TFIDF_IDS.read_text(encoding="utf-8"))
        if indexed_ids != catalog.loc[catalog["language"].eq("en"), "id"].tolist():
            raise ValueError("El índice TF-IDF no coincide con el catálogo. Regenera el índice.")
        indexed_positions = {value: i for i, value in enumerate(indexed_ids)}
        candidates = candidates[candidates["language"].eq("en")]
        candidates = candidates[candidates["id"].isin(indexed_positions)]
        if candidates.empty:
            return _empty_results(candidates.iloc[0:0])
        query_vector = vectorizer.transform([query])
        if query_vector.nnz == 0:
            return _empty_results(candidates.iloc[0:0])
        positions = [indexed_positions[value] for value in candidates["id"]]
        scores = cosine_similarity(query_vector, matrix[positions]).ravel()

    candidates = candidates.copy()
    if engine == "tfidf":
        candidates["score"] = scores.astype(np.float32)
        candidates = candidates[candidates["score"] > 0]
    candidates = candidates.sort_values(["score", "year"], ascending=[False, False])
    candidates = candidates.head(top_k).reset_index(drop=True)
    if engine != "tfidf" and generate_evidence:
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
