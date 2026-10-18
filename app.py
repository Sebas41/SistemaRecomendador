"""Búsqueda de literatura y exploración por artículos de referencia."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from sisreco.engine import (
    _load_reranker, _load_sentence_model, load_embeddings, recommend, recommend_similar,
)
from sisreco.settings import CATALOG, DATA_MANIFEST, EMBEDDINGS, EMBEDDINGS_MANIFEST

st.set_page_config(page_title="Ciencia a tu tesis", page_icon="📚", layout="wide")


def file_version(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


@st.cache_data
def load_catalog(version: tuple[int, int]) -> pd.DataFrame:
    return pd.read_parquet(CATALOG)


@st.cache_resource
def load_model():
    return _load_sentence_model(local_files_only=True)


@st.cache_resource
def load_reranker():
    return _load_reranker(local_files_only=True)


@st.cache_resource
def load_vectors(catalog_version, vector_version, manifest_version):
    return load_embeddings(load_catalog(catalog_version))


def current_vectors():
    return load_vectors(file_version(CATALOG), file_version(EMBEDDINGS), file_version(EMBEDDINGS_MANIFEST))


def navigate(action: str, article_id: str | None = None):
    st.session_state["navigation"] = (action, article_id)


def text_or_default(value, default="") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


st.title("Ciencia a tu tesis")
st.write("Describe tu investigación y elige un artículo para descubrir otras lecturas similares.")
st.caption("La afinidad temática orienta la búsqueda; cada artículo requiere tu revisión académica.")

try:
    catalog_version = file_version(CATALOG)
    catalog = load_catalog(catalog_version)
except (FileNotFoundError, ValueError, OSError) as exc:
    st.error(f"No se pudo cargar el catálogo local: {exc}")
    st.code("python scripts/download_data.py\npython scripts/build_index.py", language="bash")
    st.stop()

# Un catálogo actualizado invalida las selecciones y sus resultados almacenados.
if st.session_state.get("catalog_version") != catalog_version:
    for name in ("current_view", "search_view", "view_history", "navigation"):
        st.session_state.pop(name, None)
    st.session_state["catalog_version"] = catalog_version

with st.sidebar:
    st.header("Tu investigación")
    with st.form("search_form"):
        query = st.text_area(
            "Describe tu proyecto, objetivo o pregunta", key="query",
            placeholder="Ej.: Aprendizaje automático para pronosticar la generación de energía solar.",
            height=145,
        )
        keywords = st.text_input("Palabras clave (opcional)", key="keywords")
        fields = sorted(catalog["field"].dropna().unique().tolist())
        selected_fields = st.multiselect("Disciplina (opcional)", options=fields, key="fields")
        min_available = int(catalog["year"].min())
        max_available = int(catalog["year"].max())
        if min_available < max_available:
            year_range = st.slider("Periodo", min_value=min_available, max_value=max_available,
                                   value=(min_available, max_available), key="years")
        else:
            year_range = (min_available, max_available)
            st.caption(f"Año disponible: {min_available}")
        language_label = st.selectbox("Idioma del artículo", ["Todos", "Inglés", "Español"], key="language")
        language = {"Todos": "Todos", "Inglés": "en", "Español": "es"}[language_label]
        engine_label = st.radio(
            "Método de búsqueda",
            ["Semántico bilingüe", "Híbrido experimental", "TF-IDF (inglés)"], key="engine",
        )
        engine = {
            "Semántico bilingüe": "semantico",
            "Híbrido experimental": "hibrido",
            "TF-IDF (inglés)": "tfidf",
        }[engine_label]
        top_k = st.radio("Resultados", [5, 10], horizontal=True, key="top_k")
        submitted = st.form_submit_button("Buscar artículos", type="primary", use_container_width=True)
    st.caption("Ver similares conserva los filtros de la búsqueda inicial. Pulsa Buscar para aplicar cambios.")

summary = st.columns(3)
summary[0].metric("Artículos disponibles", f"{len(catalog):,}")
summary[1].metric("Campos académicos", f"{catalog['field'].nunique():,}")
summary[2].metric("Consultas", "Español e inglés")
if DATA_MANIFEST.exists():
    manifest = json.loads(DATA_MANIFEST.read_text(encoding="utf-8"))
    st.caption(f"Fuentes: OpenAlex y SciELO · catálogo preparado el {manifest.get('retrieved_at_utc', '')[:10]}.")

if submitted:
    full_query = " ".join(part.strip() for part in (query, keywords) if part.strip())
    if len(query.split()) < 5:
        st.warning("Escribe al menos cinco palabras en la descripción de tu investigación.")
    elif engine == "tfidf" and language == "es":
        st.warning("TF-IDF utiliza artículos y consultas en inglés. Cambia el idioma o selecciona Semántico bilingüe.")
    else:
        options = dict(fields=selected_fields, min_year=year_range[0], max_year=year_range[1],
                       language=language, top_k=top_k)
        try:
            with st.spinner("Buscando artículos relacionados..."):
                results = recommend(
                    catalog, full_query, engine=engine, **options,
                    embeddings=current_vectors() if engine != "tfidf" else None,
                    model=load_model() if engine != "tfidf" else None,
                    reranker=load_reranker() if engine in {"semantico", "hibrido"} else None,
                )
            view = dict(mode="query", query=full_query, engine=engine, options=options, results=results)
            st.session_state["current_view"] = view
            st.session_state["search_view"] = view
            st.session_state["view_history"] = []
        except (FileNotFoundError, ValueError, OSError) as exc:
            st.error(f"No se pudo completar la búsqueda: {exc}")
            st.code("python scripts/build_index.py", language="bash")

navigation = st.session_state.pop("navigation", None)
if navigation and "current_view" in st.session_state:
    action, article_id = navigation
    history = st.session_state.get("view_history", [])
    if action == "back" and history:
        st.session_state["current_view"] = history[-1]
        st.session_state["view_history"] = history[:-1]
    elif action == "search":
        st.session_state["current_view"] = st.session_state["search_view"]
        st.session_state["view_history"] = []
    elif action == "similar":
        previous = st.session_state["current_view"]
        try:
            with st.spinner("Buscando lecturas similares al artículo elegido..."):
                results = recommend_similar(catalog, article_id, embeddings=current_vectors(), **previous["options"])
            seed = catalog.loc[catalog["id"].eq(article_id)].iloc[0]
            st.session_state["view_history"] = (history + [previous])[-10:]
            st.session_state["current_view"] = dict(
                mode="similar", query=previous["query"], engine="similares", options=previous["options"],
                results=results, seed_id=article_id, seed_title=seed["title"], seed_topic=seed.get("topic"),
            )
        except (FileNotFoundError, ValueError, OSError) as exc:
            st.error(f"No se pudieron obtener artículos similares: {exc}")
            st.code("python scripts/build_index.py", language="bash")

view = st.session_state.get("current_view")
if view is None:
    st.info("Empieza con una descripción de tu proyecto. Después podrás seleccionar cualquier resultado y explorar artículos similares.")
else:
    is_similar = view["mode"] == "similar"
    if is_similar:
        st.subheader("Lecturas similares al artículo seleccionado")
        st.write(f"Artículo de referencia: **{view['seed_title']}**")
        st.caption("Se compara el contenido del artículo de referencia con el catálogo. El artículo elegido y sus duplicados se excluyen.")
        navigation_columns = st.columns(2)
        navigation_columns[0].button("Volver a la lista anterior", on_click=navigate, args=("back",), key="back")
        navigation_columns[1].button("Volver a la búsqueda inicial", on_click=navigate, args=("search",), key="return_search")
    else:
        st.subheader("Artículos para tu investigación")
        st.caption(f"Búsqueda activa: {view['query']}")
    results = view["results"]
    options = view["options"]
    filter_fields = ", ".join(options["fields"]) if options["fields"] else "Todas las disciplinas"
    st.caption(f"{filter_fields} · {options['min_year']}–{options['max_year']} · idioma: {options['language']}")
    if results.empty:
        message = "No hay otros artículos disponibles con estos filtros." if is_similar else "No se encontraron coincidencias suficientes. Prueba una descripción más precisa o amplía los filtros."
        st.info(message)
    else:
        st.caption(f"{len(results)} resultados. La puntuación ordena afinidad; no es una probabilidad ni una valoración de calidad científica.")
        for rank, (_, article) in enumerate(results.iterrows(), start=1):
            authors = article.get("authors")
            authors = list(authors) if isinstance(authors, (list, tuple, np.ndarray)) else []
            authors_text = ", ".join(str(author) for author in authors[:5]) or "Autores no disponibles"
            if len(authors) > 5:
                authors_text += " y otros"
            source_label = text_or_default(article.get("source_database"), "Fuente no disponible")
            collection = text_or_default(article.get("source_collection"))
            if collection:
                source_label += f" ({collection})"
            score_label = (
                "Similitud con el artículo" if is_similar else
                "Puntuación híbrida experimental" if view["engine"] == "hibrido" else
                "Relevancia del modelo" if view["engine"] == "semantico" else
                "Similitud TF-IDF"
            )
            with st.container(border=True):
                st.markdown(f"**{rank}. {article['title']}**")
                st.caption(f"{authors_text} · {article['year']} · {article['field']} · {source_label}")
                st.caption(f"{score_label}: {float(article['score']):.3f}")
                if is_similar:
                    topic = text_or_default(article.get("topic"))
                    if topic and topic == text_or_default(view.get("seed_topic")):
                        st.caption(f"Tema compartido en los metadatos: {topic}")
                with st.expander("Leer resumen"):
                    st.write(article["abstract"])
                    if text_or_default(article.get("evidence")):
                        st.info(f"Fragmento orientativo: “{article['evidence']}”")
                actions = st.columns(2)
                url = text_or_default(article.get("url"))
                if url:
                    actions[0].link_button("Abrir artículo", url)
                actions[1].button("Ver artículos similares", key=f"similar_{article['id']}",
                                  on_click=navigate, args=("similar", article["id"]))
