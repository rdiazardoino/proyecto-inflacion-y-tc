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
| Expectativas de inflación 12/24m (mediana, Encuesta BCU) | **resuelto** — ver "Expectativas de inflación" abajo | — |
| Expectativas de TPM e inflación de operadores financieros (sección "Mercado Financiero") | bloqueado: listado de documentos cargado por AJAX. Desde el 19-oct-2026 `descubrir_js.py` captura la red de esa página para encontrar el pedido | manual, ver `docs/guia_datos_manuales.md` |
| Expectativas de TC | **sin fuente oficial confirmada** (corregido 19-oct-2026: la sección "Mercado Financiero" trae TPM e inflación, no TC) | forward implícito por paridad cubierta, cuando estén las tasas de LRM |
| ITCR global/bilaterales | **resuelto 19-oct-2026** — ver "ITCR" abajo | — |
| TPM (todas las decisiones del Comité, mensual desde ene-2022) | **resuelto 19-oct-2026** — ver "TPM" abajo | — |
| IMAE (brecha de producto) | **resuelto 4-sep-2026** (`bcu_imae.py`) | — |
| Licitaciones (LRM BCU, Notas del Tesoro UGD) | parser sin calibrar. La home de la UGD (archivada semanal) enlaza páginas HTML "Resultado de la licitación…" con la tasa de corte; desde el 19-oct-2026 se archivan para calibrar. La página de LRM del BCU nunca se pudo bajar con requests; se agregó captura con navegador | manual, ver `docs/guia_datos_manuales.md` |

### Expectativas de inflación — resuelto sin navegador (agregado 3-sep-2026)

