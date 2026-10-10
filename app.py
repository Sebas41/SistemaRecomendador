"""Interfaz Streamlit para encontrar literatura afín a una tesis."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from sisreco.engine import _load_sentence_model, load_embeddings, recommend
from sisreco.settings import CATALOG, DATA_MANIFEST

st.set_page_config(page_title="Ciencia a tu tesis", page_icon="📚", layout="wide")


@st.cache_data
def load_catalog() -> pd.DataFrame:
    if not CATALOG.exists():
        raise FileNotFoundError("No existe el catálogo local. Sigue los pasos de instalación del README.")
    return pd.read_parquet(CATALOG)


@st.cache_resource
def load_model():
    return _load_sentence_model()


@st.cache_resource
def load_vectors(ids: tuple[str, ...]):
    frame = load_catalog()
    if tuple(frame["id"].tolist()) != ids:
        raise ValueError("El catálogo cambió; vuelve a generar los índices.")
    return load_embeddings(frame)


st.title("Ciencia a tu tesis")
st.write("Encuentra artículos científicos relacionados con tu proyecto de grado o tesis.")
st.caption("La afinidad temática orienta la búsqueda; cada artículo requiere tu revisión académica.")

try:
    catalog = load_catalog()
except (FileNotFoundError, ValueError) as exc:
    st.error(str(exc))
    st.code("python scripts/download_data.py\npython scripts/build_index.py\nstreamlit run app.py", language="bash")
    st.stop()

manifest = {}
if DATA_MANIFEST.exists():
    import json
    manifest = json.loads(DATA_MANIFEST.read_text(encoding="utf-8"))

with st.sidebar:
    st.header("Tu búsqueda")
    query = st.text_area(
        "Describe tu proyecto, objetivo o pregunta",
        placeholder="Ej.: Quiero analizar cómo el aprendizaje automático puede mejorar el pronóstico de energía solar en ciudades latinoamericanas.",
        height=145,
    )
    keywords = st.text_input("Palabras clave (opcional)", placeholder="aprendizaje automático, energía solar")
    fields = sorted(catalog["field"].dropna().unique().tolist())
    selected_fields = st.multiselect("Disciplina (opcional)", options=fields)
    min_available, max_available = int(catalog["year"].min()), int(catalog["year"].max())
    year_range = st.slider(
        "Periodo (opcional)",
        min_value=min_available,
        max_value=max_available,
        value=(min_available, max_available),
    )
    language_label = st.selectbox("Idioma del artículo", ["Todos", "Inglés", "Español"])
    language = {"Todos": "Todos", "Inglés": "en", "Español": "es"}[language_label]
    engine_label = st.radio("Criterio de similitud", ["Semántico multilingüe", "TF-IDF (inglés)"])
    engine = "semantico" if engine_label == "Semántico multilingüe" else "tfidf"
    top_k = st.radio("Resultados", [5, 10], horizontal=True)
    submitted = st.button("Buscar artículos", type="primary", use_container_width=True)

summary = st.columns(3)
summary[0].metric("Artículos disponibles", f"{len(catalog):,}")
summary[1].metric("Campos académicos", f"{catalog['field'].nunique():,}")
summary[2].metric("Consultas", "Español e inglés")

if manifest:
    st.caption(f"Fuente: OpenAlex · muestra recopilada el {manifest.get('retrieved_at_utc', 'fecha no disponible')[:10]} · catálogo reproducible.")

if submitted:
    query = " ".join(part.strip() for part in [query, keywords] if part and part.strip())
    if len(query.split()) < 5:
        st.warning("Escribe al menos cinco palabras para describir tu investigación.")
        st.stop()
    if engine == "tfidf" and language == "es":
        st.warning("TF-IDF solo compara consultas en inglés. Escribe la búsqueda en inglés o cambia al motor semántico.")
        st.stop()
    with st.spinner("Calculando afinidad temática..."):
        try:
            model = load_model() if engine == "semantico" else None
            vectors = load_vectors(tuple(catalog["id"].tolist())) if engine == "semantico" else None
            results = recommend(
                catalog,
                query,
                engine=engine,
                top_k=top_k,
                embeddings=vectors,
                model=model,
                fields=selected_fields,
                min_year=year_range[0],
                max_year=year_range[1],
                language=language,
            )
        except (FileNotFoundError, ValueError, OSError) as exc:
            st.error(str(exc))
            st.code("python scripts/build_index.py", language="bash")
            st.stop()
    if results.empty:
        st.info("No hay resultados. Prueba con otros términos o amplía los filtros.")
    else:
        st.subheader(f"{len(results)} artículos relacionados")
        st.caption("Las puntuaciones son similitudes coseno para ordenar resultados; no son probabilidades ni medidas de calidad.")
        for rank, (_, article) in enumerate(results.iterrows(), start=1):
            authors = article["authors"] if isinstance(article["authors"], list) else []
            authors_text = ", ".join(authors[:5]) or "Autores no disponibles"
            if len(authors) > 5:
                authors_text += " y otros"
            url = str(article.get("url") or "").strip()
            score = float(article["score"])
            with st.container(border=True):
                st.markdown(f"**{rank}. [{article['title']}]({url})**" if url else f"**{rank}. {article['title']}**")
                database = article.get("source_database", "OpenAlex")
                collection = article.get("source_collection")
                source_label = f"{database} ({collection})" if collection else database
                journal = article.get("source")
                journal_label = f" · {journal}" if journal else ""
                st.caption(
                    f"{authors_text} · {article['year']} · {article['field']} · "
                    f"fuente: {source_label}{journal_label} · similitud {score:.3f}"
                )
                st.write(article["abstract"])
                if article.get("evidence"):
                    st.info(f"Fragmento relacionado: “{article['evidence']}”")
