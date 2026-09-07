"""
Carga de datos manuales (descargados a mano por el analista cuando el
ETL automatico no puede traerlos -- ver docs/manifest_fuentes.md, tabla
"Pendiente de ingesta").

Convencion: toda carga manual se guarda con `fuente` prefijado "MANUAL: "
(seguido de una descripcion corta de donde salio). datos_dashboard.py
busca ese prefijo para armar la seccion "Datos cargados manualmente" del
dashboard y del informe -- asi el lector siempre sabe que numeros no
vienen del pipeline automatico y de que fecha son.

Uso, un solo punto:
    python src/etl/cargar_manual.py itcr_global 2026-08-01 98.4 \
        --fuente "BCU eportal TCRE, exportado a .xls a mano"

Uso, un CSV con varios puntos (columnas: fecha_ref,valor):
    python src/etl/cargar_manual.py tpm_bcu --csv data/raw/manual/tpm.csv \
        --fuente "Actas Copom descargadas de bcu.gub.uy"

fecha_ref: primer dia del mes al que corresponde el dato (YYYY-MM-01),
no la fecha en que se lo descargo -- esa se guarda sola como fecha_descarga.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.etl import db  # noqa: E402

PREFIJO_MANUAL = "MANUAL: "


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("var_id", help="var_id registrado en config/variables.yaml")
    ap.add_argument("fecha_ref", nargs="?", help="YYYY-MM-01 (omitir si se usa --csv)")
    ap.add_argument("valor", nargs="?", type=float, help="valor numerico (omitir si se usa --csv)")
    ap.add_argument("--csv", help="CSV con columnas fecha_ref,valor para cargar varios puntos")
    ap.add_argument("--fuente", required=True, help="de donde salio el dato (se antepone 'MANUAL: ')")
    args = ap.parse_args()

    if args.csv:
        df = pd.read_csv(args.csv)
        datos = list(zip(df["fecha_ref"], df["valor"]))
    elif args.fecha_ref is not None and args.valor is not None:
        datos = [(args.fecha_ref, args.valor)]
    else:
        ap.error("dar fecha_ref y valor, o --csv")

    con = db.conectar()
    try:
        res = db.upsert_observaciones(con, args.var_id, datos, fuente=PREFIJO_MANUAL + args.fuente)
        print(f"{args.var_id}: {res['nuevas']} nuevas, {res['revisiones']} revisiones, "
              f"{res['sin_cambio']} sin cambio (fuente: {PREFIJO_MANUAL}{args.fuente})")
    finally:
        con.close()


if __name__ == "__main__":
    main()
