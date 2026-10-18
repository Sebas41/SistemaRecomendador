# Pruebas de pertinencia — 18 de octubre de 2026

El recomendador encuentra algunos antecedentes útiles, pero todavía mezcla objetivos distintos y no ofrece cinco referencias directamente pertinentes de forma consistente. Los ejemplos más claros son aves para un proyecto de tomate, climatización para pronóstico fotovoltaico y vivienda para riesgo crediticio.

## Alcance y criterio

Se ejecutaron diez descripciones: ocho proyectos en español y traducciones equivalentes de dos de ellos al inglés. Se revisaron las 50 posiciones devueltas (no necesariamente 50 artículos únicos), con cinco resultados por consulta sobre 110,144 registros. Se usó el mismo motor semántico de la aplicación, sin filtros de disciplina, año o idioma y sin palabras clave adicionales. Se desactivó únicamente la generación de fragmentos orientativos, que no cambia el ranking. No se evaluó TF-IDF ni la navegación por artículos similares en esta prueba.

Las valoraciones fueron realizadas por el asistente de IA después de leer títulos y resúmenes del catálogo. No son juicios humanos a ciegas ni una verificación de calidad metodológica o del texto completo. Se conservaron los archivos de evaluación académica existentes sin modificarlos.

- **2, directa:** aborda el problema central y un método o componente útil para el proyecto. No exige que cubra todas las funciones, población o condiciones de validación; las diferencias se explican en cada fila.
- **1, parcial:** aporta contexto o un método transferible, pero cambia un elemento importante del objetivo, la población o el entorno.
- **0, no pertinente:** comparte palabras o técnicas generales sin aportar un antecedente suficientemente relacionado con el problema planteado.

Las fronteras entre categorías requieren validación por el estudiante. En particular, una lectura parcial puede servir como antecedente metodológico, pero no debe presentarse como respuesta directa al proyecto.

## Resultados de los ocho proyectos en español

| Proyecto | Directas | Parciales | No pertinentes |
|---|---:|---:|---:|
| Agentes de IA y arquitectura empresarial | 0 | 4 | 1 |
| Pronóstico de energía solar | 3 | 0 | 2 |
| Aplicación para autocuidado de diabetes | 3 | 2 | 0 |
| Gamificación y comprensión lectora | 0 | 4 | 1 |
| IoT para calidad del agua en ríos | 1 | 3 | 1 |
| Predicción explicable de riesgo crediticio | 1 | 1 | 3 |
| Archivo de una lengua indígena | 0 | 4 | 1 |
| Enfermedades en hojas de tomate | 2 | 1 | 2 |

En esta revisión exploratoria: **10 de 40 posiciones fueron directas**, 19 parciales y 11 no pertinentes. Son conteos de esta muestra, no una estimación validada de precisión general ni las métricas académicas del proyecto.

## Diagnóstico de las etapas

- **Tomate:** el artículo de aves pasó del puesto 497 por similitud E5 al primero tras el cross-encoder. El de enfermedades de tomate con CNN pasó del tercero al cuarto. Hay al menos un candidato pertinente disponible; este fallo no puede atribuirse únicamente al tamaño del catálogo.
- **Solar:** el artículo sobre climatización pasó del puesto 422 al quinto, y el diagnóstico térmico del 263 al cuarto. El reordenador también mejoró posiciones útiles: el artículo comparativo de radiación solar pasó del 14 al primero.
- **Recuperación inicial:** tampoco es suficiente por sí sola. Entre los primeros cinco de E5 para tomate aparecieron movilidad estudiantil, comercialización de panela y vigilancia de vallas. Por tanto, quitar el reordenador sin otra validación no resuelve todo el problema.
- **Índice:** se recodificaron seis artículos de diagnóstico y se compararon con sus vectores guardados. Los cosenos fueron aproximadamente 1,0. Esto no audita todo el índice, pero no mostró desalineación o desactualización en esa muestra.
- **Idioma:** las consultas equivalentes de arquitectura compartieron cuatro artículos de cinco; las de solar, dos. Ambas versiones solares tuvieron tres lecturas directas bajo este criterio, pero en inglés apareció un trabajo de eyecciones de masa coronal. No se observó una mejora uniforme por escribir en inglés.

## Qué conviene corregir a continuación

