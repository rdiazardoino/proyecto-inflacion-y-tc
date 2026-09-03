# Manual operativo — 1 página

## Cadencia

| Cuándo | Qué corre | Dónde |
|---|---|---|
| Días hábiles 18:30 Montevideo | ETL diario (TC, FRED) | GitHub Actions (automático) |
| Día 5 de cada mes ~10:00 Montevideo | ETL mensual (+ IPC, IMS, descubrimiento de fuentes bloqueadas) | GitHub Actions (automático) |
| Después del ETL mensual, o a demanda | Análisis completo: backtest, ensemble, escenarios, dashboard, informe | Local / Cowork (manual, este documento) |

## Corrida mensual — pasos

1. **Verificar que el ETL mensual corrió** tras la publicación del IPC (INE, ~día 4-5 hábil):
   `git pull` y chequear `SELECT MAX(fecha_ref) FROM v_series_actual WHERE var_id='ipc_general_idx'`.
   Si no avanzó, disparar manualmente el workflow `ETL` (modo `mensual`) desde GitHub Actions.
2. **Revisar alertas críticas abiertas**: `SELECT * FROM alertas WHERE resuelta=0 AND severidad='critica'`.
   Si hay alguna real (no un timeout nocturno transitorio del BCU), resolverla antes de seguir.
3. **Correr el pipeline de análisis** (en este orden, cada uno depende del anterior):
   ```
   python src/models/backtest.py              # benchmarks, ~10 seg
   python src/models/backtest_sesion4.py       # modelos económicos, ~10 seg
   python src/models/run_sesion5.py            # ensemble + escenarios, ~5 seg
   python src/report/build_dashboard.py        # dashboard.html + forecasts.csv
   python src/report/build_informe.py          # informe.html + informe.pdf
   ```
   O todo junto: `python src/forecast/run_forecast.py`.
4. **Revisar el dashboard** (`outputs/dashboards/YYYY-MM/dashboard.html`) antes de distribuirlo:
   ¿el nowcast es razonable? ¿las bandas de incertidumbre tienen sentido? ¿el semáforo de calidad
   está en verde o amarillo esperable?
5. **Decidir ajustes expertos** (si corresponde): un evento conocido no capturado por los modelos
   (tarifa anunciada, shock puntual) se registra en la tabla `ajustes_expertos` con justificación —
   nunca se edita el pronóstico del modelo directamente.
6. **Commitear y taguear**: `git add -A && git commit -m "corrida YYYY-MM" && git tag vYYYY-MM && git push --tags`.

**Tiempo estimado:** 30-45 minutos, la mayor parte en el paso 4 (revisión humana).

## Qué hacer si algo falla

- **ETL no corrió / falló:** ver `docs/manifest_fuentes.md` para el estado conocido de cada fuente.
  El BCU apaga sus servicios de noche — un fallo del SOAP a esa hora se resuelve solo al día siguiente.
- **Un modelo tira error en el backtest:** correr con datos hasta el mes anterior
  (`--modo` no aplica aquí; ver el propio script) para aislar si el problema es el dato nuevo o el código.
- **El ensemble queda vacío para un objetivo:** revisar `metricas_backtest` — probablemente falta el
  corte `2022+` para ese objetivo/horizonte (pocas observaciones). No forzar un pronóstico sin base.

## Dónde está cada cosa

- **Datos:** `db/proyecto.db` (point-in-time, nunca se pisa). Planillas crudas en `data/raw/`.
- **Modelos y backtest:** `src/models/`. Resultados en `metricas_backtest`, `errores`, `pronosticos`.
- **Reportes:** `src/report/`. Salidas en `outputs/dashboards/` y `outputs/informes/`, por mes.
- **Metodología y hallazgos de cada sesión:** `docs/eda_sesion2.md`, `backtest_sesion3.md`,
  `backtest_sesion4.md`, `ensemble_escenarios_sesion5.md`, `manifest_fuentes.md`.

## Qué falta para que esto sea más robusto (ver también `manifest_fuentes.md`)

Encuesta de Expectativas del BCU e ITCR (bloqueados, requieren navegador headless), IMAE (brecha de
producto, sin ingestor todavía), historia completa de la TPM (solo un punto), exógenas por división
para el SARIMAX bottom-up genuino. Ninguno es una tarea de modelado — todos son de ingesta de datos.
