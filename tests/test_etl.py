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
print("\n[5] Siembra de variables cubre todo var_id que escribe el ETL")
# Este test habria detectado la falla de la corrida historica 2026-08-06:
# el ETL escribia observaciones de var_ids que no existian en `variables`
# y TODO insert moria por FOREIGN KEY.
from src.etl import fred_series, seed  # noqa: E402

ESCRITAS_POR_EL_ETL = {
    "tc_usduyu_interbancario", "tc_usduyu_prom_m", "tc_usduyu_cierre_m",
    "ui_valor", "ipc_general_idx", "ipc_general_empalmado",
    "ipc_subyacente_idx",
} | set(fred_series.SERIES) | {f"ipc_div_{c}" for c in seed.DIVISIONES_CCIF}

with tempfile.TemporaryDirectory() as tmp:
    ruta = Path(tmp) / "t.db"
    db.inicializar(ruta)
    con = db.conectar(ruta)
    n = seed.sembrar_variables(con)
    check(n >= 30, f"la siembra registra el inventario completo ({n} variables)")
    registradas = seed.variables_registradas(con)
    faltan = ESCRITAS_POR_EL_ETL - registradas
    check(not faltan, f"ningun var_id del ETL queda sin registrar (faltan: {faltan or '-'})")

    # y el guardrail de db.py rechaza con mensaje claro un var_id desconocido
    try:
        db.upsert_observaciones(con, "no_existe", [("2026-01-01", 1.0)])
        check(False, "upsert con var_id desconocido debe fallar")
    except ValueError as e:
        check("variables.yaml" in str(e), "el error de var_id desconocido explica el arreglo")
    con.close()

# ---------------------------------------------------------------------
print("\n[6] Parsers del INE contra las planillas reales versionadas")
BASE = Path(__file__).resolve().parents[1] / "data" / "raw" / "ine" / "base_2022_10"
if not BASE.exists() or not any(BASE.iterdir()):
    print("  (sin planillas en data/raw/ine/base_2022_10; se salta)")
else:
    r_largo = ine_ipc.buscar_archivo(BASE, "gral", "variaciones")
    check(r_largo is not None, "planilla de serie general larga encontrada")
    if r_largo:
        s = ine_ipc.parsear_general_largo(r_largo)
        check(len(s) > 1000, f"serie larga con {len(s)} obs (>1000)")
        check(s.index.min().year == 1937, f"arranca en {s.index.min().date()}")
        check((s > 0).all(), "sin ceros ni negativos")
        var_m = s.pct_change().dropna()
        check(abs(s.loc["2022-10-01"] - 100) < 0.5,
              f"base oct-2022 ~ 100 (da {s.loc['2022-10-01']:.2f})")
        # la inflacion mensual post-2011 debe ser moderada
        post = var_m[var_m.index >= "2011-01-01"] * 100
        check(post.between(-2, 5).all(),
              "toda variacion mensual 2011+ dentro de [-2%, +5%]")

    r_reg = ine_ipc.buscar_archivo(BASE, "general_total")
    check(r_reg is not None, "planilla por region encontrada")
    if r_reg:
        reg = ine_ipc.parsear_general_regiones(r_reg)
        tp = reg["total_pais"]
        check(len(tp) >= 180, f"total pais con {len(tp)} obs desde {tp.index.min().date()}")
        if r_largo:
            comun = tp.index.intersection(s.index)
            dif = (tp[comun] - s[comun]).abs().max()
            check(dif < 0.01, f"regiones y serie larga coinciden (dif max {dif:.6f})")

    r_div = ine_ipc.buscar_archivo(BASE, "division", "pais")
    check(r_div is not None, "planilla de divisiones encontrada")
    if r_div:
        d = ine_ipc.parsear_divisiones(r_div)
        divs = sorted(d["division"].unique())
        check(divs == sorted(seed.DIVISIONES_CCIF),
              f"13 divisiones CCIF completas (hay {len(divs)})")
        obs = d.groupby("division").size()
        check(obs.nunique() == 1 and obs.iloc[0] >= 180,
              f"todas las divisiones con la misma cobertura ({obs.iloc[0]} meses)")

    r_sub = ine_ipc.buscar_archivo(BASE, "subyacente")
    check(r_sub is not None, "planilla del IPC-CE encontrada")
    if r_sub:
        n = ine_ipc.parsear_subyacente(r_sub)
        check(len(n) >= 40, f"IPC-CE con {len(n)} obs desde {n.index.min().date()}")
        check(abs(n.loc["2022-10-01"] - 100) < 1e-6, "IPC-CE ancla 100 en oct-2022")

# ---------------------------------------------------------------------
print("\n[7] Parser del IMS contra las planillas reales")
from src.etl import ine_ims  # noqa: E402
IMS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "descubrimiento" / "ims_ine"
if not IMS_DIR.exists() or not any(IMS_DIR.iterdir()):
    print("  (sin planillas del IMS; se salta)")
else:
    res = ine_ims.series(IMS_DIR)
    check("salario_nominal_ims" in res, "IMSN encontrado y parseado")
    check("ims_general_idx" in res, "IMS general encontrado y parseado")
    if "salario_nominal_ims" in res:
        s = res["salario_nominal_ims"]
        check(s.index.min() == pd.Timestamp("2002-12-01"),
              f"IMSN arranca dic-2002 (da {s.index.min().date()})")
        check(len(s) >= 280, f"IMSN con {len(s)} obs")
        vm = s.pct_change().dropna() * 100
        check(vm.between(-2, 20).all(), "variaciones mensuales del IMSN plausibles")
    if "ims_general_idx" in res:
        g = res["ims_general_idx"]
        check(g.index.min().year == 1968, f"IMS general arranca 1968 (da {g.index.min().date()})")
        check((g > 0).all(), "IMS general sin ceros ni negativos")

# ---------------------------------------------------------------------
print(f"\n{'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}")
for f in fallos:
    print("  -", f)
sys.exit(1 if fallos else 0)
