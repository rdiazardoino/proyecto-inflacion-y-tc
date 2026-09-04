# Sesión 5 — Ensemble v1 + escenarios

Origen del ejercicio: **julio 2026** (último mes con IPC y TC observados
simultáneamente). Reproducible con `python src/models/run_sesion5.py`
(pesos y pronósticos) y `python src/analysis/session5_figuras.py` (fan
charts). Persistido en `pronosticos` y `escenarios`.

## 1. Ensemble v1

**Regla (plan §8.4):** promedio ponderado por inverso del MAE, piso de 10%
por modelo admitido, mediana como control, dispersión entre modelos como
métrica de incertidumbre.

**Quién está admitido, y por qué:** dado el resultado de la sesión 4 —
ningún challenger (SARIMAX top-down, Phillips reducida, VAR(2) reducido) le
ganó a su benchmark con la significancia requerida —, el pool admitido es
la familia de benchmarks completa **menos** `estacional_historica`
(excluido: la sesión 3 encontró que su error es sesgo puro, bias≈MAE, y su
cobertura de intervalo es 3-9% — nada que combinar ahí). Concretamente:

- **Inflación:** `rw_estacional`, `media_movil_12m`, `naive`
- **TC:** `rw`, `rw_drift`

Los pesos se calculan sobre el corte **2022+** de `metricas_backtest` (el
régimen vigente), no sobre "los últimos 24 meses de backtest en
producción" — esa ventana todavía no existe porque el sistema recién
arranca; se pasa a un rolling real de 24 meses de corridas mensuales desde
que el sistema lleve ese tiempo operando (sesión 6 en adelante).

### Pesos resultantes

**Inflación:**

| Modelo | h=1 | h=6 | h=12 | h=24 |
|---|---|---|---|---|
| RW estacional | 0,361 | 0,376 | 0,337 | 0,341 |
| Media móvil 12m | 0,330 | 0,367 | 0,325 | 0,318 |
| Naive | 0,309 | 0,257 | 0,337 | 0,341 |

**TC:**

| Modelo | h=1 | h=6 | h=12 | h=24 |
|---|---|---|---|---|
| Random walk | 0,502 | 0,503 | **0,535** | **0,626** |
| RW + drift | 0,498 | 0,497 | 0,465 | 0,374 |

**Hallazgo no trivial:** en el corte "completo" (sesión 3), `rw_drift` era
marginalmente mejor que `rw` puro en todos los horizontes. En el corte
**2022+** específicamente, `rw` le gana con más margen a medida que crece
el horizonte (63% del peso a h=24). Lectura: el drift usa el diferencial de
inflación Uruguay-EEUU como proxy de depreciación esperada, pero en el
régimen de desinflación actual ese diferencial es chico — casi no hay señal
que aportar, y el ruido de estimarlo le resta en vez de sumar. Es exactamente
el tipo de cosa que el corte por régimen está diseñado para mostrar.

### Pronóstico (origen jul-2026)

| Horizonte | Mes objetivo | Inflación m/m | TC promedio |
|---|---|---|---|
| h=1 | ago-2026 | 0,12% [IC80: −0,74%, 0,99%] | 40,22 [39,80, 40,64] |
| h=6 | ene-2027 | 0,49% [IC80: −0,41%, 1,38%] | 40,27 [39,16, 41,41] |
| h=12 | jul-2027 | 0,16% [IC80: −0,51%, 0,82%] | 40,33 [38,66, 42,08] |
| h=24 | jul-2028 | 0,16% [IC80: −0,50%, 0,81%] | 40,41 [37,56, 43,49] |

**Definición de cada cifra**, como exige el proyecto: inflación m/m del IPC
total país base oct-2022=100, sin desestacionalizar, del mes objetivo
indicado; TC promedio simple del interbancario fondo del mismo mes;
intervalo 80% construido con el desvío histórico de errores del propio
modelo (backtest) más la dispersión entre los modelos admitidos —
banda empírica v1, no Monte Carlo paramétrico (eso es v2, plan §8.5).

**El salto a 0,49% en h=6 (enero) no es ruido:** es la estacionalidad de
enero que la sesión 2 identificó en Vivienda (+6,3% promedio) y otros
administrados, que `rw_estacional` y `media_movil_12m` capturan
correctamente. El pronóstico "cae" en h=12/24 porque ahí `rw_estacional`
y `naive` convergen matemáticamente al último dato observado (jul-2026:
0,07% m/m) — no es una predicción de que la inflación se mantendrá así
dos años, es la propiedad ya documentada en la sesión 3 (RW estacional a
h=12/24 = valor de hoy). Interpretarlo como pronóstico literal a 24 meses
sería un error de lectura; el informe mensual real (sesión 6) debe dejarlo
explícito.

