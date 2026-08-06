# Brief del proyecto — Inflación y Tipo de Cambio Uruguay

Fecha: 6 de agosto de 2026 · Versión 1.0 · Estado: definición cerrada, pendiente desbloqueo de ingesta

---

## 1. Problema

Necesitás una visión propia, cuantificada y actualizada de hacia dónde van la inflación uruguaya y el USD/UYU, con horizontes de 1, 6, 12 y 24 meses, para decidir asignación entre pesos nominales, unidades indexadas y dólares. Hoy esa visión depende de leer informes de terceros que llegan tarde, no son comparables entre sí y no dejan trazabilidad de qué tan bien acertaron.

El objetivo de negocio no es "hacer un modelo econométrico". Es tener, cada semana, un número defendible y un historial que permita saber si ese número sirve.

## 2. Entregable

Un sistema reproducible que en cada ejecución produce cuatro artefactos:

**Dashboard HTML interactivo** — evolución observada y esperada del TC y de la inflación, fan chart con bandas de incertidumbre, KPIs, heatmap de incidencias por componente, error histórico del modelo, señales de alerta.

**Informe** — dos variantes. El **mensual** sigue las secciones del punto 20 del documento base, con lenguaje técnico y separación explícita entre hecho observado, estimación, supuesto y opinión. El **semanal** cubre: resultados de las licitaciones de la semana (LRM del BCU y Notas del Tesoro de la UGD, con tasa de corte por plazo y moneda, monto ofrecido contra adjudicado y bid-to-cover), curva primaria actualizada y break-even implícito, movimiento del TC y de las variables externas, revisión del nowcast del mes en curso, y una lista explícita de cambios materiales —decisiones de TPM, ajustes tarifarios anunciados, revisiones de series, publicaciones del INE o del BCU, quiebres en alguna serie monitoreada.

**Excel** — tabla central de pronósticos, series históricas, escenarios, incidencias por componente.

**Resumen ejecutivo** — una página: números clave, qué cambió, implicancias.

## 3. Usuario y decisión que habilita

Usuario único: vos, para decisiones propias de inversión. Sin necesidad de lenguaje de compliance ni versión pública.

Las decisiones concretas que debe habilitar: pesos nominales versus UI (comparando break-even contra inflación proyectada), grado de dolarización del portafolio (comparando carry en pesos contra depreciación esperada), y duration.

## 4. Requisitos y restricciones

| Dimensión | Definición |
|---|---|
| Cadencia | Semanal: monitoreo y actualización del nowcast. Mensual: re-estimación completa y proyección a 1/6/12/24m. A demanda: cuando lo pidas. |
| Fecha de corte | Explícita en cada ejecución. Todo pronóstico se guarda con su vintage de datos. |
| Fuentes | Oficiales y públicas: INE, BCU, ANCAP, UTE, FRED. Sin datos inventados. |
| Almacenamiento | SQLite + Parquet dentro de `C:\Users\rdiaz\OneDrive\Documentos\Proyecto de Inflacion y TC` |
| Versionado | GitHub |
| Costo | Cero licencias. Solo herramientas gratuitas. |
| Historial | Point-in-time. Un pronóstico emitido nunca se sobrescribe con una reconstrucción posterior. |

## 5. Alcance de modelos: todo entra, pero por escalones

No se excluye nada del documento base. Se ordena por escalones de habilitación, porque con ~65 observaciones mensuales de régimen homogéneo un modelo con muchos parámetros no se puede estimar sin sobreajustar. El criterio no es "esto queda afuera", es "esto entra cuando su error out-of-sample lo justifique".

**Escalón 0 — Benchmarks.** Random walk, random walk con drift, promedio móvil, estacionalidad histórica, consenso de la encuesta BCU, forward implícito por paridad cubierta. No son candidatos a ganar: son la vara. Todo lo demás se mide contra ellos.

**Escalón 1 — Núcleo estadístico y económico.** SARIMA y SARIMAX para IPC, ETS, componentes no observados, curva de Phillips ampliada con expectativas y brecha de producto, modelos de pass-through cambiario con asimetrías por dirección, tamaño y régimen, VAR y VECM chicos, GARCH para volatilidad del TC. Estimables con la muestra disponible.

**Escalón 2 — Desagregación y estructura.** Bottom-up por las 12 divisiones COICOP con ponderaciones oficiales e incidencias, medidas propias de núcleo por media truncada, clasificación transable / no transable / administrado / volátil, Markov switching de dos regímenes, factores dinámicos sobre el panel de precios, MIDAS para mezclar frecuencia diaria del TC con la mensual del IPC.

