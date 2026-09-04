"""
Sesion 4 - VAR(2) reducido TC-inflacion (sustituye al BVAR del plan Seccion 8.3).

El plan pide un BVAR(2) con priors Minnesota sobre [DTC, pi, TPM, DBRL, DDXY].
No se puede estimar tal cual: `tpm_bcu` tiene un UNICO punto historico (5.75%,
extraido del IPOM 1T-2026, ver src/etl/bcu_ipom.py) porque el resto de la
serie de la TPM esta bloqueada (portal SPA del BCU). Sin una serie mensual
real de la TPM no hay VAR posible con esa variable.

Lo que SI se puede estimar honestamente es un VAR(2) SIN TPM, sobre
[pi, DTC, DBRL, DDXY], por OLS ecuacion por ecuacion (equivalente a un VAR
con prior plano/no informativo -- Minnesota queda pendiente de cuando haya
mas variables e historia para que el shrinkage bayesiano tenga sentido:
con solo 4 variables y una ventana de 96 meses, un VAR simple ya esta bien
identificado, la ganancia de Minnesota seria marginal).

A diferencia de sarimax_topdown.py y phillips.py, este modelo pronostica
DOS objetivos a la vez (pi e tc) desde el mismo sistema -- coherencia
conjunta TC-inflacion, que es justamente el punto del BVAR en el plan.

Ventana: rolling 96 meses, mismo criterio que los otros modelos de la sesion 4.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR

VENTANA_MESES = 96
VARIABLES = ["pi", "dtc", "dbrl", "ddxy"]


def preparar_datos(pi: pd.Series, dtc: pd.Series, dbrl: pd.Series,
                   ddxy: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"pi": pi, "dtc": dtc, "dbrl": dbrl, "ddxy": ddxy}).dropna()


def pronosticos(df: pd.DataFrame, origen: pd.Timestamp,
                horizontes: list[int]) -> dict[str, dict[int, float]]:
    """Devuelve {'pi': {h: valor}, 'dtc': {h: valor}} -- dtc en Delta% acumulado."""
    hist = df.loc[:origen]
    ventana = hist.iloc[-VENTANA_MESES:][VARIABLES]
    vacio = {v: {h: np.nan for h in horizontes} for v in ["pi", "dtc"]}
    if len(ventana) < 36:
        return vacio

    try:
        modelo = VAR(ventana.values).fit(2)
        pron = modelo.forecast(ventana.values[-2:], steps=max(horizontes))
    except Exception:                                   # noqa: BLE001
        return vacio

    idx_pi = VARIABLES.index("pi")
    idx_dtc = VARIABLES.index("dtc")
    dtc_acum = np.cumsum(pron[:, idx_dtc])

    salida = {"pi": {}, "dtc": {}}
    for h in horizontes:
        salida["pi"][h] = float(pron[h - 1, idx_pi])
        salida["dtc"][h] = float(dtc_acum[h - 1])
    return salida
