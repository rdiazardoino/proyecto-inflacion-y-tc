"""
Sesion 4 - Curva de Phillips (plan Seccion 8.2).

El plan pide: pi(t) = alpha*pi(t-1) + beta*Epi(12m) + gamma*brecha + delta*DTC
+ estacionalidad.

  - Epi(12m): la Encuesta de Expectativas del BCU estuvo bloqueada hasta el
    4-sep-2026 (ver docs/manifest_fuentes.md); se sigue usando la META del
    BCU (4.5% anual) como ancla CONSTANTE en la forma ECM de abajo --
    incorporar expectativas_inflacion_12m como regresor dinamico queda para
    una proxima iteracion (esta version resuelve brecha de producto, no
    expectativas).
  - brecha de producto: RESUELTA el 4-sep-2026 -- el IMAE desestacionalizado
    (var_id 'imae', ver bcu_imae.py) ya esta cargado. Se estima con un
    filtro HP (lambda=14400, estandar para series mensuales).

Lo que SI se implementa es la forma de correccion de error (ECM), que logra
la convergencia hacia la meta que el plan pide para h=12-24 de manera
ENDOGENA (via la propia dinamica del modelo), sin un blending ad-hoc:

    g(t)  = pi(t) - meta_m                    # brecha respecto de la meta
    g(t)  = c + alpha*g(t-1) + delta*DTC(t-1) + gamma*brecha_imae(t-1) + eps(t)
    pi(t) = g(t) + meta_m

Si |alpha| < 1 (tipico), g(t) decae hacia 0 a medida que crece el horizonte
-> pi(t) converge hacia la meta sola. Es exactamente la "convergencia
ponderada hacia el ancla" del plan, mas honesta que forzarla con un peso
inventado.

Brecha de producto point-in-time: el filtro HP es de dos colas (usa toda
la muestra que se le da), asi que aplicarlo UNA VEZ sobre la serie
completa metería informacion futura en cada backtest -- exactamente el
tipo de fuga que el resto del proyecto evita con ventanas rolling. Por
eso brecha_imae() se recalcula en CADA origen usando solo el IMAE
disponible hasta ese momento (real-time HP filter). Limitacion HONESTA y
estandar de este metodo: la estimacion del ciclo cerca del final de la
muestra es la menos confiable (se revisa a medida que llegan datos
nuevos) -- el "problema de fin de muestra" del filtro HP, no un bug.

El IMAE arranca en 2016-03 (mucho mas corto que pi/dtc, que arrancan
bastante antes) -- los origenes anteriores a esa fecha + un margen
minimo de observaciones para que el HP filter tenga sentido quedan sin
brecha (columna NaN, la fila se cae del ajuste OLS por el dropna): el
modelo entonces coincide con la version reducida anterior para esos
origenes, y gana el termino de brecha automaticamente en cuanto hay
suficiente historia de IMAE.

Ventana de estimacion de la regresion ECM: rolling 96 meses, mismo
criterio y misma razon que sarimax_topdown.py (evitar el sesgo de
mezclar regimenes de inflacion). La brecha de producto en si usa TODO el
IMAE disponible hasta el origen (no acotado a 96 meses): al ser una
serie corta, recortarla a 96 meses la haria todavia mas corta y menos
confiable para el HP filter sin necesidad -- 96 meses es la ventana que
protege a pi/dtc de mezclar regimenes de inflacion viejos, una
preocupacion que no aplica de la misma forma a la brecha de producto.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.filters.hp_filter import hpfilter

VENTANA_MESES = 96
LAMBDA_HP = 14400
MIN_OBS_HP = 24  # por debajo de esto el filtro HP es ruido, no ciclo
META_ANUAL_PCT = 4.5
META_MENSUAL = np.log(1 + META_ANUAL_PCT / 100) / 12 * 100  # equivalente log m/m


def preparar_datos(pi: pd.Series, dtc: pd.Series, imae: pd.Series | None = None) -> pd.DataFrame:
    df = pd.DataFrame({"pi": pi, "dtc": dtc}).dropna()
    if imae is not None:
        df = df.join(imae.rename("imae"))
    return df


def _brecha_hasta(imae_hist: pd.Series) -> pd.Series:
    """Filtro HP real-time: solo con el IMAE disponible hasta ese punto."""
    serie = imae_hist.dropna()
    if len(serie) < MIN_OBS_HP:
        return pd.Series(dtype=float)
    ciclo, _tendencia = hpfilter(serie, lamb=LAMBDA_HP)
    return ciclo


def _ajustar(df_ventana: pd.DataFrame):
    g = df_ventana["pi"] - META_MENSUAL
    regresores = {
        "g_l1": g.shift(1),
        "dtc_l1": df_ventana["dtc"].shift(1),
    }
    if "brecha_l1" in df_ventana:
        regresores["brecha_l1"] = df_ventana["brecha_l1"]
    X = sm.add_constant(pd.DataFrame(regresores, index=df_ventana.index)).iloc[1:]
    y = g.iloc[1:]
    datos = pd.concat([y.rename("y"), X], axis=1).dropna()
    return sm.OLS(datos["y"], datos.drop(columns="y")).fit()


def pronosticos(df: pd.DataFrame, origen: pd.Timestamp,
                horizontes: list[int]) -> dict[int, float]:
    hist = df.loc[:origen].copy()
    if len(hist) < 36:
        return {h: np.nan for h in horizontes}

    brecha_l1 = None
    if "imae" in hist:
        brecha = _brecha_hasta(hist["imae"])
        if not brecha.empty:
            # rezagada un mes: "brecha conocida al momento de pronosticar",
            # mismo criterio que dtc_l1 (evita el mismo tipo de fuga que
            # REZAGO_EXOG documenta en sarimax_topdown.py).
            hist["brecha_l1"] = brecha.shift(1).reindex(hist.index)
            brecha_l1 = hist["brecha_l1"].iloc[-1]

    ventana = hist.iloc[-VENTANA_MESES:]
    modelo = _ajustar(ventana)
    if modelo.nobs < 24:
        return {h: np.nan for h in horizontes}

    g_prev = hist["pi"].iloc[-1] - META_MENSUAL
    dtc_origen = hist["dtc"].iloc[-1]

    salida: dict[int, float] = {}
    for h in range(1, max(horizontes) + 1):
        dtc_l1 = dtc_origen if h == 1 else 0.0  # "sin novedad" para h>=2
        fila = {"const": 1.0, "g_l1": g_prev, "dtc_l1": dtc_l1}
        if "brecha_l1" in modelo.params.index:
            # la brecha en si NO se proyecta hacia adelante (supuesto
            # "sin novedad" tambien para h>=2, igual que dtc): se usa el
            # ultimo valor conocido en el origen para todos los h.
            fila["brecha_l1"] = brecha_l1 if brecha_l1 is not None and pd.notna(brecha_l1) else 0.0
        x = pd.DataFrame([fila])[modelo.params.index]
        g_pron = float(modelo.predict(x).iloc[0])
        if h in horizontes:
            salida[h] = g_pron + META_MENSUAL
        g_prev = g_pron
    return salida
