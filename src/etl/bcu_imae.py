"""
IMAE (Indicador Mensual de Actividad Economica) del BCU -- brecha de
producto para la curva de Phillips (config/variables.yaml, var_id imae).

Hallazgo real del 4-sep-2026: la pagina del informe es un cascaron
SharePoint SPA, pero embebe un <iframe> a un HTML ESTATICO separado
("Visor de paginas" -> Documents/IMAE-graficas.html) que resulta ser un
reporte R/knitr con graficos Plotly -- y Plotly embebe los datos crudos
de cada trace como JSON dentro de <script type="application/json"
data-for="htmlwidget-...">. No hace falta navegador: es HTML estatico,
descargable con requests.get() como cualquier otra pagina.

El archivo trae TRES widgets (uno por variante), cada uno con dos traces
(el nivel del indice como scatter "eje derecho" + su variacion como
barras):
  0. IMAE original (IVF, 2016=100) + variacion anual -- desde 2017-01
  1. IMAE desestacionalizado (SA) + variacion desestacionalizada -- desde 2016-03
  2. IMAE tendencia-ciclo + variacion tendencia-ciclo -- desde 2016-03

Se usa el DESESTACIONALIZADO como serie principal (var_id 'imae'): un
filtro HP sobre una serie con estacionalidad todavia adentro confundiria
estacionalidad con ciclo. Las otras dos quedan expuestas por si hacen
falta para control cruzado.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from src.etl import http_client

URL = "https://www.bcu.gub.uy/Estadisticas-e-Indicadores/Documents/IMAE-graficas.html"

_PATRON_WIDGET = re.compile(
    r'<script type="application/json" data-for="htmlwidget-[^"]+">(.*?)</script>', re.S)

# indice del widget dentro del HTML -> (nombre de la serie de nivel, var_id)
_WIDGETS = {
    0: "imae_original_idx",
    1: "imae_desestacionalizado_idx",
    2: "imae_tendencia_ciclo_idx",
}


def descargar(timeout: int = 60) -> str:
    r = http_client.get(URL, timeout=timeout)
    return r.text


def _serie_de_trace(trace: dict) -> pd.Series:
    fechas = pd.to_datetime(trace["x"])
    return pd.Series(trace["y"], index=fechas, dtype=float).sort_index()


def parsear(html: str) -> dict[str, pd.Series]:
    """
    Devuelve {var_id: serie} con el NIVEL del indice de cada variante
    (el trace tipo "scatter" -- el otro trace de cada widget es solo la
    variacion, redundante con el nivel y no se carga aparte).
    """
    bloques = _PATRON_WIDGET.findall(html)
    resultado: dict[str, pd.Series] = {}
    for i, bloque in enumerate(bloques):
        var_id = _WIDGETS.get(i)
        if var_id is None:
            continue
        datos = json.loads(bloque)
        traces = datos.get("x", {}).get("data", [])
        nivel = next((t for t in traces if t.get("type") == "scatter"), None)
        if nivel is None or not nivel.get("x"):
            continue
        resultado[var_id] = _serie_de_trace(nivel)
    return resultado


def series() -> dict[str, pd.Series]:
    return parsear(descargar())


if __name__ == "__main__":
    for var_id, s in series().items():
        print(f"{var_id}: {len(s)} obs, {s.index.min().date()} .. {s.index.max().date()}")
