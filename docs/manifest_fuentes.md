# Manifest de fuentes — cobertura real medida

Generado al cierre de la sesión 1 (2-sep-2026), tras la primera carga completa.
La fuente de verdad del inventario es `config/variables.yaml`; este manifest
documenta lo que **efectivamente** entrega cada fuente, medido contra la base.

## Cargado (31 series, ~70.700 observaciones)

| Bloque | Series | Cobertura real | Mecánica de ingesta | Rezago observado |
|---|---|---|---|---|
| IPC general largo | `ipc_general_empalmado` | jul-1937 → jul-2026 (mensual) | Planilla INE "gral y variaciones" base oct-2022: serie oficial ya reexpresada; sin empalme propio | Dato del mes M publicado ~día 4-5 de M+1 |
| IPC general | `ipc_general_idx` (+ MVD/Interior disponibles en planilla) | dic-2010 → jul-2026 | Planilla INE "General_Total Pais_Montevideo_Interior" | ídem |
| IPC divisiones | `ipc_div_01` … `ipc_div_13` (CCIF 2018) | dic-2010 → jul-2026, 188 meses c/u | Planilla INE "IPC_Division_País_desde 2010" (formato tidy) | ídem |
| Núcleo oficial | `ipc_subyacente_idx` (IPC-CE, excluye frutas/verduras/combustibles) | oct-2022 → jul-2026 | Planilla INE "Cuadro inflación subyacente" | ídem |
| TC | `tc_usduyu_interbancario` (diario), `tc_usduyu_prom_m`, `tc_usduyu_cierre_m` | ene-2000 → sep-2026 | SOAP público del BCU (`awsbcucotizaciones`), punto medio compra/venta | mismo día hábil |
| UI | `ui_valor` (diario) | jun-2002 (nacimiento de la UI) → hoy | SOAP BCU | mismo día |
| Externas FRED | `usdbrl`, `dxy`, `ust_10y`, `ust_2y`, `ust_3m`, `fed_funds`, `brent`, `soja`, `cpi_us`, `vix` | 1997 → presente (dxy desde 2006: la serie DTWEXBGS nace ahí) | API FRED con key en secret | 0-1 día hábil (mensuales: semanas) |

Notas de cobertura:
- **TC pre-2000:** el SOAP del BCU no devuelve cotizaciones anteriores a ene-2000 aunque se le pida desde 1997. Si se necesita 1997-1999, buscar serie histórica en planillas del BCU (pendiente, prioridad baja: la muestra de estimación arranca en 2011).
- **Saltos del TC >5% diarios en 2002:** reales (crisis bancaria), no errores de datos. La alerta de outlier queda como documentación.
- **Base mar-1997 del INE:** la página devolvió 404 en las tres URLs candidatas. Irrelevante para la v1: la serie oficial reexpresada desde 1937 la sustituye con ventaja.
- **`DEXUSUY` (USD/UYU en FRED):** no existe (HTTP 400). El control cruzado del TC queda pendiente de otra fuente.

## Infraestructura que quedó resuelta en esta sesión

- Tabla `variables` sembrada desde `variables.yaml` + derivadas + 13 divisiones (`src/etl/seed.py`); FK de `observaciones` ahora se cumple por construcción y el test [5] lo protege.
- SSL de `www5.ine.gub.uy` / `www.bcu.gub.uy` (no envían certificados intermedios): reparación por AIA con verificación de firmas contra raíces de certifi (`src/etl/http_client.py`); intermedios cacheados y versionados en `data/raw/certs/` (Abitab, Sectigo, Certum).
- Planillas crudas del INE versionadas en `data/raw/ine/` como archivo de vintages (el sandbox de análisis no puede descargarlas).
- Parsers del IPC específicos por planilla, con tests contra los archivos reales (test [6]).

## Pendiente de ingesta (siguiente iteración de datos)

Prioridad A del plan aún sin ingestor automático:

| Serie | Fuente | Plan |
|---|---|---|
| Encuesta de Expectativas Económicas BCU (inflación 12/24m, TC) | BCU (XLS mensual) | ingestor nuevo; el fix SSL ya destraba el host |
| ITCR global/bilaterales | BCU (XLS mensual) | ídem |
| TPM (decisiones Copom) | BCU (evento) | tabla de eventos + serie escalonada |
| IMS (Índice Medio de Salarios) | INE (XLS mensual) | mismo patrón que IPC |
| Combustibles ANCAP / tarifas UTE-OSE-Antel | ANCAP/Presidencia (evento) | tabla `eventos` con Δ% ponderado |
| Licitaciones LRM/Notas del Tesoro | BCU/UGD | calibrar `PATRONES` con los HTML/PDF ya archivados en `data/raw/licitaciones/` |

Con lo cargado alcanza para arrancar la sesión 2 (EDA: estacionalidad por división,
correlaciones TC→componentes, quiebres, pass-through preliminar).
