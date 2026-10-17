# Informe del proyecto

## Descripción del sistema

Ciencia a tu tesis recomienda artículos científicos para apoyar la búsqueda bibliográfica de estudiantes que preparan proyectos de grado y tesis. El estudiante escribe una descripción en español o inglés y recibe trabajos ordenados por afinidad temática. Cada recomendación ofrece metadatos, resumen, enlace y un fragmento del resumen cercano a la consulta.

El prototipo usa el título y el resumen de cada artículo. El motor semántico multilingüe constituye la estrategia principal; el índice TF-IDF sirve como referencia en inglés. El sistema no usa interacciones entre usuarios, no mide calidad metodológica y no reemplaza la revisión que debe hacer el estudiante.

## Fuente y construcción de datos

Se integran OpenAlex y SciELO. OpenAlex aporta una muestra multidisciplinaria de artículos de 2016 a 2025, distribuida entre sus 26 campos académicos; se buscan hasta 4.800 registros válidos por campo desde muestras aleatorias de hasta 6.000 trabajos por intento. SciELO aporta hasta tres páginas aleatorias de 100 registros de ArticleMeta por colección nacional o temática, con ventana de procesamiento 2016–2025 y filtro local por año de publicación. Sus categorías disciplinares se conservan tal como aparecen en los metadatos de las revistas, sin equipararlas a los campos de OpenAlex. La preparación verifica que el catálogo limpio alcance 100.000 artículos; los archivos de checkpoint permiten reanudar páginas o campos completados tras una interrupción.

Se descartan registros con títulos de menos de tres palabras, resúmenes fuera de 80 a 1.200 palabras, duplicados y registros sin idioma español o inglés identificable. OpenAlex permite excluir registros marcados como retractados; ArticleMeta no informa de manera consistente ese estado, por lo que los registros SciELO no se filtran con el mismo criterio. Las páginas seleccionadas en SciELO usan una semilla reproducible y no se ordenan por citaciones.

OpenAlex proporciona resúmenes como un índice de posiciones de palabras; el código reconstruye el texto antes del análisis. ArticleMeta entrega campos heredados codificados en JSON; el proceso normaliza título, resumen, autores, año, idioma, palabras clave, DOI y enlace. Si una fuente no informa el idioma, este se infiere del resumen y la inferencia queda identificada. El manifiesto registra fecha, filtros, tamaños por fuente, campo e idioma, y hashes de los archivos.

Los atributos de cada artículo son identificador, título, resumen, autores, año, idioma, campo, tema, palabras clave, DOI, enlace, revista, base de procedencia y colección SciELO cuando aplica. Cuando falte un atributo opcional, se presenta como no disponible. La interfaz muestra la fuente y, para SciELO, la colección de la que procede el artículo.

## Representación y similitud

La primera etapa representa la descripción con el prefijo `query:` y el título y resumen de cada trabajo con `passage:` usando multilingual-e5-small. Recupera los 500 candidatos más cercanos por similitud coseno. Una segunda etapa compara cada par consulta-artículo con el cross-encoder multilingüe `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` y vuelve a ordenar los candidatos. En búsquedas generales, los puntajes negativos se descartan; son señales de ordenamiento, no probabilidades ni medidas de calidad académica. El reranker se entrenó para recuperación multilingüe sobre mMARCO, una traducción de MS MARCO a 14 idiomas, incluido el español. Ambos modelos funcionan localmente una vez descargados. E5 admite como máximo 512 tokens por entrada y trunca los textos que exceden ese límite.

Para consultas que contienen los conceptos de agentes de inteligencia artificial y arquitectura empresarial, el prototipo también comprueba su presencia en el título, resumen, tema o palabras clave de cada candidato. Si hay artículos que cubren ambos, prioriza ese conjunto. Si no los hay, presenta coincidencias parciales separadas y señala cuál concepto cubre cada artículo. Este control bilingüe se basa en un vocabulario acotado de sinónimos y no generaliza todavía a cualquier combinación de conceptos.

La referencia TF-IDF usa unigramas y bigramas, excluye palabras vacías inglesas y limita su vocabulario a 30.000 características. Depende de coincidencias de palabras; por eso se evalúa en inglés. La comparación de motores emplea la misma consulta, los mismos filtros y los mismos artículos candidatos.

## Arranque en frío y arquitectura

Un estudiante nuevo obtiene recomendaciones desde su primera descripción, sin historial de lecturas o valoraciones. Un artículo nuevo se agrega tras validar sus metadatos y regenerar ambos índices. La aplicación consulta un catálogo local preparado y no conserva perfiles personales.

El diagrama en arquitectura.mmd muestra el flujo: OpenAlex y SciELO ArticleMeta proporcionan metadatos; la preparación normaliza y limpia los datos, conserva su procedencia y crea un catálogo; multilingual-e5-small recupera candidatos, el cross-encoder multilingüe los reordena y TF-IDF sirve como referencia; la aplicación filtra los resultados para que el estudiante los revise.

## Evaluación

### Tarea

Dada la descripción de un proyecto de grado o tesis, en español o inglés y con palabras clave opcionales, el sistema devuelve 10 artículos temáticamente pertinentes como punto de partida de la revisión bibliográfica. El sistema mide afinidad temática, no calidad científica: un artículo bien ubicado puede tener un diseño metodológico inadecuado para el estudiante.

### Métricas y metas

Las métricas y metas se fijaron antes de comparar configuraciones y no se modifican al conocer los resultados. La evaluación se hace sin filtros de campo, año ni idioma, igual que una búsqueda abierta en la aplicación.

