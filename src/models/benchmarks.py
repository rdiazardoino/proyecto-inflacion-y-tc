"""
Benchmarks (Escalon 0 del plan / BRIEF).

Son la vara, no candidatos a ganar. Cada funcion toma una serie con datos
SOLO hasta el origen (nunca mira el futuro) y devuelve el pronostico para
los horizontes pedidos. Un modelo entra al ensemble en sesiones futuras
solo si le gana a estos en backtest fuera de muestra.

Inflacion m/m (objetivo 'ipc_m', sobre ipc_general_empalmado):
  rw_estacional          pi(t+h) = pi(t+h-12k), el k minimo que cae <= origen
  media_movil_12m        media de los ultimos 12 meses al origen, plana
  naive                  ultimo dato observado, plano
  estacional_historica   promedio historico (expanding) de ese mes calendario
  consenso_bcu           NO DISPONIBLE: Encuesta de Expectativas bloqueada
                         (ver docs/manifest_fuentes.md). Se documenta, no se
                         inventa un numero.

TC (objetivo 'tc_prom', sobre tc_usduyu_prom_m, en Delta% acumulado):
  rw                     Delta% = 0 (nivel plano)
  rw_drift               drift = diferencial de inflacion REALIZADA 12m
                         Uruguay-EEUU (proxy de "inflacion esperada": no hay
                         encuesta de TC, se documenta la sustitucion)
  forward_bevsa          NO DISPONIBLE: BEVSA es v2 (plan, decision #2)
  expectativas_tc_bcu    NO DISPONIBLE: Encuesta de Expectativas bloqueada

MODELOS_DISPONIBLES / MODELOS_NO_DISPONIBLES documentan explicitamente
cuales corren y por que los otros no, en vez de omitirlos en silencio.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MODELOS_INFLACION = ["rw_estacional", "media_movil_12m", "naive", "estacional_historica"]
MODELOS_INFLACION_NO_DISPONIBLES = {
    "consenso_bcu": "Encuesta de Expectativas Economicas del BCU: bloqueada "
                    "(portal SPA sin datos via HTTP simple, ver manifest_fuentes.md).",
}
MODELOS_TC = ["rw", "rw_drift"]
MODELOS_TC_NO_DISPONIBLES = {
    "forward_bevsa": "Curvas BEVSA: fuera de alcance de v1 (plan, decision #2).",
    "expectativas_tc_bcu": "Encuesta de Expectativas Economicas del BCU: bloqueada.",
}


def _pi_estacional(serie: pd.Series, origen: pd.Timestamp, h: int) -> float:
    """pi(t+h) = pi(t+h-12k) con el k minimo tal que la fecha cae <= origen."""
    objetivo = origen + pd.DateOffset(months=h)
    k = 1
    while True:
        fuente = objetivo - pd.DateOffset(months=12 * k)
        if fuente <= origen:
            break
        k += 1
    return serie.get(fuente, np.nan)


def pronosticos_inflacion(serie_pi: pd.Series, origen: pd.Timestamp,
                          horizontes: list[int]) -> dict[str, dict[int, float]]:
    """serie_pi: variacion m/m (%) del IPC, indexada por fecha, SOLO hasta origen."""
    hist = serie_pi.loc[:origen]
    ultimo = hist.iloc[-1] if len(hist) else np.nan
    media12 = hist.iloc[-12:].mean() if len(hist) >= 12 else np.nan
    por_mes = hist.groupby(hist.index.month).mean()

    salida: dict[str, dict[int, float]] = {m: {} for m in MODELOS_INFLACION}
    for h in horizontes:
        salida["rw_estacional"][h] = _pi_estacional(hist, origen, h)
        salida["media_movil_12m"][h] = media12
        salida["naive"][h] = ultimo
        mes_objetivo = (origen + pd.DateOffset(months=h)).month
        salida["estacional_historica"][h] = por_mes.get(mes_objetivo, np.nan)
    return salida


def pronosticos_tc(pi_uy_m: pd.Series, pi_us_m: pd.Series,
                   origen: pd.Timestamp, horizontes: list[int]
                   ) -> dict[str, dict[int, float]]:
    """
    pi_uy_m, pi_us_m: variacion m/m log (%) de los IPC de Uruguay y EEUU
    (mismas unidades que la serie de inflacion, para que el drift quede en
    la misma escala que Delta%TC). Devuelve Delta% ACUMULADO del TC promedio
    desde el origen hasta t+h (no el nivel); el backtest convierte a nivel
    usando el TC observado en el origen.
    """
    puy = pi_uy_m.loc[:origen]
    pus = pi_us_m.loc[:origen]
    pi_uy_12m = puy.iloc[-12:].sum() if len(puy) >= 12 else np.nan
    pi_us_12m = pus.iloc[-12:].sum() if len(pus) >= 12 else np.nan
    drift_mensual = (pi_uy_12m - pi_us_12m) / 12 if pd.notna(pi_uy_12m) and pd.notna(pi_us_12m) else np.nan

    salida: dict[str, dict[int, float]] = {m: {} for m in MODELOS_TC}
    for h in horizontes:
        salida["rw"][h] = 0.0
        salida["rw_drift"][h] = drift_mensual * h if pd.notna(drift_mensual) else np.nan
    return salida
