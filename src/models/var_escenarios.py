"""
Sesion 5 - Vehiculo de escenarios: VARX(2) [pi, DTC] con BRL y DXY como
EXOGENAS (no endogenas).

Es un modelo distinto de src/models/var_tc.py (el VAR(2) de 4 variables
que compitio -y perdio- en el backtest de la sesion 4). La diferencia no
es cosmetica: un VAR de 4 variables endogenas no admite imponerle una
senda futura a dos de ellas sin un forecast condicional (Waggoner-Zha),
que es una pieza de infraestructura mas alla del alcance de v1. Un VARX
con BRL/DXY como exogenas SI lo admite de forma directa y correcta: la
senda del escenario ES el valor exogeno futuro, conocido por definicion
(lo define el escenario, no hay fuga de informacion).

    pi(t)  = c1 + a11*pi(t-1) + a12*dtc(t-1) + a13*pi(t-2) + a14*dtc(t-2)
             + b11*DBRL(t) + b12*DDXY(t) + eps1(t)
    dtc(t) = c2 + a21*pi(t-1) + a22*dtc(t-1) + a23*pi(t-2) + a24*dtc(t-2)
             + b21*DBRL(t) + b22*DDXY(t) + eps2(t)

Estimado por OLS ecuacion por ecuacion (equivalente a VARX por minimos
cuadrados), ventana rolling de 96 meses. Solo se usa para el ejercicio de
escenarios (src/models/escenarios.py) -- NO participa del backtest oficial
ni del ensemble.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

VENTANA_MESES = 96


def preparar_datos(pi: pd.Series, dtc: pd.Series, dbrl: pd.Series,
                   ddxy: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"pi": pi, "dtc": dtc, "dbrl": dbrl, "ddxy": ddxy}).dropna()


def _ajustar(ventana: pd.DataFrame) -> dict:
    X = sm.add_constant(pd.DataFrame({
        "pi_l1": ventana["pi"].shift(1), "dtc_l1": ventana["dtc"].shift(1),
        "pi_l2": ventana["pi"].shift(2), "dtc_l2": ventana["dtc"].shift(2),
        "dbrl": ventana["dbrl"], "ddxy": ventana["ddxy"],
    })).dropna()
    y_pi = ventana["pi"].loc[X.index]
    y_dtc = ventana["dtc"].loc[X.index]
    return {"pi": sm.OLS(y_pi, X).fit(), "dtc": sm.OLS(y_dtc, X).fit(), "cols": X.columns}


def pronosticos(df: pd.DataFrame, origen: pd.Timestamp, horizontes: list[int],
                dbrl_mensual: float, ddxy_mensual: float) -> dict[str, dict[int, float]]:
    """
    dbrl_mensual, ddxy_mensual: senda CONSTANTE del escenario (log-diff %
    mensual), aplicada a todos los meses del horizonte.
    """
    hist = df.loc[:origen]
    ventana = hist.iloc[-VENTANA_MESES:]
    vacio = {"pi": {h: np.nan for h in horizontes}, "dtc": {h: np.nan for h in horizontes}}
    if len(ventana) < 36:
        return vacio

    modelos = _ajustar(ventana)
    hist2 = ventana.iloc[-2:][["pi", "dtc"]].values  # [t-1, t] en orden cronologico
    pi_l2, pi_l1 = hist2[0, 0], hist2[1, 0]
    dtc_l2, dtc_l1 = hist2[0, 1], hist2[1, 1]

    salida = {"pi": {}, "dtc": {}}
    dtc_acum = 0.0
    for h in range(1, max(horizontes) + 1):
        fila = pd.DataFrame([{
            "const": 1.0, "pi_l1": pi_l1, "dtc_l1": dtc_l1,
            "pi_l2": pi_l2, "dtc_l2": dtc_l2,
            "dbrl": dbrl_mensual, "ddxy": ddxy_mensual,
        }])[modelos["cols"]]
        pi_h = float(modelos["pi"].predict(fila).iloc[0])
        dtc_h = float(modelos["dtc"].predict(fila).iloc[0])
        dtc_acum += dtc_h
        if h in horizontes:
            salida["pi"][h] = pi_h
            salida["dtc"][h] = dtc_acum
        pi_l2, pi_l1 = pi_l1, pi_h
        dtc_l2, dtc_l1 = dtc_l1, dtc_h
    return salida
