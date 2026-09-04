"""
Sesion 3 - Backtest de benchmarks en expanding window.

Metodologia (plan Seccion 9):
  - Expanding window: primer origen dic-2016, avanza un mes a la vez, hasta
    donde el horizonte maximo todavia tenga dato observado real.
  - Horizontes evaluados: 1, 6, 12, 24 meses (los nodos del plan Seccion 1.3).
  - Sin informacion futura en ninguna transformacion: cada pronostico usa
    solo datos con fecha_ref <= origen.
  - Metricas por modelo x objetivo x horizonte x corte de muestra: MAE,
    RMSE, bias, mediana |error|, directional accuracy, cobertura empirica
    de intervalos 80% y 95% (banda = desvio estandar EXPANDING de errores
    pasados del propio modelo/horizonte, sin mirar el futuro -- v1; Monte
    Carlo parametrico queda para v2, plan Seccion 8.5).
  - DM test de cada modelo vs. el random walk de su objetivo (rw_estacional
    para inflacion, rw para TC), con errores estandar HAC (Newey-West,
    maxlags=h-1) porque los origenes se solapan cuando h>1.

Resultados persistidos en errores (fila a fila) y metricas_backtest
(agregado), tal como especifica el esquema. Nunca se sobreescribe una fila
de errores ya calculada para el mismo origen -- se sobreescriben solo si
se vuelve a correr el mismo backtest (INSERT OR REPLACE), no las series de
pronosticos "reales" del sistema (esas viven en `pronosticos`, intactas).
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
from src.models import benchmarks  # noqa: E402

warnings.filterwarnings("ignore")

HORIZONTES = [1, 6, 12, 24]
ORIGEN_INICIAL = pd.Timestamp("2016-12-01")
CORTES = {
    # "completo" usa un periodo_desde sentinela ("0001-01-01") en vez de la
    # fecha real minima de la muestra: la PK de metricas_backtest es
    # (modelo_id, objetivo, horizonte_meses, ventana, periodo_desde) SIN
    # periodo_hasta, y para h=1 la fecha minima real coincide exactamente
    # con el inicio del corte "2017-2019" (origen dic-2016 + 1 mes) --
    # sin el sentinela, un INSERT OR REPLACE pisaria al otro.
    "completo": (None, None),
    "2017-2019": ("2017-01-01", "2019-12-01"),
    "2020-2021": ("2020-01-01", "2021-12-01"),
    "2022+": ("2022-01-01", None),
}
_SENTINEL_COMPLETO = "0001-01-01"


def _log_diff_pct(s: pd.Series) -> pd.Series:
    return np.log(s.astype(float)).diff() * 100


def _cargar_series(con) -> dict[str, pd.Series]:
    ipc = db.serie(con, "ipc_general_empalmado").asfreq("MS")
    tc = db.serie(con, "tc_usduyu_prom_m").asfreq("MS")
    cpi_us = db.serie(con, "cpi_us").asfreq("MS")
    return {
        "ipc_nivel": ipc,
        "pi_m": _log_diff_pct(ipc),
        "tc_nivel": tc,
        "dtc_m": _log_diff_pct(tc),
        "pi_us_m": _log_diff_pct(cpi_us),
    }


def _origenes(fecha_min: pd.Timestamp, fecha_max: pd.Timestamp, h_max: int) -> list[pd.Timestamp]:
    fin = fecha_max - pd.DateOffset(months=h_max)
    return list(pd.date_range(max(ORIGEN_INICIAL, fecha_min), fin, freq="MS"))


def registrar_modelos(con) -> None:
    filas = []
    for m in benchmarks.MODELOS_INFLACION:
        filas.append((f"bench_{m}", "benchmark", "ipc_m", m, "v1",
                      dt.date.today().isoformat(), 1))
    for m in benchmarks.MODELOS_TC:
        filas.append((f"bench_{m}", "benchmark", "tc_prom", m, "v1",
                      dt.date.today().isoformat(), 1))
    con.executemany(
        "INSERT OR REPLACE INTO modelos "
        "(modelo_id, familia, objetivo, descripcion, version, fecha_alta, activo) "
        "VALUES (?,?,?,?,?,?,?)", filas)
    con.commit()


def correr_backtest_inflacion(con, series: dict) -> pd.DataFrame:
    pi = series["pi_m"].dropna()
    origenes = _origenes(pi.index.min() + pd.DateOffset(months=13), pi.index.max(), max(HORIZONTES))
    filas = []
    for origen in origenes:
        pron = benchmarks.pronosticos_inflacion(pi, origen, HORIZONTES)
        for modelo, por_h in pron.items():
            for h, valor in por_h.items():
                fecha_obj = origen + pd.DateOffset(months=h)
                observado = pi.get(fecha_obj)
                if observado is None or pd.isna(valor):
                    continue
                error = valor - observado
                filas.append(dict(
                    modelo_id=f"bench_{modelo}", objetivo="ipc_m",
                    horizonte_meses=h, fecha_objetivo=fecha_obj.strftime("%Y-%m-%d"),
                    fecha_origen=origen, valor_pronosticado=valor,
                    valor_observado=observado, error=error, error_abs=abs(error),
                    error_cuad=error ** 2))
    return pd.DataFrame(filas)


def correr_backtest_tc(con, series: dict) -> pd.DataFrame:
    dtc = series["dtc_m"].dropna()
    tc_nivel = series["tc_nivel"]
    pi_uy_m = series["pi_m"].dropna()
    pi_us_m = series["pi_us_m"].dropna()
    inicio = max(dtc.index.min(), pi_uy_m.index.min(), pi_us_m.index.min()) + pd.DateOffset(months=13)
    origenes = _origenes(inicio, dtc.index.max(), max(HORIZONTES))
    filas = []
    for origen in origenes:
        nivel_origen = tc_nivel.get(origen)
        if nivel_origen is None or pd.isna(nivel_origen):
            continue
        pron = benchmarks.pronosticos_tc(pi_uy_m, pi_us_m, origen, HORIZONTES)
        for modelo, por_h in pron.items():
            for h, dpct_acum in por_h.items():
                fecha_obj = origen + pd.DateOffset(months=h)
                nivel_obs = tc_nivel.get(fecha_obj)
                if nivel_obs is None or pd.isna(nivel_obs) or pd.isna(dpct_acum):
                    continue
                nivel_pron = nivel_origen * np.exp(dpct_acum / 100)
                error = nivel_pron - nivel_obs
                filas.append(dict(
                    modelo_id=f"bench_{modelo}", objetivo="tc_prom",
                    horizonte_meses=h, fecha_objetivo=fecha_obj.strftime("%Y-%m-%d"),
                    fecha_origen=origen, valor_pronosticado=nivel_pron,
                    valor_observado=nivel_obs, error=error, error_abs=abs(error),
                    error_cuad=error ** 2))
    return pd.DataFrame(filas)


def _direccion_acierto(df: pd.DataFrame, objetivo_col_base: pd.Series) -> pd.Series:
    """
    Acierto de direccion: signo de (pronostico - valor_en_el_origen) vs.
    signo de (observado - valor_en_el_origen). objetivo_col_base: nivel/valor
    en la fecha de origen para cada fila (mismo indice que df).
    """
    base = objetivo_col_base.values
    dir_pron = np.sign(df["valor_pronosticado"].values - base)
    dir_obs = np.sign(df["valor_observado"].values - base)
    return (dir_pron == dir_obs).astype(int)


def _dm_test(errores_modelo: pd.Series, errores_rw: pd.Series, h: int) -> tuple[float, float]:
    """Diebold-Mariano sobre error cuadratico, HAC con maxlags=h-1."""
    import statsmodels.api as sm

    d = (errores_modelo.values ** 2) - (errores_rw.values ** 2)
    if len(d) < 8 or np.allclose(d, d[0]):
        return np.nan, np.nan
    X = np.ones((len(d), 1))
    m = sm.OLS(d, X).fit(cov_type="HAC", cov_kwds={"maxlags": max(h - 1, 0)})
    return float(m.tvalues[0]), float(m.pvalues[0])


def _subperiodo(fecha_objetivo: str) -> str:
    """Regimen segun los quiebres confirmados en la sesion 2 (Chow, sep-2020 y oct-2022)."""
    if fecha_objetivo < "2020-03-01":
        return "normal"
    if fecha_objetivo < "2022-10-01":
        return "shock"          # COVID + arranque de la desinflacion
    return "cambio_regimen"     # desinflacion post cambio de base del IPC


def guardar_errores(con, df: pd.DataFrame) -> None:
    if df.empty:
        return
    df = df.copy()
    df["subperiodo"] = df["fecha_objetivo"].map(_subperiodo)
    filas = [(r.modelo_id, r.objetivo, int(r.horizonte_meses), r.fecha_objetivo,
             r.valor_pronosticado, r.valor_observado, r.error, r.error_abs,
             r.error_cuad,
             int(r.acierto_direccion) if pd.notna(r.acierto_direccion) else None,
             int(r.dentro_ic80) if "dentro_ic80" in df.columns and pd.notna(r.dentro_ic80) else None,
             r.subperiodo)
            for r in df.itertuples()]
    con.executemany(
        "INSERT OR REPLACE INTO errores "
        "(modelo_id, objetivo, horizonte_meses, fecha_objetivo, valor_pronosticado, "
        " valor_observado, error, error_abs, error_cuad, acierto_direccion, "
        " dentro_ic80, subperiodo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", filas)
    con.commit()


def calcular_metricas(con, df: pd.DataFrame, objetivo: str, rw_modelo: str) -> pd.DataFrame:
    filas = []
    for corte, (desde, hasta) in CORTES.items():
        sub = df.copy()
        if desde:
            sub = sub[sub["fecha_objetivo"] >= desde]
        if hasta:
            sub = sub[sub["fecha_objetivo"] <= hasta]
        for modelo in sub["modelo_id"].unique():
            for h in HORIZONTES:
                s = sub[(sub["modelo_id"] == modelo) & (sub["horizonte_meses"] == h)]
                if len(s) < 5:
                    continue
                mae = s["error_abs"].mean()
                rmse = np.sqrt(s["error_cuad"].mean())
                bias = s["error"].mean()
                medae = s["error_abs"].median()
                dir_acc = s["acierto_direccion"].mean() if "acierto_direccion" in s else np.nan
                cov80 = s["dentro_ic80"].mean() if "dentro_ic80" in s and s["dentro_ic80"].notna().any() else np.nan

                dm_stat = dm_p = np.nan
                if modelo != f"bench_{rw_modelo}":
                    rw = sub[(sub["modelo_id"] == f"bench_{rw_modelo}") &
                            (sub["horizonte_meses"] == h)]
                    comunes = s.merge(rw, on="fecha_objetivo", suffixes=("", "_rw"))
                    if len(comunes) >= 8:
                        dm_stat, dm_p = _dm_test(comunes["error"], comunes["error_rw"], h)

                filas.append(dict(
                    corte=corte, modelo_id=modelo, objetivo=objetivo, horizonte_meses=h,
                    ventana="expanding",
                    periodo_desde=desde or (_SENTINEL_COMPLETO if corte == "completo"
                                            else str(df["fecha_objetivo"].min())),
                    periodo_hasta=hasta or str(df["fecha_objetivo"].max()),
                    mae=mae, rmse=rmse, mape=None, bias=bias, medae=medae,
                    dir_accuracy=dir_acc, cobertura_ic80=cov80, cobertura_ic95=None,
                    dm_stat_vs_rw=dm_stat, dm_pvalor_vs_rw=dm_p, n_obs=len(s),
                    fecha_calculo=dt.date.today().isoformat()))
    resumen = pd.DataFrame(filas)
    if not resumen.empty:
        cols_sql = ["modelo_id", "objetivo", "horizonte_meses", "ventana",
                    "periodo_desde", "periodo_hasta", "mae", "rmse", "mape", "bias",
                    "medae", "dir_accuracy", "cobertura_ic80", "cobertura_ic95",
                    "dm_stat_vs_rw", "dm_pvalor_vs_rw", "n_obs", "fecha_calculo"]
        con.executemany(
            "INSERT OR REPLACE INTO metricas_backtest "
            "(modelo_id, objetivo, horizonte_meses, ventana, periodo_desde, periodo_hasta, "
            " mae, rmse, mape, bias, medae, dir_accuracy, cobertura_ic80, cobertura_ic95, "
            " dm_stat_vs_rw, dm_pvalor_vs_rw, n_obs, fecha_calculo) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [tuple(r) for r in resumen[cols_sql].itertuples(index=False)])
        con.commit()
    return resumen


def _agregar_cobertura_expanding(df: pd.DataFrame) -> pd.DataFrame:
    """
    Banda empirica del error: desvio estandar EXPANDING de errores pasados
    del mismo modelo/horizonte (excluye el propio origen -> sin mirar el
    futuro). dentro_ic80 = 1 si |error| <= 1.2816*std hasta ese punto.
    """
    df = df.sort_values(["modelo_id", "horizonte_meses", "fecha_origen"]).copy()
    # Serie indexada por LABEL (no un array posicional): al reasignar sobre
    # df, que tiene el orden original (no el orden del sort de arriba),
    # pandas alinea por indice -- con un array numpy alinearia por posicion
    # y mezclaria los valores entre filas (bug real, detectado y corregido
    # el 3-sep-2026 con un caso de prueba minimo).
    partes = []
    for (modelo, h), grupo in df.groupby(["modelo_id", "horizonte_meses"]):
        errores_pasados = grupo["error"].shift(1).expanding(min_periods=6).std()
        banda = 1.2816 * errores_pasados
        ok = (grupo["error"].abs() <= banda).astype(float)
        ok[banda.isna()] = np.nan
        partes.append(ok)
    df["dentro_ic80"] = pd.concat(partes)
    return df


def main() -> None:
    con = db.conectar()
    registrar_modelos(con)
    series = _cargar_series(con)

    print("=" * 70)
    print("BACKTEST INFLACION (ipc_m)")
    df_pi = correr_backtest_inflacion(con, series)
    pi_en_origen = series["pi_m"].reindex(
        pd.to_datetime(df_pi["fecha_origen"])).values if len(df_pi) else np.array([])
    if len(df_pi):
        df_pi["acierto_direccion"] = _direccion_acierto(df_pi, pd.Series(pi_en_origen))
        df_pi = _agregar_cobertura_expanding(df_pi)
        df_pi["fecha_origen"] = df_pi["fecha_origen"].astype(str)
        guardar_errores(con, df_pi)
        print(f"  {len(df_pi)} filas de error ({df_pi['modelo_id'].nunique()} modelos, "
              f"origenes {df_pi['fecha_origen'].min()}..{df_pi['fecha_origen'].max()})")
        met_pi = calcular_metricas(con, df_pi, "ipc_m", "rw_estacional")
    else:
        met_pi = pd.DataFrame()
        print("  sin datos suficientes")

    print("\n" + "=" * 70)
    print("BACKTEST TC (tc_prom)")
    df_tc = correr_backtest_tc(con, series)
    if len(df_tc):
        tc_en_origen = series["tc_nivel"].reindex(
            pd.to_datetime(df_tc["fecha_origen"])).values
        df_tc["acierto_direccion"] = _direccion_acierto(df_tc, pd.Series(tc_en_origen))
        df_tc = _agregar_cobertura_expanding(df_tc)
        df_tc["fecha_origen"] = df_tc["fecha_origen"].astype(str)
        guardar_errores(con, df_tc)
        print(f"  {len(df_tc)} filas de error ({df_tc['modelo_id'].nunique()} modelos, "
              f"origenes {df_tc['fecha_origen'].min()}..{df_tc['fecha_origen'].max()})")
        met_tc = calcular_metricas(con, df_tc, "tc_prom", "rw")
    else:
        met_tc = pd.DataFrame()
        print("  sin datos suficientes")

    con.close()

    print("\n" + "=" * 70)
    print("TABLA DE MAE POR HORIZONTE - corte 'completo'")
    for nombre, met in [("INFLACION m/m", met_pi), ("TC promedio", met_tc)]:
        if met.empty:
            continue
        print(f"\n--- {nombre} (corte completo) ---")
        completo = met[met["periodo_desde"] == _SENTINEL_COMPLETO]
        tabla = completo.groupby(["modelo_id", "horizonte_meses"])["mae"].first().unstack()
        print(tabla.round(4).to_string())
        print("  n_obs:", completo.groupby("horizonte_meses")["n_obs"].first().to_dict())

    return met_pi, met_tc


if __name__ == "__main__":
    main()