| Métrica | Cómo se obtiene | Para qué sirve | Meta |
|---|---|---|---|
| **MRR@10, ítem conocido** (principal) | Automática: para cada artículo de origen se redacta una descripción de proyecto que este artículo respondería; se registra la posición en que aparece dentro del top 10 | Mide si el sistema encuentra el artículo que corresponde a una descripción de proyecto | La configuración elegida supera a la de referencia por ≥ +0,05, con p < 0,05 (prueba de aleatorización pareada) |
| Recall@10, ítem conocido | Automática: proporción de consultas cuyo artículo de origen aparece en el top 10 | Mide si ese artículo aparece en lo que ve el estudiante | ≥ 0,60 (orientativa) |
| Brecha de MRR@10 entre consultas en español y en inglés | Automática: diferencia absoluta entre el MRR@10 de las consultas redactadas en cada idioma | Mide si las consultas en español funcionan igual de bien | ≤ 0,10 |
| Precision@10 por topic | Automática: un resultado es pertinente si comparte el topic de OpenAlex con el artículo de origen | Mide la coherencia temática del top 10 | ≥ +0,05 frente a la configuración de referencia |
| P@5 y nDCG@5 con juicio humano | Verificación ciega con escala 0 (no pertinente), 1 (parcial) y 2 (directa) sobre perfiles bilingües; el nDCG ideal se calcula con todos los juicios disponibles para el perfil | Comprueba que los resultados automáticos se traducen en utilidad real | P@5 (grado ≥ 1) ≥ 0,70 |
| Exposición por idioma y fuente | Automática: proporción de artículos en español y de SciELO en el top 10 frente a su proporción en el catálogo | Evidencia para el análisis de sesgos | Se reporta, sin meta |
| Diversidad (ILD@10) | Automática: 1 − coseno medio entre los pares de artículos del top 10, con un mismo espacio de vectores para todas las configuraciones | Evidencia de sobreespecialización para el análisis de sesgos | Se reporta, sin meta |

El ítem conocido y el topic son aproximaciones automáticas. Miden propiedades relacionadas con la utilidad, pero no la utilidad misma: una consulta tiene un solo artículo de origen aunque el catálogo contenga otros igualmente pertinentes, y el topic de OpenAlex se asigna automáticamente. Por eso se incluye la verificación humana. La meta que obliga es la diferencia frente a la configuración de referencia con significancia estadística; las metas absolutas son orientativas.

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

La extracción actual produjo **124.759 registros válidos de OpenAlex**, distribuidos en sus 26 campos. Después de los filtros y la deduplicación, cada campo conserva entre 3.104 y 4.610 artículos. SciELO consultó tres páginas de hasta 100 registros en cada una de 19 colecciones; quedaron **3.529 artículos** tras limpiar y combinar las fuentes. El catálogo final contiene **110.144 artículos únicos**, de los cuales 106.615 provienen de OpenAlex y 3.529 de SciELO. Los registros sin DOI se deduplican por identificador y título, no se descartan por carecer de DOI.

En el catálogo combinado, **103.734 artículos están en inglés (94,2 %) y 6.410 en español (5,8 %)**. OpenAlex aporta 3.702 artículos en español y SciELO 2.708. Aunque la incorporación de SciELO aumenta la cobertura en español, el inglés sigue predominando. Las categorías de SciELO se mantienen separadas de los 26 campos de OpenAlex y el análisis de sesgos informa la cobertura por fuente. El manifiesto local conserva la semilla, los filtros, los conteos y el hash de los datos para identificar esta extracción aunque el servicio cambie.

El índice E5 usa la revisión 614241f622f53c4eeff9890bdc4f31cfecc418b3 sobre MPS; **13.590 resúmenes (12,3 %)** superan el límite de 512 tokens y se truncan. El reranker se aplica a la lista corta de candidatos; en consultas generales se descartan puntajes negativos, mientras que las consultas con conceptos reconocidos usan el control de cobertura descrito arriba. La evaluación genera perfiles bilingües en seis áreas y compara el recomendador semántico con TF-IDF para consultas inglesas. Las métricas de relevancia dependen de completar la calificación humana a ciegas; la selección del reranker se comprobó además con búsquedas de prueba que incluyen términos ambiguos.

La consulta de prueba «agentes de inteligencia artificial para la arquitectura empresarial» detecta ambos conceptos, pero el catálogo no contiene artículos que coincidan con ambos en sus metadatos textuales. La aplicación informa esa ausencia y separa los resultados parciales: por ejemplo, un artículo sobre práctica de arquitectura empresarial y trabajos sobre agentes de IA en otros ámbitos. Los artículos sobre arquitectura de mampostería y tácticas feministas, señalados en la prueba inicial, no aparecen como recomendaciones. Esto muestra una limitación de cobertura del catálogo: el reranking mejora el orden y el control de conceptos evita confundir términos, pero ninguno puede crear literatura ausente.

## Referencias técnicas

- [OpenAlex: atributos de trabajos y resúmenes](https://help.openalex.org/data/works/attributes/).
- [OpenAlex: campos académicos](https://help.openalex.org/data/fields/).
- [OpenAlex: muestreo y paginación](https://help.openalex.org/api/paging/).
- [SciELO ArticleMeta REST API](https://github.com/scieloorg/articles_meta/blob/master/docs/source/index.rst) y [cliente Python](https://github.com/scieloorg/articlemetaapi).
- [Modelo multilingüe E5 Small](https://huggingface.co/intfloat/multilingual-e5-small).
- [Cross-encoder multilingüe mMARCO](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1), entrenado para reordenar pasajes según su relevancia para una consulta.
- scikit-learn: [TF-IDF](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html) y [similitud coseno](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.cosine_similarity.html).
