"""
ITCR (Indice de Tipo de Cambio Real Efectivo) del BCU: Global,
Extrarregional y Regional -- mensual, base 2017=100.

Hallazgo real del 4-sep-2026: el dato llega por tres llamadas HTTP
encadenadas a un motor BI de terceros ("O3 BI", IdeaSoft):

  1. GET la pagina del guest (`/eportal/web/guest/tcre`) -- trae el id de
     layout (p_l_id) y el id de instancia del portlet O3ViewPortlet.
  2. POST a `/eportal/c/portal/render_portlet` para ESE portlet -- la
     respuesta (un fragmento HTML con JS embebido) trae un "Ticket"
     (token de sesion del motor BI, valido solo para esta sesion HTTP) y
     la "View" (identificador del reporte, ej. 'urn:o3bi:...:a:2005').
  3. POST a la misma URL del portlet con `p_p_resource_id=processCommands`
     y un XML de consulta (`queryCommand`) que usa ese Ticket como
     "password" y esa View -- devuelve el grid real: fecha + TCRE
     Global/Extrarregional/Regional.

INTENTO FALLIDO Y CORREGIDO (4-sep-2026): la primera version de este
modulo hacia el paso 1 con `requests` puro (sin navegador), asumiendo
que el markup con el portlet era HTML estatico del servidor -- fallaba
en produccion con "no se encontro ningun portlet O3ViewPortlet en la
pagina" porque NO lo es: el portlet se inserta en el DOM por una llamada
AJAX que el propio Liferay dispara al cargar (visible en las respuestas
de red capturadas por descubrir_js.py), y un GET plano nunca la ejecuta.
Por eso el paso 1 SI necesita un navegador real (Playwright) -- los
pasos 2 y 3 se hacen con el contexto de pedidos del propio navegador
(`pagina.request`), que ya comparte las cookies de la sesion, en vez de
armar una sesion de `requests` aparte.

El ITCR tiene DOS graficos en la pagina (Indice y Variacion interanual),
cada uno con su propio portlet/Ticket/View -- y trae valores DISTINTOS
(uno el nivel del indice ~75-120, el otro la variacion interanual en
%, ~-25 a +30): comprobado con datos reales, NO alcanza con resolver
cualquiera de los dos porque no hay forma confiable de saber por HTML
cual es cual (el orden de aparicion de los portlets en el markup no se
corresponde con el orden visual de los graficos). Se consultan ambos y
se elige por la magnitud de los valores devueltos (ver series()).

Fragil por diseño: depende de la estructura interna de un widget de
terceros que puede cambiar sin aviso del BCU. Si algo de esto deja de
funcionar, el paso levanta una alerta clara en vez de fallar en
silencio -- no es peor que el estado actual (sin ingestor).
"""

from __future__ import annotations

import re

import pandas as pd

BASE = "https://ganges.bcu.gub.uy:8443"
URL_GUEST = f"{BASE}/eportal/web/guest/tcre"
URL_RENDER_PORTLET = f"{BASE}/eportal/c/portal/render_portlet"

_PATRON_COL_ID = re.compile(r"(_\d+_INSTANCE_\w+__column-\d+)")
_PATRON_PORTLET_ID = re.compile(r'id="p_p_id_(O3ViewPortlet_WAR_o3partsweb_INSTANCE_\w+)_"')
_PATRON_PL_ID = re.compile(r"p_l_id=(\d+)")
_VENTANA_EMPAREJAR = 400  # caracteres entre "layout-column_<col_id>" y el div del portlet
_PATRON_TICKET = re.compile(r'Ticket:"(TK-[a-f0-9-]+)"')
_PATRON_VIEW = re.compile(r"(urn:o3bi:[\w:]+)")

_QUERY_TEMPLATE = (
    "<queryCommands xmlns='http://ns.ideasoft.biz/o3bi/schema/QueryCommands/2011-01' "
    "xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance'>"
    "<queryCommand request='VIEW_QUERY'>"
    "<ViewQuery forceGridViews='true' swapAxis='false' returnDates='true' "
    "xmlns='http://ns.ideasoft.biz/o3bi/schema/ViewQuery/2011-01'>"
    "<View>{view}</View>"
    "<LabelsMode><ColumnsLabelMode>KEY</ColumnsLabelMode>"
    "<DimensionMembersLabelMode>LABEL</DimensionMembersLabelMode></LabelsMode>"
    "<AdditionalAttributes includeAllAttributes='true'></AdditionalAttributes>"
    "</ViewQuery>"
    "<dataFilters><dataFilter type='CALCULATED'><calculatedData>false</calculatedData>"
    "<notCalculatedData>false</notCalculatedData></dataFilter></dataFilters>"
    "</queryCommand>"
    "<queryCommand request='QUERY_RESULT_CONTEXT' />"
    "</queryCommands>")

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


