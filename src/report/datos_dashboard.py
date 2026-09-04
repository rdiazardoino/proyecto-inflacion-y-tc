"""
Sesion 6 - Preparacion de datos para el dashboard y el informe (una sola
fuente para los dos, como pide el plan Seccion 20: "mismos datos que el
dashboard").

No corre modelos: lee lo que ya dejaron las sesiones 1-5 en la base
(series, backtest, ensemble, escenarios). Si `pronosticos` esta vacio
para el mes en curso, `src/forecast/run_forecast.py` corre primero
`src/models/run_sesion5.py` para poblarlo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.etl import db  # noqa: E402

DIV_NOMBRE = {
    "01": "Alimentos y bebidas no alcohólicas", "02": "Bebidas alcohólicas y tabaco",
    "03": "Prendas de vestir y calzado", "04": "Vivienda, agua, electricidad y combustibles",
    "05": "Muebles y artículos para el hogar", "06": "Salud", "07": "Transporte",
    "08": "Información y comunicación", "09": "Recreación y cultura",
    "10": "Enseñanza", "11": "Restaurantes y servicios de alojamiento",
    "12": "Seguros y servicios financieros", "13": "Cuidado personal y otros",
}
META_ANUAL = 4.5
RANGO_META = (3.0, 6.0)


def _log_diff_pct(s: pd.Series) -> pd.Series:
    return np.log(s.astype(float)).diff() * 100


def cargar(con=None) -> dict:
    """Devuelve un dict con TODO lo que necesitan dashboard e informe."""
    cerrar = con is None
    con = con or db.conectar()
    d: dict = {}

    ipc = db.serie(con, "ipc_general_idx").asfreq("MS")
    nuc = db.serie(con, "ipc_subyacente_idx").asfreq("MS")
    tc_prom = db.serie(con, "tc_usduyu_prom_m")
    tc_diario = db.serie(con, "tc_usduyu_interbancario")

    d["fecha_corte_ipc"] = ipc.index[-1]
    d["fecha_corte_tc"] = tc_diario.index[-1]
    d["ipc_mm"] = float((ipc / ipc.shift(1) - 1).iloc[-1] * 100)
    d["ipc_aa"] = float((ipc / ipc.shift(12) - 1).iloc[-1] * 100)
    d["desvio_vs_meta"] = d["ipc_aa"] - META_ANUAL
    d["nucleo_aa"] = float((nuc / nuc.shift(12) - 1).iloc[-1] * 100)

    from statsmodels.tsa.seasonal import STL
    stl = STL(np.log(nuc.dropna()), period=12, robust=True).fit()
    sa = np.exp(stl.trend + stl.resid)
    m3a = ((sa / sa.shift(3)) ** 4 - 1) * 100
    d["nucleo_3m_anualizada_sa"] = float(m3a.dropna().iloc[-1])

    d["tc_spot"] = float(tc_diario.iloc[-1])
    d["tc_spot_fecha"] = tc_diario.index[-1]
    d["tc_var_mm"] = float((tc_prom / tc_prom.shift(1) - 1).iloc[-1] * 100)
    d["tc_var_aa"] = float((tc_prom / tc_prom.shift(12) - 1).iloc[-1] * 100)

    # ---- TPM y tasa real ex ante (proxy: meta BCU en vez de Eπ12m, que
    # esta bloqueada -- documentado, no inventado)
    tpm = db.serie(con, "tpm_bcu")
    d["tpm"] = float(tpm.iloc[-1]) if len(tpm) else None
    d["tpm_fecha"] = tpm.index[-1] if len(tpm) else None
    d["tasa_real_ex_ante"] = (d["tpm"] - META_ANUAL) if d["tpm"] is not None else None

    # ---- alertas (semaforo)
    al = pd.read_sql("SELECT severidad, COUNT(*) n FROM alertas WHERE resuelta=0 GROUP BY severidad", con)
    d["alertas_criticas"] = int(al.set_index("severidad")["n"].get("critica", 0))
    d["alertas_warning"] = int(al.set_index("severidad")["n"].get("warning", 0))

    # ---- ensemble (pronostico oficial)
    for objetivo, clave in [("ipc_m", "ensemble_ipc"), ("tc_prom", "ensemble_tc")]:
        df = pd.read_sql(
            "SELECT horizonte_meses, fecha_objetivo, valor, li_80, ls_80, li_95, ls_95 "
            "FROM pronosticos WHERE modelo_id='ensemble_v1' AND objetivo=? AND escenario='base' "
            "ORDER BY horizonte_meses", con, params=(objetivo,))
        d[clave] = df

    d["origen_pronostico"] = (pd.to_datetime(d["ensemble_ipc"]["fecha_objetivo"].iloc[0])
                              - pd.DateOffset(months=int(d["ensemble_ipc"]["horizonte_meses"].iloc[0]))
                              if len(d["ensemble_ipc"]) else None)
    d["nowcast_mm"] = float(d["ensemble_ipc"].set_index("horizonte_meses")["valor"].get(1, np.nan))

    # ---- pesos del ensemble
    pesos = pd.read_sql(
        "SELECT objetivo, modelo_id, horizonte_meses, peso_ensemble FROM pronosticos "
        "WHERE modelo_id != 'ensemble_v1' AND escenario='base' AND peso_ensemble IS NOT NULL",
        con)
    d["pesos_ensemble"] = pesos.drop_duplicates(["objetivo", "modelo_id", "horizonte_meses"])

    # ---- escenarios
    d["escenarios"] = pd.read_sql(
        "SELECT escenario_id, nombre, probabilidad, supuestos, senales_monitoreo FROM escenarios "
        "WHERE fecha_generacion = (SELECT MAX(fecha_generacion) FROM escenarios)", con)
    esc_pron = pd.read_sql(
        "SELECT escenario, objetivo, horizonte_meses, fecha_objetivo, valor FROM pronosticos "
        "WHERE modelo_id='var2_reducido' ORDER BY objetivo, escenario, horizonte_meses", con)
    d["escenarios_pronostico"] = esc_pron

    # ---- backtest / performance (sesiones 3-4)
    d["metricas_backtest"] = pd.read_sql(
        "SELECT modelo_id, objetivo, horizonte_meses, mae, bias, dir_accuracy, "
        " dm_stat_vs_rw, dm_pvalor_vs_rw, n_obs FROM metricas_backtest "
        "WHERE periodo_desde='0001-01-01'", con)
    d["errores_h1_ipc"] = pd.read_sql(
        "SELECT fecha_objetivo, valor_pronosticado, valor_observado FROM errores "
        "WHERE objetivo='ipc_m' AND horizonte_meses=1 AND modelo_id='bench_rw_estacional' "
        "ORDER BY fecha_objetivo", con)

    # ---- divisiones (heatmap ultimos 24 meses)
    divs = {}
    for cod in DIV_NOMBRE:
        s = db.serie(con, f"ipc_div_{cod}").asfreq("MS")
        divs[cod] = _log_diff_pct(s).dropna().iloc[-24:]
    d["divisiones_mm"] = pd.DataFrame(divs)

    # ---- estacionalidad historica (para comparar la trayectoria proyectada)
    pi_hist = _log_diff_pct(db.serie(con, "ipc_general_empalmado").asfreq("MS")).dropna()
    pi_hist_reciente = pi_hist[pi_hist.index >= "2017-01-01"]
    d["estacional_historica_mes"] = pi_hist_reciente.groupby(pi_hist_reciente.index.month).mean()

    if cerrar:
        con.close()
    return d
