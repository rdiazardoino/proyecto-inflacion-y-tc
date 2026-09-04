"""
Sesion 4 - Backtest de los modelos economicos (Escalon 1) contra la misma
vara y la misma metodologia de la sesion 3: expanding window de ORIGENES
(dic-2016+), horizontes 1/6/12/24, DM test vs. el benchmark de cada
objetivo, cortes por regimen. Reutiliza guardar_errores/calcular_metricas/
_direccion_acierto/_agregar_cobertura_expanding de backtest.py para que los
resultados sean directamente comparables (misma tabla metricas_backtest).

Diferencia clave con la sesion 3: estos modelos se REESTIMAN en cada
origen sobre una ventana ROLLING de 96 meses (no expanding desde 2011) --
ver el docstring de cada modulo de modelo para el porque.
"""

from __future__ import annotations

import datetime as dt
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.etl import db  # noqa: E402
from src.models import backtest as bt  # noqa: E402
from src.models import phillips, sarimax_topdown, var_tc  # noqa: E402

warnings.filterwarnings("ignore")

HORIZONTES = bt.HORIZONTES
ORIGEN_INICIAL = bt.ORIGEN_INICIAL


def _log_diff_pct(s: pd.Series) -> pd.Series:
    return np.log(s.astype(float)).diff() * 100


def _cargar_series(con) -> dict[str, pd.Series]:
    ipc = db.serie(con, "ipc_general_empalmado").asfreq("MS")
    tc = db.serie(con, "tc_usduyu_prom_m").asfreq("MS")
    brent = db.serie(con, "brent").resample("MS").mean()
    cpi_us = db.serie(con, "cpi_us").asfreq("MS")
    ims = db.serie(con, "salario_nominal_ims").asfreq("MS")
    brl = db.serie(con, "usdbrl").resample("MS").mean()
    dxy = db.serie(con, "dxy").resample("MS").mean()
    imae = db.serie(con, "imae").asfreq("MS")
    pi = _log_diff_pct(ipc)
    dtc = _log_diff_pct(tc)
    return {
        "pi": pi, "tc_nivel": tc, "dtc": dtc,
        "dbrent": _log_diff_pct(brent), "dcpius": _log_diff_pct(cpi_us),
        "ims_nivel": ims, "dbrl": _log_diff_pct(brl), "ddxy": _log_diff_pct(dxy),
        "imae": imae,
    }


def registrar_modelos(con) -> None:
    filas = [
        ("sarimax_topdown", "econ", "ipc_m",
         "AR(1)+exogenas rezagadas (TC,Brent,CPI_US,IMS yoy), rolling 96m", "v1"),
        ("phillips_reducida", "econ", "ipc_m",
         "ECM hacia meta BCU 4.5% + TC rezagado + brecha de producto (IMAE, filtro HP real-time "
         "desde que hay suficiente historia), rolling 96m (sin expectativas dinamicas todavia)", "v1"),
        ("var2_reducido", "econ", "ipc_m",
         "VAR(2) [pi,DTC,DBRL,DDXY] sin TPM (bloqueada), rolling 96m", "v1"),
        ("var2_reducido", "econ", "tc_prom",
         "VAR(2) [pi,DTC,DBRL,DDXY] sin TPM (bloqueada), rolling 96m", "v1"),
    ]
    con.executemany(
        "INSERT OR REPLACE INTO modelos "
        "(modelo_id, familia, objetivo, descripcion, version, fecha_alta, activo) "
        "VALUES (?,?,?,?,?,?,?)",
        [(*f, dt.date.today().isoformat(), 1) for f in filas])
    con.commit()


def _origenes(fecha_min, fecha_max, h_max):
    fin = fecha_max - pd.DateOffset(months=h_max)
    return list(pd.date_range(max(ORIGEN_INICIAL, fecha_min), fin, freq="MS"))


def correr_inflacion(series: dict) -> pd.DataFrame:
    df_s = sarimax_topdown.preparar_datos(
        series["pi"], series["dtc"], series["dbrent"], series["dcpius"], series["ims_nivel"])
    df_p = phillips.preparar_datos(series["pi"], series["dtc"], series["imae"])
    pi = series["pi"].dropna()

    # Piso de origenes: que exista al menos una ventana rolling llena antes
    # de arrancar. En la practica ORIGEN_INICIAL (dic-2016) siempre domina,
    # porque pi/dtc/etc. arrancan bastante antes -- se deja explicito igual.
    piso = df_s.index.min() + pd.DateOffset(months=sarimax_topdown.VENTANA_MESES)
    origenes = _origenes(piso, pi.index.max(), max(HORIZONTES))
    filas = []
    for origen in origenes:
        pron_s = sarimax_topdown.pronosticos(df_s, origen, HORIZONTES)
        pron_p = phillips.pronosticos(df_p, origen, HORIZONTES)
        for modelo_id, pron in [("sarimax_topdown", pron_s), ("phillips_reducida", pron_p)]:
            for h, valor in pron.items():
                fecha_obj = origen + pd.DateOffset(months=h)
                observado = pi.get(fecha_obj)
                if observado is None or pd.isna(valor):
                    continue
                error = valor - observado
                filas.append(dict(
                    modelo_id=modelo_id, objetivo="ipc_m", horizonte_meses=h,
                    fecha_objetivo=fecha_obj.strftime("%Y-%m-%d"), fecha_origen=str(origen.date()),
                    valor_pronosticado=valor, valor_observado=observado,
                    error=error, error_abs=abs(error), error_cuad=error ** 2))
    return pd.DataFrame(filas)


