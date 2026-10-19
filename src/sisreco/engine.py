"""Recuperación densa, reordenamiento, artículos similares y referencia TF-IDF."""

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
    EMBEDDING_BATCH_SIZE,
    HYBRID_MANIFEST,
    HYBRID_MATRIX,
    HYBRID_MAX_FEATURES,
    HYBRID_RRF_K,
    HYBRID_VECTORIZER,
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
def load_retriever(spec: RetrieverSpec = RETRIEVER, *, local_files_only: bool = False):
    """Carga el recuperador; local_files_only evita descargas para que la app funcione sin conexión."""
    from sentence_transformers import SentenceTransformer

    device = _best_device()
    model = SentenceTransformer(spec.model_name, device=device, model_kwargs=_model_kwargs(device),
                                local_files_only=local_files_only)
    model.max_seq_length = spec.max_seq_length
    return model


@lru_cache(maxsize=2)
def load_reranker(spec: RerankerSpec = RERANKER, *, local_files_only: bool = False):
    from sentence_transformers import CrossEncoder

    device = _best_device()
    return CrossEncoder(spec.model_name, device=device, max_length=spec.max_length, model_kwargs=_model_kwargs(device),
                        local_files_only=local_files_only)


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


def _lexical_normalize(value: Any) -> str:
    """Minúsculas y sin tildes, para que el índice léxico compare español e inglés sin traducir."""
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", text).strip()


def hybrid_text(row: pd.Series | dict[str, Any]) -> str:
    """Texto del índice léxico bilingüe: el título se repite para darle más peso."""
    return _lexical_normalize(f"{row.get('title', '')} {row.get('title', '')} {row.get('abstract', '')} "
                              f"{_keywords_text(row.get('keywords')).replace(',', ' ')}")


