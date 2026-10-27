"""Prueba del flujo buscar → seleccionar → similares → volver, sin descargas."""

from pathlib import Path

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
import streamlit as st

import sisreco.engine as engine
import sisreco.settings as settings
from sisreco.settings import RetrieverSpec


def use_fixture_settings(tmp_path, monkeypatch, catalog_path, vectors):
    """Apunta la app a un catálogo y un índice de prueba, sin cargar modelos reales."""
    vectors_path = tmp_path / "vectors.npy"
    vectors_path.write_text("fixture")
    vectors_path.with_suffix(".json").write_text("fixture")
    monkeypatch.setattr(settings, "CATALOG", catalog_path)
    monkeypatch.setattr(settings, "DATA_MANIFEST", tmp_path / "absent.json")
    monkeypatch.setattr(settings, "RETRIEVER", RetrieverSpec("fake", max_seq_length=512, vectors_path=vectors_path))
    monkeypatch.setattr(engine, "load_vectors", lambda *_: vectors)
    monkeypatch.setattr(engine, "load_retriever", lambda *_, **__: object())
    monkeypatch.setattr(engine, "load_reranker", lambda *_, **__: object())


def test_explore_similar_keeps_results_filters_and_back_navigation(tmp_path, monkeypatch):
    frame = pd.DataFrame([
        dict(id="solar", title="Solar forecasting methods", abstract="Forecasting solar energy in cities.",
             authors=["Ana Pérez"], year=2022, language="en", field="Energy", doi=None),
        dict(id="wind", title="Wind forecasting methods", abstract="Predicting renewable wind energy.",
             authors=["Luis Díaz"], year=2023, language="en", field="Energy", doi=None),
        dict(id="health", title="Diabetes patient care", abstract="Care for patients with diabetes.",
             authors=[], year=2024, language="en", field="Medicine", doi=None),
    ])
    catalog_path = tmp_path / "catalog.parquet"
    frame.to_parquet(catalog_path)
    use_fixture_settings(tmp_path, monkeypatch, catalog_path, np.array([[1, 0], [.9, .1], [.1, .9]], dtype=np.float32))
    calls = []

    def search(catalog, query, **kwargs):
        calls.append(query)
        return catalog.iloc[:1].assign(score=2.0, evidence="")

    monkeypatch.setattr(engine, "recommend", search)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
    app.text_area(key="query").set_value("Forecast solar power for electric grids")
    app.multiselect(key="fields").select("Energy")
    next(button for button in app.button if button.label == "Buscar artículos").click().run()
    assert not app.exception
    assert calls == ["Forecast solar power for electric grids"]
    assert any("Ana Pérez" in caption.value for caption in app.caption)
    app.run()
    assert len(calls) == 1
    assert app.session_state["current_view"]["results"].id.tolist() == ["solar"]

    app.button(key="similar_solar").click().run()
    assert not app.exception
    view = app.session_state["current_view"]
    assert view["mode"] == "similar"
    assert view["seed_id"] == "solar"
    assert view["results"].id.tolist() == ["wind"]  # Excludes seed and Medicine.
    assert view["options"]["fields"] == ["Energy"]

    app.button(key="similar_wind").click().run()
    assert app.session_state["current_view"]["seed_id"] == "wind"
    assert app.session_state["current_view"]["results"].id.tolist() == ["solar"]
    app.button(key="back").click().run()
    assert app.session_state["current_view"]["seed_id"] == "solar"
    app.button(key="return_search").click().run()
    assert app.session_state["current_view"]["mode"] == "query"
    assert app.session_state["current_view"]["results"].id.tolist() == ["solar"]
    assert not app.session_state["view_history"]
    assert len(calls) == 1
    assert not app.exception