Hallazgo real de la primera corrida del ETL mensual con los pasos nuevos:
`https://www.bcu.gub.uy/Politica-Economica-y-Mercados/Paginas/Expectativas-de-los-agentes.aspx`
(página clásica SharePoint) **sí trae el dato en HTML estático** — al
contrario de lo que la sesión 1 había concluido para "todo lo clásico del
BCU". La mediana de expectativas de inflación a 12 y 24 meses viene como
texto narrativo dentro de un JSON embebido en un `<script>` de un widget
("La mediana de expectativas de inflación a 24 meses en agosto se mantiene
en la meta de inflación del BCU de 4.5%..."). `src/etl/bcu_expectativas.py`
lo descarga con `requests` (vía `http_client`, sin Playwright) y lo extrae
por regex sobre ese texto. Nuevas variables: `expectativas_inflacion_12m`,
`expectativas_inflacion_24m` (ver `config/variables.yaml`).

**Limitación honesta:** solo el valor vigente al momento de la consulta,
igual que la TPM vía IPOM — no hay serie histórica por esta vía (el listado
de encuestas anteriores está en una tabla cargada por AJAX). Corriendo el
ETL mensual se va construyendo una serie real hacia adelante. La sección
"Expectativas del Mercado Financiero" (TC, TPM esperada) de la misma
página **no** trae valores en HTML estático — es un listado de documentos,
mismo patrón AJAX — sigue pendiente.

### ITCR — resuelto (19-oct-2026)

El widget O3 BI del eportal pide su grid con un POST `...p_p_resource_id=processCommands`
al cargar la página. Replicar esos pedidos a mano (versión anterior de `bcu_itcr.py`) daba
HTTP 401 en producción; en la MISMA corrida del 5-sep-2026 el capturador pasivo de
`descubrir_js.py` recibió los dos grids con status 200. `bcu_itcr.py` ahora abre la página con
Chromium e intercepta esas respuestas; elige el grid de niveles (mediana > 40) y descarta el de
variación interanual. Si la página no responde, `etl_itcr` usa la última captura archivada en
`itcr_bcu_js/red/`, con el vintage de esa fecha y una alerta. Datos: Global, Extrarregional y
Regional, base 2017=100, mensual desde ene-2019.

### TPM — resuelto desde los comunicados del Comité (19-oct-2026)

`Comite-de-Politica-Monetaria.aspx` (archivada por `descubrir_fuentes.py` desde el
3-sep-2026) trae en HTML estático la tabla de comunicados desde ene-2022 con fecha y título;
37 de 38 títulos dicen la tasa resultante. `bcu_tpm.py` arma la TPM vigente a fin de cada mes.
Si un título no trae la tasa, la busca en el detalle del comunicado; si no la encuentra, ese
tramo queda sin dato (may-jun 2022 en la copia archivada). Reemplaza a `bcu_ipom.py`, que
daba un punto por trimestre con fecha aproximada (asignaba 5,75% a ene-2026, cuando la tasa a
fin de ese mes era 6,5%) y tenía la URL del IPOM 1T-2026 fija en el código.

### Descubrimiento con Chromium (Playwright) — agregado 3-sep-2026

`src/etl/descubrir_js.py`, corre en el paso `descubrimiento_fuentes_js` del ETL
mensual. Mismo propósito que `descubrir_fuentes.py` pero con un navegador
real (Chromium headless, instalado en el workflow con
`playwright install --with-deps chromium`): renderiza la página, espera a
que termine el tráfico de red (`wait_until="networkidle"` + 3s de margen
para AJAX lento), y archiva el HTML ya renderizado, cualquier planilla que
solo aparece en el DOM post-render, y las tablas HTML visibles (volcadas a
CSV). Soporta además `clic_texto`: clickear un texto visible después del
primer render, para páginas SPA que enrutan por JS sin `<a href>` navegable
(usado para seguir el link "IMAE" en `subsitio.bcu.gub.uy/estadisticas/`).

Validado contra el BCU real el 3-sep-2026 (primera corrida manual del
workflow tras agregar esto): renderizó las tres páginas sin error de
`goto()`. Dos bugs reales encontrados y corregidos en esa corrida:

1. En pandas ≥2.1 (proyecto en 3.0.5), `pd.read_html()` dejó de aceptar un
   string HTML literal — lo interpreta como ruta de archivo o URL y tira
   `FileNotFoundError` con el HTML entero como "nombre de archivo".
   Corregido envolviendo el string en `io.StringIO()` (encontrado antes de
   commitear, contra una página de prueba local).
2. Contra el HTML real del BCU, `pd.read_html()` necesitó el flavor
   `html5lib` como fallback (lxml no pudo parsear ese HTML) y la
   dependencia no estaba instalada — `ImportError` no capturado que
   abortaba toda la función antes de cerrar el navegador. Agregado
   `html5lib` a `requirements.txt` y ensanchado el `except` a cualquier
   excepción (no solo `ValueError`) para que un fallo ahí nunca tire abajo
   el resto del archivado.

### Otras fuentes pendientes

| Serie | Estado | Dónde |
|---|---|---|
| Combustibles (precios de venta al público) | página encontrada, sin planillas enlazadas | [URSEA — precios de referencia y PMIT](https://www.gub.uy/unidad-reguladora-servicios-energia-agua/comunicacion/publicaciones/precios-venta-publico-referencia-para-gasolinas-gasoil-50-s-pmit-2) | revisar si la tabla está en el cuerpo de la página (HTML) en vez de un archivo adjunto |
| Tarifas UTE/OSE/Antel | sin explorar | [INE — precios de servicios públicos](https://www.ine.gub.uy/precios-de-servicios-publicos); decretos de Presidencia | tabla `eventos` con Δ% ponderado |
| Licitaciones LRM/Notas del Tesoro | crudos archivados, parser sin calibrar | BCU Operaciones Monetarias / UGD (`data/raw/licitaciones/`) | calibrar `PATRONES` |

Con lo cargado (32 series, incluido el IMS) alcanza para la sesión 3 (benchmarks).
El resto son mejoras que entran sin tocar la arquitectura cuando se resuelvan.
