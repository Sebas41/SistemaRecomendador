# Pruebas de regresión del recomendador

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Añadir pruebas rápidas para MMR, referencias RIS, guardado de artículos y fallback de memoria, sin modelos ni artefactos reales.

**Architecture:** Probar MMR y serialización RIS como funciones puras con datos pequeños. Usar Streamlit AppTest y modelos simulados para cubrir guardar/quitar artículos y el fallback al fallar el reordenador.

**Tech Stack:** pytest, NumPy, pandas, Streamlit AppTest.

**Spec:** Mejoras recientes en `src/sisreco/engine.py` y `app.py`.

## Global Constraints

- No descargar modelos ni reconstruir índices durante las pruebas.
- Mantener el catálogo de prueba pequeño y determinista.
- No alterar la estrategia semántica del recomendador.

---

### Task 1: Probar MMR y fallback sin reordenador

**Files:**
- Modify: `tests/test_core.py`

- [x] Probar que λ=1 conserva el orden por relevancia y que MMR selecciona un resultado menos redundante.
- [x] Probar `recommend(..., rerank_enabled=False)` con un reordenador simulado que falla si se invoca; confirmar que el score sigue siendo la similitud del recuperador.

### Task 2: Probar RIS como serialización pura

**Files:**
- Create: `src/sisreco/references.py`
- Create: `tests/test_references.py`
- Modify: `app.py`

- [x] Extraer `export_ris` a un módulo importable sin ejecutar Streamlit.
- [x] Probar exportación de título, autores, año, DOI, URL, palabras clave y resumen; comprobar omisión de valores ausentes.

### Task 3: Probar guardado y fallback de la interfaz

**Files:**
- Modify: `tests/test_app.py`

- [x] Probar que guardar y quitar un resultado actualiza el estado de sesión y que aparece la descarga RIS.
- [x] Simular WinError 1455 al cargar el reordenador y confirmar que la búsqueda conserva resultados semánticos sin excepción de Streamlit.

### Verification

- [x] Ejecutar las pruebas focalizadas con `pytest tests/test_core.py tests/test_references.py tests/test_app.py` (35 pasaron).
- [x] Confirmar que no se cargan modelos reales y que el índice de producción no se modifica.
