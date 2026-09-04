"""
Orquestador del ETL. Corre en GitHub Actions, no en Cowork.

Modos:
  --modo diario     TC del BCU + series diarias de FRED
  --modo semanal    diario + licitaciones
  --modo mensual    todo, incluida la recarga del IPC del INE
  --modo historico  carga inicial completa desde 1997

Cada paso deja registro en logs_actualizacion y levanta alertas cuando
una fuente no responde o una serie no trae dato nuevo donde deberia.
El proceso NO aborta al primer error: cada fuente falla de forma aislada.
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
import traceback
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.etl import bcu_cotizaciones, bcu_expectativas, bcu_imae, bcu_ipom, fred_series, ine_ipc, ine_ims, licitaciones  # noqa: E402
from src.etl import db, descubrir_fuentes, descubrir_js, seed  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"


# ---------------------------------------------------------------------
def paso(nombre: str):
    """Decorador: mide, loguea y aisla fallos de cada fuente."""
    def deco(fn):
        def wrapper(con, *a, **kw):
            t0 = time.time()
            try:
                res = fn(con, *a, **kw)
                db.log(con, "etl", "ok", var_id=nombre,
                       filas_nuevas=res if isinstance(res, int) else None,
                       mensaje=None, duracion_seg=round(time.time() - t0, 1))
                return res
            except Exception as e:                    # noqa: BLE001
                db.log(con, "etl", "error", var_id=nombre,
                       mensaje=f"{type(e).__name__}: {e}",
                       duracion_seg=round(time.time() - t0, 1))
                db.alerta(con, "serie_desactualizada", "critica",
                          f"{nombre} fallo: {e}", var_id=nombre)
                print(f"[etl] ERROR en {nombre}: {e}")
                traceback.print_exc()
                return 0
        return wrapper
    return deco


# ---------------------------------------------------------------------
@paso("tc_usduyu_interbancario")
def etl_tc(con, desde: str) -> int:
    registros = bcu_cotizaciones.cotizaciones("USD", desde=desde)
    if not registros:
        raise RuntimeError("el SOAP del BCU no devolvio observaciones")
    puntos = bcu_cotizaciones.punto_medio(registros)
    r = db.upsert_observaciones(con, "tc_usduyu_interbancario", puntos,
                                fuente="BCU-SOAP")
    print(f"[etl] TC: {r}")

    # Agregados mensuales derivados: promedio y cierre
    s = pd.Series({pd.Timestamp(f): v for f, v in puntos}).sort_index()
    prom = s.resample("MS").mean()
    cierre = s.resample("MS").last()
    db.upsert_observaciones(con, "tc_usduyu_prom_m",
                            [(i.strftime("%Y-%m-%d"), v) for i, v in prom.items()],
                            fuente="BCU-SOAP (derivado)")
    db.upsert_observaciones(con, "tc_usduyu_cierre_m",
                            [(i.strftime("%Y-%m-%d"), v) for i, v in cierre.items()],
                            fuente="BCU-SOAP (derivado)")
    return r["nuevas"]


@paso("ui_unidad_indexada")
def etl_ui(con, desde: str) -> int:
    registros = bcu_cotizaciones.cotizaciones("UI", desde=desde)
    puntos = bcu_cotizaciones.punto_medio(registros)
    r = db.upsert_observaciones(con, "ui_valor", puntos, fuente="BCU-SOAP")
    return r["nuevas"]


@paso("fred")
def etl_fred(con, desde: str) -> int:
    total = 0
    for var_id, datos in fred_series.bajar_todas(desde=desde).items():
        if not datos:
            db.alerta(con, "serie_desactualizada", "warning",
                      f"FRED no devolvio datos para {var_id}", var_id=var_id)
            continue
        r = db.upsert_observaciones(con, var_id, datos, fuente="FRED")
        total += r["nuevas"]
    return total


def _upsert_serie(con, var_id: str, s: pd.Series, fuente: str) -> int:
    r = db.upsert_observaciones(
        con, var_id, [(i.strftime("%Y-%m-%d"), v) for i, v in s.items()],
        fuente=fuente)
    print(f"[etl] {var_id}: {r}")
    return r["nuevas"]


@paso("ine_ipc")
def etl_ipc(con) -> int:
    """
    Ingesta del IPC con parsers especificos por planilla (calibrados contra
    los archivos reales, ver ine_ipc.py). Cada planilla falla aislada con
    alerta; si ninguna parsea, la corrida del paso falla.
    """
    ine_ipc.bajar_todo()
    base = ine_ipc.RAW / "base_2022_10"
    total = 0
    parseo_ok = False

    def _intento(nombre, fragmentos, fn):
        nonlocal parseo_ok
        ruta = ine_ipc.buscar_archivo(base, *fragmentos)
        if ruta is None:
            db.alerta(con, "estructura", "critica",
                      f"No se encontro la planilla de {nombre} en {base}. "
                      f"El INE pudo haber renombrado el archivo.",
                      var_id="ipc_general_idx")
            return None
        try:
            res = fn(ruta)
            parseo_ok = True
            return res
        except Exception as e:                        # noqa: BLE001
            db.alerta(con, "estructura", "critica",
                      f"Fallo el parseo de {nombre} ({ruta.name}): {e}",
                      var_id="ipc_general_idx")
            return None

    # 1. Serie oficial reexpresada base oct-2022 desde julio 1937.
    #    Cumple el rol de la serie larga: no hace falta empalme propio.
    largo = _intento("serie general larga", ("gral", "variaciones"),
                     ine_ipc.parsear_general_largo)
    if largo is not None and len(largo):
        total += _upsert_serie(
            con, "ipc_general_empalmado", largo,
            "INE, serie oficial reexpresada base oct-2022=100 (desde 1937)")

    # 2. IPC general Total Pais (y control regional) desde dic-2010
    regiones = _intento("general por region", ("general_total",),
                        ine_ipc.parsear_general_regiones)
    if regiones and len(regiones.get("total_pais", [])):
        total += _upsert_serie(con, "ipc_general_idx", regiones["total_pais"],
                               "INE base oct-2022=100")
        # control cruzado contra la serie larga
        if largo is not None and len(largo):
            comun = regiones["total_pais"].index.intersection(largo.index)
            dif = (regiones["total_pais"][comun] - largo[comun]).abs().max()
            if dif > 0.01:
                db.alerta(con, "estructura", "warning",
                          f"Serie regiones vs. serie larga difieren hasta "
                          f"{dif:.4f} puntos de indice", var_id="ipc_general_idx")

    # 3. Divisiones COICOP 01-13 desde dic-2010
    divisiones = _intento("divisiones", ("division", "pais"),
                          ine_ipc.parsear_divisiones)
    if divisiones is not None and len(divisiones):
        for cod, grupo in divisiones.groupby("division"):
            s = pd.Series(grupo["indice"].values,
                          index=pd.DatetimeIndex(grupo["fecha"]))
            total += _upsert_serie(con, f"ipc_div_{cod}", s,
                                   "INE base oct-2022=100, division CCIF")

    # 4. Nucleo oficial IPC-CE (excluye frutas, verduras y combustibles)
    nucleo = _intento("IPC-CE (subyacente)", ("subyacente",),
                      ine_ipc.parsear_subyacente)
    if nucleo is not None and len(nucleo):
        total += _upsert_serie(con, "ipc_subyacente_idx", nucleo,
                               "INE IPC-CE base oct-2022=100")

    if not parseo_ok:
        raise RuntimeError("ninguna planilla del IPC pudo parsearse")

    if largo is not None and len(largo):
        PROC.mkdir(parents=True, exist_ok=True)
        largo.to_frame("ipc").to_parquet(PROC / "ipc_empalmado.parquet")
    return total


@paso("licitaciones")
def etl_licitaciones(con) -> int:
    licitaciones.descubrir()
    filas = []
    for pdf in sorted((ROOT / "data" / "raw" / "licitaciones").rglob("*.pdf")):
        emisor = "BCU" if "bcu" in str(pdf).lower() else "UGD"
        filas.extend(licitaciones.parsear_pdf_resultado(pdf, emisor))
    n = db.upsert_licitaciones(con, filas)
    if n == 0:
        db.alerta(con, "estructura", "warning",
                  "No se extrajo ninguna licitacion. Revisar la salida de "
                  "`licitaciones descubrir` y calibrar PATRONES.")
    print(f"[etl] licitaciones: {n} filas")
    return n


@paso("ine_ims")
def etl_ims(con) -> int:
    """IMS nominal (dic-2002+) e IMS general largo (1968+)."""
    ine_ims.bajar()
    resultado = ine_ims.series()
    if not resultado:
        raise RuntimeError("ninguna planilla del IMS pudo parsearse")
    total = 0
    fuentes = {"salario_nominal_ims": "INE IMSN base jul-2008=100",
               "ims_general_idx": "INE IMS general base jul-2008=100 (desde 1968)"}
    for var_id, s in resultado.items():
        total += _upsert_serie(con, var_id, s, fuentes[var_id])
    return total


@paso("bcu_tpm_ipom")
def etl_tpm(con) -> int:
    """
    TPM vigente extraida del ultimo IPOM archivado por el paso de
    descubrimiento. No es una serie mensual real (ver docstring de
    bcu_ipom.py): un punto por trimestre, con fecha_ref aproximada.
    """
    resultado = bcu_ipom.valor_vigente()
    if resultado is None:
        raise RuntimeError("no se encontro TPM parseable en ningun IPOM archivado")
    fecha_ref, valor, ruta = resultado
    r = db.upsert_observaciones(
        con, "tpm_bcu", [(fecha_ref, valor)],
        fuente=f"BCU IPOM ({ruta.name}), extraccion de texto del Resumen Ejecutivo")
    print(f"[etl] tpm_bcu: {valor}% en {fecha_ref} ({r})")
    return r["nuevas"]


@paso("bcu_expectativas")
def etl_expectativas(con) -> int:
    """
    Mediana de expectativas de inflacion a 12/24m, extraida de HTML
    estatico (no requiere navegador -- ver docstring de bcu_expectativas.py).
    Solo el valor vigente al momento de la consulta: la serie se construye
    hacia adelante, un punto por corrida mensual.
    """
    resultado = bcu_expectativas.valor_vigente()
    if not resultado:
        raise RuntimeError("no se encontro el bloque de expectativas en la pagina del BCU")
    mes_ref = resultado.get("mes_referencia", db.hoy())
    total = 0
    for horizonte, var_id in [("12", "expectativas_inflacion_12m"),
                             ("24", "expectativas_inflacion_24m")]:
        if horizonte not in resultado:
            continue
        r = db.upsert_observaciones(
            con, var_id, [(mes_ref, resultado[horizonte])],
            fuente="BCU, Expectativas de los agentes (encuesta a analistas)")
        print(f"[etl] {var_id}: {resultado[horizonte]}% en {mes_ref} ({r})")
        total += r["nuevas"]
    return total


@paso("bcu_imae")
def etl_imae(con) -> int:
    """
    IMAE (original, desestacionalizado, tendencia-ciclo), extraido de un
    HTML estatico que embebe graficos Plotly con la serie completa --
    ver docstring de bcu_imae.py. A diferencia de expectativas/TPM, ESTA
    si es la serie historica completa, no solo el valor vigente.
    """
    resultado = bcu_imae.series()
    if not resultado:
        raise RuntimeError("no se encontro ningun widget de IMAE en la pagina del BCU")
    total = 0
    for var_id, s in resultado.items():
        total += _upsert_serie(con, var_id, s, "BCU, IMAE-graficas.html (Plotly/R)")
    return total


@paso("descubrimiento_fuentes")
def etl_descubrimiento(con) -> int:
    """
    Archiva paginas y planillas de las fuentes prioridad A que aun no
    tienen ingestor (expectativas BCU, ITCR, TPM, IMS, combustibles).
    Los crudos versionados permiten calibrar los parsers sin red.
    """
    resumenes = descubrir_fuentes.descubrir_todo()
    total = 0
    for r in resumenes:
        if r["pagina"] is None:
            db.alerta(con, "estructura", "warning",
                      f"Descubrimiento de {r['clave']}: ninguna URL candidata "
                      f"respondio. Actualizar FUENTES en descubrir_fuentes.py.")
        total += r["planillas"]
    return total


@paso("descubrimiento_fuentes_js")
def etl_descubrimiento_js(con) -> int:
    """
    Igual que etl_descubrimiento pero con Chromium headless (Playwright)
    para expectativas_bcu_js e itcr_bcu_js: confirmado (ver
    docs/manifest_fuentes.md) que esas paginas solo muestran el dato
    despues de ejecutar JavaScript -- requests.get() nunca lo va a ver.
    """
    resumenes = descubrir_js.descubrir_todo_js()
    total = 0
    for r in resumenes:
        if r["html"] is None:
            db.alerta(con, "estructura", "warning",
                      f"Descubrimiento JS de {r['clave']}: no se pudo renderizar "
                      f"la pagina. Revisar la URL en descubrir_js.py.")
        total += r["planillas"] + r["tablas"]
    return total


# ---------------------------------------------------------------------
def controles(con) -> None:
    """Chequeos de frescura y de rango. Alertan, no abortan."""
    hoy = dt.date.today()
    limites = {
        "tc_usduyu_interbancario": 5,
        # fecha_ref es el primer dia del mes: el dato de julio se publica
        # ~5 de agosto y recien esta "vencido" cuando falta el de agosto
        # (~5 de setiembre) => tolerancia ~70 dias desde la fecha_ref.
        "ipc_general_idx": 70,
        "usdbrl": 7,
        "ust_10y": 7,
        "brent": 7,
    }
    for var_id, dias in limites.items():
        s = db.serie(con, var_id)
        if s.empty:
            db.alerta(con, "serie_desactualizada", "critica",
                      f"{var_id} sin datos", var_id=var_id)
            continue
        atraso = (hoy - s.index.max().date()).days
        if atraso > dias:
            db.alerta(con, "serie_desactualizada", "warning",
                      f"{var_id} sin actualizar hace {atraso} dias "
                      f"(tolerancia {dias})", var_id=var_id)

    # Rango plausible del TC
    tc = db.serie(con, "tc_usduyu_interbancario")
    if not tc.empty:
        ult = tc.iloc[-1]
        if not (20 <= ult <= 100):
            db.alerta(con, "fuera_de_rango", "critica",
                      f"TC ultimo = {ult}, fuera del rango plausible 20-100",
                      var_id="tc_usduyu_interbancario")
        var_d = tc.pct_change().abs()
        saltos = var_d[var_d > 0.05]
        if len(saltos):
            db.alerta(con, "outlier", "warning",
                      f"{len(saltos)} saltos diarios del TC mayores a 5%. "
                      f"Ultimo: {saltos.index[-1].date()}",
                      var_id="tc_usduyu_interbancario")

    # Variacion mensual del IPC plausible
    ipc = db.serie(con, "ipc_general_idx")
    if len(ipc) > 1:
        var_m = ipc.pct_change() * 100
        raros = var_m[(var_m < -2) | (var_m > 5)]
        if len(raros):
            db.alerta(con, "outlier", "warning",
                      f"{len(raros)} variaciones mensuales del IPC fuera de "
                      f"[-2%, +5%]. Ultima: {raros.index[-1].date()} "
                      f"= {raros.iloc[-1]:.2f}%", var_id="ipc_general_idx")


def resumen(con) -> None:
    print("\n===== RESUMEN =====")
    df = pd.read_sql(
        """SELECT var_id, COUNT(*) n, MIN(fecha_ref) desde, MAX(fecha_ref) hasta
           FROM v_series_actual GROUP BY var_id ORDER BY var_id""", con)
    print(df.to_string(index=False) if not df.empty else "(sin datos)")
    al = pd.read_sql(
        "SELECT tipo, severidad, var_id, detalle FROM alertas "
        "WHERE resuelta = 0 AND fecha = ? ORDER BY severidad",
        con, params=(db.hoy(),))
    if not al.empty:
        print("\n----- ALERTAS -----")
        print(al.to_string(index=False))


# ---------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", default="semanal",
                    choices=["diario", "semanal", "mensual", "historico"])
    ap.add_argument("--desde", default=None,
                    help="fecha ISO de inicio; por defecto depende del modo")
    args = ap.parse_args()

    desde = args.desde or {
        "diario": (dt.date.today() - dt.timedelta(days=15)).isoformat(),
        "semanal": (dt.date.today() - dt.timedelta(days=60)).isoformat(),
        "mensual": (dt.date.today() - dt.timedelta(days=400)).isoformat(),
        "historico": "1997-01-01",
    }[args.modo]

    db.respaldar()
    db.inicializar()
    con = db.conectar()
    n_vars = seed.sembrar_variables(con)
    t0 = time.time()
    print(f"[etl] modo={args.modo} desde={desde} ({n_vars} variables sembradas)")

    try:
        etl_tc(con, desde)
        etl_fred(con, desde)
        if args.modo in ("semanal", "mensual", "historico"):
            etl_ui(con, desde)
            etl_licitaciones(con)
        if args.modo in ("mensual", "historico"):
            etl_ipc(con)
            etl_ims(con)
            etl_expectativas(con)
            etl_imae(con)
            etl_descubrimiento(con)
            etl_descubrimiento_js(con)
            etl_tpm(con)

        controles(con)
        resumen(con)
        db.log(con, "etl", "ok", mensaje=f"corrida {args.modo} completa",
               duracion_seg=round(time.time() - t0, 1))
    finally:
        con.close()


if __name__ == "__main__":
    main()
