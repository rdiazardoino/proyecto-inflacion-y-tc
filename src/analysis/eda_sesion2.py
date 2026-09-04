"""
Sesion 2 - Analisis exploratorio (EDA).

Corre localmente sobre db/proyecto.db (sin red). Produce las figuras de
outputs/eda/<YYYY-MM>/ y vuelca a stdout las tablas numericas que alimentan
docs/eda_sesion2.md.

Muestra de estimacion: enero 2011 en adelante (empalme oficial por
divisiones). La serie general larga se usa solo para contexto.

Uso: python src/analysis/eda_sesion2.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.etl import db, seed  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from statsmodels.tsa.stattools import adfuller  # noqa: E402
import statsmodels.api as sm  # noqa: E402

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
MES = pd.Timestamp.today().strftime("%Y-%m")
OUT = ROOT / "outputs" / "eda" / MES
OUT.mkdir(parents=True, exist_ok=True)

# Paleta de referencia del skill de dataviz (light mode)
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
S1, S2 = "#2a78d6", "#eb6834"          # slots categoricos 1-2
DIV_NEG, DIV_MID, DIV_POS = "#2a78d6", "#f0efec", "#e34948"  # divergente
CMAP_DIV = LinearSegmentedColormap.from_list("div", [DIV_NEG, DIV_MID, DIV_POS])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "text.color": INK,
    "axes.edgecolor": INK2, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": "#e8e7e3", "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "figure.dpi": 150,
})

DIV_CORTO = {
    "01": "Alimentos y beb. no alc.", "02": "Beb. alcoholicas y tabaco",
    "03": "Vestimenta y calzado", "04": "Vivienda y suministros",
    "05": "Muebles y hogar", "06": "Salud", "07": "Transporte",
    "08": "Informacion y comunic.", "09": "Recreacion y cultura",
    "10": "Ensenanza", "11": "Restaurantes y alojam.",
    "12": "Seguros y serv. financieros", "13": "Cuidado personal y otros",
}

DESDE = "2011-01-01"


def cargar() -> dict:
    con = db.conectar()
    datos = {"ipc": db.serie(con, "ipc_general_idx"),
             "ipc_largo": db.serie(con, "ipc_general_empalmado"),
             "nucleo": db.serie(con, "ipc_subyacente_idx"),
             "tc": db.serie(con, "tc_usduyu_prom_m"),
             "brl": db.serie(con, "usdbrl")}
    for cod in DIV_CORTO:
        datos[f"div_{cod}"] = db.serie(con, f"ipc_div_{cod}")
    con.close()
    return datos


def var_m(s: pd.Series) -> pd.Series:
    """Variacion mensual log en %."""
    s = s.asfreq("MS") if s.index.freq is None else s
    return np.log(s).diff() * 100


def main() -> None:
    d = cargar()
    pi = var_m(d["ipc"]).loc[DESDE:].dropna()
    dtc = var_m(d["tc"].resample("MS").last()).loc[DESDE:].dropna()
    dbrl = var_m(d["brl"].resample("MS").mean()).loc[DESDE:].dropna()

    # =========================================================
    # 1. Estacionalidad por division: media de la var. m/m por mes calendario
    # =========================================================
    est = {}
    for cod, nombre in DIV_CORTO.items():
        v = var_m(d[f"div_{cod}"]).loc[DESDE:].dropna()
        est[f"{cod} {nombre}"] = v.groupby(v.index.month).mean()
    est_df = pd.DataFrame(est).T
    est_df.columns = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                      "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]

    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    lim = np.nanmax(np.abs(est_df.values))
    im = ax.imshow(est_df.values, cmap=CMAP_DIV,
                   norm=TwoSlopeNorm(vcenter=0, vmin=-lim, vmax=lim),
                   aspect="auto")
    ax.set_xticks(range(12), est_df.columns)
    ax.set_yticks(range(len(est_df)), est_df.index, fontsize=8.5)
    ax.grid(False)
    for i in range(est_df.shape[0]):
        for j in range(12):
            v = est_df.values[i, j]
            if abs(v) >= 0.8 * lim or abs(v) >= 1.0:
                ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                        fontsize=7, color=INK)
    fig.colorbar(im, ax=ax, shrink=0.7, label="promedio var. m/m (%)")
    ax.set_title("Estacionalidad del IPC por division\n"
                 "Promedio de la variacion m/m por mes calendario, "
                 f"ene-2011 a {pi.index[-1]:%m-%Y}",
                 fontsize=10, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "fig1_estacionalidad_divisiones.png")
    plt.close(fig)

    print("\n== 1. ESTACIONALIDAD (media m/m % por mes calendario) ==")
    print(est_df.round(2).to_string())

    # =========================================================
    # 2. Correlacion TC -> division, rezagos 0-6
    # =========================================================
    filas = {}
    for cod, nombre in DIV_CORTO.items():
        v = var_m(d[f"div_{cod}"]).loc[DESDE:].dropna()
        filas[f"{cod} {nombre}"] = [
            v.corr(dtc.shift(k)) for k in range(7)]
    corr_df = pd.DataFrame(filas, index=[f"t-{k}" for k in range(7)]).T
    # tambien el agregado
    corr_df.loc["IPC general"] = [pi.corr(dtc.shift(k)) for k in range(7)]

    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    im = ax.imshow(corr_df.values, cmap=CMAP_DIV,
                   norm=TwoSlopeNorm(vcenter=0, vmin=-0.6, vmax=0.6),
                   aspect="auto")
    ax.set_xticks(range(7), corr_df.columns)
    ax.set_yticks(range(len(corr_df)), corr_df.index, fontsize=8.5)
    ax.grid(False)
    for i in range(corr_df.shape[0]):
        for j in range(7):
            v = corr_df.values[i, j]
            if abs(v) >= 0.25:
                ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                        fontsize=7, color=INK)
    fig.colorbar(im, ax=ax, shrink=0.7, label="correlacion")
    ax.set_title("Correlacion entre la variacion m/m de cada division y la del\n"
                 "TC promedio (rezagos 0-6 meses), ene-2011 en adelante",
                 fontsize=10, color=INK, loc="left")
    ax.set_xlabel("rezago del TC")
    fig.tight_layout()
    fig.savefig(OUT / "fig2_correlacion_tc_divisiones.png")
    plt.close(fig)

    print("\n== 2. CORRELACION var. m/m division vs var. m/m TC (rezagos) ==")
    print(corr_df.round(2).to_string())

    # =========================================================
    # 3. ADF y persistencia por subperiodo
    # =========================================================
    print("\n== 3. RAIZ UNITARIA (ADF, p-valor) y PERSISTENCIA AR(1) ==")
    series_test = {"pi m/m (general)": pi, "d log TC": dtc,
                   "pi nucleo m/m": var_m(d["nucleo"]).dropna()}
    for nombre, s in series_test.items():
        p = adfuller(s.dropna(), autolag="AIC")[1]
        print(f"  ADF {nombre:22s}: p={p:.4f} "
              f"({'estacionaria' if p < 0.05 else 'NO rechaza raiz unitaria'})")

    subper = {"2011-2019": ("2011-01-01", "2019-12-01"),
              "2020-2021 (COVID)": ("2020-01-01", "2021-12-01"),
              "2022+ (desinflacion)": ("2022-01-01", None)}
    print("  Persistencia AR(1) de pi m/m (con dummies de mes):")
    ar1 = {}
    for nombre, (a, b) in subper.items():
        y = pi.loc[a:b]
        X = pd.get_dummies(y.index.month, drop_first=True, dtype=float)
        X.index = y.index
        X["ar1"] = y.shift(1)
        X = sm.add_constant(X).dropna()
        yy = y.loc[X.index]
        m = sm.OLS(yy, X).fit()
        ar1[nombre] = (m.params["ar1"], m.bse["ar1"], len(yy))
        print(f"    {nombre:22s}: rho={m.params['ar1']:.3f} "
              f"(ee {m.bse['ar1']:.3f}, n={len(yy)})")

    # =========================================================
    # 4. Quiebres: Chow en sep-2020 y oct-2022 sobre AR(1)+estacionalidad
    # =========================================================
    print("\n== 4. TEST DE CHOW (AR(1)+dummies mes, muestra 2011+) ==")
    from scipy import stats as sps

    def chow(y: pd.Series, fecha: str) -> tuple[float, float]:
        X = pd.get_dummies(y.index.month, drop_first=True, dtype=float)
        X.index = y.index
        X["ar1"] = y.shift(1)
        X = sm.add_constant(X).dropna()
        yy = y.loc[X.index]
        rss_t = sm.OLS(yy, X).fit().ssr
        m1 = sm.OLS(yy.loc[:fecha], X.loc[:fecha]).fit()
        m2 = sm.OLS(yy.loc[fecha:], X.loc[fecha:]).fit()
        k = X.shape[1]
        f = ((rss_t - m1.ssr - m2.ssr) / k) / ((m1.ssr + m2.ssr) /
                                               (len(yy) - 2 * k))
        p = 1 - sps.f.cdf(f, k, len(yy) - 2 * k)
        return f, p

    for fecha in ["2020-09-01", "2022-10-01"]:
        f, p = chow(pi, fecha)
        print(f"  quiebre en {fecha[:7]}: F={f:.2f}, p={p:.4f} "
              f"({'quiebre' if p < 0.05 else 'sin evidencia'})")

    # =========================================================
    # 5. Pass-through preliminar: proyecciones locales (Jorda)
    #    respuesta acumulada de pi a un shock de 1% en el TC
    # =========================================================
    H = 12
    controles = pd.DataFrame({
        "pi_l1": pi.shift(1), "pi_l2": pi.shift(2),
        "dtc_l1": dtc.shift(1), "dbrl": dbrl.reindex(pi.index)})

    def lp(muestra_ini: str, muestra_fin: str | None, hmax: int):
        betas, lo, hi = [], [], []
        for h in range(hmax + 1):
            y = pi.rolling(h + 1).sum().shift(-h)   # pi acumulada t..t+h
            df = pd.concat([y.rename("y"), dtc.rename("dtc"), controles],
                           axis=1).loc[muestra_ini:muestra_fin].dropna()
            X = sm.add_constant(df[["dtc", "pi_l1", "pi_l2", "dtc_l1", "dbrl"]])
            m = sm.OLS(df["y"], X).fit(cov_type="HAC",
                                       cov_kwds={"maxlags": h + 1})
            betas.append(m.params["dtc"])
            lo.append(m.params["dtc"] - 1.645 * m.bse["dtc"])
            hi.append(m.params["dtc"] + 1.645 * m.bse["dtc"])
        return np.array(betas), np.array(lo), np.array(hi)

    b_pre, lo_pre, hi_pre = lp("2011-01-01", "2019-12-01", H)
    b_pos, lo_pos, hi_pos = lp("2022-01-01", None, 6)

    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    hs = np.arange(H + 1)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.fill_between(hs, lo_pre, hi_pre, color=S1, alpha=0.15, linewidth=0)
    ax.plot(hs, b_pre, color=S1, linewidth=2, marker="o", markersize=4,
            label="2011-2019")
    hs2 = np.arange(7)
    ax.fill_between(hs2, lo_pos, hi_pos, color=S2, alpha=0.15, linewidth=0)
    ax.plot(hs2, b_pos, color=S2, linewidth=2, marker="o", markersize=4,
            label="2022+")
    ax.set_xlabel("horizonte h (meses)")
    ax.set_ylabel("p.p. de inflacion acumulada por 1% de suba del TC")
    ax.set_title("Pass-through cambiario preliminar - proyecciones locales:\n"
                 "respuesta acumulada de la inflacion m/m a un shock de 1% en el TC "
                 "(bandas 90%)", fontsize=10, color=INK, loc="left")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "fig3_passthrough_lp.png")
    plt.close(fig)

    print("\n== 5. PASS-THROUGH ACUMULADO (p.p. por 1% de TC) ==")
    for h in [1, 3, 6, 12]:
        linea = f"  h={h:2d}: 2011-19 = {b_pre[h]:.3f} [{lo_pre[h]:.3f},{hi_pre[h]:.3f}]"
        if h <= 6:
            linea += f" | 2022+ = {b_pos[h]:.3f} [{lo_pos[h]:.3f},{hi_pos[h]:.3f}]"
        print(linea)

    # =========================================================
    # 6. Contexto: inflacion a/a y tendencia 3m anualizada SA (STL)
    # =========================================================
    from statsmodels.tsa.seasonal import STL
    ipc = d["ipc"].asfreq("MS")
    aa = (ipc / ipc.shift(12) - 1) * 100
    stl = STL(np.log(ipc.dropna()), period=12, robust=True).fit()
    sa = np.exp(stl.trend + stl.resid)
    m3a = ((sa / sa.shift(3)) ** 4 - 1) * 100
    print("\n== 6. ULTIMOS DATOS (fecha de corte: ultimo IPC cargado) ==")
    print(f"  ultimo mes: {ipc.dropna().index[-1]:%Y-%m}")
    print(f"  inflacion a/a: {aa.dropna().iloc[-1]:.2f}%  (IPC total pais, base oct-2022=100)")
    print(f"  m/m: {var_m(ipc).dropna().iloc[-1]:.2f}%")
    print(f"  3m anualizada SA (STL): {m3a.dropna().iloc[-1]:.2f}%")
    nu = d["nucleo"].asfreq("MS")
    print(f"  nucleo IPC-CE a/a: {((nu/nu.shift(12)-1)*100).dropna().iloc[-1]:.2f}%")

    print(f"\nFiguras en {OUT}")


if __name__ == "__main__":
    main()