**Escalón 3 — Machine learning.** Ridge, Lasso, Elastic Net, Random Forest, Gradient Boosting, XGBoost, LightGBM, SVR. Con validación temporal estricta —nunca k-fold aleatorio—, SHAP y partial dependence para interpretabilidad, y test de estabilidad temporal de la importancia de variables. Con esta muestra el prior razonable es que los regularizados lineales anden y los de árboles no; el sistema lo mide en vez de suponerlo.

**Escalón 4 — Equilibrio de largo plazo y simulación.** BEER, FEER, PPP, paridad descubierta. Monte Carlo para bandas de incertidumbre del escenario conjunto inflación-TC en lugar de bandas paramétricas. Relevantes para los horizontes de 12 y 24 meses, donde el random walk deja de ser difícil de vencer.

**Regla de ingreso al ensemble.** Un modelo se estima, se backtestea rolling y expanding, y se le calcula MAE, RMSE, bias, directional accuracy, cobertura de intervalos y Diebold-Mariano contra el benchmark. Entra al ensemble con peso proporcional a su desempeño por horizonte. Si no supera al benchmark, se sigue calculando y se muestra en el dashboard como challenger, pero con peso cero. El informe siempre dice qué modelos están pesando.

**Lo único que queda efectivamente afuera:** recomendaciones de portafolio por perfil de inversor —no aplica, usuario único— y redes neuronales profundas, que con 65 observaciones no es una decisión de alcance sino de aritmética.

## 6. Criterios de aceptación

La v1 se considera terminada cuando:

1. El pipeline corre de punta a punta sin intervención manual salvo el paso de ingesta, y produce los cuatro artefactos.
2. Todo número del informe es rastreable a una fila de la base con fuente, fecha de publicación y vintage.
3. Existe backtesting rolling window de al menos 36 meses con MAE, RMSE, bias, directional accuracy y cobertura de intervalos, por modelo y por horizonte.
4. El ensemble empata o supera al random walk y al consenso BCU en MAE a 1 y 6 meses en el backtest. Si no lo hace, el sistema reporta el benchmark como pronóstico principal y lo dice.
5. La inflación se reporta siempre con su definición explícita: variación mensual del IPC general base **octubre 2022 = 100**, variación interanual, subyacente, transable y no transable, cada una identificada.
6. Cada ejecución deja registro en `logs_actualizacion` y levanta alertas si una serie no se actualizó o un pronóstico cae fuera de rango plausible.
7. Ningún modelo entra al ensemble sin haber superado a su benchmark en backtest out-of-sample al horizonte donde se lo usa. Los que no lo superan se estiman igual y se reportan como challengers, con su error a la vista.
8. El informe semanal se emite aunque no haya dato nuevo de IPC, y contiene siempre: resultados de las licitaciones de la semana con tasa de corte y bid-to-cover, movimiento del TC y de las variables externas, revisión del nowcast del mes en curso, y lista explícita de cambios materiales.

## 7. Contradicciones y supuestos detectados

**El motor de ejecución no puede hacer la ingesta.** Verificado empíricamente: el entorno de ejecución de Cowork no tiene salida a internet hacia ine.gub.uy, bcu.gub.uy ni fred.stlouisfed.org (HTTP 403 del proxy). Sí tiene acceso a PyPI, Python 3.10, pandas y capacidad de instalar statsmodels y scikit-learn. Conclusión: el ETL debe correr fuera del sandbox. Resolución adoptada: GitHub Actions ejecuta la descarga y escribe los datos al repo; Cowork hace transformación, modelos, validación y reportes sobre los datos locales.

**Cadencia semanal versus datos mensuales.** El IPC se publica una vez por mes. Un informe semanal no puede traer inflación nueva. Resolución: el informe semanal actualiza lo que sí cambia (TC diario, commodities, tasas externas, riesgo país) y revisa el nowcast del mes en curso; el ciclo mensual completo se dispara con la publicación del INE.

**Carpeta en OneDrive, no Google Drive.** Es equivalente para el propósito. Advertencia: SQLite sobre carpeta sincronizada puede corromperse si dos procesos escriben a la vez. Mitigación: escritura desde un solo proceso y respaldo del `.db` antes de cada ejecución.

**"Superar benchmarks de forma consistente" no es verificable al lanzamiento.** Se puede demostrar en backtest pseudo out-of-sample, que es más débil que un track record real. Un historial honesto requiere 12 a 24 meses de pronósticos emitidos en tiempo real. El sistema lo registra desde el día uno, pero la afirmación no se puede hacer todavía.

