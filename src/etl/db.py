"""
Capa de acceso a la base. Diseno point-in-time: nunca se pisa historia.

Toda escritura de datos observados pasa por upsert_observaciones(), que
inserta una fila por (var_id, fecha_ref, vintage). Si el valor de un dato
ya cargado cambia en un vintage posterior, se agrega una fila nueva y se
registra el valor anterior en revision_de. El dato original queda.
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "db" / "proyecto.db"
SCHEMA_PATH = ROOT / "db" / "schema.sql"
BACKUP_DIR = ROOT / "db" / "backups"


def hoy() -> str:
    return dt.date.today().isoformat()


def conectar(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=30)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def inicializar(db_path: Path | str = DB_PATH) -> None:
    """Crea el esquema si no existe. Idempotente."""
    con = conectar(db_path)
    try:
        con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        con.commit()
    finally:
        con.close()


def respaldar(db_path: Path | str = DB_PATH, conservar: int = 10) -> Path | None:
    """
    Copia el .db antes de cada corrida. Mitigacion del riesgo de corrupcion
    por escritura concurrente en carpeta sincronizada (OneDrive).
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destino = BACKUP_DIR / f"proyecto_{dt.datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(db_path, destino)
    respaldos = sorted(BACKUP_DIR.glob("proyecto_*.db"))
    for viejo in respaldos[:-conservar]:
        viejo.unlink(missing_ok=True)
    return destino


# ---------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------
def registrar_variable(con: sqlite3.Connection, **campos) -> None:
    cols = ", ".join(campos)
    ph = ", ".join("?" * len(campos))
    con.execute(
        f"INSERT OR REPLACE INTO variables ({cols}) VALUES ({ph})",
        tuple(campos.values()),
    )