def build_hybrid_index(catalog: pd.DataFrame) -> None:
    """Crea el índice léxico bilingüe que la recuperación combinada fusiona con la búsqueda densa."""
    if catalog.empty:
        raise ValueError("No se puede indexar un catálogo vacío.")
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=HYBRID_MAX_FEATURES, min_df=2, max_df=0.95,
                                 sublinear_tf=True, dtype=np.float32)
    matrix = vectorizer.fit_transform(catalog.apply(hybrid_text, axis=1).tolist())
    HYBRID_VECTORIZER.parent.mkdir(parents=True, exist_ok=True)
    import joblib
    from scipy.sparse import save_npz

    joblib.dump(vectorizer, HYBRID_VECTORIZER)
    save_npz(HYBRID_MATRIX, matrix)
    HYBRID_MANIFEST.write_text(json.dumps({
        "catalog_ids": catalog["id"].tolist(), "ngram_range": [1, 2], "max_features": HYBRID_MAX_FEATURES,
        "min_df": 2, "max_df": 0.95, "sublinear_tf": True, "normalization": "casefold_and_strip_accents",
        "document": "title twice, abstract, keywords",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def load_hybrid_index(catalog: pd.DataFrame) -> tuple[Any, Any]:
    """Carga el índice léxico bilingüe y rechaza el de otro catálogo."""
    if not all(path.exists() for path in (HYBRID_VECTORIZER, HYBRID_MATRIX, HYBRID_MANIFEST)):
        raise FileNotFoundError("Falta el índice léxico bilingüe. Ejecuta: python scripts/build_index.py")
    import joblib
    from scipy.sparse import load_npz

    manifest = json.loads(HYBRID_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("catalog_ids") != catalog["id"].tolist():
        raise ValueError("El índice léxico no coincide con el catálogo actual. Regenera el índice.")
    return joblib.load(HYBRID_VECTORIZER), load_npz(HYBRID_MATRIX)


def reciprocal_rank_fusion(rankings: list[list[str]], *, k: int = HYBRID_RRF_K,
                           weights: list[float] | None = None) -> dict[str, float]:
    """Fusiona listas por posición (RRF): cada aparición suma weight / (k + puesto)."""
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
    if min_year is not None and max_year is not None and min_year > max_year:
        raise ValueError("El año inicial no puede ser posterior al año final.")
    if language not in {"Todos", "en", "es"}:
        raise ValueError("Idioma desconocido: usa Todos, en o es.")
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


def _empty_results(candidates: pd.DataFrame) -> pd.DataFrame:
    return candidates.iloc[0:0].assign(score=pd.Series(dtype="float32"), retrieval_score=pd.Series(dtype="float32"),
                                       evidence=pd.Series(dtype="object"))


def _top(scores: np.ndarray, count: int) -> np.ndarray:
    """Posiciones de los count puntajes más altos, ordenadas de mayor a menor."""
    count = min(count, len(scores))
    if count <= 0:
        return np.empty(0, dtype=int)
    best = np.argpartition(-scores, count - 1)[:count]
    return best[np.argsort(-scores[best], kind="stable")]


def recommend(catalog: pd.DataFrame, query: str, *, engine: str = "semantico", top_k: int = TOP_K,
              vectors: np.ndarray | None = None, retriever: Any | None = None, reranker: Any | None = None,
              retriever_spec: RetrieverSpec = RETRIEVER, reranker_spec: RerankerSpec | None = RERANKER,
              lexical_index: tuple[Any, Any] | None = None,
              fields: list[str] | None = None, min_year: int | None = None, max_year: int | None = None,
              language: str = "Todos", generate_evidence: bool = True,
              diagnostics: dict[str, Any] | None = None) -> pd.DataFrame:
    """Devuelve los top_k artículos más afines. Los puntajes ordenan; no son probabilidades ni miden calidad.

    Con lexical_index, la lista corta combina por RRF los candidatos densos y los del índice
    léxico bilingüe antes de reordenar; sin él, la lista corta sale solo de la búsqueda densa.
    diagnostics, si se entrega, registra los identificadores de cada etapa.
    """
    if len(query.split()) < 5:
        raise ValueError("Describe el proyecto con al menos cinco palabras.")
    if top_k <= 0:
        raise ValueError("La cantidad de resultados debe ser positiva.")
    if engine not in {"semantico", "tfidf"}:
        raise ValueError("Motor desconocido: selecciona semántico o TF-IDF.")
    candidates = _filter(catalog, fields, min_year, max_year, language)
    if engine == "tfidf":
        return _recommend_tfidf(catalog, candidates, query, top_k)
    if candidates.empty:
        return _empty_results(candidates)

    retriever = retriever or load_retriever(retriever_spec)
    vectors = vectors if vectors is not None else load_vectors(catalog, retriever_spec)
    _validate_vectors(catalog, vectors)
    positions = np.flatnonzero(catalog.index.isin(candidates.index))
    scores = dense_scores(vectors, encode_query(query, retriever_spec, retriever),
                          None if len(positions) == len(catalog) else positions)
    shortlist = max(top_k, reranker_spec.candidates if reranker_spec is not None else top_k)
    dense = _top(scores, shortlist)
    results = candidates.iloc[dense].copy()
    results["retrieval_score"] = scores[dense]
    if diagnostics is not None:
        diagnostics["dense_ids"] = results["id"].tolist()
    if lexical_index is not None:
        results = _fuse_lexical(candidates, positions, results, query, lexical_index, shortlist, diagnostics)
    results["score"] = results["retrieval_score"]
    if reranker_spec is not None:
        reranker = reranker or load_reranker(reranker_spec)
        results["score"] = rerank_scores(query, [article_text(row) for _, row in results.iterrows()], reranker)
        results = results.sort_values("score", ascending=False, kind="stable")
    # Top-k fijo: sin umbral, porque los puntajes del reordenador no están calibrados entre
    # consultas y un corte fijo deja listas vacías o incompletas.
    results = results.head(top_k).reset_index(drop=True)
    if diagnostics is not None:
        diagnostics["final_ids"] = results["id"].tolist()
    if generate_evidence:
        results["evidence"] = [_semantic_evidence(query, abstract, retriever_spec, retriever)
                               for abstract in results["abstract"].tolist()]
    else:
        results["evidence"] = ""
    return results


def _fuse_lexical(candidates: pd.DataFrame, positions: np.ndarray, dense: pd.DataFrame, query: str,
                  lexical_index: tuple[Any, Any], shortlist: int, diagnostics: dict[str, Any] | None) -> pd.DataFrame:
    """Combina por RRF la lista densa con la léxica y conserva los shortlist primeros."""
    vectorizer, matrix = lexical_index
    lexical_query = vectorizer.transform([_lexical_normalize(query)])
    lexical_ids: list[str] = []
    if lexical_query.nnz:
        lexical_scores = cosine_similarity(lexical_query, matrix[positions]).ravel()
        top_lexical = [index for index in _top(lexical_scores, shortlist) if lexical_scores[index] > 0]
        lexical_ids = candidates.iloc[top_lexical]["id"].tolist()
    fused = reciprocal_rank_fusion([dense["id"].tolist(), lexical_ids])
    order = sorted(fused, key=lambda identifier: -fused[identifier])[:shortlist]
    by_id = candidates.set_index("id", drop=False)
    results = by_id.loc[order].copy()
    results["retrieval_score"] = results["id"].map(fused).astype(np.float32)
    if diagnostics is not None:
        diagnostics.update({"lexical_ids": lexical_ids, "fused_ids": order})
    return results.reset_index(drop=True)


def _validate_vectors(catalog: pd.DataFrame, vectors: np.ndarray) -> None:
    if vectors.ndim != 2 or vectors.shape[0] != len(catalog):
        raise ValueError("Los vectores no corresponden al catálogo. Regenera el índice.")


def _title_key(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return " ".join(_lexical_normalize(value).split())


def _doi_key(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).casefold().strip()
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text)


def recommend_similar(catalog: pd.DataFrame, article_id: str, *, top_k: int = TOP_K, vectors: np.ndarray | None = None,
                      retriever_spec: RetrieverSpec = RETRIEVER, fields: list[str] | None = None,
                      min_year: int | None = None, max_year: int | None = None, language: str = "Todos") -> pd.DataFrame:
    """Recomienda artículos parecidos a uno elegido, por coseno entre sus vectores.

    No ejecuta modelos: reutiliza el vector ya indexado del artículo. Excluye el artículo de
    referencia y sus duplicados por DOI o título; la cercanía no garantiza pertinencia científica.
    """
    if top_k <= 0:
        raise ValueError("La cantidad de resultados debe ser positiva.")
    frame = catalog.reset_index(drop=True)
    seed_positions = np.flatnonzero(frame["id"].eq(article_id).to_numpy())
    if len(seed_positions) != 1:
        raise ValueError("El artículo seleccionado no existe o su identificador está duplicado.")
    vectors = vectors if vectors is not None else load_vectors(catalog, retriever_spec)
    _validate_vectors(catalog, vectors)
    seed = frame.iloc[int(seed_positions[0])]
    seed_vector = np.asarray(vectors[int(seed_positions[0])], dtype=np.float32)
    seed_norm = float(np.linalg.norm(seed_vector))
    if not np.isfinite(seed_norm) or seed_norm == 0:
        raise ValueError("El artículo seleccionado no tiene un vector válido. Regenera el índice.")
    candidates = _filter(frame, fields, min_year, max_year, language)
    candidates = candidates[candidates["id"].ne(article_id)]
    doi, title = _doi_key(seed.get("doi")), _title_key(seed.get("title"))
    if doi:
        candidates = candidates[candidates["doi"].map(_doi_key).ne(doi)]
    if title:
        candidates = candidates[candidates["title"].map(_title_key).ne(title)]
    if candidates.empty:
        return _empty_results(candidates)
    # Los vectores están normalizados; se divide igual por las normas para no depender de ello.
    selected = np.asarray(vectors[candidates.index.to_numpy()], dtype=np.float32)
    norms = np.linalg.norm(selected, axis=1) * seed_norm
    with np.errstate(invalid="ignore", divide="ignore"):
        scores = (selected @ seed_vector) / norms
    valid = np.isfinite(scores) & (scores > 0)
    results = candidates.loc[valid].assign(score=np.clip(scores[valid], -1, 1).astype(np.float32))
    results = results.sort_values(["score", "year", "id"], ascending=[False, False, True], kind="stable")
    results = results.head(top_k).reset_index(drop=True)
    results["retrieval_score"] = results["score"]
    results["evidence"] = ""
    results["seed_id"] = article_id
    return results


def _recommend_tfidf(catalog: pd.DataFrame, candidates: pd.DataFrame, query: str, top_k: int) -> pd.DataFrame:
    import joblib
    from scipy.sparse import load_npz

    if not all(path.exists() for path in (TFIDF_VECTORIZER, TFIDF_MATRIX, TFIDF_IDS)):
        raise FileNotFoundError("Falta el índice TF-IDF. Ejecuta: python scripts/build_index.py")
    indexed_ids = json.loads(TFIDF_IDS.read_text(encoding="utf-8"))
    if indexed_ids != catalog.loc[catalog["language"].eq("en"), "id"].tolist():
        raise ValueError("El índice TF-IDF no coincide con el catálogo. Regenera el índice.")
    vectorizer = joblib.load(TFIDF_VECTORIZER)
    matrix = load_npz(TFIDF_MATRIX)
    indexed_positions = {value: i for i, value in enumerate(indexed_ids)}
    candidates = candidates[candidates["language"].eq("en") & candidates["id"].isin(indexed_positions)]
    query_vector = vectorizer.transform([query])
    if candidates.empty or query_vector.nnz == 0:
        return _empty_results(candidates)
    scores = cosine_similarity(query_vector, matrix[[indexed_positions[value] for value in candidates["id"]]]).ravel()
    # Un puntaje cero significa que el artículo no comparte ningún término con la consulta.
    results = candidates.assign(score=scores.astype(np.float32))
    results = results[results["score"] > 0]
    results = results.sort_values("score", ascending=False, kind="stable").head(top_k).reset_index(drop=True)
    results["retrieval_score"] = results["score"]
    results["evidence"] = ""
    return results
