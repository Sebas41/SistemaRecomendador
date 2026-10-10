# Informe del proyecto

## Descripción del sistema

Ciencia a tu tesis recomienda artículos científicos para apoyar la búsqueda bibliográfica de estudiantes que preparan proyectos de grado y tesis. El estudiante escribe una descripción en español o inglés y recibe trabajos ordenados por afinidad temática. Cada recomendación ofrece metadatos, resumen, enlace y un fragmento del resumen cercano a la consulta.

El prototipo usa el título y el resumen de cada artículo. El motor semántico multilingüe constituye la estrategia principal; el índice TF-IDF sirve como referencia en inglés. El sistema no usa interacciones entre usuarios, no mide calidad metodológica y no reemplaza la revisión que debe hacer el estudiante.

## Fuente y construcción de datos

Se usa OpenAlex, una fuente abierta de metadatos bibliográficos. La selección abarca artículos de 2016 a 2025 distribuidos entre los 26 campos académicos de OpenAlex. Se buscan hasta 300 trabajos por campo; cada campo debe aportar al menos 100. Se descartan registros retractados, títulos con menos de tres palabras, resúmenes fuera de 80 a 1.200 palabras, duplicados y registros sin idioma español o inglés identificable.

OpenAlex proporciona resúmenes como un índice de posiciones de palabras; el código reconstruye el texto antes del análisis. Si no informa el idioma, este se infiere del resumen y la inferencia queda identificada. El manifiesto registra fecha, filtros, tamaños por campo, idiomas y hashes de los archivos.

Los atributos de cada artículo son identificador, título, resumen, autores, año, idioma, campo, tema, palabras clave, DOI, enlace y fuente. Cuando falte un atributo opcional, se presenta como no disponible.

## Representación y similitud

El motor semántico compara una descripción de investigación, con el prefijo query, con título y resumen de cada trabajo, con el prefijo passage. Calcula similitud coseno entre vectores normalizados y ordena los artículos según ese valor. La puntuación es una similitud textual, no una probabilidad, una citación futura ni una medida de calidad académica. El modelo acepta como máximo 512 tokens por entrada y trunca los textos que exceden ese límite.

La referencia TF-IDF usa unigramas y bigramas, excluye palabras vacías inglesas y limita su vocabulario a 30.000 características. Depende de coincidencias de palabras; por eso se evalúa en inglés. La comparación de motores emplea la misma consulta, los mismos filtros y los mismos artículos candidatos.

## Arranque en frío y arquitectura

Un estudiante nuevo obtiene recomendaciones desde su primera descripción, sin historial de lecturas o valoraciones. Un artículo nuevo se agrega tras validar sus metadatos y regenerar ambos índices. La aplicación consulta un catálogo local preparado y no conserva perfiles personales.

El diagrama en arquitectura.mmd muestra el flujo: OpenAlex proporciona metadatos; el proceso de preparación limpia los datos y crea un catálogo; dos índices representan el contenido; la aplicación filtra y ordena resultados para que el estudiante los revise.

## Evaluación

Se preparan seis temas de investigación en seis áreas, cada uno con consultas paralelas en inglés y español. La comparación entre los dos motores usa las consultas en inglés. Las consultas bilingües evalúan el motor semántico.

La evaluación manual ciega asigna 0 (no pertinente), 1 (parcialmente pertinente) o 2 (directamente pertinente). Precision@5 y nDCG@5 resumen los primeros cinco resultados que una persona haya calificado. No se informa recall, porque no hay etiquetas de relevancia para todo el catálogo.

## Sesgos, impacto y mitigación

- **Cobertura disciplinar y de la fuente:** OpenAlex no incluye todos los trabajos por igual y asigna automáticamente los temas. Revisar la composición del catálogo, informar vacíos y sumar repositorios disciplinarios en una extensión.
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

La descarga produjo 7.800 registros muestreados. Después de los filtros de metadatos, la deduplicación y la selección de idioma, el catálogo contiene **6.641 artículos en los 26 campos**. Cada campo tiene entre 194 y 290 artículos válidos, por encima del mínimo de 100. Los registros sin DOI se deduplican por identificador y título, no se descartan por carecer de DOI.

La composición lingüística está desequilibrada: **6.404 artículos están en inglés (96,4 %) y 237 en español (3,6 %)**. En 124 artículos el idioma se infirió porque OpenAlex no lo proporcionó. Esta brecha limita el análisis de publicaciones en español; las consultas en español pueden recuperar artículos en inglés mediante el motor multilingüe. Se conserva el idioma del artículo como atributo para auditar los resultados.

El índice E5 usa la revisión 614241f622f53c4eeff9890bdc4f31cfecc418b3. **869 resúmenes (13,1 %)** superan el límite de 512 tokens y se truncan. Se generaron 90 resultados ordenados y 64 artículos únicos para la evaluación humana a ciegas. Las métricas de relevancia quedan pendientes de completar sus etiquetas. No se asume que el motor semántico supere a TF-IDF sin revisar los resultados.

## Referencias técnicas

- [OpenAlex: atributos de trabajos y resúmenes](https://help.openalex.org/data/works/attributes/).
- [OpenAlex: campos académicos](https://help.openalex.org/data/fields/).
- [OpenAlex: muestreo y paginación](https://help.openalex.org/api/paging/).
- [Modelo multilingüe E5 Small](https://huggingface.co/intfloat/multilingual-e5-small).
- scikit-learn: [TF-IDF](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html) y [similitud coseno](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.cosine_similarity.html).
