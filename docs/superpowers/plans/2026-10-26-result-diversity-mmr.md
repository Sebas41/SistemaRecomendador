# Control de diversidad MMR en recomendaciones Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Añadir una opción visible para equilibrar afinidad y variedad en las recomendaciones semánticas.

**Architecture:** El motor recupera y reordena los candidatos como ahora; antes de cortar el top 5/10, aplica MMR sobre esos candidatos usando sus vectores BGE normalizados. La interfaz ofrece tres niveles y conserva el puntaje original de afinidad, explicando que el orden puede incorporar diversidad.

**Tech Stack:** Python 3.11/3.12, NumPy, pandas, Streamlit, Sentence Transformers.

**Spec:** Mitigación E1 en `docs/informe_proyecto.md` §3.2, donde se propone MMR con λ≈0,7.

## Global Constraints

- Mantener `BAAI/bge-m3` como representación semántica del catálogo.
- Aplicar diversidad únicamente a la búsqueda semántica; TF-IDF conserva su orden léxico.
- Aplicar MMR al shortlist existente, nunca al catálogo completo.
- Mostrar el puntaje como afinidad del modelo, no como probabilidad ni calidad.
- No reconstruir vectores ni cambiar datos, filtros o parámetros de recuperación.
- No ejecutar ni añadir pruebas automatizadas en esta tarea.

---

### Task 1: Aplicar MMR al shortlist semántico

**Files:**
- Modify: `src/sisreco/engine.py`

**Interfaces:**
- Add `_mmr_order(relevance: np.ndarray, vectors: np.ndarray, relevance_weight: float) -> np.ndarray`.
- Add `diversity_lambda: float = 1.0` to `recommend(...)`; λ=1 conserva el orden actual.

- [x] Añadir una función MMR voraz que normalice relevancia a [0,1], penalice la similitud máxima con artículos ya elegidos y mantenga desempates estables.
- [x] Después del reranker, extraer vectores BGE de los candidatos por ID, obtener el orden MMR y seleccionar el top_k antes de generar evidencia.
- [x] Validar λ entre 0 y 1 y conservar la ruta TF-IDF sin cambios.

### Task 2: Exponer el nivel de diversidad en Streamlit

**Files:**
- Modify: `app.py`

**Interfaces:**
- Añadir un selector semántico: `Más afines`→λ=1.0, `Equilibrados`→λ=0.7, `Más variados`→λ=0.5.
- Guardar la opción por separado de `options`, ya que ese diccionario también se pasa a `recommend_similar`.

- [x] Mostrar el selector dentro del formulario solo para búsqueda semántica.
- [x] Pasar λ a `recommend` sin alterar la búsqueda TF-IDF ni la navegación a artículos similares.
- [x] Explicar en resultados que la puntuación mide afinidad y el selector puede modificar el orden para aumentar variedad.

### Task 3: Documentar la mitigación implementada

**Files:**
- Modify: `README.md`
- Modify: `docs/informe_proyecto.md`

- [x] Describir los tres niveles y el funcionamiento del MMR en la guía del usuario.
- [x] Cambiar la fila E1 de mitigación de propuesta a implementada en la interfaz, aclarando que el impacto cuantitativo aún requiere comparación con ILD y pertinencia humana.

### Verification

- [x] Revisar el diff para asegurar que λ=1 preserva el comportamiento actual y que la búsqueda TF-IDF no cambia.
- [x] No ejecutar pruebas ni build del índice; el usuario no solicitó pruebas y el índice existente debe reutilizarse.