# ---------------------------------------------------------------------
# Observaciones
# ---------------------------------------------------------------------
def upsert_observaciones(
    con: sqlite3.Connection,
    var_id: str,
    datos: Iterable[tuple[str, float]],
    vintage: str | None = None,
    fuente: str | None = None,
    fecha_publicacion: str | None = None,
) -> dict[str, int]:
    """
    datos: iterable de (fecha_ref ISO, valor).

    Devuelve conteo de filas nuevas, revisiones detectadas y sin cambio.
    Una revision es un valor distinto al ultimo vintage conocido para la
    misma fecha_ref. Se inserta como fila nueva con revision_de = valor viejo.
    """
    vintage = vintage or hoy()
    descarga = hoy()

    existe = con.execute("SELECT 1 FROM variables WHERE var_id = ?",
                         (var_id,)).fetchone()
    if not existe:
        raise ValueError(
            f"var_id '{var_id}' no esta registrado en la tabla variables. "
            f"Agregarlo a config/variables.yaml o a seed.DERIVADAS y "
            f"correr seed.sembrar_variables() antes de insertar datos.")

    previos = dict(
        con.execute(
            """
            SELECT o.fecha_ref, o.valor
            FROM observaciones o
            JOIN (SELECT fecha_ref, MAX(vintage) mv
                  FROM observaciones WHERE var_id = ? GROUP BY fecha_ref) u
              ON o.fecha_ref = u.fecha_ref AND o.vintage = u.mv
            WHERE o.var_id = ?
            """,
            (var_id, var_id),
        ).fetchall()
    )

    nuevas = revisiones = igual = 0
    filas = []
    for fecha_ref, valor in datos:
        if valor is None or (isinstance(valor, float) and pd.isna(valor)):
            continue
        valor = float(valor)
        anterior = previos.get(fecha_ref)
        if anterior is None:
            nuevas += 1
            rev = None
        elif abs(anterior - valor) > 1e-9:
            revisiones += 1
            rev = anterior
        else:
            igual += 1
            continue  # nada que guardar
        filas.append(
            (var_id, fecha_ref, vintage, valor, fecha_publicacion,
             descarga, fuente, "pendiente", rev)
        )

    if filas:
        con.executemany(
            """
            INSERT OR IGNORE INTO observaciones
              (var_id, fecha_ref, vintage, valor, fecha_publicacion,
               fecha_descarga, fuente, estado_validacion, revision_de)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            filas,
        )
    con.commit()
    return {"nuevas": nuevas, "revisiones": revisiones, "sin_cambio": igual}


def serie(con: sqlite3.Connection, var_id: str,
          vintage_max: str | None = None) -> pd.Series:
    """
    Serie de una variable al ultimo vintage disponible, o al vintage indicado
    (para reproducir exactamente lo que se sabia en una fecha dada).
    """
    if vintage_max:
        q = """
            SELECT o.fecha_ref, o.valor FROM observaciones o
            JOIN (SELECT fecha_ref, MAX(vintage) mv FROM observaciones
                  WHERE var_id = ? AND vintage <= ? GROUP BY fecha_ref) u
              ON o.fecha_ref = u.fecha_ref AND o.vintage = u.mv
            WHERE o.var_id = ? ORDER BY o.fecha_ref
        """
        df = pd.read_sql(q, con, params=(var_id, vintage_max, var_id))
    else:
        df = pd.read_sql(
            "SELECT fecha_ref, valor FROM v_series_actual WHERE var_id = ? "
            "ORDER BY fecha_ref", con, params=(var_id,))
    if df.empty:
        return pd.Series(dtype=float, name=var_id)
    s = pd.Series(df["valor"].values,
                  index=pd.to_datetime(df["fecha_ref"]), name=var_id)
    return s


# ---------------------------------------------------------------------
# Licitaciones y eventos
# ---------------------------------------------------------------------
def upsert_licitaciones(con: sqlite3.Connection,
                        filas: Sequence[dict]) -> int:
    if not filas:
        return 0
    cols = ["licitacion_id", "fecha_licitacion", "emisor", "instrumento",
            "serie", "moneda", "plazo_dias", "fecha_vencimiento",
            "monto_ofrecido", "monto_demandado", "monto_adjudicado",
            "bid_to_cover", "tasa_corte", "tasa_promedio", "tasa_minima",
            "precio_corte", "desierta", "fecha_descarga", "fuente_url", "notas"]
    ph = ", ".join("?" * len(cols))
    con.executemany(
        f"INSERT OR REPLACE INTO licitaciones ({', '.join(cols)}) VALUES ({ph})",
        [tuple(f.get(c) for c in cols) for f in filas],
    )
    con.commit()
    return len(filas)


def registrar_evento(con: sqlite3.Connection, fecha: str, tipo: str,
                     titulo: str, detalle: str | None = None,
                     impacto_esperado: str | None = None,
                     magnitud_estimada: float | None = None,
                     fuente_url: str | None = None) -> None:
    con.execute(
        """INSERT INTO eventos (fecha, tipo, titulo, detalle, impacto_esperado,
                                magnitud_estimada, fuente_url)
           VALUES (?,?,?,?,?,?,?)""",
        (fecha, tipo, titulo, detalle, impacto_esperado,
         magnitud_estimada, fuente_url),
    )
    con.commit()


# ---------------------------------------------------------------------
# Logs y alertas
# ---------------------------------------------------------------------
def log(con: sqlite3.Connection, proceso: str, estado: str,
        var_id: str | None = None, filas_nuevas: int | None = None,
        mensaje: str | None = None, duracion_seg: float | None = None) -> None:
    con.execute(
        """INSERT INTO logs_actualizacion
           (fecha, proceso, var_id, estado, filas_nuevas, mensaje, duracion_seg)
           VALUES (?,?,?,?,?,?,?)""",
        (dt.datetime.now().isoformat(timespec="seconds"), proceso, var_id,
         estado, filas_nuevas, mensaje, duracion_seg),
    )
    con.commit()


def alerta(con: sqlite3.Connection, tipo: str, severidad: str,
           detalle: str, var_id: str | None = None,
           modelo_id: str | None = None) -> None:
    con.execute(
        """INSERT INTO alertas (fecha, tipo, severidad, var_id, modelo_id, detalle)
           VALUES (?,?,?,?,?,?)""",
        (hoy(), tipo, severidad, var_id, modelo_id, detalle),
    )
    con.commit()


if __name__ == "__main__":
    inicializar()
    print(f"Base inicializada en {DB_PATH}")
