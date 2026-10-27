# Guardar artículos y exportar referencias

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Permitir guardar artículos recomendados durante la sesión y exportar sus referencias en formato RIS.

**Architecture:** Mantener los identificadores guardados en `st.session_state`, reutilizando el catálogo cargado para mostrar y exportar los registros. Generar RIS desde los metadatos disponibles sin añadir dependencias.

**Tech Stack:** Python, pandas, Streamlit.

**Spec:** Solicitud del usuario: guardar artículos y exportar referencias para importarlas en un gestor bibliográfico.

## Global Constraints

- No cambiar recomendación, catálogo, índice ni datos.
- Guardados temporales por sesión; no requerir login ni almacenamiento externo.
- Omitir campos bibliográficos no disponibles y exportar RIS UTF-8.
- No ejecutar ni añadir pruebas automatizadas en esta tarea.

---

### Task 1: Agregar guardado de artículos y panel de guardados

**Files:**
- Modify: `app.py`

**Interfaces:**
- `toggle_saved(article_id: str) -> None` actualiza el conjunto `saved_article_ids` de la sesión.
- `export_ris(articles: pd.DataFrame) -> str` serializa las referencias en RIS.

- [x] Añadir el estado de sesión y un control Guardar/Quitar en cada tarjeta de artículo.
- [x] Mostrar una sección de guardados con títulos y opción para quitar artículos.
- [x] Incluir un botón de descarga `.ris` con autores, título, año, DOI/URL y palabras clave disponibles.

### Task 2: Documentar el uso

**Files:**
- Modify: `README.md`

- [x] Explicar que los guardados duran la sesión y que RIS se puede importar en un gestor bibliográfico.

### Verification

- [x] Revisar manualmente el diff y confirmar que no requiere reconstruir el índice ni instalar dependencias.
- [x] No ejecutar pruebas automatizadas.
