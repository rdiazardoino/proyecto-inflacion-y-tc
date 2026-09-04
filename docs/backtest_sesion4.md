# Sesión 4 — Modelos económicos (Escalón 1): ninguno le gana a la vara, y eso se dice

Misma metodología que la sesión 3 (expanding window de orígenes desde
dic-2016, horizontes 1/6/12/24, sin información futura, DM test vs. el
benchmark ganador de cada objetivo). Resultados en las mismas tablas
(`errores`, `metricas_backtest`) — comparables fila a fila con la sesión 3.
Reproducible con `python src/models/backtest_sesion4.py`.

**Veredicto adelantado, porque el plan lo exige explícitamente:** ninguno de
los tres modelos de esta sesión supera a su benchmark con la significancia
requerida (DM 10% o mejora de MAE >5% sostenida). Según la regla del propio
proyecto (BRIEF §5), **quedan como challengers, con peso cero, visibles en
el dashboard** — no entran al ensemble. Esto no es un fracaso de la sesión:
es exactamente el resultado que el proceso de backtest está diseñado para
detectar, y ocultarlo sería falsear el sistema.

## Qué se pudo construir y qué no (limitaciones de datos, no de tiempo)

El plan pide un SARIMAX bottom-up por 13 divisiones, una curva de Phillips
ampliada con expectativas y brecha de producto, y un BVAR(2) con TPM. Con
los datos disponibles hoy, ninguno de los tres se puede construir tal cual:

| Modelo del plan | Bloqueo | Qué se construyó en su lugar |
|---|---|---|
| SARIMAX bottom-up (13 divisiones) | Exógenas por división (FAO/CBOT, novillo INAC, combustibles ANCAP, tarifas UTE/OSE) no están cargadas | **SARIMAX top-down** (agregado) con las exógenas que sí existen: TC, Brent, CPI EEUU, IMS |
| Phillips ampliada (expectativas + brecha) | Encuesta de Expectativas todavía no integrada como regresor dinámico; brecha de producto RESUELTA 4-sep-2026 (IMAE + filtro HP real-time) | **Phillips reducida+brecha**: ECM hacia la meta del BCU (4,5%) + TC rezagado + brecha de producto (IMAE) donde hay suficiente historia |
| BVAR(2) [ΔTC, π, TPM, ΔBRL, ΔDXY] | `tpm_bcu` tiene un único punto histórico (5,75%, del IPOM 1T-2026) — no hay serie mensual de la TPM | **VAR(2) reducido** [π, ΔTC, ΔBRL, ΔDXY], sin TPM, sin priors Minnesota |

Los tres se estiman en **ventana móvil de 96 meses** (8 años), no expanding
desde 2011 — lección de la sesión 3: un modelo estimado sobre toda la
muestra mezcla el régimen de inflación alta (2011-2015) con el actual y
arrastra sesgo de nivel. Ninguno lleva dummies de mes: la estacionalidad
calendario ya la cubre `rw_estacional`; estos modelos compiten aportando
drivers económicos, no repitiendo el mismo trabajo con menos datos por mes.

## Resultado — MAE por horizonte

**Inflación m/m** (p.p.; `bench_rw_estacional` es la referencia de la sesión 3):

| Modelo | h=1 | h=6 | h=12 | h=24 |
|---|---|---|---|---|
| **RW estacional** (benchmark) | **0,357** | **0,343** | **0,347** | **0,342** |
| Phillips reducida | 0,435 | 0,402 | 0,408 | 0,393 |
| SARIMAX top-down | 0,447 | 0,433 | 0,431 | 0,419 |
| VAR(2) reducido | 0,474 | 0,407 | 0,414 | 0,401 |

**TC promedio** (UYU/USD):

| Modelo | h=1 | h=6 | h=12 | h=24 |
|---|---|---|---|---|
| **Random walk** (benchmark) | **0,505** | **1,821** | **3,018** | **5,025** |
| VAR(2) reducido | 0,597 | 2,065 | 3,460 | 6,254 |

## Significancia (Diebold-Mariano vs. el benchmark)

