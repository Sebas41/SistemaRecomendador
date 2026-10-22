# Ciencia a tu tesis

Prototipo académico que recomienda artículos científicos a estudiantes que preparan su proyecto de grado o tesis. El estudiante describe su proyecto en español o en inglés, con palabras clave opcionales, y recibe diez artículos afines como punto de partida de su revisión bibliográfica. Desde cada resultado puede explorar lecturas similares. El sistema ordena por afinidad temática: no mide la calidad científica ni reemplaza la lectura crítica del estudiante.

Proyecto del curso Sistemas Recomendadores, Universidad Icesi. Grupo 8: Sebastian Erazo Ochoa, Ricardo Andrés Chamorro Martinez y Juan Camilo Muñoz Barco. El informe completo está en [docs/informe_proyecto.md](docs/informe_proyecto.md).

## Cómo funciona

1. **Catálogo.** 108.252 artículos publicados entre 2016 y 2025: una muestra estratificada de los 26 campos de [OpenAlex](https://openalex.org/) y una muestra de las 19 colecciones de [SciELO ArticleMeta](https://github.com/scieloorg/articles_meta/blob/master/docs/source/index.rst). La preparación limpia los resúmenes, asigna el idioma detectado en el resumen y deduplica por identificador, DOI y título.
2. **Representación.** Cada artículo se representa con el texto `título. palabras clave. topic. resumen`, codificado con [`BAAI/bge-m3`](https://huggingface.co/BAAI/bge-m3) hasta 1.024 tokens. La descripción del estudiante y sus palabras clave se codifican con el mismo modelo.
3. **Recomendación.** Se aplican los filtros elegidos (campo, años, idioma), se recuperan los 100 artículos más cercanos por similitud coseno y [`BAAI/bge-reranker-v2-m3`](https://huggingface.co/BAAI/bge-reranker-v2-m3) los reordena leyendo la consulta y cada artículo juntos. Se muestran los 10 primeros, sin umbral.
4. **Artículos similares.** Desde un resultado, el sistema compara su vector con el resto del catálogo y conserva los filtros de la búsqueda.
5. **Referencia léxica.** TF-IDF de unigramas y bigramas sobre los artículos en inglés, disponible en la interfaz para comparar.

La configuración final se eligió comparando cinco alternativas con 200 consultas de ítem conocido y una verificación humana ciega. Los resultados están en el informe.

## Instalación

El entorno comprobado usa Python 3.12:

~~~bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
~~~

También funciona con Python 3.11 mediante `python -m pip install -e ".[dev]"`. Los modelos se descargan de Hugging Face la primera vez; la aplicación luego los usa desde la caché local, sin conexión. Con GPU, bge-m3 y su reordenador se cargan en media precisión (fp16); en CPU funcionan, pero cada búsqueda tarda más.

OpenAlex ofrece una clave gratuita que amplía la cuota de consultas. Para usarla, copia la plantilla y reemplaza el valor de ejemplo (el archivo `.env` está excluido de Git):

~~~bash
cp .env.example .env
~~~

## Preparar los datos y los índices

~~~bash
python scripts/download_data.py
python scripts/build_index.py
~~~

`download_data.py` descarga las muestras, guarda los originales en `data/raw/` y construye el catálogo limpio en `data/processed/catalog.parquet`, con un manifiesto que registra la fecha de extracción, los filtros, los conteos, el informe de limpieza y los hashes. Si los archivos crudos ya existen, el catálogo puede reconstruirse sin volver a descargar:

~~~bash
python -c "from sisreco.catalog import build_catalog; build_catalog()"
~~~

`build_index.py` codifica el catálogo con bge-m3 (unos 70 minutos en una GPU de 4 GB), construye el índice TF-IDF y descarga el reordenador. Para reconstruir solo TF-IDF: `python scripts/build_index.py --tfidf-only`. Los archivos grandes quedan en `artifacts/` y no se versionan.

Opciones de descarga útiles:

~~~bash
python scripts/download_data.py --sources openalex
python scripts/download_data.py --sources scielo --scielo-pages-per-collection 5 --minimum-catalog-size 0
~~~

## Ejecutar la aplicación

~~~bash
streamlit run app.py
~~~

Escribe una descripción de al menos cinco palabras. Puedes añadir palabras clave, filtrar por disciplina, periodo e idioma y elegir entre la búsqueda semántica y la referencia TF-IDF (solo inglés). Cada resultado muestra autores, año, campo, fuente, resumen, enlace, un fragmento del resumen cercano a la consulta y su puntaje. El puntaje ordena los resultados; no es una probabilidad ni una valoración de calidad. **Ver artículos similares** toma un resultado como referencia; puedes volver a la lista anterior o a la búsqueda inicial. La navegación se guarda solo durante la sesión.

## Reproducir la evaluación

Los conjuntos de evaluación están en `data/evaluation/`: 200 consultas de ítem conocido (`known_item.jsonl`) y 10 perfiles bilingües para la verificación humana (`topics.jsonl`).

~~~bash
python scripts/evaluate_configs.py            # ejecuta las configuraciones A–E sobre las 200 consultas
python scripts/score_known_item.py --configs A B C D E
python scripts/prepare_evaluation.py --chosen C   # hoja ciega para calificar
python scripts/score_evaluation.py --ratings artifacts/human_ratings_<iniciales>.csv
python scripts/analyze_bias.py
python scripts/diagnose_retrieval.py          # etapas por perfil y auditoría de los vectores
~~~

`evaluate_configs.py` construye los índices de las alternativas que no usa la aplicación (e5-small y el índice léxico bilingüe) la primera vez que los necesita. La guía de calificación está en [docs/guia_calificacion.md](docs/guia_calificacion.md); no consultes `artifacts/human_ratings_key.csv` antes de terminar de calificar. Los resultados quedan en `artifacts/` (`evaluation_metrics.csv`, `evaluation_comparison.csv`, `evaluation_breakdown.csv`, `evaluation_exposure.csv`, `human_metrics.csv`, `human_comparison.csv`, `bias_coverage_*.csv`) junto con `evaluation_manifest.json`, que registra modelos, revisiones, parámetros, semilla y hash del catálogo.

Los scripts `sample_known_items.py` y `build_known_item_set.py` documentan cómo se seleccionaron los artículos de origen y cómo se validaron las descripciones de las consultas.

Pruebas automatizadas:

~~~bash
pytest -q
~~~

## Notebook, diagrama e informe

- [notebooks/01_recomendador_explicado.ipynb](notebooks/01_recomendador_explicado.ipynb): análisis exploratorio del catálogo, preparación, modelo, ejemplos y evaluación, con una explicación en cada sección.
- [docs/arquitectura.mmd](docs/arquitectura.mmd): diagrama de módulos en Mermaid.
- [docs/informe_proyecto.md](docs/informe_proyecto.md): informe con las tres partes del taller.

## Limitaciones

- El 5,3 % del catálogo está en español y el 3,3 % proviene de SciELO. En física, materiales, química, ingeniería química y bioquímica, el español no llega al 1 %.
- Con consultas en español, el reordenador prioriza artículos en español; según la verificación humana, eso a veces trae artículos menos precisos al primer puesto.
- Solo se usan metadatos y resúmenes. Las categorías de SciELO no equivalen a los campos de OpenAlex, y su `topic` es la primera palabra clave de la revista.
- ArticleMeta no informa de manera consistente si un artículo fue retractado; los registros de SciELO no se filtran con el mismo criterio que los de OpenAlex.
- Agregar artículos exige reconstruir el catálogo y recodificar el índice.
- El prototipo no guarda consultas ni perfiles entre sesiones.
