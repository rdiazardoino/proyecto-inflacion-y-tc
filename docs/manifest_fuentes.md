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
2. Un portal nuevo Liferay embebido por iframe (`ganges.bcu.gub.uy:8443/eportal/...`)
   — confirmado que existe (p.ej. `/eportal/web/guest/tcre` para el ITCR), pero la
   tabla de datos se carga por JavaScript/AJAX después de la carga inicial de la
   página: un `GET` simple (sin ejecutar JS) trae el cascarón del portal, no la
   serie. Requeriría un navegador headless (Playwright) para renderizar, o
   encontrar el endpoint AJAX que llama internamente.
3. Archivos sueltos en el dominio clásico con naming predecible — así se resolvió
   el TC (SOAP). Para expectativas se intentó el patrón
   `.../Encuesta de Expectativas Econmicas/iees06i{MM}{YY}.pdf` (confirmado con
   ejemplos reales de 2021 a abril-2026), pero **los meses jun-set/2026 dieron
   404**: el contenido se migró a otro lado en algún punto de 2026. Se encontró
   un **cuarto dominio** (`subsitio.bcu.gub.uy`, un sitio moderno separado tanto
   del SharePoint clásico como del eportal Liferay) que parece ser el destino de
   la migración de la sección de política monetaria — agregado como candidato,
   pendiente de verificar en la próxima corrida si sirve datos reales o es otra
   SPA que requiere JavaScript.

**Nota operativa: el BCU apaga sus servicios web de noche** (connect timeout a las
~22:30 de Montevideo, incluido el SOAP de cotizaciones que de día funciona); el
descubrimiento debe correr en horario hábil de Uruguay.

| Serie | Estado | Dónde se obtiene | Plan |
|---|---|---|---|
| Encuesta de Expectativas BCU (inflación 12/24m, TC) | intentando por patrón de nombre | [Expectativas Económicas](https://www.bcu.gub.uy/Estadisticas-e-Indicadores/Paginas/Expectativas-Economicas.aspx) | esperar el próximo descubrimiento; si no trae el PDF, **bajarlo manualmente** de esa página y subirlo a `data/raw/descubrimiento/expectativas_bcu/` |
| ITCR global/bilaterales | bloqueado (dato vía AJAX) | [Tipo de cambio real efectivo](https://www.bcu.gub.uy/Estadisticas-e-Indicadores/Paginas/Tipo-de-cambio-real-efectivo.aspx) → botón de descarga en la página | **requiere descarga manual**: abrir la página, exportar la serie, subir el XLS/CSV a `data/raw/descubrimiento/itcr_bcu/` |
| TPM (decisiones Copom; hoy 5,75%) | bloqueado (mismo portal) | [Política Económica y Mercados](https://www.bcu.gub.uy/Politica-Economica-y-Mercados/Paginas/default.aspx) — comunicados Copom e Informe de Política Monetaria (IPOM, trimestral, con la serie de TPM en anexo) | alternativa: extraer del IPOM en PDF (ya se sabe descargar PDFs, ver licitaciones) |
| Combustibles (precios de venta al público) | página encontrada, sin planillas enlazadas | [URSEA — precios de referencia y PMIT](https://www.gub.uy/unidad-reguladora-servicios-energia-agua/comunicacion/publicaciones/precios-venta-publico-referencia-para-gasolinas-gasoil-50-s-pmit-2) | revisar si la tabla está en el cuerpo de la página (HTML) en vez de un archivo adjunto |
| Tarifas UTE/OSE/Antel | sin explorar | [INE — precios de servicios públicos](https://www.ine.gub.uy/precios-de-servicios-publicos); decretos de Presidencia | tabla `eventos` con Δ% ponderado |
| Licitaciones LRM/Notas del Tesoro | crudos archivados, parser sin calibrar | BCU Operaciones Monetarias / UGD (`data/raw/licitaciones/`) | calibrar `PATRONES` |

Con lo cargado (32 series, incluido el IMS) alcanza para la sesión 3 (benchmarks).
El resto son mejoras que entran sin tocar la arquitectura cuando se resuelvan.
