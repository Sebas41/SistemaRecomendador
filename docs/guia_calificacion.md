# Guía de calificación de pertinencia

Esta guía acompaña al archivo `artifacts/human_ratings.csv`. Cada fila es un artículo recomendado para un perfil de proyecto de grado. La columna `relevance` se llena con 0, 1 o 2.

La hoja es ciega: los resultados de las dos configuraciones comparadas vienen mezclados y la columna que identifica cada configuración no aparece. Un mismo artículo se califica una sola vez por perfil, aunque las dos configuraciones lo hayan recomendado.

## Qué se califica

Se califica si el artículo **sirve como antecedente** para el proyecto descrito en el perfil, leyendo el título y el resumen. No se califica la calidad metodológica, el prestigio de la revista ni la cantidad de citas: un artículo bien hecho puede no servir para este proyecto, y un artículo discutible puede ser un antecedente pertinente.

Tampoco influyen el idioma, el año ni la fuente. Un artículo en inglés para un perfil escrito en español se califica igual que cualquier otro.

## Escala

### 2 — Directamente pertinente

El artículo trata el mismo problema que el perfil, o un problema tan cercano que el estudiante lo citaría en sus antecedentes. Responde a la descripción, no solo a una palabra de ella.

> **Perfil P03** (aprendizaje automático para pronóstico de energía solar y eólica)
> **Grado 2:** un estudio que compara modelos de aprendizaje automático para predecir la producción de una planta fotovoltaica a 24 horas.
> **Grado 2:** una revisión de métodos de pronóstico de generación eólica y su efecto en la operación de la red.

### 1 — Parcialmente pertinente

El artículo se relaciona con el perfil pero no responde a su pregunta. Cubre uno de sus componentes y no los demás, o trata el tema desde un ángulo que el estudiante probablemente no usará como antecedente central. Puede servir para el marco teórico o para un capítulo lateral.

> **Perfil P03**
> **Grado 1:** un trabajo sobre pronóstico de demanda eléctrica con redes neuronales, sin energías renovables. Comparte el método y el sector, no el objeto.
> **Grado 1:** un estudio sobre el potencial solar de una región, sin modelos de predicción. Comparte el objeto, no el método.

### 0 — No pertinente

El artículo no aporta al proyecto. Coincide con el perfil solo por una palabra usada en otro sentido, pertenece a otra disciplina sin relación, o es una pieza que no reporta investigación (una nota editorial, un obituario, la descripción de una revista).

> **Perfil P03**
> **Grado 0:** un estudio sobre la eficiencia térmica de hornos industriales. Comparte la palabra «energía» y nada más.
> **Grado 0:** un artículo sobre redes de interacción entre proteínas. «Red» aparece en otro sentido.

## Casos que conviene decidir igual entre calificadores

- **Mismo tema, otro país o población.** Un estudio del mismo problema en otro contexto es **2**: los antecedentes de una tesis incluyen trabajos de otros lugares.
- **Mismo tema, escala muy distinta.** Un estudio de laboratorio cuando el perfil pregunta por una política pública, o al revés, es **1**.
- **Revisión de literatura del tema del perfil.** Es **2**, y suele ser el antecedente más útil.
- **Artículo que solo comparte el método.** Es **1** si el método es central en el perfil, y **0** si el perfil no menciona métodos.
- **Artículo cuyo resumen no permite decidir.** Se califica con lo que el resumen dice, sin buscar el texto completo. Si no alcanza para ver relación con el perfil, es **0**.
- **Perfiles difíciles (P07, P08, P09).** Están diseñados alrededor de palabras ambiguas. Un artículo sobre agentes químicos para el perfil de agentes de inteligencia artificial es **0**, aunque el buscador lo haya puesto primero.

## Procedimiento

1. Lee la descripción del perfil completa antes de calificar sus artículos.
2. Califica todos los artículos de un perfil antes de pasar al siguiente, para mantener el mismo criterio.
3. No consultes la llave de las configuraciones (`artifacts/human_ratings_key.csv`) antes de terminar.
4. Si dos personas califican el mismo archivo, hazlo por separado y compara después; las diferencias se resuelven conversando y se registra el valor acordado.