1. Evaluar con estas descripciones y un conjunto independiente una combinación de recuperación semántica y léxica, en lugar de dejar que el cross-encoder decida todo el orden final.
2. Comprobar que se mantenga el objeto de estudio y la tarea: tomate frente a aves, impago frente a precios, generación fotovoltaica frente a meteorología espacial. Evitar un diccionario exclusivo para una consulta.
3. Calibrar la selección con valoraciones humanas y admitir menos resultados cuando la evidencia de pertinencia sea insuficiente. El corte actual de puntuación cero no evita los errores observados.
4. Separar lecturas de apoyo de antecedentes directos y validar las mejoras sobre consultas nuevas. Los resultados actuales no justifican afirmar que el sistema ya tiene buena pertinencia general.

Esta entrega documenta y reproduce las pruebas; no modifica el ranking para ajustarlo a los ejemplos.

## Registro y reproducción

- Código evaluado: `15c5f45991bac58dcd10e40940c8339f7ee996d7`.
- SHA-256 del catálogo: `845853d5eb86ff6d4d6845743f3e2dd4ecc2cde0f9e1003e1be96224e86cc11c`.
- Revisión E5: `614241f622f53c4eeff9890bdc4f31cfecc418b3`.
- Descripciones y ejecución: `scripts/audit_project_queries.py`.
- Salida local con resúmenes, puntuaciones y tiempos: `artifacts/project_query_audit.json`.
- Diagnóstico local: `artifacts/project_query_diagnostics.json` y `artifacts/index_audit_sample.json`.
- Valoraciones trazables por identificador y posición: `docs/revision_pertinencia_2026-10-18.json`.
- Los resultados completos del catálogo permanecen locales; el informe y las valoraciones se conservan en Git.

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/audit_project_queries.py
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/audit_project_queries.py --diagnostics-only
```

El comando vuelve a ejecutar las consultas y reemplaza la salida local; no vuelve a generar ni modifica las valoraciones del informe.

## Descripciones y revisión de cada resultado

### Agentes de IA y arquitectura empresarial

Diseñar un sistema de agentes de inteligencia artificial que apoye la arquitectura empresarial, identificando dependencias entre procesos de negocio, aplicaciones y capacidades organizacionales para proponer mejoras alineadas con la estrategia de la empresa.

1. **No pertinente** — [Design and Implementation of Intelligent Decision Support System in Modernization of Social Governance](https://doi.org/10.2478/amns-2025-0836). Trata apoyo a decisiones en gobernanza social; no desarrolla agentes para arquitectura empresarial. Puntuación del reordenador: 4.856.

2. **Parcial** — [AI-powered SAP: Transforming enterprise intelligence for the future](https://doi.org/10.30574/wjaets.2025.15.2.0612). Aporta contexto sobre IA e integración en SAP, pero no analiza agentes ni dependencias entre capacidades, procesos y aplicaciones. Puntuación del reordenador: 4.045.

3. **Parcial** — [Cloud-Native Workforce Engineering : A DevOps and CI/CD Strategy for Rapid Deployment of AI Models Across Distributed HCM Systems](https://doi.org/10.32628/cseit2281224). Describe despliegue de modelos en sistemas empresariales de recursos humanos; sirve como contexto técnico, no como solución al objetivo de agentes y arquitectura empresarial. Puntuación del reordenador: 3.973.

4. **Parcial** — [An AI-Driven Architecture for Cross-Domain Data Management in Enterprise Systems](https://doi.org/10.63282/3050-922x.ijeret-v5i2p118). Aborda arquitectura de datos, interoperabilidad y gobierno empresarial con IA; no demuestra el enfoque de agentes y capacidades organizacionales solicitado. Puntuación del reordenador: 3.842.

5. **Parcial** — [Federated AI for Multi-Enterprise Supply Chain Collaboration](https://doi.org/10.32996/jcsts.2025.7.12.34). Ofrece arquitectura federada entre empresas para cadenas de suministro, con un problema y mecanismo distintos de los agentes propuestos. Puntuación del reordenador: 3.646.

### Pronóstico de energía solar

Desarrollar un modelo de aprendizaje automático para pronosticar la generación de energía de paneles solares a partir de datos meteorológicos e irradiancia, y comparar su precisión con modelos estadísticos tradicionales.

1. **Directa** — [Evaluation of Machine Learning Models in Solar Radiation Prediction for Photovoltaic System Design](https://www.e3s-conferences.org/10.1051/e3sconf/202568000010/pdf). Compara modelos estadísticos y de aprendizaje automático para radiación solar y diseño fotovoltaico; aporta directamente a la etapa de pronóstico. Puntuación del reordenador: 5.557.

2. **Directa** — [The prediction of the usual solar irradiation in the Sahel using the artificial neural networks (case study: 50 MW power plant in Nouakchott)](http://dx.doi.org/10.11591/ijpeds.v15.i3.pp1739-1748). Predice irradiación con redes neuronales y describe su conversión a energía generada en una planta solar. Puntuación del reordenador: 3.856.

3. **Directa** — [Automated Deep CNN-LSTM Architecture Design for Solar Irradiance Forecasting](https://doi.org/10.1109/tsmc.2021.3093519). Pronostica irradiancia mediante CNN-LSTM y compara modelos; es un antecedente directo del componente predictivo. Puntuación del reordenador: 3.667.

4. **No pertinente** — [Diagnostic method of solar thermal system based on the short time on-line measurements](https://doi.org/10.1016/j.applthermaleng.2018.11.048). Diagnostica parámetros de colectores térmicos; no aborda el pronóstico de generación fotovoltaica mediante aprendizaje automático. Puntuación del reordenador: 3.454.

5. **No pertinente** — [Supervised learning based iterative learning control platform for optimal HVAC start-stop in a real building context](https://doi.org/10.1016/j.csite.2024.105055). Optimiza el encendido y apagado de climatización de edificios; comparte vocabulario energético, pero cambia el problema central. Puntuación del reordenador: 3.256.

### Aplicación para autocuidado de diabetes

Desarrollar y evaluar una aplicación móvil para apoyar el autocuidado de adultos con diabetes tipo 2, mediante registro de glucosa, recordatorios de medicación y seguimiento de la adherencia al tratamiento.

1. **Directa** — [Effect of a Mobile Phone–Based Glucose-Monitoring and Feedback System for Type 2 Diabetes Management in Multiple Primary Care Clinic Settings: Cluster Randomized Controlled Trial](https://doi.org/10.2196/16266). Evalúa una aplicación de monitorización de glucosa y retroalimentación en diabetes tipo 2; incluye adherencia y evaluación clínica. Puntuación del reordenador: 5.602.

2. **Directa** — [Developing a Culturally Adapted Digital Health Application for Older Hispanic Adults With Type 2 Diabetes: Protocol for a Qualitative and Pilot Study](https://doi.org/10.2196/76294). Propone y prepara la evaluación de una aplicación para adherencia en adultos con diabetes tipo 2; es un protocolo, no evidencia de eficacia ya demostrada. Puntuación del reordenador: 4.793.

3. **Parcial** — [Smart Chat TB: Aplikasi Mobile untuk Deteksi Dini dan Monitoring Pengobatan Tuberkulosis](https://journal.publinesia.com/index.php/sistematik/article/view/192). Comparte aplicación móvil, autocuidado y recordatorios, pero aborda tuberculosis. Solo aporta un antecedente tecnológico transferible. Puntuación del reordenador: 3.900.

4. **Parcial** — [Evaluating the Usability of an mHealth App for Empowering Cancer Survivors With Disabilities: Heuristic Evaluation and Usability Testing](https://doi.org/10.2196/51522). Aporta evaluación de usabilidad de una aplicación de autocuidado; la población son supervivientes de cáncer, no pacientes con diabetes. Puntuación del reordenador: 3.443.

5. **Directa** — [Evaluating the Impact of mySugr® Mobile Health Application on Glycemic Control in People with Diabetes Mellitus in India: A Real-World Data Analysis](https://doi.org/10.1007/s13300-025-01768-x). Evalúa una aplicación de registro de glucosa y autocuidado en diabetes; el resumen no restringe la población a tipo 2 ni demuestra todas las funciones solicitadas. Puntuación del reordenador: 2.914.

### Gamificación y comprensión lectora

Evaluar el efecto de la gamificación en la comprensión lectora de estudiantes de educación primaria, comparando una intervención con actividades digitales y recompensas con clases de lectura tradicionales.

1. **Parcial** — [The effectiveness of gamified learning environments in promoting grammar mastery in Jordanian secondary school EFL learners](https://doi.org/10.53894/ijirss.v8i2.6013). Evalúa gamificación con grupo de control, pero mide gramática en secundaria, no comprensión lectora en primaria. Puntuación del reordenador: 5.103.

2. **Parcial** — [Using Interactive E-Book User Log Variables to Track Reading Processes and Predict Digital Learning Outcomes](https://doi.org/10.1177/1534508420941935). Estudia lectura digital en primaria y sus resultados, pero no la intervención de gamificación comparada con clases tradicionales. Puntuación del reordenador: 4.696.

3. **No pertinente** — [Effectiveness of a digital literacy program in High School Basic education students \[Eficacia de un programa de alfabetización digital en estudiantes de Educación Básica de Secundaria\]](https://doi.org/10.25115/ecp.v16i34.9516). Evalúa alfabetización digital en secundaria; cambia tanto el aprendizaje objetivo como la intervención. Puntuación del reordenador: 3.723.

4. **Parcial** — [Gamificación en Medicina de Urgencia](https://doi.org/10.6018/edumed.531501). Puede orientar el diseño comparativo de una intervención gamificada, pero estudia medicina de urgencias en universitarios, no lectura infantil. Puntuación del reordenador: 3.290.

5. **Parcial** — [How can a foundation be outlined for a successful serious game to increase reading engagement](https://doi.org/10.17083/ijsg.v10i1.578). Combina juego y lectura con un grupo de control, pero mide participación en secundaria; no demuestra comprensión lectora en primaria. Puntuación del reordenador: 3.233.

### IoT para calidad del agua en ríos

Diseñar un sistema de monitoreo de calidad del agua en ríos mediante sensores de bajo costo e Internet de las cosas, midiendo pH, turbidez y temperatura para detectar cambios y generar alertas tempranas de contaminación.

1. **Directa** — [Water Quality Monitoring Kit](https://doi.org/10.22214/ijraset.2025.76306). Revisa sensores, arquitecturas y problemas de implementación de monitoreo de calidad de agua con IoT; aporta directamente al diseño, aunque no demuestra el sistema específico de río y bajo costo. Puntuación del reordenador: 5.297.

2. **Parcial** — [Iot-Based Recirculating Systems: Advancing Climate-Resilient Aquaculture](https://bpasjournals.com/library-science/index.php/journal/article/view/1224). Usa IoT para parámetros de calidad del agua, pero en acuicultura recirculante, con condiciones distintas a las de un río. Puntuación del reordenador: 5.281.

3. **Parcial** — [Optimization Method of River Water Pollution Prevention and Early Warning System Supporting Spectrum Classification and 3D Remote Sensing Technology](http://dx.doi.org/10.38007/wppcp.2023.040102). Aborda contaminación de ríos y alertas, pero mediante teledetección y clasificación espectral, no el sistema de sensores de bajo costo propuesto. Puntuación del reordenador: 5.144.

4. **No pertinente** — [DEPLOYMENT APPROACH TO NODES OF THE IOT FOR MONITORING SYSTEMS IN PORTS](https://www.airitilibrary.com/Publication/Index?FirstID=10232796-201602-201603300006-201603300006-39-46). Optimiza despliegue de nodos IoT en puertos; el resumen no establece un vínculo con calidad del agua ni medición de los parámetros requeridos. Puntuación del reordenador: 4.846.

5. **Parcial** — [A three stage attention enabled stacked deep CNN-BiLSTM (ASDCBNet) model for end-to-end monitoring of wastewater treatment plant](https://doi.org/10.1007/s13201-025-02575-2). Monitorea sensores y calidad del agua con aprendizaje profundo en plantas de tratamiento; el contexto y la arquitectura difieren del sistema de río. Puntuación del reordenador: 4.313.

### Predicción explicable de riesgo crediticio

Comparar modelos de aprendizaje automático para predecir el incumplimiento de créditos en pequeñas empresas, utilizando indicadores financieros y técnicas de explicabilidad para interpretar los factores asociados al riesgo.

1. **Directa** — [Explainable AI in Credit Models: Balancing Predictive Power with Transparency](https://doi.org/10.52783/jisem.v10i61s.13462). Aborda modelos de crédito e interpretabilidad con SHAP, LIME y contrafactuales; aporta directamente al componente explicable, aunque no valida una comparación específica en pequeñas empresas. Puntuación del reordenador: 3.065.

2. **Parcial** — [Machine learning and financial big data control using IoT](https://doi.org/10.3233/idt-230156). Compara modelos de riesgo financiero empresarial, sin establecer que prediga impago de créditos ni que estudie pequeñas empresas. Puntuación del reordenador: 2.535.

3. **No pertinente** — [Predictive power of ensemble learning in audit qualifications: insights from Indian firms](https://doi.org/10.1504/ijpmb.2025.149981). Predice opiniones de auditoría; no incumplimiento crediticio. Puntuación del reordenador: 1.755.

4. **No pertinente** — [A Comparative Study of Machine Learning Algorithms for Predicting Housing Prices in Chinese Cities](https://doi.org/10.71465/fias374). Predice precios de vivienda; el objetivo es distinto del riesgo de impago. Puntuación del reordenador: 1.663.

5. **No pertinente** — [A Comparative Study of Feature Selection Techniques in Machine Learning for Predicting Stock Market Trends](https://doi.org/10.47738/jads.v4i3.99). Selecciona variables para predicción bursátil; no aborda préstamos o incumplimiento. Puntuación del reordenador: 1.651.

### Archivo de una lengua indígena

Crear un archivo digital participativo para documentar y preservar una lengua indígena en riesgo, mediante grabaciones de relatos orales, transcripciones y colaboración con hablantes de la comunidad.

1. **Parcial** — [DIGITAL PRESERVATION AND DOCUMENTATION OF INDIGENOUS KNOWLEDGE IN AFRICA: A DATA-DRIVEN APPROACH](https://doi.org/10.69778/3007-7184/2025/2.1/a2). Aporta preservación digital, participación y propiedad comunitaria de conocimiento indígena, pero no desarrolla documentación de una lengua en riesgo. Puntuación del reordenador: 3.214.

2. **Parcial** — [La lucha palestina en el muro: Archivando el arte callejero propalestina en Santiago, Chile](https://digitalcollections.sit.edu/cir/4). Describe construcción de un archivo digital mediante trabajo de campo y entrevistas; sirve como referencia de archivística, pero preserva murales y no lengua oral. Puntuación del reordenador: 0.928.

3. **No pertinente** — [Transcultural language, native Chilean peoples and a new AI-based artistic-cultural expression](https://doi.org/10.37467/revhuman.v19.4932). Procesa retratos de pueblos originarios para crear piezas artísticas; la palabra lenguaje no corresponde a documentación lingüística en el resumen. Puntuación del reordenador: 0.864.

4. **Parcial** — [Building an archive for 'future pasts': Undergraduates document their local Covid-19 'moment' in World History](https://www.scielo.org.za/scielo.php?script=sci_arttext&pid=S2223-03862023000200004&tlng=en). Describe un archivo participativo con Omeka y aportes en lenguas locales; su finalidad es documentar la pandemia, no preservar una lengua indígena. Puntuación del reordenador: 0.635.

5. **Parcial** — [Dialect-Mandarin bidirectional translation based on Transformer](https://doi.org/10.54254/2977-3903/2025.25994). Construye un corpus e incluye entrevistas comunitarias para traducción cantonés-mandarín; aporta un método relacionado, pero no un archivo participativo de relatos en una lengua indígena en riesgo. Puntuación del reordenador: 0.529.

### Enfermedades en hojas de tomate

Desarrollar un sistema de visión por computador para detectar enfermedades en hojas de tomate a partir de fotografías tomadas con teléfonos móviles, utilizando redes neuronales convolucionales y evaluando su desempeño en condiciones de campo.

1. **No pertinente** — [Classification of Poultry Birds Based on Health State Using Convolutional Neural Network](https://doi.org/10.4314/aujst.v5i1.12). Clasifica enfermedades en aves; coincidir en CNN e imágenes no lo convierte en antecedente específico de hojas de tomate. Puntuación del reordenador: 3.997.

2. **Parcial** — [Image‐Feature Based Deep Learning Model for Plant Leaf Disease Detection](https://doi.org/10.1002/masy.202200216). Detecta enfermedades en hojas y menciona teléfonos, pero el resumen describe SVM y no identifica tomate; el título no basta para atribuirle el método requerido. Puntuación del reordenador: 3.724.

3. **Directa** — [DETECTION OF PLANT LEAVE DISEASE USING HYBRID TECHNIQUES](https://zenodo.org/record/8112700). Incluye hojas de tomate, características extraídas con CNN y clasificación de enfermedades. No demuestra validación en campo o con teléfonos. Puntuación del reordenador: 3.648.

4. **Directa** — [Utilizing Deep Convolutional Neural Networks for Multi-Classification of Plant Diseases from Image Data](https://doi.org/10.18280/ts.400416). Usa CNN e imágenes de tomate de PlantVillage para clasificar enfermedades; es un antecedente directo, con la limitación de evaluación en dataset. Puntuación del reordenador: 2.848.

5. **No pertinente** — [Building a fish disease detection application based on Smart Fishery with Image Processing and Deep Learning](https://doi.org/10.47709/brilliance.v5i1.5719). Detecta enfermedades en peces con CNN; cambia el organismo y el objeto de estudio. Puntuación del reordenador: 2.312.

### Arquitectura empresarial: consulta en inglés

Design an artificial intelligence agent system to support enterprise architecture by identifying dependencies between business processes, applications and organizational capabilities, and proposing improvements aligned with the company's strategy.

1. **Parcial** — [AI-powered SAP: Transforming enterprise intelligence for the future](https://doi.org/10.30574/wjaets.2025.15.2.0612). Contexto de IA en SAP, sin resolver agentes y dependencias de arquitectura empresarial. Puntuación del reordenador: 2.832.

2. **No pertinente** — [Design and Implementation of Intelligent Decision Support System in Modernization of Social Governance](https://doi.org/10.2478/amns-2025-0836). Apoyo a decisiones en gobernanza social, no agentes para arquitectura empresarial. Puntuación del reordenador: 2.490.

3. **Parcial** — [Inteligencia artificial en la mejora del talento humano y gestión del conocimiento en organizaciones: una revisión sistemática en Scopus](https://doi.org/10.51252/rcsi.v5i1.889). Revisa IA en talento humano y conocimiento organizacional; aporta contexto de negocio, sin el enfoque de agentes y arquitectura propuesto. Puntuación del reordenador: 0.798.

4. **Parcial** — [Cloud-Native Workforce Engineering : A DevOps and CI/CD Strategy for Rapid Deployment of AI Models Across Distributed HCM Systems](https://doi.org/10.32628/cseit2281224). Despliegue de modelos de IA en recursos humanos; no el problema central de agentes y arquitectura empresarial. Puntuación del reordenador: 0.716.

5. **Parcial** — [An AI-Driven Architecture for Cross-Domain Data Management in Enterprise Systems](https://doi.org/10.63282/3050-922x.ijeret-v5i2p118). Arquitectura e interoperabilidad de datos empresariales; falta el enfoque solicitado de agentes y capacidades. Puntuación del reordenador: 0.682.

### Energía solar: consulta en inglés

Develop a machine learning model to forecast solar panel energy generation from weather and irradiance data, and compare its accuracy with traditional statistical models.

1. **Directa** — [Evaluation of Machine Learning Models in Solar Radiation Prediction for Photovoltaic System Design](https://www.e3s-conferences.org/10.1051/e3sconf/202568000010/pdf). Compara modelos de pronóstico de radiación solar para sistemas fotovoltaicos. Puntuación del reordenador: 7.517.

2. **Directa** — [Construction and Research of Ultra-Short Term Prediction Model of Solar Short Wave Irradiance Suitable for Qinghai–Tibet Plateau](https://doi.org/10.3390/atmos14071150). Compara ARIMA, Random Forest y LSTM para pronóstico de irradiancia, directamente útil al objetivo. Puntuación del reordenador: 1.751.

3. **No pertinente** — [CME Arrival Modeling with Machine Learning](https://doi.org/10.3847/1538-4357/ad1cee). Predice llegada de eyecciones de masa coronal a la Tierra; confunde fenómenos solares con generación fotovoltaica. Puntuación del reordenador: 1.657.

4. **Directa** — [The prediction of the usual solar irradiation in the Sahel using the artificial neural networks (case study: 50 MW power plant in Nouakchott)](http://dx.doi.org/10.11591/ijpeds.v15.i3.pp1739-1748). Predice irradiación con redes neuronales y la conecta con energía generada. Puntuación del reordenador: 1.411.

5. **Parcial** — [Hybrid XGBoost-BiLSTM Net-Load Forecasting Framework With Holographic Integration for High-PV IoT Environments](https://doi.org/10.1109/tce.2025.3647579). Predice carga neta usando generación solar y clima; es un objetivo relacionado, pero no idéntico a generación de paneles. Puntuación del reordenador: 1.126.
