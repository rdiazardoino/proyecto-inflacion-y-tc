"""
Series externas desde FRED.

Requiere una API key gratuita: https://fredaccount.stlouisfed.org/apikeys
Se lee de la variable de entorno FRED_API_KEY (secret en GitHub Actions).
"""

from __future__ import annotations

import os
import time

import requests

BASE = "https://api.stlouisfed.org/fred/series/observations"

# var_id local -> series_id de FRED
SERIES = {
    "usdbrl":     "DEXBZUS",     # Brazilian Reals to USD, diario
    "dxy":        "DTWEXBGS",    # Broad dollar index, diario
    "ust_10y":    "DGS10",       # Treasury 10y constant maturity, diario
    "ust_2y":     "DGS2",
    "ust_3m":     "DTB3",
    "fed_funds":  "FEDFUNDS",    # mensual
    "brent":      "DCOILBRENTEU",
    "soja":       "PSOYBUSDM",   # mensual, precio global soja
    "cpi_us":     "CPIAUCSL",    # mensual
    "vix":        "VIXCLS",
    # "usduyu_fred": "DEXUSUY" eliminado: FRED devuelve 400, la serie no
    # existe (verificado 6-ago-2026). El control cruzado del TC queda
    # pendiente de otra fuente.
}


def observaciones(series_id: str, desde: str = "1997-01-01",
                  api_key: str | None = None,
                  timeout: int = 60,
                  reintentos: int = 3) -> list[tuple[str, float]]:
    api_key = api_key or os.environ.get("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("Falta FRED_API_KEY")
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": desde,
    }
    ultimo = None
    for intento in range(reintentos):
        try:
            r = requests.get(BASE, params=params, timeout=timeout)
            r.raise_for_status()
            datos = r.json().get("observations", [])
            salida = []
            for o in datos:
                if o.get("value") in (".", "", None):
                    continue
                try:
                    salida.append((o["date"], float(o["value"])))
                except ValueError:
                    continue
            return salida
        except Exception as e:                        # noqa: BLE001
            ultimo = e
            time.sleep(2 ** intento)
    raise RuntimeError(f"FRED fallo para {series_id}: {ultimo}")


def bajar_todas(desde: str = "1997-01-01") -> dict[str, list[tuple[str, float]]]:
    salida = {}
    for var_id, sid in SERIES.items():
        try:
            salida[var_id] = observaciones(sid, desde=desde)
            print(f"[fred] {var_id} ({sid}): {len(salida[var_id])} obs")
        except Exception as e:                        # noqa: BLE001
            print(f"[fred] ERROR {var_id}: {e}")
            salida[var_id] = []
        time.sleep(0.3)
    return salida


if __name__ == "__main__":
    for k, v in bajar_todas("2020-01-01").items():
        if v:
            print(k, v[-1])
