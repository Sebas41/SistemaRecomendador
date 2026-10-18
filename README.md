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

OpenAlex ofrece una clave gratuita para aumentar la cuota de consultas. Crea el archivo local desde la plantilla y reemplaza el valor de ejemplo; `.env` está excluido de Git:

~~~bash
cp .env.example .env
~~~

La clave también puede definirse en la variable de entorno `OPENALEX_API_KEY`. No la compartas ni la guardes en el repositorio.

## Preparar los datos y el índice

~~~bash
python scripts/download_data.py
python scripts/build_index.py
~~~

El proceso consulta los campos académicos actuales de OpenAlex y crea muestras con semilla fija. Busca hasta 4.800 artículos válidos por cada uno de sus 26 campos, a partir de muestras de hasta 6.000 trabajos por intento; cada campo debe aportar al menos 100. SciELO elige hasta tres páginas aleatorias de 100 registros por cada colección incluida. La muestra usa la ventana de procesamiento de ArticleMeta de 2016 a 2025 y luego filtra por año de publicación. OpenAlex guarda un checkpoint por campo y SciELO por página para poder reanudar una extracción interrumpida. Ambos orígenes se normalizan al mismo esquema, se deduplican por identificador, DOI normalizado y título, y conservan su procedencia en `source_database`.

La preparación exige por defecto un catálogo limpio de al menos 100.000 artículos y se detiene con un mensaje si no alcanza ese tamaño. El API de OpenAlex tiene una cuota diaria anónima compartida; se recomienda usar una clave propia gratuita con `.env` para esta descarga amplia.

Para preparar solo una fuente o ajustar el tamaño de SciELO:

~~~bash
python scripts/download_data.py --sources scielo --scielo-pages-per-collection 5 --minimum-catalog-size 0
python scripts/download_data.py --sources openalex
python scripts/download_data.py --sources scielo --scielo-collections col mex scl --minimum-catalog-size 0
~~~

La preparación combina los archivos crudos disponibles en `data/raw/`, así que los originales de OpenAlex y SciELO se conservan por separado. Las clasificaciones de SciELO siguen las categorías de sus revistas y no se equiparan artificialmente con los 26 campos de OpenAlex. SciELO publica metadatos ArticleMeta en un esquema JSON heredado; el código convierte título, resumen, autores, idioma, palabras clave, año, DOI y enlaces. Los términos de reutilización pueden depender de cada publicación; esta versión usa metadatos y resúmenes, no descarga el cuerpo completo.

La extracción actual produjo 124.759 registros válidos de OpenAlex en sus 26 campos y consultó tres páginas por cada una de las 19 colecciones SciELO. Tras combinar ambas fuentes, filtrar metadatos y deduplicar, el catálogo contiene **110.144 artículos**: 106.615 de OpenAlex y 3.529 de SciELO. De ellos, 103.734 están en inglés y 6.410 en español. El manifiesto local conserva fecha, filtros, conteos por campo e idioma y hashes para identificar esta versión. La interfaz admite consultas en ambos idiomas y puede recomendar artículos en inglés para una consulta en español.

Los originales quedan en data/raw/openalex_works.jsonl.gz. El catálogo procesado y su manifiesto quedan en data/processed/. Los vectores semánticos y el índice TF-IDF se guardan en artifacts/. Los archivos grandes se excluyen de Git. El manifiesto registra la fecha de extracción, los filtros y los hashes de origen y catálogo.

La preparación usa CUDA cuando está disponible, Apple Metal (MPS) en equipos compatibles y CPU como alternativa. También descarga el reranker multilingüe que utiliza la aplicación. Una vez preparados los datos y modelos, las consultas funcionan localmente.

## Ejecutar la aplicación

~~~bash
streamlit run app.py
~~~

Escribe una descripción de al menos cinco palabras. Puedes añadir palabras clave, filtrar por disciplina, años e idioma y elegir el recomendador semántico, el híbrido experimental o TF-IDF. E5 recupera hasta 500 candidatos por similitud coseno y el cross-encoder multilingüe los reordena; se descartan puntajes negativos para todas las consultas. El híbrido añade un índice léxico multilingüe de título, resumen y palabras clave, y fusiona sus posiciones con E5 antes de reordenar. Sigue siendo experimental: no sustituye el motor semántico hasta completar la evaluación humana. TF-IDF permanece como referencia en inglés y devuelve una lista vacía cuando no hay vocabulario compartido.

Cada resultado incluye **Ver artículos similares**. Al seleccionarlo, el artículo se convierte en la referencia: el sistema compara su vector de título y resumen con los demás vectores del catálogo, conserva los filtros de la búsqueda inicial y excluye el artículo elegido y sus duplicados por DOI o título. Puedes seleccionar otra lectura, volver a la lista anterior o regresar a la búsqueda inicial. Las últimas diez listas se guardan solo en la sesión de Streamlit; no se crea una cuenta ni un historial persistente.

Los resultados permanecen visibles mientras navegas. Los cambios en el formulario se aplican al pulsar Buscar artículos. El modo de artículos similares reutiliza los vectores existentes, sin descargar modelos ni volver a codificar el catálogo. No necesitas regenerar los índices para activar esta función si ya estaban preparados. La interfaz carga los modelos de búsqueda exclusivamente desde la caché local; si faltan, indica cómo prepararlos.

