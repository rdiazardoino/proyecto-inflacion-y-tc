"""
Sesion 5 - Ensemble v1 (plan Seccion 8.4).

    "Promedio ponderado por inverso del MAE de los ultimos 24 meses de
    backtest, por objetivo y por horizonte, con piso de 10% por modelo
    admitido y actualizacion mensual de pesos. Mediana como control.
    Dispersion entre modelos reportada como metrica de incertidumbre."

Dos decisiones de diseño, documentadas:

1. "Ultimos 24 meses de backtest" asume una operacion mensual que todavia
   no arranco (recien esta corriendo la primera vez). En su lugar se usa
   el corte '2022+' de metricas_backtest -- el regimen vigente, la mejor
   aproximacion disponible a "desempeño reciente" sin inventar una ventana
   de produccion que no existe. Se actualiza a un rolling real de 24 meses
   cuando el sistema lleve ese tiempo corriendo (sesion 6 en adelante).

2. "Modelo admitido" para el PESO no es lo mismo que "modelo admitido AL
   ENSEMBLE" para un challenger nuevo (esa es la regla estricta de
   backtest.py/backtest_sesion4.py: gana con DM 10% o >5% de MAE, si no,
   entra con peso CERO como challenger -- ninguno de los tres modelos de
   la sesion 4 la supero). Dentro del conjunto de BENCHMARKS, que no
   compiten por "entrar" sino que son la base del sistema, se excluye
   unicamente bench_estacional_historica: la sesion 3 encontro que su
   error es sesgo puro (bias~MAE) y su cobertura de intervalo es 3-9% --
   forzarle un piso de 10% de peso pesaria el ensemble hacia un modelo
   diagnosticado como no funcional, no hacia "diversificacion sana".
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.etl import db  # noqa: E402
from src.models import benchmarks  # noqa: E402

CORTE_RECIENTE = "2022-01-01"
PISO_PESO = 0.10
EXCLUIDOS = {"bench_estacional_historica"}


def pesos_por_objetivo(con, objetivo: str, horizontes: list[int]) -> pd.DataFrame:
    """
    Admitidos = benchmarks del objetivo, menos EXCLUIDOS, MAS cualquier
    challenger cuyo modelo_id no empiece con 'bench_' Y que haya ganado su
    DM test (dm_pvalor_vs_rw < 0.10) en ESE horizonte -- ninguno lo hizo en
    la sesion 4, asi que hoy el pool es solo benchmarks admitidos, pero el
    codigo no lo asume: si un futuro challenger gana, entra solo.
    """
    met = pd.read_sql(
        "SELECT modelo_id, horizonte_meses, mae, dm_stat_vs_rw, dm_pvalor_vs_rw "
        "FROM metricas_backtest WHERE objetivo=? AND periodo_desde=?",
        con, params=(objetivo, CORTE_RECIENTE))
    filas = []
    for h in horizontes:
        sub = met[met["horizonte_meses"] == h].copy()
        es_bench = sub["modelo_id"].str.startswith("bench_")
        # "gana" el DM test = error significativamente MENOR que el de
        # referencia: dm_stat < 0 (no solo dm_pvalor < 0.10 -- un stat
        # positivo y significativo quiere decir que el challenger es
        # significativamente PEOR, lo opuesto de "ganar". Bug real
        # encontrado y corregido el 3-sep-2026: sin el chequeo de signo,
        # var2_reducido quedaba "admitido" en tc_prom h=12/24 del corte
        # 2022+ por perder con significancia, no por ganar.
        gano_dm = (sub["dm_pvalor_vs_rw"].notna() & (sub["dm_pvalor_vs_rw"] < 0.10)
                  & (sub["dm_stat_vs_rw"] < 0))
        admitido = (es_bench & ~sub["modelo_id"].isin(EXCLUIDOS)) | (~es_bench & gano_dm)
        sub = sub[admitido]
        if sub.empty:
            continue
        inv_mae = 1.0 / sub["mae"]
        peso = inv_mae / inv_mae.sum()
        peso = np.maximum(peso, PISO_PESO)
        peso = peso / peso.sum()
        for modelo_id, w, mae in zip(sub["modelo_id"], peso, sub["mae"]):
            filas.append(dict(objetivo=objetivo, horizonte_meses=h,
                              modelo_id=modelo_id, mae=mae, peso=w))
    return pd.DataFrame(filas)


def pronostico_ensemble(con, series: dict, objetivo: str, origen: pd.Timestamp,
                        horizontes: list[int]) -> pd.DataFrame:
    """
    Combina los pronosticos puntuales de los modelos admitidos para el
    ORIGEN REAL actual (no backtest). Devuelve una fila por horizonte con
    valor, mediana de control, banda 80% (desvio historico del backtest,
    ponderado, mas la dispersion ENTRE modelos admitidos) y los pesos.
    """
    pesos = pesos_por_objetivo(con, objetivo, horizontes)
    if pesos.empty:
        return pd.DataFrame()

    if objetivo == "ipc_m":
        pron_por_modelo = benchmarks.pronosticos_inflacion(series["pi"].dropna(), origen, horizontes)
    else:
        pron_por_modelo = benchmarks.pronosticos_tc(
            series["pi"].dropna(), series["pi_us"].dropna(), origen, horizontes)

    # desvio historico de cada modelo/horizonte, del ultimo vintage de backtest
    desvios = pd.read_sql(
        "SELECT modelo_id, horizonte_meses, error FROM errores WHERE objetivo=?",
        con, params=(objetivo,))

    filas, detalle = [], []
    for h in horizontes:
        ph = pesos[pesos["horizonte_meses"] == h]
        valores, pesos_h, varianzas = [], [], []
        for _, r in ph.iterrows():
            modelo = r["modelo_id"].replace("bench_", "")
            if modelo not in pron_por_modelo or h not in pron_por_modelo[modelo]:
                continue
            v = pron_por_modelo[modelo][h]
            if pd.isna(v):
                continue
            valores.append(v)
            pesos_h.append(r["peso"])
            errs = desvios[(desvios["modelo_id"] == r["modelo_id"]) &
                          (desvios["horizonte_meses"] == h)]["error"]
            varianzas.append(errs.var() if len(errs) >= 6 else np.nan)
            detalle.append(dict(objetivo=objetivo, horizonte_meses=h,
                                modelo_id=r["modelo_id"], valor=v, peso=r["peso"]))
        if not valores:
            continue
        pesos_h = np.array(pesos_h) / sum(pesos_h)
        valor_ensemble = float(np.dot(pesos_h, valores))
        mediana = float(np.median(valores))
        # incertidumbre: promedio ponderado de varianzas intra-modelo +
        # dispersion entre modelos (varianza de los puntos combinados) --
        # suma valida bajo el supuesto simplificador de independencia (v1;
        # Monte Carlo conjunto queda para v2, plan Seccion 8.5)
        varianzas_validas = [v for v in varianzas if not np.isnan(v)]
        media_var = np.mean(varianzas_validas) if varianzas_validas else 0.0
        var_intra = float(np.dot(pesos_h, [v if not np.isnan(v) else media_var for v in varianzas]))
        var_entre = float(np.var(valores)) if len(valores) > 1 else 0.0
        desvio_total = np.sqrt(max(var_intra, 0) + var_entre)
        filas.append(dict(
            objetivo=objetivo, horizonte_meses=h, valor=valor_ensemble, mediana=mediana,
            li_80=valor_ensemble - 1.2816 * desvio_total, ls_80=valor_ensemble + 1.2816 * desvio_total,
            li_95=valor_ensemble - 1.96 * desvio_total, ls_95=valor_ensemble + 1.96 * desvio_total,
            dispersion_entre_modelos=np.sqrt(var_entre), n_modelos=len(valores)))
    resultado = pd.DataFrame(filas)
    resultado.attrs["detalle"] = pd.DataFrame(detalle)
    return resultado


def guardar(con, objetivo: str, origen: pd.Timestamp, detalle: pd.DataFrame,
           ensemble: pd.DataFrame, tc_nivel_origen: float | None = None) -> None:
    """detalle: resultado.attrs['detalle'] de pronostico_ensemble() -- una
    fila por (modelo_id, horizonte) con su valor puntual y su peso."""
    hoy = dt.date.today().isoformat()
    con.execute("INSERT OR REPLACE INTO modelos (modelo_id, familia, objetivo, descripcion, version, fecha_alta, activo) "
               "VALUES ('ensemble_v1','ensemble',?,?,?,?,1)",
               (objetivo, "Promedio ponderado por inverso del MAE (corte 2022+), piso 10%", "v1", hoy))

    for _, r in ensemble.iterrows():
        fecha_obj = (origen + pd.DateOffset(months=int(r["horizonte_meses"]))).strftime("%Y-%m-%d")
        valor = r["valor"]
        li80, ls80, li95, ls95 = r["li_80"], r["ls_80"], r["li_95"], r["ls_95"]
        if objetivo == "tc_prom" and tc_nivel_origen is not None:
            valor = tc_nivel_origen * np.exp(valor / 100)
            li80 = tc_nivel_origen * np.exp(r["li_80"] / 100)
            ls80 = tc_nivel_origen * np.exp(r["ls_80"] / 100)
            li95 = tc_nivel_origen * np.exp(r["li_95"] / 100)
            ls95 = tc_nivel_origen * np.exp(r["ls_95"] / 100)
        con.execute(
            "INSERT INTO pronosticos (fecha_generacion, vintage_datos, modelo_id, objetivo, "
            " fecha_objetivo, horizonte_meses, escenario, valor, li_80, ls_80, li_95, ls_95, peso_ensemble) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (hoy, str(origen.date()), "ensemble_v1", objetivo, fecha_obj,
             int(r["horizonte_meses"]), "base", valor, li80, ls80, li95, ls95, 1.0))

    for _, r in detalle.iterrows():
        fecha_obj = (origen + pd.DateOffset(months=int(r["horizonte_meses"]))).strftime("%Y-%m-%d")
        valor = r["valor"]
        if objetivo == "tc_prom" and tc_nivel_origen is not None:
            valor = tc_nivel_origen * np.exp(valor / 100)
        con.execute(
            "INSERT INTO pronosticos (fecha_generacion, vintage_datos, modelo_id, objetivo, "
            " fecha_objetivo, horizonte_meses, escenario, valor, peso_ensemble) "
            "VALUES (?,?,?,?,?,?, 'base', ?, ?)",
            (hoy, str(origen.date()), r["modelo_id"], objetivo, fecha_obj,
             int(r["horizonte_meses"]), valor, r["peso"]))
    con.commit()
