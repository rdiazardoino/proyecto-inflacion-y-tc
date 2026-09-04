# Sesión 2 — EDA: hallazgos y decisiones para los modelos

Fecha de corte: **IPC julio 2026** (publicado ~5-ago-2026). Muestra de estimación:
enero 2011 → julio 2026 salvo indicación. Script reproducible:
`src/analysis/eda_sesion2.py`; figuras en `outputs/eda/2026-09/`.

Definiciones: inflación m/m y a/a = variación del IPC total país base oct-2022=100,
sin desestacionalizar salvo que diga "SA". Núcleo = IPC-CE oficial del INE.
TC = promedio mensual del interbancario fondo (punto medio).

## Punto de partida (últimos datos)

| Medida | Valor | Definición |
|---|---|---|
| Inflación a/a | **4,27%** | IPC total país, jul-2026 vs jul-2025, NSA |
| Inflación m/m | 0,07% | jul-2026, NSA |
| Tendencia 3m anualizada | 4,92% | IPC SA por STL, anualizada |
| Núcleo a/a | 4,11% | IPC-CE (excluye frutas, verduras y combustibles), NSA |

La inflación corre dentro del rango meta del BCU, con la tendencia de corto plazo
levemente por encima del registro interanual.

## 1. Estacionalidad por división (fig. 1)

Muy marcada y concentrada en pocas divisiones — esto es lo que el bottom-up explota:

- **Vivienda y suministros (04):** +6,3% promedio en enero y **−4,2% en diciembre** —
  el plan "UTE Premia" / descuentos de diciembre y su reversión + ajustes tarifarios
  de enero. Es el driver estacional dominante del IPC agregado.
- **Enseñanza (10):** +3,7% feb y +1,6% mar (matrículas), +1,7% ago.
- **Vestimenta (03):** cambio de temporada: −1,4% ene y −1,1% jul (liquidaciones),
  +1,3% abr y +2,1% oct.
- **Bebidas alcohólicas y tabaco (02):** +2,7% ene (impuestos).
- Alimentos (01) con estacionalidad más repartida (picos ene/mar/set, caída nov).

Decisión: en los SARIMAX por división, la estacionalidad de 02/04/10 se modela
mejor como **determinística de calendario** (dummies enero/febrero/diciembre
asociadas a decisiones administradas) que como SAR(12) puro.

## 2. Correlación TC → divisiones (fig. 2)

- **Transporte (07): 0,46 contemporánea** y 0,25 a t-1 — el canal combustibles.
- Muebles y hogar (05): 0,23 t-0; Información y comunicación (08): 0,21 t-0 —
  bienes durables importados, traslado rápido.
- Alimentos (01): más difusa, máxima a t-1 (0,19).
- No transables (10 Enseñanza, 11 Restaurantes): correlación nula o negativa —
  consistente con la partición transable/no transable del plan.
- IPC general: 0,15 t-0 y 0,14 t-1; casi nada después → el traslado directo es
  rápido y chico.

Decisión: exógenas de TC con rezagos 0-1 (no 0-3) para las divisiones transables;
para no transables, IMS y expectativas cuando estén cargadas.

## 3. Raíz unitaria y persistencia

| Serie | ADF p-valor | Lectura |
|---|---|---|
| π m/m general | 0,43 | no rechaza raíz unitaria — **artefacto de la desinflación** (tendencia decreciente en la media), no de una π integrada; con la muestra 2022+ sola es estacionaria alrededor de una media baja |
| Δlog TC | 0,00 | estacionaria |
| π m/m núcleo | 0,00 | estacionaria |

Persistencia AR(1) de π m/m (controlando estacionalidad):

| Subperíodo | ρ | ee | n |
|---|---|---|---|
| 2011-2019 | 0,10 | 0,10 | 107 |
| 2020-2021 (COVID) | 0,19 | 0,30 | 23 |
| **2022+ (desinflación)** | **0,58** | 0,12 | 54 |

La persistencia medida **subió** en el régimen de desinflación. Lectura: no es más
inercia inflacionaria clásica sino una m/m más suave y predecible (menos ruido de
shocks grandes, trayectoria gradual). Implicancia directa: **los parámetros no son
constantes entre regímenes** — confirma la regla del plan §6 de estimar por
subperíodo y validar solo sobre 2020+.

## 4. Quiebres estructurales (Chow sobre AR(1)+estacionalidad, 2011+)

| Fecha candidata | F | p | Veredicto |
|---|---|---|---|
| sep-2020 (vuelta a la TPM) | 3,03 | 0,0005 | quiebre |
| oct-2022 (cambio de base + desinflación) | 3,68 | <0,0001 | quiebre |

Ambos quiebres del plan §6 se confirman en los datos. Los modelos v1 llevan
dummies/regímenes en esas fechas; el ensemble pondera más el desempeño 2022+.

## 5. Pass-through cambiario preliminar (fig. 3, proyecciones locales)

Respuesta acumulada de la inflación a un shock de 1% en el TC (controles: 2 rezagos
de π, rezago de ΔTC, ΔBRL; errores HAC; bandas 90%):

| Horizonte | 2011-2019 | 2022+ |
|---|---|---|
| 1 mes | 0,07 [−0,01, 0,14] | 0,08 [−0,04, 0,20] |
| 3 meses | 0,01 | 0,00 |
| 6 meses | 0,03 | 0,14 [−0,06, 0,33] |
| 12 meses | 0,11 [−0,00, 0,23] | (muestra corta) |

El pass-through es **bajo (~10% acumulado al año) y frontloaded** (casi todo el
efecto significativo está en el primer mes, vía combustibles/durables). En 2022+
el punto es similar pero con bandas anchas (54 obs). Implicancia: el canal
TC→inflación aporta al nowcast y h=1, pero **no alcanza para mover el pronóstico
a 12-24m** — ahí mandan expectativas, salarios e inercia. Esto eleva la prioridad
de cargar la Encuesta de Expectativas del BCU y el IMS.

## Implicancias para la sesión 3 (benchmarks) y 4 (modelos)

1. La estacionalidad histórica pura va a ser un benchmark difícil de batir en
   los meses de ajustes administrados (ene/feb/dic): el bottom-up debe tratar esos
   meses como información de calendario.
2. π m/m general con media cambiante entre regímenes → los benchmarks y modelos se
   evalúan por subperíodo; el DM test del período completo engaña.
3. Pass-through chico → el BVAR TC-π va a dar trayectorias conjuntas con
   acoplamiento débil; las probabilidades de escenario de TC no deben trasladarse
   mecánicamente a escenarios de inflación.
4. Falta cargar expectativas BCU e IMS antes de la sesión 4 (Phillips y ancla
   12-24m); ver `docs/manifest_fuentes.md` § pendientes.
