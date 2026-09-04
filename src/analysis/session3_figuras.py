"""
Figuras de la sesion 3 (benchmarks): MAE por horizonte y modelo, la vara
publicada que el plan pide como referencia para medir todo lo que venga
despues (SARIMAX, BVAR, ensemble). Lee de metricas_backtest, ya poblada
por src/models/backtest.py -- no vuelve a correr el backtest.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.etl import db  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MES = pd.Timestamp.today().strftime("%Y-%m")
OUT = ROOT / "outputs" / "eda" / MES
OUT.mkdir(parents=True, exist_ok=True)

SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
COLORES = {
    "bench_rw_estacional": "#2a78d6", "bench_media_movil_12m": "#eb6834",
    "bench_naive": "#1baf7a", "bench_estacional_historica": "#eda100",
    "bench_rw": "#2a78d6", "bench_rw_drift": "#eb6834",
}
NOMBRES = {
    "bench_rw_estacional": "RW estacional", "bench_media_movil_12m": "Media movil 12m",
    "bench_naive": "Naive (ultimo dato)", "bench_estacional_historica": "Estacionalidad historica",
    "bench_rw": "Random walk", "bench_rw_drift": "RW + drift (dif. inflacion)",
}
SENTINEL_COMPLETO = "0001-01-01"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.edgecolor": INK2, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
    "grid.color": "#e8e7e3", "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "figure.dpi": 150,
})


def _mae_completo(con: sqlite3.Connection, objetivo: str) -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT modelo_id, horizonte_meses, mae, n_obs FROM metricas_backtest "
        "WHERE objetivo=? AND periodo_desde=?", con, params=(objetivo, SENTINEL_COMPLETO))
    return df


def _grafico(df: pd.DataFrame, titulo: str, ylabel: str, ruta: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for modelo in df["modelo_id"].unique():
        s = df[df["modelo_id"] == modelo].sort_values("horizonte_meses")
        ax.plot(s["horizonte_meses"], s["mae"], marker="o", markersize=5,
                linewidth=2, color=COLORES.get(modelo, INK2),
                label=NOMBRES.get(modelo, modelo))
    ax.set_xticks(sorted(df["horizonte_meses"].unique()))
    ax.set_xlabel("horizonte (meses)")
    ax.set_ylabel(ylabel)
    ax.set_title(titulo, fontsize=10, color=INK, loc="left")
    ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)


def main() -> None:
    con = db.conectar()
    n = con.execute("SELECT COUNT(*) FROM metricas_backtest").fetchone()[0]
    if n == 0:
        raise RuntimeError("metricas_backtest esta vacia; correr src/models/backtest.py primero")

    pi = _mae_completo(con, "ipc_m")
    _grafico(pi, "MAE de los benchmarks de inflacion m/m, por horizonte\n"
                "Expanding window dic-2016+; la vara para todo modelo futuro",
             "MAE (p.p. de inflacion m/m)", OUT / "fig4_benchmarks_mae_inflacion.png")

    tc = _mae_completo(con, "tc_prom")
    _grafico(tc, "MAE de los benchmarks de TC promedio, por horizonte\n"
                "Expanding window dic-2016+; nivel en pesos por dolar",
             "MAE (UYU/USD)", OUT / "fig5_benchmarks_mae_tc.png")

    con.close()
    print(f"Figuras en {OUT}")


if __name__ == "__main__":
    main()
