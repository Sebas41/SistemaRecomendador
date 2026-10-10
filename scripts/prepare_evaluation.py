#!/usr/bin/env python3
"""Prepara resultados codificados para evaluación manual a ciegas."""

import json
import random
import pandas as pd

from sisreco.engine import _load_sentence_model, load_embeddings, recommend
from sisreco.settings import ARTIFACTS_DIR, CATALOG

PROFILES = [
    {"id":"P01","field":"Medicine","topic":"screening and prevention of cardiovascular disease in adults","es":"Quiero investigar la detección temprana y prevención de enfermedades cardiovasculares en personas adultas, incluyendo los factores de riesgo y las intervenciones de salud pública.","en":"I want to study early screening and prevention of cardiovascular disease in adults, including risk factors and public health interventions."},
    {"id":"P02","field":"Social Sciences","topic":"educational technology and learning outcomes in higher education","es":"Mi proyecto estudia cómo las tecnologías digitales educativas se relacionan con los resultados de aprendizaje y la participación de estudiantes universitarios.","en":"My project studies how digital educational technologies relate to learning outcomes and student engagement in higher education."},
    {"id":"P03","field":"Energy","topic":"machine learning for renewable energy forecasting","es":"Quiero investigar el uso de aprendizaje automático para predecir la generación de energía solar y eólica y mejorar la operación de redes eléctricas.","en":"I want to study machine learning for solar and wind energy generation forecasting and improved electric grid operation."},
    {"id":"P04","field":"Environmental Science","topic":"climate change effects on biodiversity and ecosystems","es":"Mi tesis estudia los efectos del cambio climático sobre la biodiversidad, la distribución de especies y la conservación de los ecosistemas.","en":"My thesis studies climate change effects on biodiversity, species distribution, and ecosystem conservation."},
    {"id":"P05","field":"Economics, Econometrics and Finance","topic":"causal effects of monetary policy on inflation and employment","es":"Quiero analizar los efectos de la política monetaria sobre la inflación, el empleo y la desigualdad, comparando evidencia de diferentes economías.","en":"I want to analyze the effects of monetary policy on inflation, employment, and inequality using evidence from different economies."},
    {"id":"P06","field":"Arts and Humanities","topic":"digitization and preservation of indigenous languages","es":"Mi investigación explora la documentación digital y preservación de lenguas indígenas, con participación comunitaria y respeto por el patrimonio cultural.","en":"My research explores digital documentation and preservation of Indigenous languages through community participation and cultural heritage."},
]


def main():
    if not CATALOG.exists():
        raise SystemExit("Falta el catálogo. Ejecuta primero: python scripts/download_data.py")
    catalog = pd.read_parquet(CATALOG)
    model = _load_sentence_model()
    vectors = load_embeddings(catalog)
    rng = random.Random(42)
    engine_to_label = {"semantico":"A","tfidf":"B"}
    if rng.random() < .5:
        engine_to_label = {"semantico":"B","tfidf":"A"}
    rows = []
    for profile in PROFILES:
        for language in ("en","es"):
            query = profile[language]
            # Same English article universe for the engine comparison.
            # Spanish requests search English and Spanish articles to test cross-language retrieval.
            candidate_language = "en" if language == "en" else "Todos"
            semantic = recommend(catalog, query, engine="semantico", top_k=5, embeddings=vectors,
                model=model, fields=[profile["field"]], language=candidate_language, generate_evidence=False)
            outputs = {"semantico":semantic}
            if language == "en":
                outputs["tfidf"] = recommend(catalog, query, engine="tfidf", top_k=5,
                    fields=[profile["field"]], language="en", generate_evidence=False)
            for engine_name, results in outputs.items():
                for rank, (_, article) in enumerate(results.iterrows(), start=1):
                    rows.append({"profile_id":profile["id"],"profile_topic":profile["topic"],
                        "query_language":language,"anonymous_engine":engine_to_label[engine_name],
                        "rank":rank,"article_id":article["id"],"title":article["title"],
                        "abstract":article["abstract"],"field":article["field"],"year":article["year"],
                        "article_language":article["language"],
                        "url":article["url"]})
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    candidates = pd.DataFrame(rows)
    candidates.to_csv(ARTIFACTS_DIR / "evaluation_candidates.csv", index=False)
    rating_columns = ["profile_id", "profile_topic", "article_id", "title", "abstract", "field", "year", "article_language", "url"]
    ratings = candidates[rating_columns].drop_duplicates(["profile_id", "article_id"]).copy()
    ratings["relevance"] = ""
    ratings.to_csv(ARTIFACTS_DIR / "evaluation_ratings.csv", index=False)
    (ARTIFACTS_DIR / "evaluation_blind_key.json").write_text(
        json.dumps({label:engine for engine,label in engine_to_label.items()},indent=2),encoding="utf-8")
    (ARTIFACTS_DIR / "evaluation_profiles.json").write_text(
        json.dumps(PROFILES,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Archivo de evaluación: {ARTIFACTS_DIR / 'evaluation_candidates.csv'}")
    print(f"Resultados ordenados: {len(candidates)}; artículos únicos a calificar: {len(ratings)}")
    print(f"Completa relevance en {ARTIFACTS_DIR / 'evaluation_ratings.csv'}: 0 (no pertinente), 1 (parcial), 2 (directa).")


if __name__ == "__main__":
    main()