## 2. Escenarios

**Regla (plan §10):** tres escenarios definidos como sendas de exógenas
(no como ajustes del resultado), recorriendo el mismo modelo para que la
coherencia interna sea automática. Definidos en `config/scenarios.yaml`.

**Vehículo:** `var2_reducido` — el único modelo que tiene TC e inflación
como salidas conjuntas de un mismo sistema. Es un challenger que **no** le
ganó al benchmark en la sesión 4: los escenarios son una herramienta de
**sensibilidad direccional**, no una sustitución del pronóstico oficial de
la sección 1. Esto se declara explícitamente en el propio YAML.

Como no hay BVAR con TPM (bloqueada) ni Encuesta de Expectativas (bloqueada)
para derivar probabilidades de un modelo o de un consenso de mercado, las
probabilidades son **juicio documentado**, como el plan permite cuando esas
fuentes no están disponibles.

| Escenario | Prob. | Senda (mensual, constante) | Justificación |
|---|---|---|---|
| Base | 60% | ΔBRL=0%, ΔDXY=0% | Continuidad: TPM sin cambios (IPOM 1T-2026), inflación dentro del rango meta |
| Benigno | 20% | ΔBRL=+0,3% (real se aprecia), ΔDXY=−0,3% (dólar global débil) | Canal regional favorable + menor inflación importada |
| Adverso | 20% | ΔBRL=−0,3% (real se deprecia), ΔDXY=+0,3% (dólar global fuerte) | Espejo del benigno |

### Trayectorias resultantes (VAR2, origen jul-2026)

| Horizonte | Inflación m/m — Base / Benigno / Adverso | TC — Base / Benigno / Adverso |
|---|---|---|
| h=1 | 0,47% / 0,46% / 0,48% | 40,28 / 40,24 / 40,31 |
| h=12 | 0,53% / 0,52% / 0,54% | 40,62 / 40,17 / 41,08 |
| h=24 | 0,53% / 0,52% / 0,54% | 41,14 / 40,22 / **42,08** |

**El TC es donde el ejercicio de escenarios realmente aporta**: a h=24 hay
casi 2 pesos de diferencia entre el escenario adverso y el benigno (42,08
vs. 40,22), una brecha del ~4,6% — mientras que la inflación apenas se
mueve entre escenarios (0,52-0,54%, diferencias de centésimas). Esto es
coherente con el pass-through bajo que se documentó en la sesión 2 (~0,10
p.p. acumulado a 12 meses por 1% de TC): mover el TC vía BRL/DXY no se
traslada mucho a la inflación en este sistema, así que los escenarios
cambian bastante el TC pero casi nada la inflación. Es un resultado
económicamente sensato, no una limitación del ejercicio.

**Señales de confirmación** (3-5 por escenario, para monitoreo mensual):
completas en `config/scenarios.yaml`; resumen: USD/BRL y DXY sostenidos en
una dirección por 2+ meses, contexto de aversión al riesgo (VIX), y para
el caso base, continuidad de la TPM en las próximas reuniones del Copom.

## 3. Qué queda pendiente para que esto sea más que un ejercicio v1

1. **Backtest a horizontes intermedios** (h=2,3,4,5,7...): hoy el ensemble
   solo tiene base estadística en los 4 nodos oficiales (1/6/12/24); el fan
   chart conecta esos puntos con líneas rectas. Extender `backtest.py` a
   los 24 horizontes mensuales daría una trayectoria completa validada
   (la que pide el plan §1.3), a costo de más tiempo de cómputo — no crítico
   ahora, sí deseable antes de un uso más serio del sistema.
2. **Ventana real de "últimos 24 meses"** en vez del corte 2022+: se
   resuelve solo, corriendo el sistema mensualmente (sesión 6 en adelante).
3. **Probabilidades de escenario desde el BVAR simulado**: pendiente de la
   TPM histórica (mismo bloqueo de siempre, ver `manifest_fuentes.md`).
4. Durante el desarrollo se encontró y corrigió un bug real antes de dar
   el resultado por bueno: el criterio de admisión de un challenger al
   ensemble comprobaba solo la significancia del DM test, no su signo — un
   modelo significativamente **peor** quedaba admitido igual. Concretamente,
   `var2_reducido` en TC pasaba el filtro en h=12/24 del corte 2022+ (p=0,079
   y p=0,042) por perder con significancia frente al random walk, no por
   ganarle (el estadístico DM era positivo en ambos casos, es decir, error
   del challenger mayor al de referencia). Corregido exigiendo además
   `dm_stat_vs_rw < 0`; verificado que tras el fix los pesos por horizonte
   vuelven a sumar exactamente 1 entre los modelos correctamente admitidos.
