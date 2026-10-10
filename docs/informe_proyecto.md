# Informe del proyecto

## Descripción del sistema

Ciencia a tu tesis recomienda artículos científicos para apoyar la búsqueda bibliográfica de estudiantes que preparan proyectos de grado y tesis. El estudiante escribe una descripción en español o inglés y recibe trabajos ordenados por afinidad temática. Cada recomendación ofrece metadatos, resumen, enlace y un fragmento del resumen cercano a la consulta.

El prototipo usa el título y el resumen de cada artículo. El motor semántico multilingüe constituye la estrategia principal; el índice TF-IDF sirve como referencia en inglés. El sistema no usa interacciones entre usuarios, no mide calidad metodológica y no reemplaza la revisión que debe hacer el estudiante.

## Fuente y construcción de datos

Se integran OpenAlex y SciELO. OpenAlex aporta una muestra multidisciplinaria de artículos de 2016 a 2025, distribuida entre sus 26 campos académicos; se buscan hasta 300 trabajos por campo y cada campo debe aportar al menos 100. SciELO aporta una muestra aleatoria de páginas de ArticleMeta por colección nacional o temática, con ventana de procesamiento 2016–2025 y filtro local por año de publicación. Sus categorías disciplinares se conservan tal como aparecen en los metadatos de las revistas, sin equipararlas a los campos de OpenAlex.

Se descartan registros con títulos de menos de tres palabras, resúmenes fuera de 80 a 1.200 palabras, duplicados y registros sin idioma español o inglés identificable. OpenAlex permite excluir registros marcados como retractados; ArticleMeta no informa de manera consistente ese estado, por lo que los registros SciELO no se filtran con el mismo criterio. Las páginas seleccionadas en SciELO usan una semilla reproducible y no se ordenan por citaciones.

OpenAlex proporciona resúmenes como un índice de posiciones de palabras; el código reconstruye el texto antes del análisis. ArticleMeta entrega campos heredados codificados en JSON; el proceso normaliza título, resumen, autores, año, idioma, palabras clave, DOI y enlace. Si una fuente no informa el idioma, este se infiere del resumen y la inferencia queda identificada. El manifiesto registra fecha, filtros, tamaños por fuente, campo e idioma, y hashes de los archivos.

Los atributos de cada artículo son identificador, título, resumen, autores, año, idioma, campo, tema, palabras clave, DOI, enlace, revista, base de procedencia y colección SciELO cuando aplica. Cuando falte un atributo opcional, se presenta como no disponible. La interfaz muestra la fuente y, para SciELO, la colección de la que procede el artículo.

## Representación y similitud

El motor semántico compara una descripción de investigación, con el prefijo query, con título y resumen de cada trabajo, con el prefijo passage. Calcula similitud coseno entre vectores normalizados y ordena los artículos según ese valor. La puntuación es una similitud textual, no una probabilidad, una citación futura ni una medida de calidad académica. El modelo acepta como máximo 512 tokens por entrada y trunca los textos que exceden ese límite.

La referencia TF-IDF usa unigramas y bigramas, excluye palabras vacías inglesas y limita su vocabulario a 30.000 características. Depende de coincidencias de palabras; por eso se evalúa en inglés. La comparación de motores emplea la misma consulta, los mismos filtros y los mismos artículos candidatos.

## Arranque en frío y arquitectura

Un estudiante nuevo obtiene recomendaciones desde su primera descripción, sin historial de lecturas o valoraciones. Un artículo nuevo se agrega tras validar sus metadatos y regenerar ambos índices. La aplicación consulta un catálogo local preparado y no conserva perfiles personales.

El diagrama en arquitectura.mmd muestra el flujo: OpenAlex y SciELO ArticleMeta proporcionan metadatos; el proceso de preparación normaliza y limpia los datos, conserva su procedencia y crea un catálogo; dos índices representan el contenido; la aplicación filtra y ordena resultados para que el estudiante los revise.

## Evaluación

Se preparan seis temas de investigación en seis áreas, cada uno con consultas paralelas en inglés y español. La comparación entre los dos motores usa las consultas en inglés. Las consultas bilingües evalúan el motor semántico.

La evaluación manual ciega asigna 0 (no pertinente), 1 (parcialmente pertinente) o 2 (directamente pertinente). Precision@5 y nDCG@5 resumen los primeros cinco resultados que una persona haya calificado. No se informa recall, porque no hay etiquetas de relevancia para todo el catálogo.

## Sesgos, impacto y mitigación