Las tarjetas muestran autores, año, fuente, resumen, enlace y puntuación. La búsqueda semántica muestra el puntaje del reordenador; Ver similares muestra coseno entre artículos. Son escalas distintas: ninguna es una probabilidad ni una valoración de calidad. La exploración se basa en contenido y en la selección explícita de un artículo, no en valoraciones de otros usuarios.

Para guardar ejemplos reproducibles sobre el catálogo instalado, sin modificar la evaluación manual:

~~~bash
python scripts/check_recommendations.py
python scripts/check_recommendations.py --article-id https://openalex.org/W3131117291
~~~

El segundo comando explora directamente un artículo del catálogo y no carga modelos. El archivo local `artifacts/recommendation_examples.json` registra títulos, identificadores, puntuaciones, tiempos y hash del catálogo. Son ejemplos de funcionamiento, no métricas de relevancia.

## Evaluación manual y sesgos

La [auditoría exploratoria del 18 de octubre de 2026](docs/pruebas_pertinencia_2026-10-18.md) revisa diez descripciones de proyectos y documenta aciertos y errores de pertinencia. Incluye las consultas, los artículos, las razones de cada valoración y cómo repetir las pruebas. Sus valoraciones son del asistente de IA y no sustituyen los juicios humanos de la evaluación académica.

~~~bash
python scripts/prepare_evaluation.py
~~~

El archivo artifacts/evaluation_candidates.csv contiene resultados ordenados de perfiles en seis temas y consultas en inglés y español. El archivo artifacts/evaluation_ratings.csv presenta cada artículo una sola vez por perfil para facilitar la evaluación; su cantidad se imprime al generar los archivos. Califica relevance como 0 (no pertinente), 1 (parcialmente pertinente) o 2 (directamente pertinente). Después ejecuta:

~~~bash
python scripts/score_evaluation.py
python scripts/analyze_bias.py
~~~

Las métricas quedan en artifacts/evaluation_metrics.csv. Las tablas de cobertura por campo, idioma y periodo quedan en artifacts/bias_coverage_by_field.csv y artifacts/bias_coverage_by_field_language.csv; `analyze_bias.py` también crea tablas por fuente, idioma de la fuente y campo de la fuente. La llave de los motores A y B está en artifacts/evaluation_blind_key.json; consúltala después de calificar.

La comparación de motores usa consultas inglesas y los mismos candidatos. Las consultas bilingües evalúan el motor semántico. Precision@5 y nDCG@5 dependen de juicios humanos. No se calcula recall porque no existen etiquetas para todos los artículos del catálogo.

La evaluación de pertinencia v2 separa ocho proyectos de desarrollo y ocho reservados, en español e inglés. Compara E5, el método actual y las variantes híbridas; oculta el motor, puntuación y posición original a quien califica. No sobrescribe la evaluación anterior:

~~~bash
python scripts/prepare_evaluation_v2.py
python scripts/score_evaluation_v2.py
python scripts/diagnose_retrieval.py --sample-size 100
python scripts/compare_rankings.py --configuration hybrid_50_text_0.50
python scripts/audit_similar_articles.py
python scripts/calibrate_threshold.py
python scripts/score_similar_articles.py
~~~

`prepare_evaluation_v2.py` genera `evaluation_v2_ratings.csv`. Completa `relevance` con 0, 1 o 2 antes de ejecutar el cálculo de métricas. `score_evaluation_v2.py` reporta Precision@5 directa y amplia, nDCG@5 con el conjunto común de artículos valorados, primer resultado no pertinente, listas vacías, cantidad de resultados y latencia p95. El diagnóstico verifica una muestra estratificada de 100 vectores y conserva la traza de recuperación y reordenamiento. `compare_rankings.py` permite probar listas de 50, 100 o 500 candidatos, ambos formatos de pasaje y pesos de 0,25, 0,50 y 0,75 sin cambiar la interfaz.

`audit_similar_articles.py` prepara una revisión separada de cinco artículos similares para ocho referencias. Sus valoraciones no se mezclan con las métricas de consultas textuales.

`calibrate_threshold.py` solo usa valoraciones humanas del conjunto de desarrollo y selecciona cortes de la puntuación del reordenador por Precision@5 directa, nDCG@5 y menor proporción de primeros resultados irrelevantes. El conjunto reservado no se usa para ajustar esos parámetros. `score_similar_articles.py` calcula las métricas de las referencias seleccionadas por separado.

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
- Para construir solo el índice léxico híbrido tras actualizar el catálogo, ejecuta `python scripts/build_index.py --hybrid-only`; no vuelve a codificar los vectores E5.
- La navegación conserva temporalmente la consulta, los filtros y hasta diez listas en la sesión; no guarda perfiles ni preferencias entre sesiones.
- La similitud entre artículos puede conducir a temas vecinos o repetir perspectivas. La pertinencia debe evaluarse manualmente.
- No se aplican diccionarios de temas específicos: todas las consultas siguen el mismo criterio. La ausencia de una frase literal no demuestra ausencia de literatura relevante.
