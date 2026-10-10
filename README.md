# Recotesis

Prototipo académico que recomienda artículos científicos de varias disciplinas a partir de una descripción del proyecto de grado o tesis. Las consultas y el catálogo admiten español e inglés. La aplicación ordena los artículos por afinidad temática; no mide calidad científica ni reemplaza la revisión académica.

Las fuentes de metadatos son [OpenAlex](https://openalex.org/) y la [API ArticleMeta de SciELO](https://github.com/scieloorg/articles_meta/blob/master/docs/source/index.rst). OpenAlex da amplitud multidisciplinaria; SciELO incorpora revistas de sus colecciones nacionales y temáticas. El catálogo es una muestra reproducible de artículos publicados entre 2016 y 2025. Se conserva el origen de cada registro, la fecha, los filtros, la distribución del conjunto y los hashes para identificar cada versión de los datos.

## Requisitos e instalación

El entorno preparado y comprobado usa Python 3.12. Desde la carpeta del proyecto:

~~~bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
~~~

Para instalar en Python 3.11, usa python -m pip install -e ".[dev]". El archivo requirements-lock.txt fija las versiones exactas comprobadas en el entorno de desarrollo.

OpenAlex ofrece una clave gratuita para aumentar la cuota de consultas; no es obligatoria para una muestra moderada. Si tienes una clave, defínela como variable de entorno OPENALEX_API_KEY. No la guardes en el repositorio.

## Preparar los datos y el índice

~~~bash
python scripts/download_data.py
python scripts/build_index.py
~~~

El proceso consulta los campos académicos actuales de OpenAlex y crea muestras con semilla fija. Busca hasta 300 artículos válidos por cada uno de sus 26 campos; requiere un mínimo de 100. También elige hasta tres páginas aleatorias de 100 registros por cada colección SciELO incluida. La muestra usa la ventana de procesamiento de ArticleMeta de 2016 a 2025 y luego filtra por año de publicación. El ritmo se limita para respetar el servicio; descargar todas las colecciones puede tardar varios minutos. Ambos orígenes se normalizan al mismo esquema, se deduplican por identificador, DOI normalizado y título, y conservan su procedencia en `source_database`.

Para preparar solo una fuente o ajustar el tamaño de SciELO:

~~~bash
python scripts/download_data.py --sources scielo --scielo-pages-per-collection 5
python scripts/download_data.py --sources openalex
python scripts/download_data.py --sources scielo --scielo-collections col mex scl
~~~

La preparación combina los archivos crudos disponibles en `data/raw/`, así que los originales de OpenAlex y SciELO se conservan por separado. Las clasificaciones de SciELO siguen las categorías de sus revistas y no se equiparan artificialmente con los 26 campos de OpenAlex. SciELO publica metadatos ArticleMeta en un esquema JSON heredado; el código convierte título, resumen, autores, idioma, palabras clave, año, DOI y enlaces. Los términos de reutilización pueden depender de cada publicación; esta versión usa metadatos y resúmenes, no descarga el cuerpo completo.

La muestra OpenAlex preparada el 10 de octubre de 2026 produjo 7.800 registros candidatos y 6.641 artículos utilizables. En la extracción de SciELO se consultaron 19 colecciones y se obtuvo una página de registros en 18 de ellas; quedaron 1.152 artículos válidos tras la normalización y deduplicación. El catálogo combinado tiene 7.793 artículos: 6.625 en inglés y 1.168 en español. La muestra SciELO local usa una página por colección; el valor predeterminado para nuevas descargas es tres. El manifiesto registra offsets elegidos, filtros, conteos y hashes para identificar esta versión. La interfaz permite consultar en ambos idiomas; para responder en español puede recomendar publicaciones cuyo idioma sea inglés.

Los originales quedan en data/raw/openalex_works.jsonl.gz. El catálogo procesado y su manifiesto quedan en data/processed/. Los vectores semánticos y el índice TF-IDF se guardan en artifacts/. Los archivos grandes se excluyen de Git. El manifiesto registra la fecha de extracción, los filtros y los hashes de origen y catálogo.

## Ejecutar la aplicación

~~~bash
streamlit run app.py
~~~

Escribe una descripción de al menos cinco palabras. Puedes añadir palabras clave, filtrar por área, años e idioma y elegir el motor semántico o TF-IDF. TF-IDF sirve para consultas en inglés. Los resultados muestran título, autores, año, resumen, enlace y similitud coseno. La puntuación ordena los resultados; no es una probabilidad ni una valoración de calidad.

## Evaluación manual y sesgos

~~~bash
python scripts/prepare_evaluation.py
~~~

El archivo artifacts/evaluation_candidates.csv contiene resultados ordenados de perfiles en seis temas y consultas en inglés y español. El archivo artifacts/evaluation_ratings.csv presenta cada artículo una sola vez por perfil (64 juicios en esta muestra) para facilitar la evaluación; califica relevance como 0 (no pertinente), 1 (parcialmente pertinente) o 2 (directamente pertinente). Después ejecuta:

~~~bash
python scripts/score_evaluation.py
python scripts/analyze_bias.py
~~~

Las métricas quedan en artifacts/evaluation_metrics.csv. Las tablas de cobertura por campo, idioma y periodo quedan en artifacts/bias_coverage_by_field.csv y artifacts/bias_coverage_by_field_language.csv; `analyze_bias.py` también crea tablas por fuente, idioma de la fuente y campo de la fuente. La llave de los motores A y B está en artifacts/evaluation_blind_key.json; consúltala después de calificar.

La comparación de motores usa consultas inglesas y los mismos candidatos. Las consultas bilingües evalúan el motor semántico. Precision@5 y nDCG@5 dependen de juicios humanos. No se calcula recall porque no existen etiquetas para todos los artículos del catálogo.

Para ejecutar las pruebas automatizadas:

~~~bash
pytest -q
~~~

## Notebook, diagrama e informe

El notebook notebooks/01_recomendador_explicado.ipynb presenta los datos, la representación textual, los dos métodos, los resultados y sus limitaciones. El diagrama está en docs/arquitectura.mmd. El informe de proyecto y su matriz de cumplimiento están en docs/informe_proyecto.md.

## Decisiones y limitaciones

- El sistema usa título y resumen; la cobertura depende de la disponibilidad de metadatos en OpenAlex y SciELO. La muestra SciELO es acotada y no representa todas sus publicaciones.
- ArticleMeta no informa de manera consistente el estado de retractación; los registros SciELO no se pueden filtrar con el mismo criterio disponible en OpenAlex.
- La muestra equilibra su tamaño inicial por disciplina, pero no corrige todos los sesgos de la fuente.
- Cuando falta el idioma en OpenAlex, se infiere del resumen y se conserva esa información en el catálogo.
- E5 procesa un máximo de 512 tokens por entrada; los textos largos se truncan.
- Un artículo nuevo requiere limpiar el catálogo y regenerar ambos índices.
- El prototipo no conserva consultas ni perfiles personales.
