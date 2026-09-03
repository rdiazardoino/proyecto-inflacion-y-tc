"""
Sesion 4 - SARIMAX top-down para inflacion m/m (plan Seccion 8.2).

Especificacion (AR(1) + exogenas rezagadas, sin componente MA ni busqueda
de orden por origen -- el plan pide reestimar PARAMETROS en cada corrida y
revisar la ESPECIFICACION solo trimestralmente; buscar el orden optimo en
cada uno de los ~90 origenes del backtest seria carisimo y ademas violaria
esa regla operativa):

    pi(t) = c + phi*pi(t-1) + b1*DTC(t-1) + b2*DBrent(t-1)
          + b3*DCPI_US(t-1) + b4*DIMS_yoy(t-1) + eps(t)

Todas las exogenas van en REZAGO 1 (nunca contemporaneo): al origen, el
valor en (origen) es real y conocido, así que el pronostico a h=1 usa
informacion completamente realizada. Para h>=2 la exogena en (origen+h-1)
todavia no existe -> se asume "sin novedad" (Delta=0, nivel plano) --
supuesto explicito, no una fuga de informacion futura.

Ventana de estimacion: ROLLING de 96 meses (8 anios), no expanding desde
2011. Motivo (aprendido en la sesion 3): un modelo estimado sobre toda la
muestra 2011+ mezcla el regimen de inflacion alta (2011-2015, ~8-9% anual)
con el actual (~4-5%) y arrastra un sesgo de nivel -- exactamente lo que
hundio a "estacionalidad historica" en el backtest de benchmarks. Una
ventana movil de 8 anios evita ese sesgo sin dejar de tener ~96 obs para
un modelo de 6 parametros.

Deliberadamente NO lleva dummies de mes: la estacionalidad calendario ya
la cubre el benchmark rw_estacional: este modelo compite aportando lo que
un pronostico estacional puro no tiene, drivers economicos, no repitiendo
el mismo trabajo con menos datos por mes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

VENTANA_MESES = 96
REZAGO_EXOG = 1

COLUMNAS_EXOG = ["dtc", "dbrent", "dcpius", "dims_yoy"]


def preparar_datos(pi: pd.Series, dtc: pd.Series, dbrent: pd.Series,
                   dcpius: pd.Series, ims_nivel: pd.Series) -> pd.DataFrame:
    """Alinea todo a frecuencia mensual; dims_yoy = variacion interanual del IMS."""
    dims_yoy = (ims_nivel / ims_nivel.shift(12) - 1) * 100
    df = pd.DataFrame({"pi": pi, "dtc": dtc, "dbrent": dbrent,
                       "dcpius": dcpius, "dims_yoy": dims_yoy}).dropna()
    return df


def _ajustar(df_ventana: pd.DataFrame):
    y = df_ventana["pi"].iloc[REZAGO_EXOG:]
    X = pd.DataFrame({"pi_l1": df_ventana["pi"].shift(REZAGO_EXOG)})
    for col in COLUMNAS_EXOG:
        X[col] = df_ventana[col].shift(REZAGO_EXOG)
    X = sm.add_constant(X.iloc[REZAGO_EXOG:])
    modelo = sm.OLS(y, X).fit()
    return modelo


def pronosticos(df: pd.DataFrame, origen: pd.Timestamp,
                horizontes: list[int]) -> dict[int, float]:
    """
    df: salida de preparar_datos(), con fecha_ref como indice.
    Devuelve {h: pi_pronosticado} usando SOLO datos hasta `origen`.
    """
    hist = df.loc[:origen]
    ventana = hist.iloc[-VENTANA_MESES:]
    if len(ventana) < 36:
        return {h: np.nan for h in horizontes}

    modelo = _ajustar(ventana)

    ultimo_pi = hist["pi"].iloc[-1]
    ultimas_exog = {col: hist[col].iloc[-1] for col in COLUMNAS_EXOG}

    salida: dict[int, float] = {}
    pi_prev = ultimo_pi
    for h in range(1, max(horizontes) + 1):
        fila = {"const": 1.0, "pi_l1": pi_prev}
        for col in COLUMNAS_EXOG:
            # h==1 usa la exogena REAL del origen (rezago 1 = valor en t=origen,
            # conocido); h>=2 asume "sin novedad" (Delta=0) porque esa exogena
            # todavia no existe en tiempo real.
            fila[col] = ultimas_exog[col] if h == 1 else 0.0
        x = pd.DataFrame([fila])[modelo.params.index]
        pi_pron = float(modelo.predict(x).iloc[0])
        if h in horizontes:
            salida[h] = pi_pron
        pi_prev = pi_pron
    return salida
