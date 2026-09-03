"""Figuras de la sesion 4: los modelos economicos contra su benchmark ganador."""

from __future__ import annotations

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
    "bench_rw_estacional": "#2a78d6", "bench_rw": "#2a78d6",
    "phillips_reducida": "#eb6834", "sarimax_topdown": "#1baf7a",
    "var2_reducido": "#e34948",
}
NOMBRES = {
    "bench_rw_estacional": "RW estacional (benchmark)", "bench_rw": "Random walk (benchmark)",
    "phillips_reducida": "Phillips reducida", "sarimax_topdown": "SARIMAX top-down",
    "var2_reducido": "VAR(2) reducido",
}
ANCHO = {"bench_rw_estacional": 3.2, "bench_rw": 3.2}
SENTINEL = "0001-01-01"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.edgecolor": INK2, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
    "grid.color": "#e8e7e3", "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "figure.dpi": 150,
})


def _grafico(con, objetivo: str, modelos: list[str], titulo: str, ylabel: str, ruta: Path) -> None:
    df = pd.read_sql(
        "SELECT modelo_id, horizonte_meses, mae FROM metricas_backtest "
        "WHERE objetivo=? AND periodo_desde=?", con, params=(objetivo, SENTINEL))
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for modelo in modelos:
        s = df[df["modelo_id"] == modelo].sort_values("horizonte_meses")
        if s.empty:
            continue
        ax.plot(s["horizonte_meses"], s["mae"], marker="o", markersize=5,
                linewidth=ANCHO.get(modelo, 2), color=COLORES.get(modelo, INK2),
                label=NOMBRES.get(modelo, modelo))
    ax.set_xticks(sorted(df[df["modelo_id"].isin(modelos)]["horizonte_meses"].unique()))
    ax.set_xlabel("horizonte (meses)")
    ax.set_ylabel(ylabel)
    ax.set_title(titulo, fontsize=10, color=INK, loc="left")
    ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)


def main() -> None:
    con = db.conectar()
    _grafico(con, "ipc_m",
             ["bench_rw_estacional", "phillips_reducida", "sarimax_topdown", "var2_reducido"],
             "Modelos economicos (Escalon 1) vs. su benchmark\n"
             "Ninguno le gana a RW estacional en MAE, en ningun horizonte",
             "MAE (p.p. de inflacion m/m)", OUT / "fig6_sesion4_inflacion_vs_benchmark.png")
    _grafico(con, "tc_prom", ["bench_rw", "var2_reducido"],
             "VAR(2) reducido vs. random walk (TC)\n"
             "El VAR no le gana al random walk en ningun horizonte",
             "MAE (UYU/USD)", OUT / "fig7_sesion4_tc_vs_benchmark.png")
    con.close()
    print(f"Figuras en {OUT}")


if __name__ == "__main__":
    main()