def test_app_joins_keywords_and_passes_the_selected_engine(tmp_path, monkeypatch):
    frame = pd.DataFrame([dict(id="solar", title="Solar forecasting", abstract="Solar energy forecast research.", authors=[], year=2022, language="en", field="Energy", doi=None)])
    catalog_path = tmp_path / "catalog.parquet"
    frame.to_parquet(catalog_path)
    use_fixture_settings(tmp_path, monkeypatch, catalog_path, np.array([[1, 0]], dtype=np.float32))
    seen = []

    def search(catalog, query, **kwargs):
        seen.append((query, kwargs["engine"], kwargs["top_k"]))
        return catalog.assign(score=.1, evidence="")

    monkeypatch.setattr(engine, "recommend", search)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
    app.text_area(key="query").set_value("Solar energy forecasting for electricity research")
    app.text_input(key="keywords").set_value("photovoltaic, forecasting")
    next(button for button in app.button if button.label == "Buscar artículos").click().run()
    app.radio(key="engine").set_value("TF-IDF (inglés)")
    next(button for button in app.button if button.label == "Buscar artículos").click().run()
    assert seen == [
        ("Solar energy forecasting for electricity research. Palabras clave: photovoltaic, forecasting", "semantico", 10),
        ("Solar energy forecasting for electricity research. Palabras clave: photovoltaic, forecasting", "tfidf", 10),
    ]
    assert not app.exception


def test_app_saves_and_removes_an_article_and_offers_ris_download(tmp_path, monkeypatch):
    frame = pd.DataFrame([dict(
        id="solar", title="Solar forecasting", abstract="Solar energy forecast research.",
        authors=["Ana Pérez"], year=2022, language="en", field="Energy", doi="10.1234/solar",
        url="https://example.org/solar", keywords=["solar", "forecasting"], topic="Energy",
    )])
    catalog_path = tmp_path / "catalog.parquet"
    frame.to_parquet(catalog_path)
    use_fixture_settings(tmp_path, monkeypatch, catalog_path, np.array([[1, 0]], dtype=np.float32))
    monkeypatch.setattr(engine, "recommend", lambda catalog, *_args, **_kwargs:
                        catalog.iloc[:1].assign(score=.8, evidence="Solar forecasting research."))
    st.cache_resource.clear()

    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
    app.text_area(key="query").set_value("Solar energy forecasting for electricity research")
    next(button for button in app.button if button.label == "Buscar artículos").click().run()
    app.button(key="save_solar").click().run()

    assert app.session_state["saved_article_ids"] == {"solar"}
    assert [button.label for button in app.get("download_button")] == ["Descargar referencias (.ris)"]
    app.button(key="remove_saved_solar").click().run()
    assert app.session_state["saved_article_ids"] == set()
    assert not app.get("download_button")
    assert not app.exception


def test_app_falls_back_to_dense_results_if_reranker_hits_memory_limit(tmp_path, monkeypatch):
    frame = pd.DataFrame([dict(
        id="solar", title="Solar forecasting", abstract="Solar energy forecast research.",
        authors=["Ana Pérez"], year=2022, language="en", field="Energy", doi=None,
        url=None, keywords=[], topic="Energy",
    )])
    catalog_path = tmp_path / "catalog.parquet"
    frame.to_parquet(catalog_path)
    use_fixture_settings(tmp_path, monkeypatch, catalog_path, np.array([[1, 0]], dtype=np.float32))

    def raise_memory_error(*_args, **_kwargs):
        raise OSError("The paging file is too small to complete the operation (1455)")

    calls = []

    def search(catalog, *_args, **kwargs):
        calls.append(kwargs)
        return catalog.iloc[:1].assign(score=.8, evidence="Solar forecasting research.")

    monkeypatch.setattr(engine, "load_reranker", raise_memory_error)
    monkeypatch.setattr(engine, "recommend", search)
    st.cache_resource.clear()
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
    app.text_area(key="query").set_value("Solar energy forecasting for electricity research")
    next(button for button in app.button if button.label == "Buscar artículos").click().run()

    assert calls and calls[0]["rerank_enabled"] is False
    assert app.session_state["current_view"]["reranker_fallback"] is True
    assert any("similitud semántica" in warning.value.lower() for warning in app.warning)
    assert not app.exception
