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
| IMS (Índice Medio de Salarios) | `salario_nominal_ims` (IMSN), `ims_general_idx` | dic-2002 → jul-2026 (IMSN); 1968 → jul-2026 (general) | Planilla INE "IMSN_M_B08" / "IMS_C1_Gral_emp_M_B08", mismo layout que el IPC | ~día 4-5 de M+1 |

Notas de cobertura:
- **TC pre-2000:** el SOAP del BCU no devuelve cotizaciones anteriores a ene-2000 aunque se le pida desde 1997. Si se necesita 1997-1999, buscar serie histórica en planillas del BCU (pendiente, prioridad baja: la muestra de estimación arranca en 2011).
- **Saltos del TC >5% diarios en 2002:** reales (crisis bancaria), no errores de datos. La alerta de outlier queda como documentación.
- **Base mar-1997 del INE:** la página devolvió 404 en las tres URLs candidatas. Irrelevante para la v1: la serie oficial reexpresada desde 1937 la sustituye con ventaja.
- **`DEXUSUY` (USD/UYU en FRED):** no existe (HTTP 400). El control cruzado del TC queda pendiente de otra fuente.
- **Bug de encoding en nombres de archivo (corregido 3-sep-2026):** `ine_ipc.descargar()` no decodificaba `%20` antes de sanitizar el nombre, así que los archivos quedaban como `IMSN_20M_20B08.xls` en vez de `IMSN_M_B08.xls`. No corrompía el contenido (se parseaba igual con la heurística genérica) pero rompía cualquier matching por nombre de archivo — causó que el primer intento de ingestor del IMS fallara. Las planillas históricas ya commiteadas quedan con el nombre sucio (no se reescribe el historial); las nuevas descargas salen limpias.

## Infraestructura que quedó resuelta en esta sesión

- Tabla `variables` sembrada desde `variables.yaml` + derivadas + 13 divisiones (`src/etl/seed.py`); FK de `observaciones` ahora se cumple por construcción y el test [5] lo protege.
- SSL de `www5.ine.gub.uy` / `www.bcu.gub.uy` (no envían certificados intermedios): reparación por AIA con verificación de firmas contra raíces de certifi (`src/etl/http_client.py`); intermedios cacheados y versionados en `data/raw/certs/` (Abitab, Sectigo, Certum).
- Planillas crudas del INE versionadas en `data/raw/ine/` como archivo de vintages (el sandbox de análisis no puede descargarlas).
- Parsers del IPC específicos por planilla, con tests contra los archivos reales (test [6]).

## Pendiente de ingesta

**Hallazgo clave del BCU (3-sep-2026): el sitio no tiene una sola arquitectura.**
Tiene tres capas distintas y el dato real vive en lugares distintos según la serie:

1. Páginas clásicas `.aspx` (SharePoint) — cascarones vacíos, sin el dato.
2. Un portal Liferay embebido por iframe (`ganges.bcu.gub.uy:8443/eportal/...`) —
   confirmado que existe (`/eportal/web/guest/tcre` para el ITCR responde 200 con
   una página real del BCU), pero la tabla de datos se carga por JavaScript/AJAX
   después de la carga inicial: un `GET` simple trae el cascarón del portal
   (menús, título "TCRE"), no la serie.
3. Un sitio moderno (`subsitio.bcu.gub.uy/politica-monetaria/`), hallado el
   3-sep-2026 buscando dónde migró el contenido tras el 404 en las rutas clásicas
   — mismo problema: 13 scripts externos, el `<body>` estático trae solo el texto
   introductorio ("¿Qué es la política monetaria?"), la TPM y los datos se
   renderizan client-side.

**Conclusión, no es un problema de URL: es estructural.** Las tres plataformas
nuevas del BCU (Liferay, subsitio) exigen ejecutar JavaScript para ver el dato.
Ninguna URL alternativa lo resuelve con `requests.get()`. La única vía
automatizada real es un navegador headless (Playwright) corriendo en GitHub
Actions (que sí tiene red completa, a diferencia del sandbox de análisis) — no
implementado todavía, queda como decisión pendiente por su costo (nueva
dependencia pesada, automatizar contra 3 portales sin poder probarlos desde acá).

**Nota operativa: el BCU apaga sus servicios web de noche** (connect timeout a las
~22:30 de Montevideo, incluido el SOAP de cotizaciones que de día funciona); el
descubrimiento debe correr en horario hábil de Uruguay.

