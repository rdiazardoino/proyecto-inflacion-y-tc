# Guía de datos manuales

Actualizada el 19-oct-2026. Qué datos hay que conseguir a mano (porque el ETL todavía no los trae
solo), dónde están y cómo cargarlos.

## Ya no hace falta bajar a mano

| Dato | Desde | Cómo entra |
|---|---|---|
| ITCR global, extrarregional y regional | 19-oct-2026 | `bcu_itcr.py`: intercepta las respuestas del gráfico del BCU |
| TPM (todas las decisiones desde ene-2022) | 19-oct-2026 | `bcu_tpm.py`: listado de comunicados del Comité de Política Monetaria |
| IMAE / brecha de producto | 4-sep-2026 | `bcu_imae.py` |
| Expectativas de inflación 12 y 24 meses (encuesta a analistas) | 3-sep-2026 | `bcu_expectativas.py` (un punto por mes, se acumula) |
| Precios de combustibles | — | No hace falta bajarlos: están en HTML estático de URSEA y MIEM, ya archivados cada mes. Falta escribir el parser |

## Cómo se carga un dato manual

Un valor:

```
python src/etl/cargar_manual.py <var_id> <YYYY-MM-01> <valor> --fuente "de dónde salió"
```

Varios valores (CSV con columnas `fecha_ref,valor`):

```
python src/etl/cargar_manual.py <var_id> --csv archivo.csv --fuente "..."
```

`fecha_ref` es el mes al que corresponde el dato, no el día de descarga. Todo lo que entra así
aparece solo en un recuadro del dashboard y del informe, con la serie, el mes del dato y la fecha
de carga.

## Lo que sigue manual, por prioridad

### 1. Notas del Tesoro en pesos y en UI → break-even de inflación

- **Para qué**: la diferencia entre la tasa en pesos y la tasa en UI al mismo plazo es la inflación
  que descuenta el mercado. Hoy el informe no tiene ninguna expectativa de mercado contra la cual
  contrastar el pronóstico, y la sección "Implicancias de inversión" está limitada por eso.
- **Dónde**: <https://deuda.mef.gub.uy/>, sección de licitaciones. Cada licitación tiene una página
  "Resultado de la licitación de la Serie N en Pesos Nominales (UYU)" o "... en Unidades Indexadas".
- **Qué anotar, por licitación**: fecha, serie, moneda (UYU / UI / UP), fecha de vencimiento,
  tasa de corte (%), monto adjudicado.
- **Formato**: CSV con columnas `fecha,serie,moneda,vencimiento,tasa_corte,monto_adjudicado`.
  Va a la tabla `licitaciones`, no por `cargar_manual.py` (el cargador para esa tabla se escribe
  con el primer archivo real).
- **Frecuencia**: cada licitación (el calendario del 2.º semestre 2026 tiene 19).
- **Probablemente deje de ser manual pronto**: desde el 19-oct-2026 el ETL semanal archiva esas
  páginas de resultado; con 2 o 3 páginas reales se calibra el parser sin adivinar.

### 2. Letras de Regulación Monetaria (LRM) del BCU → tasa corta en pesos

- **Para qué**: es el tramo corto de la curva en pesos. Con esa tasa y la del Tesoro de EE.UU. se
  calcula el tipo de cambio forward implícito, que sirve como referencia de mercado para el
  pronóstico de TC (hoy no hay ninguna).
- **Dónde**: <https://www.bcu.gub.uy/Politica-Economica-y-Mercados/Paginas/Operaciones-Monetarias.aspx>
- **Qué anotar, por licitación**: fecha, plazo (días), tasa de corte (%), monto adjudicado.
- **Formato**: CSV con columnas `fecha,plazo_dias,tasa_corte,monto_adjudicado`.
- **Estado de la automatización**: esa página nunca se pudo bajar con un pedido HTTP común. Desde
  el 19-oct-2026 el ETL mensual la abre con navegador y captura su tráfico de red, para ver si se
  puede automatizar.

### 3. Expectativas de operadores financieros (TPM esperada e inflación)

- **Para qué**: qué tasa espera el mercado para las próximas reuniones del Comité. Sirve para leer
  si el mercado ve más recortes o subas y para contrastar con la TPM vigente.
- **Dónde**: <https://www.bcu.gub.uy/Politica-Economica-y-Mercados/Paginas/Expectativas-de-los-agentes.aspx>,
  sección "Mercado Financiero". Según la propia página, trae expectativas de TPM e inflación de
  operadores primarios, aspirantes y AFAP.
- **Qué anotar**: el formato del documento todavía no se conoce (el listado se carga por
  JavaScript y nunca se pudo archivar). Guardar el documento más reciente tal cual (PDF o Excel)
  en `data/raw/manual/`; con el primero se definen y registran las series.
- **Frecuencia**: mensual.

### 4. Expectativas de tipo de cambio

- La sección "Mercado Financiero" de la encuesta del BCU trae TPM e inflación, no tipo de cambio,
  y en lo archivado de esa página no aparece ninguna expectativa de TC.
- **A confirmar**: si en esa misma página hay otra encuesta (por ejemplo, a analistas) que
  publique el TC esperado a fin de año, ese es el dato. Se carga con
  `cargar_manual.py exp_tc_bcu_dic <mes de la encuesta> <valor>`.
- **Alternativa sin encuesta**: el forward implícito del punto 2.

### 5. Tarifas de UTE, OSE y Antel

- **Para qué**: son precios administrados que se anuncian antes de entrar en vigencia (sobre todo en
  enero). Cargados a tiempo, mejoran el nowcast del mes en que aplican.
- **Dónde**: decretos y comunicados del Poder Ejecutivo; el MIEM publica los pliegos tarifarios de
  UTE en <https://www.gub.uy/ministerio-industria-energia-mineria/tematica/tarifas>.
- **Qué anotar**: el % de ajuste promedio y el mes en que entra en vigencia.
- **Cómo**: `cargar_manual.py tarifa_ute 2027-01-01 <% de ajuste> --fuente "Decreto ..."`.
  Para OSE y Antel no hay series registradas todavía (se agregan a `config/variables.yaml` cuando
  haya un dato real).
- **Frecuencia**: cuando se anuncian (típicamente una vez al año).

### No recomendado: curvas de BEVSA

Mercado secundario, más fino que el primario, pero sin acceso automático y con datos que cambian a
diario. Las licitaciones (puntos 1 y 2) cubren lo que el sistema necesita.