def correr_var(series: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_v = var_tc.preparar_datos(series["pi"], series["dtc"], series["dbrl"], series["ddxy"])
    pi = series["pi"].dropna()
    tc_nivel = series["tc_nivel"]

    piso = df_v.index.min() + pd.DateOffset(months=var_tc.VENTANA_MESES)
    origenes = _origenes(piso, df_v.index.max(), max(HORIZONTES))
    filas_pi, filas_tc = [], []
    for origen in origenes:
        nivel_origen = tc_nivel.get(origen)
        if nivel_origen is None or pd.isna(nivel_origen):
            continue
        pron = var_tc.pronosticos(df_v, origen, HORIZONTES)
        for h, valor in pron["pi"].items():
            fecha_obj = origen + pd.DateOffset(months=h)
            observado = pi.get(fecha_obj)
            if observado is None or pd.isna(valor):
                continue
            error = valor - observado
            filas_pi.append(dict(
                modelo_id="var2_reducido", objetivo="ipc_m", horizonte_meses=h,
                fecha_objetivo=fecha_obj.strftime("%Y-%m-%d"), fecha_origen=str(origen.date()),
                valor_pronosticado=valor, valor_observado=observado,
                error=error, error_abs=abs(error), error_cuad=error ** 2))
        for h, dpct_acum in pron["dtc"].items():
            fecha_obj = origen + pd.DateOffset(months=h)
            nivel_obs = tc_nivel.get(fecha_obj)
            if nivel_obs is None or pd.isna(nivel_obs) or pd.isna(dpct_acum):
                continue
            nivel_pron = nivel_origen * np.exp(dpct_acum / 100)
            error = nivel_pron - nivel_obs
            filas_tc.append(dict(
                modelo_id="var2_reducido", objetivo="tc_prom", horizonte_meses=h,
                fecha_objetivo=fecha_obj.strftime("%Y-%m-%d"), fecha_origen=str(origen.date()),
                valor_pronosticado=nivel_pron, valor_observado=nivel_obs,
                error=error, error_abs=abs(error), error_cuad=error ** 2))
    return pd.DataFrame(filas_pi), pd.DataFrame(filas_tc)


def main() -> None:
    con = db.conectar()
    registrar_modelos(con)
    series = _cargar_series(con)

    print("=" * 70)
    print("SESION 4 - SARIMAX top-down + Phillips reducida (ipc_m)")
    df_econ = correr_inflacion(series)
    if len(df_econ):
        base = series["pi"].reindex(pd.to_datetime(df_econ["fecha_origen"])).values
        df_econ["acierto_direccion"] = bt._direccion_acierto(df_econ, pd.Series(base))
        df_econ = bt._agregar_cobertura_expanding(df_econ)
        bt.guardar_errores(con, df_econ)
        print(f"  {len(df_econ)} filas ({df_econ['modelo_id'].nunique()} modelos, "
              f"origenes {df_econ['fecha_origen'].min()}..{df_econ['fecha_origen'].max()})")

    print("\n" + "=" * 70)
    print("SESION 4 - VAR(2) reducido (ipc_m + tc_prom)")
    df_var_pi, df_var_tc = correr_var(series)
    for nombre, dfx in [("pi", df_var_pi), ("tc", df_var_tc)]:
        if len(dfx):
            base = (series["pi"] if nombre == "pi" else series["tc_nivel"]).reindex(
                pd.to_datetime(dfx["fecha_origen"])).values
            dfx["acierto_direccion"] = bt._direccion_acierto(dfx, pd.Series(base))
            df2 = bt._agregar_cobertura_expanding(dfx)
            bt.guardar_errores(con, df2)
            print(f"  VAR/{nombre}: {len(df2)} filas, origenes "
                  f"{df2['fecha_origen'].min()}..{df2['fecha_origen'].max()}")

    # ---- metricas: se recalculan sobre TODOS los modelos de cada objetivo
    # (benchmarks + econ), leyendo la tabla errores completa, para que la
    # comparacion de MAE/DM quede en una sola tabla.
    print("\n" + "=" * 70)
    print("METRICAS (benchmarks + modelos economicos)")
    for objetivo, rw in [("ipc_m", "rw_estacional"), ("tc_prom", "rw")]:
        df_obj = pd.read_sql(
            "SELECT modelo_id, objetivo, horizonte_meses, fecha_objetivo, "
            "valor_pronosticado, valor_observado, error, error_abs, error_cuad, "
            "acierto_direccion, dentro_ic80 FROM errores WHERE objetivo=?",
            con, params=(objetivo,))
        met = bt.calcular_metricas(con, df_obj, objetivo, rw)
        completo = met[met["periodo_desde"] == bt._SENTINEL_COMPLETO]
        tabla = completo.groupby(["modelo_id", "horizonte_meses"])["mae"].first().unstack()
        print(f"\n--- {objetivo} (MAE, corte completo) ---")
        print(tabla.round(4).to_string())

    con.close()


if __name__ == "__main__":
    main()