| Serie | Estado | Alternativa mientras tanto |
|---|---|---|
| Encuesta de Expectativas BCU (inflación 12/24m, TC) | **en prueba** — ver "Descubrimiento con Chromium" abajo | **descarga manual**: abrir [Política Monetaria — BCU](https://subsitio.bcu.gub.uy/politica-monetaria/), exportar la encuesta, subir el archivo a `data/raw/descubrimiento/expectativas_bcu/` |
| ITCR global/bilaterales | **en prueba** — ver "Descubrimiento con Chromium" abajo | **descarga manual**: abrir [`/eportal/web/guest/tcre`](https://ganges.bcu.gub.uy:8443/eportal/web/guest/tcre), exportar la serie, subir a `data/raw/descubrimiento/itcr_bcu/` |
| TPM (decisiones Copom) | **resuelto parcialmente** — ver abajo | [IPOM](https://www.bcu.gub.uy/Politica-Economica-y-Mercados/Reportes%20de%20Poltica%20Monetaria/IPOM_2026-1.pdf) (trimestral, sí es PDF estático) |
| TPM histórica completa (todas las reuniones del Copom) | sin ingestor; candidatas de URL sin confirmar en `descubrir_fuentes.py` (`tpm_historica_bcu`) | pendiente de lo que archive el próximo ETL mensual |
| IMAE (brecha de producto) | sin ingestor; candidatas de URL sin confirmar en `descubrir_fuentes.py` (`imae_bcu`) y `descubrir_js.py` (`imae_bcu_js`) | pendiente de lo que archive el próximo ETL mensual |

### Descubrimiento con Chromium (Playwright) — agregado 3-sep-2026

`src/etl/descubrir_js.py`, corre en el paso `descubrimiento_fuentes_js` del ETL
mensual. Mismo propósito que `descubrir_fuentes.py` pero con un navegador
real (Chromium headless, instalado en el workflow con
`playwright install --with-deps chromium`): renderiza la página, espera a
que termine el tráfico de red (`wait_until="networkidle"` + 3s de margen
para AJAX lento), y archiva el HTML ya renderizado, cualquier planilla que
solo aparece en el DOM post-render, y las tablas HTML visibles (volcadas a
CSV — frecuente que el portal Liferay muestre el dato en una tabla en vez
de una planilla descargable).

**No se pudo probar contra las páginas reales de BCU** (el sandbox de
análisis no tiene salida a `bcu.gub.uy`, solo GitHub Actions la tiene). Se
validó la mecánica contra una página de prueba local servida en el propio
sandbox — confirmado que Playwright funciona en este entorno, que captura
correctamente contenido inyectado por `setTimeout`, descarga el archivo
enlazado post-render, y extrae la tabla a CSV. La calibración real (¿la URL
de `subsitio.bcu.gub.uy/politica-monetaria/` sigue siendo válida?, ¿el
`eportal` de `itcr_bcu_js` responde fuera de horario hábil de Uruguay?, ¿qué
forma tiene el HTML/tabla real?) se hace la primera vez que el ETL mensual
corra este paso y archive algo real en `data/raw/descubrimiento/*_js/`.

Bug real encontrado durante esa prueba local, antes de commitear: en pandas
≥2.1 (proyecto en 3.0.5), `pd.read_html()` dejó de aceptar un string HTML
literal — lo interpreta como ruta de archivo o URL y tira
`FileNotFoundError` con el HTML entero como "nombre de archivo". Corregido
envolviendo el string en `io.StringIO()`.

### TPM: extracción del IPOM (resuelta con una limitación documentada)

El Informe de Política Monetaria (IPOM, trimestral) sí es un PDF estático
descargable — a diferencia de ITCR y Expectativas, no requiere JavaScript.
`src/etl/bcu_ipom.py` extrae por regex la frase del Resumen Ejecutivo
("...resolvió mantener la Tasa de Política Monetaria (TPM) en 5,75%...") y la
carga como observación de `tpm_bcu`. Verificado contra el IPOM real del
1T-2026: extrae **5,75%** correctamente.

**Limitación honesta:** el IPOM no siempre da la fecha exacta de la reunión
del Copom, así que `fecha_ref` es el primer mes del trimestre que cubre el
informe (deducido del nombre `IPOM_{año}-{trimestre}.pdf`), no la fecha real
de la decisión. Además solo da el valor *vigente al momento del informe*: la
serie queda con un punto por trimestre (cuando se archive el próximo IPOM),
no la serie mensual completa de todas las reuniones del Copom — para eso
haría falta parsear los comunicados individuales de cada reunión (~8/año),
que si están en el dominio clásico como PDFs sueltos (`/Acerca-de-BCU/...ACTA
*COPOM.pdf`, confirmado que existe al menos uno por búsqueda web) — pendiente
para una iteración futura si se necesita mayor frecuencia.
| Combustibles (precios de venta al público) | página encontrada, sin planillas enlazadas | [URSEA — precios de referencia y PMIT](https://www.gub.uy/unidad-reguladora-servicios-energia-agua/comunicacion/publicaciones/precios-venta-publico-referencia-para-gasolinas-gasoil-50-s-pmit-2) | revisar si la tabla está en el cuerpo de la página (HTML) en vez de un archivo adjunto |
| Tarifas UTE/OSE/Antel | sin explorar | [INE — precios de servicios públicos](https://www.ine.gub.uy/precios-de-servicios-publicos); decretos de Presidencia | tabla `eventos` con Δ% ponderado |
| Licitaciones LRM/Notas del Tesoro | crudos archivados, parser sin calibrar | BCU Operaciones Monetarias / UGD (`data/raw/licitaciones/`) | calibrar `PATRONES` |

Con lo cargado (32 series, incluido el IMS) alcanza para la sesión 3 (benchmarks).
El resto son mejoras que entran sin tocar la arquitectura cuando se resuelvan.
