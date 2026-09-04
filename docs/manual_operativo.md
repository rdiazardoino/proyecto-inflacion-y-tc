# Manual operativo — 1 página

## Cadencia

| Cuándo | Qué corre | Dónde |
|---|---|---|
| Días hábiles 18:30 Montevideo | ETL diario (TC, FRED) | GitHub Actions (automático) |
| Día 5 de cada mes ~10:00 Montevideo | ETL mensual (+ IPC, IMAE, expectativas, ITCR, descubrimiento) | GitHub Actions (automático) |
| Día 5 de cada mes ~11:30 Montevideo | Análisis completo: backtest, ensemble, escenarios, dashboard, informe | GitHub Actions (automático, workflow `Analisis mensual`) |

**Automatizado de punta a punta desde el 4-sep-2026** (workflow `analisis.yml`, 90 min de margen
después del ETL para que este termine y commitee). Antes era manual — ver más abajo cómo disparar
o repetir a demanda.

**Importante sobre los `schedule:` de ambos workflows**: GitHub Actions solo evalúa los triggers de
cron usando el archivo tal como está en la rama **default** del repositorio. Si en algún momento se
vuelve a trabajar en una rama que no es la default, los cron no van a dispararse solos aunque el
workflow esté commiteado ahí — hay que fusionar a la rama default (o cambiar cuál es la default)
para que la automatización real funcione. Esto ya pasó una vez (3 y 4-sep-2026): el cron estaba
configurado hacía días y nunca había corrido solo por esta razón exacta.

## Corrida mensual — qué revisar (ya no hace falta disparar nada a mano)

1. **Confirmar que las dos corridas del día 5 terminaron bien**: pestaña Actions de GitHub, workflows
   `ETL` y `Analisis mensual`. Si alguna falló, revisar el log — casi siempre es una fuente puntual
   caída (ver `docs/manifest_fuentes.md`), no el pipeline entero.
2. **Revisar alertas críticas abiertas**: `SELECT * FROM alertas WHERE resuelta=0 AND severidad='critica'`.
   Si hay alguna real (no un timeout nocturno transitorio del BCU), resolverla.
3. **Descargar el dashboard y el informe** del artefacto `analisis-<N>` del run de `Analisis mensual`
   (Actions → el run del día 5 → Artifacts). No se versionan en git a propósito (se regeneran cada
   corrida, ver `.gitignore`).
4. **Revisar el dashboard** antes de distribuirlo: ¿el nowcast es razonable? ¿las bandas de
   incertidumbre tienen sentido? ¿el semáforo de calidad está en verde o amarillo esperable?
5. **Decidir ajustes expertos** (si corresponde): un evento conocido no capturado por los modelos
   (tarifa anunciada, shock puntual) se registra en la tabla `ajustes_expertos` con justificación —
   nunca se edita el pronóstico del modelo directamente.

**A demanda / si algo falló**: disparar manualmente cualquiera de los dos workflows desde Actions
(`workflow_dispatch`) — `ETL` primero (elegir modo `mensual` si hace falta recargar IPC/IMAE/etc.),
`Analisis mensual` después, una vez que el primero haya commiteado.

**Correr localmente** (debug, o si GitHub Actions no es una opción): mismos pasos que antes,
`python src/forecast/run_forecast.py` corre todo el pipeline de análisis en orden.

## Qué hacer si algo falla

- **ETL no corrió / falló:** ver `docs/manifest_fuentes.md` para el estado conocido de cada fuente.
  El BCU apaga sus servicios de noche — un fallo del SOAP a esa hora se resuelve solo al día siguiente.
- **Un modelo tira error en el backtest:** correr `python src/models/backtest_sesion4.py` (u otro
  script suelto) localmente para aislar si el problema es el dato nuevo o el código.
- **El ensemble queda vacío para un objetivo:** revisar `metricas_backtest` — probablemente falta el
  corte `2022+` para ese objetivo/horizonte (pocas observaciones). No forzar un pronóstico sin base.
- **El workflow `Analisis mensual` corrió pero el PDF del informe no aparece:** weasyprint necesita
  librerías del sistema (Pango/Cairo) — si el paso de instalación de esas librerías falla o cambia
  de nombre en una imagen de Ubuntu futura, el informe sigue generándose en HTML igual (el PDF es
  best-effort, ver el try/except en `build_informe.py`).

## Dónde está cada cosa

- **Datos:** `db/proyecto.db` (point-in-time, nunca se pisa). Planillas crudas en `data/raw/`.
- **Modelos y backtest:** `src/models/`. Resultados en `metricas_backtest`, `errores`, `pronosticos`.
- **Reportes:** `src/report/`. Salidas en `outputs/dashboards/` y `outputs/informes/`, por mes.
- **Metodología y hallazgos de cada sesión:** `docs/eda_sesion2.md`, `backtest_sesion3.md`,
  `backtest_sesion4.md`, `ensemble_escenarios_sesion5.md`, `manifest_fuentes.md`.

## Qué falta para que esto sea más robusto (ver también `manifest_fuentes.md`)

**Resuelto el 4-sep-2026**:
- Expectativas de inflación del BCU (mediana 12/24m) — HTML estático de una página que se creía
  bloqueada (`src/etl/bcu_expectativas.py`). Solo da el valor vigente en cada corrida, no la serie
  histórica completa — se construye hacia adelante.
- IMAE (brecha de producto) — serie histórica COMPLETA (original, desestacionalizada,
  tendencia-ciclo, 2016-2026) embebida como JSON en un reporte Plotly/R (`src/etl/bcu_imae.py`),
  sin necesitar navegador. Ya integrado como regresor en la curva de Phillips (`src/models/
  phillips.py`, filtro HP real-time — ver docstring del módulo para la limitación honesta del
  "problema de fin de muestra").
- Automatización del pipeline de análisis mensual completo (ver más arriba).

**Intentado, pausado**: ITCR — el dato SÍ se puede traer sin navegador extra (tres pedidos HTTP
encadenados a un motor BI de terceros, `src/etl/bcu_itcr.py`), pero el paso 1 (encontrar los
portlets, insertados por AJAX) necesita Chromium igual. Validado offline contra piezas reales del
BCU y contra una simulación local completa; en producción tuvo dos fallas distintas ya corregidas
(401 por usar el contexto de pedidos de Playwright en vez de `fetch()` desde la página) y luego dos
timeouts de red seguidos navegando a la página — no se pudo confirmar el fix final contra el BCU
real en esta sesión. El código queda commiteado y se reintenta solo en la próxima corrida mensual;
si vuelve a fallar, revisar el log de `bcu_itcr` en el workflow `ETL` antes de asumir que el bug
sigue ahí. Mientras tanto, descarga manual (ver `manifest_fuentes.md`).

**Sin resolver**: TPM histórica completa (todas las reuniones del Copom, hoy solo un punto vía
IPOM) — sin planilla encontrada todavía, dos páginas candidatas revisadas fueron caminos muertos.
Exógenas por división para el SARIMAX bottom-up genuino — sin abordar, baja prioridad (la sesión 4
no encontró ningún challenger que le ganara al benchmark top-down). Expectativas de inflación como
regresor dinámico en Phillips (hoy usa la meta constante del BCU) — dato ya cargado, falta
integrarlo al modelo. Ninguno de estos bloquea la operación mensual.
