"""
Sesion 4 - Curva de Phillips reducida (plan Seccion 8.2, version v1).

El plan pide: pi(t) = alpha*pi(t-1) + beta*Epi(12m) + gamma*brecha + delta*DTC
+ estacionalidad. Dos de esos cuatro ingredientes no estan disponibles:

  - Epi(12m): la Encuesta de Expectativas del BCU esta bloqueada (portal
    SPA, ver docs/manifest_fuentes.md). Se sustituye por la META del BCU
    (4.5% anual) como ancla CONSTANTE -- una aproximacion, no una
    expectativa dinamica de mercado. Documentado, no inventado.
  - brecha de producto: no hay IMAE cargado todavia (pendiente de ingesta).
    Se omite del v1 en vez de improvisar un proxy sin sustento.

Lo que SI se implementa es la forma de correccion de error (ECM), que logra
la convergencia hacia la meta que el plan pide para h=12-24 de manera
ENDOGENA (via la propia dinamica del modelo), sin un blending ad-hoc:

    g(t)  = pi(t) - meta_m                    # brecha respecto de la meta
    g(t)  = c + alpha*g(t-1) + delta*DTC(t-1) + eps(t)
    pi(t) = g(t) + meta_m

Si |alpha| < 1 (tipico), g(t) decae hacia 0 a medida que crece el horizonte
-> pi(t) converge hacia la meta sola. Es exactamente la "convergencia
ponderada hacia el ancla" del plan, mas honesta que forzarla con un peso
inventado.

Ventana de estimacion: rolling 96 meses, mismo criterio y misma razon que
sarimax_topdown.py (evitar el sesgo de mezclar regimenes de inflacion).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

VENTANA_MESES = 96
META_ANUAL_PCT = 4.5
META_MENSUAL = np.log(1 + META_ANUAL_PCT / 100) / 12 * 100  # equivalente log m/m


def preparar_datos(pi: pd.Series, dtc: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"pi": pi, "dtc": dtc}).dropna()


def _ajustar(df_ventana: pd.DataFrame):
    g = df_ventana["pi"] - META_MENSUAL
    y = g.iloc[1:]
    X = sm.add_constant(pd.DataFrame({
        "g_l1": g.shift(1).iloc[1:],
        "dtc_l1": df_ventana["dtc"].shift(1).iloc[1:],
    }))
    return sm.OLS(y, X).fit()


def pronosticos(df: pd.DataFrame, origen: pd.Timestamp,
                horizontes: list[int]) -> dict[int, float]:
    hist = df.loc[:origen]
    ventana = hist.iloc[-VENTANA_MESES:]
    if len(ventana) < 36:
        return {h: np.nan for h in horizontes}

    modelo = _ajustar(ventana)
    g_prev = hist["pi"].iloc[-1] - META_MENSUAL
    dtc_origen = hist["dtc"].iloc[-1]

    salida: dict[int, float] = {}
    for h in range(1, max(horizontes) + 1):
        dtc_l1 = dtc_origen if h == 1 else 0.0  # "sin novedad" para h>=2
        x = pd.DataFrame([{"const": 1.0, "g_l1": g_prev, "dtc_l1": dtc_l1}])[modelo.params.index]
        g_pron = float(modelo.predict(x).iloc[0])
        if h in horizontes:
            salida[h] = g_pron + META_MENSUAL
        g_prev = g_pron
    return salida
