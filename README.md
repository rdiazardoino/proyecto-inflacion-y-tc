# Proyecto Inflación y Tipo de Cambio — Uruguay

Sistema propio de nowcast y pronóstico del IPC uruguayo y del USD/UYU a 1, 6, 12 y 24 meses, con backtesting, registro point-in-time y reportes automáticos.

El brief completo está en [`docs/BRIEF.md`](docs/BRIEF.md).

## Arquitectura

El ETL corre en **GitHub Actions** y el análisis en **Cowork**. La separación no es estética: el entorno de ejecución de Cowork no tiene salida a internet hacia `ine.gub.uy`, `bcu.gub.uy` ni `fred.stlouisfed.org`. Actions descarga, valida y commitea los datos al repo; Cowork transforma, modela y reporta sobre los datos ya locales.

```
GitHub Actions  →  descarga  →  db/proyecto.db  →  commit
                                      ↓
                              OneDrive (git pull)
                                      ↓
Cowork          →  transformación, modelos, backtest, reportes
```

## Puesta en marcha

**1. Clonar el repo dentro de la carpeta de OneDrive.**

```bash
cd "C:\Users\rdiaz\OneDrive\Documentos"
git clone https://github.com/rdiazardoino/proyecto-inflacion-y-tc.git "Proyecto de Inflacion y TC"
```

Si la carpeta ya tiene estos archivos, en vez de clonar:

```bash
cd "C:\Users\rdiaz\OneDrive\Documentos\Proyecto de Inflacion y TC"
git init
git remote add origin https://github.com/rdiazardoino/proyecto-inflacion-y-tc.git
git add -A && git commit -m "estructura inicial: brief, esquema, ETL"
git branch -M main && git push -u origin main
```

**2. Sacar la API key de FRED.** Gratis, sale en un minuto: https://fredaccount.stlouisfed.org/apikeys

**3. Cargarla como secret del repo.** En GitHub: Settings → Secrets and variables → Actions → New repository secret. Nombre `FRED_API_KEY`.

**4. Correr la carga histórica.** En la pestaña Actions del repo: workflow `ETL` → Run workflow → modo `historico`. Tarda unos minutos porque el SOAP del BCU se pide por tramos anuales desde 1997.

**5. Traer los datos a la carpeta local.** `git pull`.

## Cadencia automática

| Cuándo | Modo | Qué trae |
|---|---|---|
| Días hábiles 18:30 Montevideo | `diario` | TC del BCU, series diarias de FRED |
| Viernes 18:30 | `semanal` | lo anterior más UI y licitaciones |
| Día 5 de cada mes 10:00 | `mensual` | todo, incluido el IPC del INE |

Se puede disparar a mano en cualquier momento desde Actions → Run workflow.

## Fuentes

| Serie | Fuente | Acceso |
|---|---|---|
| USD/UYU diario, UI | BCU | Web service SOAP público (`cotizaciones.bcu.gub.uy`) |
| IPC y aperturas | INE | Planillas de tres bases encadenadas (1997, 2010, 2022) |
| Externas y commodities | FRED | API con key gratuita |
| Licitaciones LRM | BCU | Publicación en el día, antes de las 17:00 |
| Notas del Tesoro UYU/UI/UP | UGD / MEF | `deuda.mef.gub.uy`, mismo día |

**BEVSA queda afuera.** El sitio es un ASPX renderizado por JavaScript y no publica API abierta. No es bloqueante: las tasas de corte de las licitaciones dan curva primaria en pesos, UI y UP, y con eso se calcula break-even de inflación y forward USD/UYU por paridad cubierta.

## Estado de verificación del código

Lo que está probado y lo que no, sin ambigüedad:

**Verificado offline** (`python tests/test_etl.py`, 22 checks, corre también en CI antes de cada ETL): el diseño point-in-time —una revisión del INE agrega un vintage nuevo y nunca pisa el dato original, y `serie(vintage_max=...)` reproduce exactamente lo que se sabía en una fecha pasada—, el empalme de las bases del IPC por variación mensual sin discontinuidad en el corte, el parseo de etiquetas de período del INE y la detección de moneda en textos de licitación.

**Sin verificar contra el servidor real**, porque no hay salida a internet desde acá: la estructura exacta de la respuesta del SOAP del BCU, el layout de las planillas del INE, y sobre todo el parser de licitaciones. Los tres están escritos de forma defensiva: si no encuentran lo que esperan levantan una alerta en la tabla `alertas` en vez de escribir un número inventado.

Para calibrar el parser de licitaciones hay un modo de descubrimiento que archiva los documentos crudos y vuelca su estructura:

```bash
python -m src.etl.licitaciones descubrir
```

La primera corrida de `historico` en Actions va a mostrar en el log qué parsea bien y qué no.

## Estructura

```
config/variables.yaml      inventario de variables con fuente, rezago e hipótesis
db/schema.sql              esquema SQLite point-in-time (20 tablas)
db/proyecto.db             la base. Versionada: es el registro histórico
src/etl/                   descarga: BCU SOAP, INE, FRED, licitaciones
src/{transform,features,models,validation,forecast,scenarios,report,viz,qc}/
data/raw/                  documentos crudos con fecha de descarga
docs/BRIEF.md              objetivo, alcance, criterios de aceptación
tests/test_etl.py          tests offline
```

## Advertencia sobre SQLite en OneDrive

Escribir la base desde dos procesos a la vez la puede corromper. El ETL respalda el `.db` antes de cada corrida (`db/backups/`, se conservan 10). Regla operativa: no correr el ETL local mientras Actions está corriendo, y esperar a que OneDrive termine de sincronizar antes de un `git pull`.