| Modelo | h=1 | h=6 | h=12 | h=24 |
|---|---|---|---|---|
| Phillips reducida | p=0,077 | p=0,141 | p=0,064 | p=0,125 |
| SARIMAX top-down | p=0,063 | **p=0,026** | **p=0,013** | p=0,075 |
| VAR(2) reducido (π) | **p=0,016** | p=0,132 | p=0,057 | p=0,077 |
| VAR(2) reducido (TC) | p=0,42 | p=0,55 | p=0,71 | p=0,50 |

Todos los estadísticos DM son positivos (los modelos nuevos tienen error
cuadrático mayor, nunca menor, que el benchmark). SARIMAX top-down pierde
con significancia clara en h=6 y h=12; VAR(2) pierde con significancia en
π a h=1. El resto no alcanza el 10% de significación, pero **tampoco le
gana** al benchmark en ningún caso — la regla de entrada al ensemble exige
ganar, no empatar.

## Lecturas

**Phillips reducida es la mejor de las tres, y la que más se acerca al
benchmark** (gap de ~0,05 p.p. en vez de ~0,08-0,13 de las otras dos). Tiene
sentido: es el modelo más parsimonioso (3 parámetros) y el único con una
estructura de corrección de error hacia un ancla estable. Además, su
**directional accuracy es la mejor de todas** (70-76% en todos los
horizontes, contra 48-76% de `rw_estacional`) — acierta más veces la
dirección del cambio, aunque su magnitud (MAE) sea peor. Esto sugiere que
el término de convergencia hacia la meta capta algo real sobre el sentido
del movimiento, incluso si el punto no supera al benchmark. Agregada el
4-sep-2026 la brecha de producto (IMAE, filtro HP real-time) como
regresor adicional -- MAE prácticamente sin cambios en el corte completo
(la brecha solo entra en origenes recientes, con suficiente historia de
IMAE). Candidato natural a mejorar cuando la Encuesta de Expectativas se
integre como regresor dinámico (reemplazando la meta constante por el
ancla que pide el plan).

**SARIMAX top-down es el que peor generaliza a los horizontes cortos-medios**
(único con significancia clara en h=6 y h=12). Con solo 6 parámetros sobre
96 observaciones no está sobreajustado en el sentido clásico, pero el
supuesto de "sin novedad" en las exógenas para h≥2 (todas las diferencias
puestas en cero más allá del origen) probablemente pesa: el modelo pierde
justo la información que en teoría lo hace superior a un benchmark puro.

**VAR(2) reducido no aporta nada en TC** — de hecho es sistemáticamente
peor que el random walk en los cuatro horizontes, algo esperable dado lo
que ya mostró la sesión 3 (el random walk es muy difícil de vencer en TC) y
consistente con la ausencia de la TPM, la variable que en teoría ancla el
canal de política monetaria del VAR.

## Qué habilita esto para la sesión 5

El ensemble de la sesión 5 pondera por desempeño de backtest — con este
resultado, **el ensemble de inflación y de TC arrancan con el 100% del peso
en los benchmarks** (`rw_estacional` e inflación, `rw`/`rw_drift` en TC), y
los tres modelos de esta sesión quedan con peso cero, visibles como
challengers. El informe mensual debe decir esto explícitamente, tal como
exige el plan — no presentar un modelo más sofisticado como si ganara
cuando no lo hace.

**Camino de mejora, en orden de esfuerzo/impacto esperado:**
1. Integrar `expectativas_inflacion_12m` (ya cargada desde el 4-sep-2026,
   ver `docs/manifest_fuentes.md`) como regresor dinámico en Phillips, en
   vez de la meta constante — mejora directa.
2. ~~Cargar IMAE (brecha de producto)~~ — RESUELTO el 4-sep-2026.
3. Reconstruir la serie histórica de la TPM parseando los IPOM trimestrales
   pasados (~20 informes desde 2020) o las actas del Copom — habilita el
   BVAR real.
4. Cargar las exógenas por división (FAO, novillo INAC, combustibles,
   tarifas) — habilita el SARIMAX bottom-up genuino del plan.

Ninguno de estos cuatro es una tarea de modelado: son tareas de ingesta,
como las de la sesión 1.
