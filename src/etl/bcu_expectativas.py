"""
Encuesta de Expectativas Economicas del BCU -- mediana de inflacion
esperada a 12 y 24 meses.

Hallazgo real del 3-sep-2026: la pagina clasica (SharePoint) SI trae el
dato en HTML estatico, via requests.get() -- no hace falta navegador
headless para esto. Lo que la sesion 1 marco como "bloqueado" eran otras
URLs candidatas de esta misma clave que devolvian 404 (Expectativas-
Economicas.aspx, Encuesta-de-Expectativas-Economicas.aspx); esta URL
especifica (Expectativas-de-los-agentes.aspx) SI responde y trae, dentro
de un bloque <script> de un widget "BCUSliderWebPart", un JSON con el
resumen de la encuesta como texto narrativo (no una tabla limpia):

    "-La mediana de expectativas de inflacion a 24 meses en agosto se
    mantiene en la meta de inflacion del BCU de 4.5%.
    ...
    -La mediana de expectativas de inflacion a 12 meses se mantiene en
    4.5%."

Se extrae por regex sobre ese texto. Es SOLO el valor vigente al momento
de la consulta (como el TPM via IPOM, ver bcu_ipom.py) -- no la serie
historica completa. Corriendo esto cada mes se va construyendo una serie
real hacia adelante; el historico previo no esta disponible por esta via
(el listado de encuestas anteriores esta en una tabla cargada por AJAX,
sin resolver todavia -- ver docs/manifest_fuentes.md).

La seccion "Expectativas del Mercado Financiero" (TC, TPM esperada) de
la misma pagina NO trae valores en HTML estatico -- es un listado de
documentos (AJAX), no un resumen narrativo como el de inflacion. Ese
dato sigue pendiente.
"""

from __future__ import annotations

import json
import re

from src.etl import http_client

URL = "https://www.bcu.gub.uy/Politica-Economica-y-Mercados/Paginas/Expectativas-de-los-agentes.aspx"

_PATRON_BLOB = re.compile(r"bcuSliderWebPartRender\.render\(`(\{.*?\})`\s*,\s*\"analistas\"\)", re.S)
_PATRON_MEDIANA = re.compile(
    r"mediana de expectativas de inflaci[oó]n a (\d+) meses[^.]*?(\d+[.,]\d+)\s*%\.", re.I)

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def descargar(timeout: int = 60) -> str:
    r = http_client.get(URL, timeout=timeout)
    return r.text


def parsear(html: str) -> dict:
    """
    Devuelve {"12": valor, "24": valor, "mes_referencia": "YYYY-MM-01"} con
    los horizontes encontrados (puede faltar alguno si el BCU cambia la
    redaccion). mes_referencia sale de "complementaryText" (ej. "Agosto
    2026"), aproximado igual que fecha_ref del TPM via IPOM.
    """
    m_blob = _PATRON_BLOB.search(html)
    if m_blob is None:
        return {}
    datos = json.loads(m_blob.group(1))
    item = datos["items"][0]
    descripcion = item["description"]

    resultado: dict = {}
    for horizonte, valor in _PATRON_MEDIANA.findall(descripcion):
        resultado[horizonte] = float(valor.replace(",", "."))

    m_mes = re.match(r"(\w+)\s+(\d{4})", item.get("complementaryText", ""))
    if m_mes:
        nombre_mes, anio = m_mes.group(1).lower(), int(m_mes.group(2))
        mes = MESES.get(nombre_mes)
        if mes:
            resultado["mes_referencia"] = f"{anio:04d}-{mes:02d}-01"
    return resultado


def valor_vigente() -> dict:
    return parsear(descargar())


if __name__ == "__main__":
    print(valor_vigente())
