"""
Sesion 5 - Fan chart: pronostico del ensemble (nodos 1/6/12/24, unicos
horizontes con backtest real) mas las 3 sendas de escenario del
VAR(2) reducido (vehiculo de sensibilidad, no pronostico oficial).
"""

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
AZUL, VERDE, ROJO = "#2a78d6", "#1baf7a", "#e34948"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.edgecolor": INK2, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
    "grid.color": "#e8e7e3", "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "figure.dpi": 150,
})


def _fan(con, objetivo: str, titulo: str, ylabel: str, ruta: Path, fmt=".2f") -> None:
    ens = pd.read_sql(
        "SELECT horizonte_meses, valor, li_80, ls_80, li_95, ls_95 FROM pronosticos "
        "WHERE modelo_id='ensemble_v1' AND objetivo=? AND escenario='base' "
        "ORDER BY horizonte_meses", con, params=(objetivo,))
    esc = pd.read_sql(
        "SELECT escenario, horizonte_meses, valor FROM pronosticos "
        "WHERE modelo_id='var2_reducido' AND objetivo=? ORDER BY escenario, horizonte_meses",
        con, params=(objetivo,))

    fig, ax = plt.subplots(figsize=(8.2, 5))
    h, v = ens["horizonte_meses"], ens["valor"]
    ax.fill_between(h, ens["li_95"], ens["ls_95"], color=AZUL, alpha=0.10, linewidth=0,
                    label="Ensemble, banda 95%")
    ax.fill_between(h, ens["li_80"], ens["ls_80"], color=AZUL, alpha=0.22, linewidth=0,
                    label="Ensemble, banda 80%")
    ax.plot(h, v, color=AZUL, linewidth=2.6, marker="o", markersize=6,
            label="Ensemble v1 (pronostico oficial)")

    colores_esc = {"benigno": VERDE, "adverso": ROJO}
    for clave, color in colores_esc.items():
        s = esc[esc["escenario"] == clave].sort_values("horizonte_meses")
        ax.plot(s["horizonte_meses"], s["valor"], color=color, linewidth=1.6,
                linestyle="--", marker=".", markersize=4,
                label=f"Escenario {clave} (VAR2, sensibilidad)")

    ax.set_xlabel("horizonte (meses desde jul-2026)")
    ax.set_ylabel(ylabel)
    ax.set_title(titulo, fontsize=10, color=INK, loc="left")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)


def main() -> None:
    con = db.conectar()
    _fan(con, "ipc_m",
         "Inflacion m/m - ensemble v1 (nodos 1/6/12/24) + escenarios VAR2\n"
         "Origen: julio 2026 (ultimo IPC observado)",
         "inflacion m/m (%)", OUT / "fig8_fanchart_inflacion.png")
    _fan(con, "tc_prom",
         "TC promedio (UYU/USD) - ensemble v1 (nodos 1/6/12/24) + escenarios VAR2\n"
         "Origen: julio 2026",
         "UYU/USD", OUT / "fig9_fanchart_tc.png")
    con.close()
    print(f"Figuras en {OUT}")


if __name__ == "__main__":
    main()
