"""
Sesion 5 - Orquestador: ensemble (pronostico oficial) + escenarios
(sensibilidad direccional). Corre sobre datos reales, origen = jul-2026
(el ultimo mes con IPC Y TC observados simultaneamente).

Uso: python src/models/run_sesion5.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.etl import db  # noqa: E402
from src.models import ensemble, var_escenarios  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
HORIZONTES = [1, 3, 6, 9, 12, 15, 18, 21, 24]   # trayectoria para el fan chart
ORIGEN = pd.Timestamp("2026-07-01")


def _log_diff_pct(s: pd.Series) -> pd.Series:
    return np.log(s.astype(float)).diff() * 100


def cargar_series(con) -> dict[str, pd.Series]:
    ipc = db.serie(con, "ipc_general_empalmado").asfreq("MS")
    tc = db.serie(con, "tc_usduyu_prom_m").asfreq("MS")
    cpi_us = db.serie(con, "cpi_us").asfreq("MS")
    brl = db.serie(con, "usdbrl").resample("MS").mean()
    dxy = db.serie(con, "dxy").resample("MS").mean()
    return {
        "pi": _log_diff_pct(ipc), "pi_us": _log_diff_pct(cpi_us),
        "tc_nivel": tc, "dtc": _log_diff_pct(tc),
        "dbrl": _log_diff_pct(brl), "ddxy": _log_diff_pct(dxy),
    }


def correr_ensemble(con, series: dict) -> dict[str, pd.DataFrame]:
    salida = {}
    tc_origen = series["tc_nivel"].get(ORIGEN)
    for objetivo in ["ipc_m", "tc_prom"]:
        res = ensemble.pronostico_ensemble(con, series, objetivo, ORIGEN, HORIZONTES)
        if res.empty:
            print(f"  {objetivo}: sin modelos admitidos")
            continue
        detalle = res.attrs["detalle"]
        ensemble.guardar(con, objetivo, ORIGEN, detalle, res,
                         tc_nivel_origen=tc_origen if objetivo == "tc_prom" else None)
        salida[objetivo] = res
        print(f"\n  {objetivo} -- pesos:")
        print(detalle.pivot(index="modelo_id", columns="horizonte_meses", values="peso").round(3).to_string())
    return salida


def correr_escenarios(con, series: dict) -> dict[str, pd.DataFrame]:
    cfg = yaml.safe_load((ROOT / "config" / "scenarios.yaml").read_text())
    df_v = var_escenarios.preparar_datos(series["pi"], series["dtc"], series["dbrl"], series["ddxy"])
    tc_origen = series["tc_nivel"].get(ORIGEN)

    resultados = {}
    hoy = pd.Timestamp.today().date().isoformat()
    # mismo criterio que ensemble.guardar(): append-only ENTRE vintages,
    # idempotente DENTRO del mismo vintage_datos (re-correr el mismo mes no
    # debe acumular duplicados en pronosticos).
    con.execute(
        "DELETE FROM pronosticos WHERE modelo_id='var2_reducido' AND vintage_datos=?",
        (str(ORIGEN.date()),))
    for clave, esc in cfg["escenarios"].items():
        pron = var_escenarios.pronosticos(
            df_v, ORIGEN, HORIZONTES,
            dbrl_mensual=esc["supuestos"]["dbrl_mensual"],
            ddxy_mensual=esc["supuestos"]["ddxy_mensual"])
        filas = []
        for h in HORIZONTES:
            fecha_obj = (ORIGEN + pd.DateOffset(months=h)).strftime("%Y-%m-%d")
            pi_h, dtc_acum_h = pron["pi"][h], pron["dtc"][h]
            tc_h = tc_origen * np.exp(dtc_acum_h / 100) if tc_origen and pd.notna(dtc_acum_h) else np.nan
            filas.append(dict(horizonte_meses=h, fecha_objetivo=fecha_obj,
                              pi_m=pi_h, tc_nivel=tc_h))
            for objetivo, valor in [("ipc_m", pi_h), ("tc_prom", tc_h)]:
                if pd.isna(valor):
                    continue
                con.execute(
                    "INSERT INTO pronosticos (fecha_generacion, vintage_datos, modelo_id, "
                    " objetivo, fecha_objetivo, horizonte_meses, escenario, valor) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (hoy, str(ORIGEN.date()), "var2_reducido", objetivo, fecha_obj, h, clave, valor))
        resultados[clave] = pd.DataFrame(filas)
        con.execute(
            "INSERT OR REPLACE INTO escenarios (escenario_id, fecha_generacion, nombre, "
            " probabilidad, supuestos, senales_monitoreo) VALUES (?,?,?,?,?,?)",
            (clave, hoy, esc["nombre"], esc["probabilidad"],
             yaml.dump(esc["supuestos"], allow_unicode=True),
             yaml.dump(esc["senales_confirmacion"], allow_unicode=True)))
    con.commit()
    return resultados


def main() -> None:
    con = db.conectar()
    series = cargar_series(con)

    print("=" * 70)
    print(f"ENSEMBLE v1 -- origen {ORIGEN.date()}")
    res_ensemble = correr_ensemble(con, series)

    print("\n" + "=" * 70)
    print(f"ESCENARIOS -- vehiculo var2_reducido, origen {ORIGEN.date()}")
    res_escenarios = correr_escenarios(con, series)
    for clave, df in res_escenarios.items():
        print(f"\n  {clave}:")
        print(df.set_index("horizonte_meses")[["pi_m", "tc_nivel"]].round(3).to_string())

    con.close()
    return res_ensemble, res_escenarios


if __name__ == "__main__":
    main()
