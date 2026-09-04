"""
Indice Medio de Salarios (INE).

Mismo patron de publicacion que el IPC: pagina de series historicas en
gub.uy con planillas .xls, layout "Cua" (fecha datetime en col 0, indice
en col 1, encabezado 'Mes y año'). Se reutiliza el parser del IPC.

Series que se cargan:
  salario_nominal_ims  IMSN (Ley 17.649), base jul-2008=100, dic-2002 ->
                       la que se usa para indexaciones y la Phillips.
  ims_general_idx      IMS general, ene-1968 -> (serie larga, contexto).

Calibrado contra los archivos reales del 3-sep-2026 (IMSN_M_B08.xls,
IMS_C1_Gral_emp_M_B08.xls), versionados en data/raw/descubrimiento/ims_ine/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.etl import http_client, ine_ipc

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "ims"

PAGINAS = [
    "https://www.gub.uy/instituto-nacional-estadistica/datos-y-estadisticas/estadisticas/series-historicas-indice-medio-salarios-ims-base-julio-2008100",
]

# fragmento normalizado del nombre de archivo -> var_id
PLANILLAS = {
    "imsn_m_b08": "salario_nominal_ims",
    "ims_c1_gral_emp_m_b08": "ims_general_idx",
}


def bajar() -> list[Path]:
    """Descarga las planillas del IMS a data/raw/ims/ (versionadas)."""
    rutas: list[Path] = []
    for url in PAGINAS:
        try:
            enlaces = ine_ipc.descubrir_planillas(url)
        except Exception as e:                        # noqa: BLE001
            print(f"[ims] no se pudo leer {url}: {e}")
            continue
        for u in enlaces:
            try:
                rutas.append(ine_ipc.descargar(u, RAW))
            except Exception as e:                    # noqa: BLE001
                print(f"[ims] fallo descarga {u}: {e}")
        if rutas:
            break
    print(f"[ims] {len(rutas)} archivos")
    return rutas


def series(directorio: Path | None = None) -> dict[str, pd.Series]:
    """
    Parsea las planillas clave presentes en `directorio` (default RAW).
    Devuelve {var_id: serie}. Las planillas usan el layout 'Cua' del INE,
    el mismo parser del IPC largo aplica tal cual.
    """
    directorio = directorio or RAW
    salida: dict[str, pd.Series] = {}
    for fragmento, var_id in PLANILLAS.items():
        ruta = ine_ipc.buscar_archivo(directorio, fragmento)
        if ruta is None:
            print(f"[ims] falta planilla para {var_id} ({fragmento})")
            continue
        s = ine_ipc.parsear_general_largo(ruta)
        if len(s):
            salida[var_id] = s
    return salida


if __name__ == "__main__":
    bajar()
    for var_id, s in series().items():
        print(f"{var_id}: {len(s)} obs {s.index.min().date()}..{s.index.max().date()}")