- **Cobertura disciplinar y de la fuente:** OpenAlex y SciELO cubren publicaciones de manera desigual; SciELO ofrece una muestra acotada por colecciones y sus categorías no son idénticas a los campos de OpenAlex. Revisar la composición por fuente y disciplina, informar vacíos y ampliar las colecciones o sumar repositorios disciplinarios.
- **Idioma:** el catálogo y el rendimiento pueden variar entre inglés y español. Comparar consultas equivalentes, informar la cobertura y sumar publicaciones en español si la evaluación muestra una brecha.
- **Selección por metadatos:** exigir resúmenes extensos excluye registros escasos. Documentar los descartes y considerar fuentes adicionales o una ruta para metadatos breves.
- **Periodo:** el corte 2016–2025 puede dejar fuera trabajos clásicos. Mostrar el periodo y permitir material anterior en una versión futura.
- **Concentración temática y popularidad:** un resultado afín puede reiterar subtemas y excluir perspectivas relacionadas. Revisar categorías y términos del top 5 y evaluar un reordenamiento diverso junto con su efecto en relevancia.
- **Afinidad confundida con calidad:** un resumen cercano puede pertenecer a una investigación inadecuada para el diseño del estudiante. Indicar que la recomendación es temática y promover la revisión del método, la fuente y la evidencia.

Las mitigaciones se describen en el informe académico; su implementación no es requisito del prototipo.

## Correspondencia con la rúbrica

| Actividad | Evidencia |
|---|---|
| 1.1 | Contexto, problema de búsqueda bibliográfica y utilidad del sistema. |
| 1.2 | Perfil del estudiante y atributos disponibles de los artículos. |
| 1.3 | Justificación del filtrado por contenido, comparación TF-IDF y límites de filtrado colaborativo y popularidad. |
| 2.1 | Inicio para un estudiante nuevo e incorporación de un artículo nuevo. |
| 2.2 | Diagrama de arquitectura y explicación del flujo. |
| 2.3 | Aplicación ejecutable, fuente de los datos, código comentado y criterio de similitud. |
| 3.1 | Sesgos de cobertura, idioma, selección, periodo y afinidad. |
| 3.2 | Mitigación propuesta para cada sesgo identificado. |

## Resultados y limitaciones observados

La extracción de OpenAlex produjo 7.800 registros candidatos y **6.641 artículos utilizables** en sus 26 campos. Cada campo aporta entre 194 y 290 artículos, por encima del mínimo de 100. SciELO consultó 19 colecciones y obtuvo una página aleatoria de registros en 18 de ellas; tras normalizar y deduplicar, añadió **1.152 artículos válidos** y el catálogo combinado tiene **7.793 artículos**. La muestra SciELO puede ampliarse a tres páginas por colección mediante la configuración del descargador. Los registros sin DOI se deduplican por identificador y título, no se descartan por carecer de DOI.

En el catálogo combinado, **6.625 artículos están en inglés (85,0 %) y 1.168 en español (15,0 %)**. SciELO aporta 931 de los artículos en español, frente a los 237 del catálogo OpenAlex de base. Esta muestra mejora la representación lingüística, aunque sigue concentrada en unas pocas categorías SciELO: Health Sciences (413), Applied Social Sciences (255) y Human Sciences (124). Las categorías se mantienen separadas de las 26 de OpenAlex y el análisis de sesgos informa la cobertura por fuente. El manifiesto local conserva los offsets y la semilla usados, además del hash de los datos, para identificar la extracción aunque el servicio cambie.

El índice E5 usa la revisión 614241f622f53c4eeff9890bdc4f31cfecc418b3. **869 resúmenes (13,1 %)** superan el límite de 512 tokens y se truncan. Se generaron 90 resultados ordenados y 64 artículos únicos para la evaluación humana a ciegas. Las métricas de relevancia quedan pendientes de completar sus etiquetas. No se asume que el motor semántico supere a TF-IDF sin revisar los resultados.

## Referencias técnicas

- [OpenAlex: atributos de trabajos y resúmenes](https://help.openalex.org/data/works/attributes/).
- [OpenAlex: campos académicos](https://help.openalex.org/data/fields/).
- [OpenAlex: muestreo y paginación](https://help.openalex.org/api/paging/).
- [SciELO ArticleMeta REST API](https://github.com/scieloorg/articles_meta/blob/master/docs/source/index.rst) y [cliente Python](https://github.com/scieloorg/articlemetaapi).
- [Modelo multilingüe E5 Small](https://huggingface.co/intfloat/multilingual-e5-small).
- scikit-learn: [TF-IDF](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html) y [similitud coseno](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.cosine_similarity.html).
