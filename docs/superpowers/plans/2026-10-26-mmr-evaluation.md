# Evaluación de diversidad MMR

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Comparar λ=1, 0,7 y 0,5 por diversidad de listas y pertinencia humana usando los perfiles bilingües existentes.

**Architecture:** Un script genera para cada perfil e idioma los top 10 tras aplicar MMR al mismo shortlist de 100 candidatos, calcula ILD@10 y crea una hoja ciega de calificación deduplicada por perfil-artículo. Un segundo script combina los juicios con la llave y produce P@5, P@5 de grado 2, nDCG@10 y comparaciones pareadas.

**Tech Stack:** Python, pandas, NumPy, modelos del proyecto, CSV.

**Spec:** Mitigación E1 en `docs/informe_proyecto.md` §3.2; perfiles en `data/evaluation/topics.jsonl`.

## Global Constraints

- Mantener fijos el catálogo, los vectores, los filtros, el reranker y el shortlist de 100 candidatos.
- Probar MMR solo con λ=1, 0,7 y 0,5; evaluar el top 10 de cada lista.
- La hoja humana no debe revelar lambda, idioma de consulta ni posición; guardar la llave por separado.
- No reconstruir los vectores ni alterar el catálogo.
- No ejecutar los modelos reales durante pruebas automatizadas.

---

### Task 1: Generar rankings, ILD y hoja ciega

**Files:**
- Create: `scripts/evaluate_mmr.py`
- Create: `src/sisreco/mmr_evaluation.py`
- Create: `tests/test_mmr_evaluation.py`

**Interfaces:**
- La CLI genera `artifacts/mmr/rankings_key.csv`, `artifacts/mmr/diversity.csv`, `artifacts/mmr/human_ratings.csv`, `artifacts/mmr/human_ratings_key.csv` y `artifacts/mmr/manifest.json`.
- Las listas de ranking registran lambda, perfil, idioma, rango, artículo y score; la hoja ciega contiene el perfil, metadatos del artículo y `relevance` vacío.

- [x] Procesar los 10 perfiles en español e inglés con λ=1, 0,7 y 0,5, `top_k=10` y `generate_evidence=False`.
- [x] Calcular ILD@10 con los vectores normalizados del catálogo y guardar las tres vistas de archivo.
- [x] Deduplicar calificaciones por perfil y artículo; mezclar filas con semilla fija y guardar la llave aparte.
- [x] Probar la construcción de hoja ciega y métricas de ILD usando datos sintéticos.

### Task 2: Puntuar juicios humanos

**Files:**
- Create: `scripts/score_mmr.py`
- Modify: `tests/test_mmr_evaluation.py`

- [x] Validar que `relevance` esté completa y contenga únicamente 0, 1 o 2.
- [x] Calcular P@5, P@5 grado 2 y nDCG@10 por perfil, idioma y lambda.
- [x] Comparar lambdas de forma pareada por perfil-idioma mediante prueba de aleatorización y exportar CSV de resumen.
- [x] Añadir pruebas con rankings y juicios sintéticos.

### Task 3: Documentar el procedimiento

**Files:**
- Modify: `README.md`
- Modify: `docs/informe_proyecto.md`

- [x] Documentar comandos de generación, calificación ciega y puntuación.
- [x] Mantener explícito que el impacto real queda pendiente hasta calificar la hoja y que los resultados deben interpretarse con el número de perfiles disponible.

### Verification

- [x] Ejecutar las pruebas de evaluación MMR y la suite completa (53 pasaron).
- [x] Validar `--help` de ambas CLIs sin cargar modelos.
- [x] No ejecutar la evaluación completa: requiere cargar modelos y depende de memoria disponible; dejar instrucciones para correrla en equipo con recursos suficientes.
