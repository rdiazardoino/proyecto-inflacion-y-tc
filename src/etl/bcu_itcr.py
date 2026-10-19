"""
ITCR (Indice de Tipo de Cambio Real Efectivo) del BCU: Global,
Extrarregional y Regional -- mensual, base 2017=100.

El dato vive en un widget de un motor BI de terceros ("O3 BI", IdeaSoft)
embebido en el eportal Liferay (`/eportal/web/guest/tcre`). Al cargar la
pagina, el propio widget pide el grid con un POST
`...?p_p_resource_id=processCommands` que devuelve JSON con fecha +
TCRE Global/Extrarregional/Regional.

Mecanica (corregida 19-oct-2026): se abre la pagina con Chromium y se
INTERCEPTAN esas respuestas (`pagina.on("response")`), sin pedir nada a
mano. La version anterior replicaba los pedidos (render_portlet ->
Ticket/View -> processCommands) y en produccion devolvia HTTP 401 en
todas las corridas (5-sep-2026), mientras que en esa misma corrida el
capturador pasivo de descubrir_js.py recibia los dos grids con status
200 -- el navegador real arma su propia sesion con el widget (tokens
CSRF de Vaadin incluidos) y eso no se reproduce desde afuera.

La pagina tiene DOS graficos (Indice y Variacion interanual), cada uno
con su propio grid. Se elige el de niveles por magnitud: mediana > 40
(niveles ~75-120) en vez de variacion porcentual (~-25 a +30).

`series_desde_capturas()` lee las mismas respuestas desde lo que
descubrir_js.py ya archivo en data/raw/descubrimiento/itcr_bcu_js/red/
-- respaldo si la pagina no responde en vivo.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
URL_GUEST = "https://ganges.bcu.gub.uy:8443/eportal/web/guest/tcre"
DIR_CAPTURAS = ROOT / "data" / "raw" / "descubrimiento" / "itcr_bcu_js" / "red"
_MARCA_GRID = "p_p_resource_id=processCommands"

MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def _fecha_de_caption(caption: str) -> str | None:
    """'ene / 2019' -> '2019-01-01'."""
    m = re.match(r"(\w+)\s*/\s*(\d{4})", caption.strip().lower())
    if not m:
        return None
    mes = MESES.get(m.group(1)[:3])
    if mes is None:
        return None
    return f"{int(m.group(2)):04d}-{mes:02d}-01"


def _series_del_grid(resultado: dict) -> dict[str, pd.Series]:
    grid = resultado["queryCommandsResult"]["queryCommandResult"][0]["grid"]["grid"]
    columnas = {c["@name"]: c["@label0"] for c in grid["columns"] if c["@member"] == "false"}
    fechas, valores = [], {nombre: [] for nombre in columnas.values()}
    for fila in grid["rows"]:
        fecha = _fecha_de_caption(fila["element0"]["Caption"])
        if fecha is None:
            continue
        fechas.append(fecha)
        for clave, nombre in columnas.items():
            valores[nombre].append(float(fila[clave]["Value"]))
    idx = pd.to_datetime(fechas)
    return {nombre: pd.Series(vals, index=idx).sort_index() for nombre, vals in valores.items()}


def elegir_niveles(grids: list[dict]) -> dict[str, pd.Series]:
    """De los grids capturados, el de niveles del indice (no el de variacion)."""
    for g in grids:
        try:
            series_por_nombre = _series_del_grid(g)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        medianas = [s.abs().median() for s in series_por_nombre.values()]
        if medianas and min(medianas) > 40:
            return series_por_nombre
    raise RuntimeError(f"ningun grid con cara de niveles entre {len(grids)} capturados")


def series(timeout_ms: int = 60_000, espera_grids_s: int = 25) -> dict[str, pd.Series]:
    """{'TCRE - Global': serie, 'TCRE - Extrarregional': serie, 'TCRE - Regional': serie}."""
    from playwright.sync_api import sync_playwright  # import diferido: pesado, solo hace falta aca

    grids: list[dict] = []

    def _on_response(resp):                               # noqa: ANN001
        if _MARCA_GRID in resp.url and resp.status == 200:
            try:
                grids.append(resp.json())
            except Exception:                             # noqa: BLE001
                pass

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        pagina.on("response", _on_response)
        try:
            pagina.goto(URL_GUEST, timeout=timeout_ms, wait_until="networkidle")
            limite = time.time() + espera_grids_s
            while len(grids) < 2 and time.time() < limite:
                pagina.wait_for_timeout(500)
        finally:
            navegador.close()
    return elegir_niveles(grids)


def series_desde_capturas(directorio: Path = DIR_CAPTURAS) -> tuple[dict[str, pd.Series], str]:
    """(series, 'YYYY-MM-DD' de la captura) desde la captura archivada mas reciente que sirva."""
    por_fecha: dict[str, list[Path]] = {}
    for p in directorio.glob("*.json"):
        if re.match(r"\d{8}_\d{3}_", p.name):
            por_fecha.setdefault(p.name[:8], []).append(p)
    for fecha in sorted(por_fecha, reverse=True):
        grids = []
        for p in sorted(por_fecha[fecha]):
            try:
                contenido = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except ValueError:
                continue
            if isinstance(contenido, dict) and "queryCommandsResult" in contenido:
                grids.append(contenido)
        try:
            return elegir_niveles(grids), f"{fecha[:4]}-{fecha[4:6]}-{fecha[6:]}"
        except RuntimeError:
            continue
    raise RuntimeError(f"ninguna captura archivada con el grid de niveles en {directorio}")


if __name__ == "__main__":
    for nombre, s in series().items():
        print(f"{nombre}: {len(s)} obs, {s.index.min().date()} .. {s.index.max().date()}")
