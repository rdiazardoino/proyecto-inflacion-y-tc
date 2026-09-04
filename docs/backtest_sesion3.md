# Sesión 3 — Benchmarks (Escalón 0): la vara

Fecha de corte: IPC julio-2026. Metodología: expanding window, primer origen
dic-2016, avanzando un mes a la vez, hasta donde el horizonte máximo todavía
tenga dato observado real (último origen jul-2024 para inflación, sep-2024
para TC). Horizontes evaluados: 1, 6, 12, 24 meses. Ningún pronóstico usa
información posterior a su fecha de origen — desestacionalizaciones,
promedios y "estacionalidad histórica" se recalculan dentro de cada ventana.

Resultados persistidos en `errores` (2.224 filas, una por origen×modelo×
horizonte) y `metricas_backtest` (96 filas agregadas) — reproducible con
`python src/models/backtest.py`. Figuras: `outputs/eda/2026-09/fig4_*` y
`fig5_*`.

**Regla del plan:** un modelo entra al ensemble solo si le gana a estos
benchmarks en backtest fuera de muestra (DM test 10%, o mejora de MAE >5%
sostenida). Estos no son candidatos a ganar — son la vara.

## Modelos evaluados vs. no disponibles

| Objetivo | Evaluado | No disponible (por qué) |
|---|---|---|
| Inflación m/m | RW estacional, media móvil 12m, naive, estacionalidad histórica | **Consenso BCU** — Encuesta de Expectativas bloqueada (ver `manifest_fuentes.md`) |
| TC promedio | Random walk, RW + drift | **Forward BEVSA** (fuera de alcance v1) y **expectativas de TC del BCU** (bloqueada) |

Cuando la Encuesta de Expectativas se resuelva (manual o vía scraper con
navegador), el benchmark institucional se suma sin tocar esta arquitectura.

## Resultado — MAE por horizonte, muestra completa (dic-2016 a jul/sep-2024)

**Inflación m/m** (p.p.):

| Modelo | h=1 | h=6 | h=12 | h=24 |
|---|---|---|---|---|
| **RW estacional** | **0,357** | **0,343** | 0,347 | 0,342 |
| Media móvil 12m | 0,421 | 0,392 | 0,400 | 0,396 |
| Naive (último dato) | 0,552 | 0,575 | 0,347 | 0,342 |
| Estacionalidad histórica | 1,416 | 1,430 | 1,431 | 1,470 |

**TC promedio** (UYU/USD):

| Modelo | h=1 | h=6 | h=12 | h=24 |
|---|---|---|---|---|
| Random walk | 0,505 | 1,821 | 3,018 | 5,025 |
| **RW + drift** (dif. inflación) | 0,522 | **1,678** | **2,869** | **4,845** |

## Lecturas

**RW estacional gana en inflación, y por mucho, en casi todos los horizontes.**
Es matemáticamente el benchmark más fuerte: en h=1 y h=6 le gana a naive con
significancia altísima (DM t≈2,7 y 4,95; p<0,01 y p<0,0001). A h=12 y h=24 RW
estacional **coincide exactamente** con naive — es una propiedad matemática,
no una coincidencia: predecir "el mismo valor de hace 12 meses" en h=12 es
idéntico a predecir "el mismo valor de hoy" cuando el horizonte es un
múltiplo exacto de 12. Confirma lo que dice el plan (§7): la mediana de la
Encuesta de Expectativas del BCU es "el benchmark institucional más difícil
de batir a 12-24m" — y ahora sabemos que a esos horizontes ni siquiera hace
falta esa encuesta para tener una vara dura: el propio calendario ya lo es.

**Estacionalidad histórica pura queda muy mal (MAE ~1,4 en todos los
horizontes) — y el motivo es economía, no un error de cálculo.** Este
benchmark promedia TODOS los valores históricos de ese mes calendario, sin
distinguir régimen. Con inflación de ~8-9% anual en 2011-2015 y ~4-5% en
2022+, promediar "todos los eneros" mezcla dos mundos: el promedio queda
sistemáticamente muy por encima de la inflación actual, y el sesgo (`bias`)
es prácticamente idéntico al MAE en las cuatro columnas — confirma que el
error es casi puro sesgo, no ruido. Verificado por régimen (`metricas_backtest`,
corte 2017-2019 / 2020-2021 / 2022+): el MAE se mantiene ~1,3-1,5 en los tres
subperíodos, o sea que ni siquiera acotando a un régimen mejora — la
estacionalidad calendario (ver sesión 2: Vivienda +6,3%/−4,2% en ene/dic) es
demasiado grande para que un promedio histórico simple la capture bien.

**En TC, el random walk es difícil de vencer — tal como anticipa el plan.**
El drift por diferencial de inflación realizada (proxy de la UIP, ya que no
hay encuesta de expectativas de TC) gana en MAE a partir de h=6, pero la
mejora es marginal (~8% a h=6, ~4% a h=24) y el DM test **no es significativo
en ningún horizonte** (p entre 0,14 y 0,84). Conclusión honesta: el drift no
bate al random walk con confianza estadística — es exactamente lo que el
plan preveía ("batirlo a horizontes cortos es raro y hay que decirlo").

**Directional accuracy de los modelos "planos" (naive, RW) da 0% por
construcción**, no por una falla: un pronóstico "sin cambio" nunca acierta
la dirección salvo que el valor observado coincida exactamente con el de
origen. No es una métrica útil para esos dos modelos — sí lo es para RW
estacional y media móvil 12m, que si devuelven un valor distinto del de
origen: aciertan la dirección 48-76% de las veces según horizonte, mejor que
azar en la mayoría de los casos.

## Cobertura de intervalos (banda 80%, desvío expanding de errores pasados)

Para los modelos con error razonable, la cobertura empírica queda cerca del
80% nominal: RW estacional 76-84%, media móvil 12m 83-85%, naive 80-88%,
random walk de TC 56-85%. Es una banda simple v1 (desvío histórico de
errores del propio modelo) — Monte Carlo paramétrico queda para v2 (plan
§8.5).

**Estacionalidad histórica es la excepción: cobertura de solo 3-9%.** No es
un problema de la banda — es la consecuencia directa de su sesgo: la banda
se construye con el desvío estándar de errores *pasados* (que mide
dispersión alrededor de un promedio), pero cuando el error de un modelo es
consistentemente grande en la misma dirección (bias≈MAE, visto arriba), la
dispersión puede ser chica aunque el error mismo sea grande — la banda queda
angosta justo donde el modelo más se equivoca. Confirma, desde otro ángulo,
que este benchmark no sirve tal cual está: ni el punto ni el intervalo son
utilizables mientras mezcle regímenes de inflación distintos.

*(Nota técnica: se encontró y corrigió un bug real de desalineación
fila-a-columna en el cálculo de cobertura — un array de NumPy indexado por
posición se asignaba a un DataFrame reordenado por índice, mezclando el
resultado entre filas de un mismo grupo. Verificado con un caso mínimo antes
y después del fix; MAE/bias/DM no estaban afectados, solo `cobertura_ic80`.)*

## Qué habilita esto para la sesión 4

Los SARIMAX por división, la curva de Phillips y el BVAR entran al ensemble
**solo si le ganan a esta tabla** en la misma metodología (expanding window,
mismos cortes, mismo DM test). La vara de inflación es dura de vencer a
h=12/24 (RW estacional ≈ naive); la de TC lo es en todos los horizontes. Si
un modelo nuevo no le gana al random walk en TC a h=1, el sistema debe
decirlo explícitamente en el informe, tal como exige el plan — no ocultar
el resultado.