**El gap de datos de mercado está mayormente cerrado.** El TC deja de depender de scraping: el BCU expone un web service SOAP público de cotizaciones, con serie diaria completa por moneda y rango de fechas. Las curvas de BEVSA siguen sin acceso automático, pero dejan de ser bloqueantes: los resultados de licitaciones del BCU (LRM) y de la UGD (Notas del Tesoro en pesos nominales, UI y UP) se publican el mismo día antes de las 17:00 y dan rendimiento de corte por plazo y moneda. Con eso se arma curva primaria, break-even de inflación (nominal menos UI) y forward USD/UYU por paridad cubierta. Es mercado primario en vez de secundario, con menos puntos y menor frecuencia, pero es dato público, auditable y automatizable. BEVSA queda como mejora futura, no como requisito.

**Muestra corta.** Uruguay bajo régimen de metas de inflación con TPM como instrumento arranca en 2020. Series mensuales útiles: ~65 observaciones. Esto limita fuertemente lo que se puede estimar. Es la razón principal por la que ML y modelos multiecuacionales grandes quedan fuera de la v1.

## 8. Plan por fases

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Brief, arquitectura, esquema de base, inventario de variables | Hecho |
| 1 | ETL vía GitHub Actions: INE (3 bases encadenadas), BCU SOAP cotizaciones, FRED, ANCAP, licitaciones BCU y UGD. Carga histórica | Bloqueado — requiere repo |
| 2 | Control de calidad, empalme de bases del IPC, transformaciones, features, análisis exploratorio | Pendiente |
| 3 | Escalón 0: benchmarks — random walk, drift, promedio móvil, estacionalidad, consenso BCU, forward por paridad cubierta | Pendiente |
| 4 | Escalón 1: SARIMA/SARIMAX, ETS, componentes no observados, Phillips ampliada, pass-through con asimetrías, VAR/VECM, GARCH | Pendiente |
| 5 | Backtesting rolling y expanding, métricas por horizonte, Diebold-Mariano contra benchmark | Pendiente |
| 6 | Ensemble ponderado por error histórico, diferenciado por horizonte. Modelos que no ganan quedan con peso cero y visibles | Pendiente |
| 7 | Escenarios base, favorable y adverso, con probabilidades y señales de monitoreo | Pendiente |
| 8 | Dashboard, informe mensual, informe semanal, Excel, resumen ejecutivo | Pendiente |
| 9 | Automatización semanal y mensual | Pendiente |
| 10 | Escalón 2: bottom-up por división COICOP, núcleo por media truncada, Markov switching, factores dinámicos, MIDAS | Pendiente |
| 11 | Escalón 3: ML regularizado y de árboles con validación temporal, SHAP y test de estabilidad | Pendiente |
| 12 | Escalón 4: BEER/FEER/PPP/UIP y Monte Carlo para bandas conjuntas | Pendiente |

## 9. Decisiones metodológicas pendientes

Período histórico inicial: resuelto operativamente. El IPC se reconstruye encadenando las tres bases del INE —marzo 1997 = 100, diciembre 2010 = 100 cerrada en octubre 2022, y octubre 2022 = 100 vigente— empalmando por variación mensual, no por nivel. Eso da serie desde 1997. Se estima sobre la muestra larga con dummies de régimen (pre-2002, crisis 2002, 2003-2013, metas cuantitativas 2013-2020, metas con TPM 2020 en adelante) y se valida exclusivamente sobre 2020 en adelante. Los modelos que solo funcionan con muestra larga y fallan en la validación 2020+ se descartan.

Tratamiento del quiebre de la pandemia (2020-2021): dummies puntuales versus exclusión del período de la muestra de estimación.

Medida de brecha de producto: filtro HP sobre IMAE, con la advertencia estándar sobre el problema de fin de muestra.

Definición operativa de inflación núcleo: la del INE, o una medida propia de media truncada.

Aproximación del forward USD/UYU: resuelto. Paridad cubierta con tasa de corte de LRM del BCU contra curva Treasury al mismo plazo. Pendiente menor: si corresponde ajustar por prima de riesgo de conversión y con qué proxy.

Interpolación de la curva primaria: los plazos licitados no coinciden entre instrumentos ni entre licitaciones. Pendiente elegir método —lineal sobre rendimientos, Nelson-Siegel, o spline— para poder calcular break-even a plazos homogéneos.
