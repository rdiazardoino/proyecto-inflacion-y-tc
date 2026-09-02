"""
Siembra de la tabla `variables` desde config/variables.yaml.

Esta era la pieza faltante que hizo fallar la corrida historica del
6-ago-2026: `observaciones.var_id` tiene FK contra `variables.var_id`,
pero nada poblaba `variables`, asi que TODOS los inserts de datos morian
con "FOREIGN KEY constraint failed".

variables.yaml es la fuente de verdad de las series de origen. Las series
DERIVADAS (agregados que calcula el propio ETL) no son fuentes y se
declaran aca, no en el yaml.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "variables.yaml"

# Series que produce el ETL a partir de otras. No estan en variables.yaml
# porque no son fuentes: son calculo propio.
DERIVADAS = [
    dict(var_id="tc_usduyu_prom_m",
         nombre="TC USD/UYU promedio mensual (punto medio interbancario)",
         frecuencia="M", fuente="BCU-SOAP (derivado)",
         transformacion="pct_m,pct_yoy",
         hipotesis_econ="Variable objetivo T1 del plan.",
         modelo_destino="tc", prioridad="indispensable"),
    dict(var_id="tc_usduyu_cierre_m",
         nombre="TC USD/UYU cierre de mes (ultimo dia habil)",
         frecuencia="M", fuente="BCU-SOAP (derivado)",
         transformacion="pct_m,pct_yoy",
         hipotesis_econ="Variable objetivo T2 del plan.",
         modelo_destino="tc", prioridad="indispensable"),
    dict(var_id="ui_valor",
         nombre="Valor de la Unidad Indexada (diario)",
         frecuencia="D", fuente="BCU-SOAP",
         transformacion="pct_m",
         hipotesis_econ="Inflacion implicita de corto plazo; deflactor UI.",
         modelo_destino="ambos", prioridad="importante"),
    dict(var_id="ipc_general_empalmado",
         nombre="IPC general empalmado 1997->presente (base oct-2022=100)",
         frecuencia="M", fuente="INE (empalme propio por variacion mensual)",
         transformacion="pct_m,pct_yoy",
         hipotesis_econ="Serie larga para estimacion; el empalme por variacion evita el salto de canasta.",
         modelo_destino="inflacion", prioridad="indispensable"),
]


# Divisiones CCIF 2018 del IPC base octubre 2022 (13 divisiones).
# variables.yaml las documenta como una sola entrada (ipc_divisiones_idx);
# aca se expanden a una variable por division para el bottom-up.
DIVISIONES_CCIF = {
    "01": "Alimentos y bebidas no alcoholicas",
    "02": "Bebidas alcoholicas y tabaco",
    "03": "Prendas de vestir y calzado",
    "04": "Alojamiento, agua, electricidad, gas y otros combustibles",
    "05": "Muebles, articulos y servicios para el hogar",
    "06": "Salud",
    "07": "Transporte",
    "08": "Informacion y comunicacion",
    "09": "Recreacion, deporte y cultura",
    "10": "Servicios de ensenanza",
    "11": "Restaurantes y servicios de alojamiento",
    "12": "Seguros y servicios financieros",
    "13": "Cuidado personal, proteccion social y bienes diversos",
}

VARIABLES_DIVISIONES = [
    dict(var_id=f"ipc_div_{cod}",
         nombre=f"IPC division {cod} - {nombre} (indice Total Pais)",
         frecuencia="M", fuente="INE",
         transformacion="pct_m,incidencia",
         hipotesis_econ="Base del modelo bottom-up y de las incidencias.",
         modelo_destino="inflacion", prioridad="indispensable")
    for cod, nombre in DIVISIONES_CCIF.items()
]


def _entradas_yaml() -> list[dict]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    entradas = []
    for seccion, contenido in cfg.items():
        if seccion == "meta" or not isinstance(contenido, list):
            continue
        for item in contenido:
            if isinstance(item, dict) and "var_id" in item:
                entradas.append(item)
    return entradas


def sembrar_variables(con: sqlite3.Connection) -> int:
    """Inserta/actualiza todas las variables conocidas. Idempotente."""
    columnas = ("var_id", "nombre", "descripcion", "unidad", "frecuencia",
                "fuente", "fuente_url", "fecha_inicio", "rezago_dias",
                "transformacion", "hipotesis_econ", "modelo_destino",
                "prioridad", "notas")
    n = 0
    for item in _entradas_yaml() + DERIVADAS + VARIABLES_DIVISIONES:
        fila = {}
        for c in columnas:
            v = item.get(c)
            if isinstance(v, list):
                v = ",".join(str(x) for x in v)
            fila[c] = v
        # minimos obligatorios del esquema
        fila["nombre"] = fila["nombre"] or fila["var_id"]
        fila["frecuencia"] = fila["frecuencia"] or "M"
        fila["fuente"] = fila["fuente"] or "desconocida"
        cols = ", ".join(fila)
        ph = ", ".join("?" * len(fila))
        con.execute(f"INSERT OR REPLACE INTO variables ({cols}) VALUES ({ph})",
                    tuple(fila.values()))
        n += 1
    con.commit()
    return n


def variables_registradas(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT var_id FROM variables")}


if __name__ == "__main__":
    from src.etl import db
    db.inicializar()
    c = db.conectar()
    print(f"{sembrar_variables(c)} variables sembradas")
    c.close()
