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

from src.etl import bcu_cotizaciones, fred_series, ine_ipc, licitaciones  # noqa: E402
from src.etl import db, seed  # noqa: E402

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


@paso("ine_ipc")
def etl_ipc(con) -> int:
    archivos = ine_ipc.bajar_todo()
    series_por_base: dict[str, pd.Series] = {}
    for clave, rutas in archivos.items():
        mejor = pd.Series(dtype=float)
        for ruta in rutas:
            s = ine_ipc.leer_indice(ruta)
            if len(s) > len(mejor):
                mejor = s
        if len(mejor):
            series_por_base[clave] = mejor
            print(f"[etl] IPC {clave}: {len(mejor)} obs")
        else:
            db.alerta(con, "estructura", "critica",
                      f"No se pudo parsear ninguna planilla de {clave}. "
                      f"El layout del INE probablemente cambio.",
                      var_id="ipc_general_idx")

    if not series_por_base:
        raise RuntimeError("ninguna base del IPC pudo parsearse")

    # Serie de la base vigente, tal cual la publica el INE
    vigente = series_por_base.get("base_2022_10")
    if vigente is not None and len(vigente):
        db.upsert_observaciones(
            con, "ipc_general_idx",
            [(i.strftime("%Y-%m-%d"), v) for i, v in vigente.items()],
            fuente="INE base oct-2022=100")

    # Serie empalmada desde 1997, expresada en la base vigente
    empalmada = ine_ipc.empalmar(series_por_base)
    r = db.upsert_observaciones(
        con, "ipc_general_empalmado",
        [(i.strftime("%Y-%m-%d"), v) for i, v in empalmada.items()],
        fuente="INE (empalme por variacion mensual)")
    print(f"[etl] IPC empalmado: {len(empalmada)} obs "
          f"desde {empalmada.index.min().date() if len(empalmada) else '-'}")

    PROC.mkdir(parents=True, exist_ok=True)
    empalmada.to_frame("ipc").to_parquet(PROC / "ipc_empalmado.parquet")
    return r["nuevas"]


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


# ---------------------------------------------------------------------
def controles(con) -> None:
    """Chequeos de frescura y de rango. Alertan, no abortan."""
    hoy = dt.date.today()
    limites = {
        "tc_usduyu_interbancario": 5,
        "ipc_general_idx": 45,
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

        controles(con)
        resumen(con)
        db.log(con, "etl", "ok", mensaje=f"corrida {args.modo} completa",
               duracion_seg=round(time.time() - t0, 1))
    finally:
        con.close()


if __name__ == "__main__":
    main()
