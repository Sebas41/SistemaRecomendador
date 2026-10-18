#!/usr/bin/env python3
"""Reproduce búsquedas de proyectos para inspeccionar pertinencia, sin calificarlas."""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from time import perf_counter

import numpy as np
import pandas as pd

from sisreco.engine import _load_reranker, _load_sentence_model, encode_documents, load_embeddings, recommend
from sisreco.settings import ARTIFACTS_DIR, CATALOG, DATA_MANIFEST, EMBEDDINGS_MANIFEST

PROFILES = {
    "arquitectura_empresarial": "Diseñar un sistema de agentes de inteligencia artificial que apoye la arquitectura empresarial, identificando dependencias entre procesos de negocio, aplicaciones y capacidades organizacionales para proponer mejoras alineadas con la estrategia de la empresa.",
    "energia_solar": "Desarrollar un modelo de aprendizaje automático para pronosticar la generación de energía de paneles solares a partir de datos meteorológicos e irradiancia, y comparar su precisión con modelos estadísticos tradicionales.",
    "diabetes": "Desarrollar y evaluar una aplicación móvil para apoyar el autocuidado de adultos con diabetes tipo 2, mediante registro de glucosa, recordatorios de medicación y seguimiento de la adherencia al tratamiento.",
    "educacion": "Evaluar el efecto de la gamificación en la comprensión lectora de estudiantes de educación primaria, comparando una intervención con actividades digitales y recompensas con clases de lectura tradicionales.",
    "agua": "Diseñar un sistema de monitoreo de calidad del agua en ríos mediante sensores de bajo costo e Internet de las cosas, midiendo pH, turbidez y temperatura para detectar cambios y generar alertas tempranas de contaminación.",
    "credito": "Comparar modelos de aprendizaje automático para predecir el incumplimiento de créditos en pequeñas empresas, utilizando indicadores financieros y técnicas de explicabilidad para interpretar los factores asociados al riesgo.",
    "lenguas": "Crear un archivo digital participativo para documentar y preservar una lengua indígena en riesgo, mediante grabaciones de relatos orales, transcripciones y colaboración con hablantes de la comunidad.",
    "cultivos": "Desarrollar un sistema de visión por computador para detectar enfermedades en hojas de tomate a partir de fotografías tomadas con teléfonos móviles, utilizando redes neuronales convolucionales y evaluando su desempeño en condiciones de campo.",
    "arquitectura_empresarial_en": "Design an artificial intelligence agent system to support enterprise architecture by identifying dependencies between business processes, applications and organizational capabilities, and proposing improvements aligned with the company's strategy.",
    "energia_solar_en": "Develop a machine learning model to forecast solar panel energy generation from weather and irradiance data, and compare its accuracy with traditional statistical models.",
}


def diagnose(catalog, vectors, model, report):
    """Contrasta las etapas y una muestra de vectores; no cambia el recomendador."""
    diagnostics = []
    for profile in report["profiles"]:
        if profile["name"] not in {"energia_solar", "cultivos", "credito"}:
            continue
        query = model.encode([f"query: {profile['query']}"], normalize_embeddings=True,
                             convert_to_numpy=True, show_progress_bar=False)
        order = np.argsort(-(vectors @ query.reshape(-1)), kind="stable")
        ranks = dict(zip(catalog.iloc[order]["id"], range(1, len(catalog) + 1)))
        diagnostics.append({"name": profile["name"],
            "before": catalog.iloc[order[:5]][["id", "title", "abstract", "url"]].to_dict("records"),
            "after": [dict(id=row["id"], title=row["title"], e5_rank=ranks[row["id"]],
                           reranker_rank=i + 1, score=row["score"])
                      for i, row in enumerate(profile["results"])]})
    (ARTIFACTS_DIR / "project_query_diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    # Incluye aciertos y errores observados, tanto en español como en inglés.
    sample_ids = ["W4404651996", "W4386307387", "W4408118937", "W2973763692", "W7116704433", "W7215807552"]
    positions = [int(np.flatnonzero(catalog["id"].eq(f"https://openalex.org/{i}"))[0]) for i in sample_ids]
    sample = catalog.iloc[positions]
    fresh = encode_documents(sample, model=model, show_progress_bar=False)
    old = vectors[positions]
    cosines = (old * fresh).sum(axis=1) / (np.linalg.norm(old, axis=1) * np.linalg.norm(fresh, axis=1))
    records = [dict(id=row["id"], title=row["title"], saved_vs_current_cosine=float(score))
               for (_, row), score in zip(sample.iterrows(), cosines)]
    (ARTIFACTS_DIR / "index_audit_sample.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Diagnóstico guardado: tres perfiles y seis vectores.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics-only", action="store_true",
                        help="Revisa etapas y vectores usando la última salida de consultas; no repite el reranking.")
    args = parser.parse_args()
    catalog = pd.read_parquet(CATALOG)
    vectors = load_embeddings(catalog)
    model = _load_sentence_model(local_files_only=True)
    manifest = json.loads(DATA_MANIFEST.read_text())
    output = ARTIFACTS_DIR / "project_query_audit.json"
    if args.diagnostics_only:
        report = json.loads(output.read_text())
        if report["catalog_sha256"] != manifest["catalog_sha256"]:
            raise ValueError("El catálogo cambió. Ejecuta primero la auditoría de consultas.")
        diagnose(catalog, vectors, model, report)
        return
    reranker = _load_reranker(local_files_only=True)
    report = {
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "catalog_records": len(catalog), "catalog_sha256": manifest["catalog_sha256"],
        "embedding_revision": json.loads(EMBEDDINGS_MANIFEST.read_text())["revision"],
        "method": "Semantic search, top 5, no discipline/year/language filters. Evidence generation disabled; ranking unchanged.",
        "note": "Raw retrieval results. Any later assistant review is exploratory, not human ground truth.",
        "profiles": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = ["id", "title", "abstract", "year", "field", "topic", "language", "url", "score", "semantic_score"]
    for name, query in PROFILES.items():
        started = perf_counter()
        results = recommend(catalog, query, top_k=5, embeddings=vectors,
                            model=model, reranker=reranker, generate_evidence=False)
        report["profiles"].append({"name": name, "query": query,
            "seconds": round(perf_counter() - started, 3),
            "results": results[columns].to_dict("records")})
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{name}: {len(results)} resultados ({report['profiles'][-1]['seconds']} s)", flush=True)
    print(output)


if __name__ == "__main__":
    main()
