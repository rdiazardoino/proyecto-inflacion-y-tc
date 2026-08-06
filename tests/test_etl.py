"""
Tests que NO requieren internet. Cubren lo que se puede romper en silencio:
el diseno point-in-time y el empalme de bases del IPC.

Correr: python tests/test_etl.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.etl import db, ine_ipc  # noqa: E402

fallos = []


def check(cond, msg):
    print(("  OK   " if cond else "  FALLA ") + msg)
    if not cond:
        fallos.append(msg)


# ---------------------------------------------------------------------
print("\n[1] Point-in-time: una revision no pisa el dato original")
with tempfile.TemporaryDirectory() as tmp:
    ruta = Path(tmp) / "t.db"
    db.inicializar(ruta)
    con = db.conectar(ruta)
    con.execute("INSERT INTO variables (var_id, nombre, frecuencia, fuente) "
                "VALUES ('x','X','M','test')")
    con.commit()

    r1 = db.upsert_observaciones(con, "x", [("2026-01-01", 100.0),
                                            ("2026-02-01", 101.0)],
                                 vintage="2026-03-01")
    check(r1["nuevas"] == 2, f"carga inicial inserta 2 filas (dio {r1['nuevas']})")

    # mismo dato, sin cambios
    r2 = db.upsert_observaciones(con, "x", [("2026-01-01", 100.0)],
                                 vintage="2026-04-01")
    check(r2["sin_cambio"] == 1 and r2["nuevas"] == 0,
          "recarga identica no duplica filas")

    # revision del INE: enero pasa de 100.0 a 100.4
    r3 = db.upsert_observaciones(con, "x", [("2026-01-01", 100.4)],
                                 vintage="2026-04-01")
    check(r3["revisiones"] == 1, "revision detectada")

    filas = con.execute(
        "SELECT vintage, valor, revision_de FROM observaciones "
        "WHERE var_id='x' AND fecha_ref='2026-01-01' ORDER BY vintage").fetchall()
    check(len(filas) == 2, f"quedan 2 vintages para enero (hay {len(filas)})")
    check(filas[0][1] == 100.0, "el valor original 100.0 sigue existiendo")
    check(filas[1][1] == 100.4 and filas[1][2] == 100.0,
          "la revision guarda el valor previo en revision_de")

    check(db.serie(con, "x").loc["2026-01-01"] == 100.4,
          "serie() sin vintage devuelve el dato revisado")
    check(db.serie(con, "x", vintage_max="2026-03-15").loc["2026-01-01"] == 100.0,
          "serie() con vintage_max reproduce lo que se sabia en esa fecha")
    con.close()

# ---------------------------------------------------------------------
print("\n[2] Empalme de bases del IPC por variacion mensual")
# Serie verdadera con inflacion 0.5% mensual
idx = pd.date_range("2015-01-01", "2026-07-01", freq="MS")
verdadera = pd.Series(100 * (1.005 ** np.arange(len(idx))), index=idx)

corte = pd.Timestamp("2022-10-01")
vieja = verdadera[verdadera.index <= corte]
vieja = vieja / vieja.iloc[0] * 100                 # rebasada a ene-2015 = 100
nueva = verdadera[verdadera.index >= corte]
nueva = nueva / nueva.iloc[0] * 100                 # rebasada a oct-2022 = 100

emp = ine_ipc.empalmar({"base_2010_12": vieja, "base_2022_10": nueva})
check(len(emp) == len(verdadera),
      f"el empalme cubre toda la muestra ({len(emp)} de {len(verdadera)})")
check(abs(emp.loc[corte] - 100.0) < 1e-6, "el ancla queda en 100 en oct-2022")

var_emp = emp.pct_change().dropna()
check(np.allclose(var_emp.values, 0.005, atol=1e-9),
      "toda variacion mensual del empalme es 0.5%, sin salto en el corte")

salto = abs(emp.pct_change().loc[corte] - 0.005)
check(salto < 1e-9, f"no hay discontinuidad en la fecha de corte ({salto:.2e})")

# El empalme por NIVEL habria roto esto: se verifica que es distinto
ingenuo = pd.concat([vieja[vieja.index < corte], nueva])
check(abs(ingenuo.pct_change().loc[corte] - 0.005) > 0.1,
      "control: empalmar por nivel si genera un salto falso")

# ---------------------------------------------------------------------
print("\n[3] Parseo de etiquetas de periodo del INE")
casos = [("Enero 2023", "2023-01-01"), ("2023-01", "2023-01-01"),
         ("01/2023", "2023-01-01"), ("Setiembre 2022", "2022-09-01"),
         ("Diciembre 2010", "2010-12-01"), ("basura", None)]
for entrada, esperado in casos:
    check(ine_ipc._a_fecha(entrada) == esperado,
          f"'{entrada}' -> {esperado}")

# ---------------------------------------------------------------------
print("\n[4] Deteccion de moneda en texto de licitaciones")
from src.etl import licitaciones  # noqa: E402
for txt, esperado in [("Nota del Tesoro en UI a 5 años", "UI"),
                      ("Letra de Regulación Monetaria en pesos", "UYU"),
                      ("Nota en Unidades Previsionales", "UP"),
                      ("Bono en dólares", "USD")]:
    check(licitaciones.detectar_moneda(txt) == esperado,
          f"'{txt[:35]}' -> {esperado}")

# ---------------------------------------------------------------------
print(f"\n{'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}")
for f in fallos:
    print("  -", f)
sys.exit(1 if fallos else 0)