def _pares_portlet_col(html_guest: str) -> list[dict]:
    """
    Cada (portlet_id, col_id) real de un grafico O3ViewPortlet -- hay dos
    en la pagina (Indice y Variacion) y no se puede saber cual es cual
    solo por el orden de aparicion en el HTML (confirmado con datos
    reales). Se emparejan por proximidad: el div del portlet aparece a
    pocos caracteres del id de su columna contenedora.
    """
    pl_ids = _PATRON_PL_ID.findall(html_guest)
    if not pl_ids:
        raise RuntimeError("no se encontro p_l_id en la pagina del ITCR")

    cols_3 = [(m.start(), m.group(1)) for m in _PATRON_COL_ID.finditer(html_guest)
             if m.group(1).endswith("__column-3")]
    pares = []
    for pos_col, col_id in cols_3:
        ventana = html_guest[pos_col:pos_col + _VENTANA_EMPAREJAR]
        m_portlet = _PATRON_PORTLET_ID.search(ventana)
        if m_portlet:
            pares.append({"col_id": col_id, "portlet_id": m_portlet.group(1), "p_l_id": pl_ids[0]})
    if not pares:
        raise RuntimeError("no se encontro ningun portlet O3ViewPortlet en la pagina del ITCR")
    return pares


def _obtener_ticket_y_view(pagina, cfg: dict, timeout_ms: int) -> tuple[str, str]:
    """`pagina`: Playwright Page ya navegada al guest -- se usa pagina.request
    (comparte cookies con la pagina) en vez de una sesion de requests aparte."""
    params = {
        "p_l_id": cfg["p_l_id"], "p_p_id": cfg["portlet_id"], "p_p_lifecycle": "0",
        "p_t_lifecycle": "0", "p_p_state": "normal", "p_p_mode": "view",
        "p_p_col_id": cfg["col_id"], "p_p_col_pos": "0", "p_p_col_count": "1",
        "p_p_isolated": "1", "currentURL": "/eportal/web/guest/tcre",
    }
    r = pagina.request.post(URL_RENDER_PORTLET, params=params, timeout=timeout_ms)
    if not r.ok:
        raise RuntimeError(f"render_portlet respondio {r.status}")
    texto = r.text()
    m_ticket = _PATRON_TICKET.search(texto)
    m_view = _PATRON_VIEW.search(texto)
    if not m_ticket or not m_view:
        raise RuntimeError("no se encontro Ticket/View en la respuesta de render_portlet")
    return m_ticket.group(1), m_view.group(1)


def _consultar_grid(pagina, cfg: dict, ticket: str, view: str, timeout_ms: int) -> dict:
    params = {
        "p_p_id": cfg["portlet_id"], "p_p_lifecycle": "2", "p_p_state": "normal",
        "p_p_mode": "view", "p_p_resource_id": "processCommands",
        "p_p_cacheability": "cacheLevelPage", "p_p_col_id": cfg["col_id"],
        "p_p_col_count": "1",
        f"_{cfg['portlet_id']}_resource-name": "processCommands",
    }
    # 'form' (no 'data'): x-www-form-urlencoded, igual que el POST real del
    # navegador -- 'data' en Playwright serializa a JSON por defecto.
    formulario = {
        "senchapost": "true",
        "queryCommand": _QUERY_TEMPLATE.format(view=view),
        "username": "guest", "password": ticket,
        "x-rest-locale": "en_US", "typeAccept": "application/is-grid+json", "export": "false",
    }
    r = pagina.request.post(URL_GUEST, params=params, form=formulario, timeout=timeout_ms)
    if not r.ok:
        raise RuntimeError(f"processCommands respondio {r.status}")
    return r.json()


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


def series(timeout_ms: int = 60_000) -> dict[str, pd.Series]:
    """{'TCRE - Global': serie, 'TCRE - Extrarregional': serie, 'TCRE - Regional': serie}.

    Los NIVELES del indice (base 2017=100) -- la pagina tiene dos
    graficos (Indice y Variacion) y no hay forma confiable de saber por
    HTML cual portlet es cual (ver _pares_portlet_col), asi que se
    consultan todos y se elige el resultado cuyos valores tienen cara de
    nivel (mediana > 40) en vez de variacion porcentual (tipicamente
    entre -30 y +30).

    El paso 1 (encontrar los portlets) necesita un navegador real -- el
    portlet se inserta en el DOM por una llamada AJAX que Liferay dispara
    al cargar, un GET plano nunca la ejecuta (ver docstring del modulo).
    Los pasos 2 y 3 reusan el contexto de pedidos de esa misma pagina.
    """
    from playwright.sync_api import sync_playwright  # import diferido: pesado, solo hace falta aca

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        try:
            pagina.goto(URL_GUEST, timeout=timeout_ms, wait_until="networkidle")
            pagina.wait_for_timeout(3000)  # margen para el AJAX que inserta los portlets
            html_guest = pagina.content()
            pares = _pares_portlet_col(html_guest)

            candidatos: list[dict[str, pd.Series]] = []
            errores = []
            for cfg in pares:
                try:
                    ticket, view = _obtener_ticket_y_view(pagina, cfg, timeout_ms)
                    resultado = _consultar_grid(pagina, cfg, ticket, view, timeout_ms)
                    candidatos.append(_series_del_grid(resultado))
                except Exception as e:                            # noqa: BLE001
                    errores.append(f"{cfg['portlet_id']}: {type(e).__name__}: {e}")
        finally:
            navegador.close()

    for series_por_nombre in candidatos:
        medianas = [s.abs().median() for s in series_por_nombre.values()]
        if medianas and min(medianas) > 40:
            return series_por_nombre

    detalle = "; ".join(errores) if errores else "ningun candidato parecia niveles (todos < 40)"
    raise RuntimeError(f"no se pudo identificar el grafico de Indice del ITCR ({detalle})")


if __name__ == "__main__":
    for nombre, s in series().items():
        print(f"{nombre}: {len(s)} obs, {s.index.min().date()} .. {s.index.max().date()}")
