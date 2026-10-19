"""
Tasa de Politica Monetaria (TPM) desde el listado de comunicados del
Comite de Politica Monetaria del BCU.

Hallazgo del 19-oct-2026: la pagina clasica (SharePoint)
`Comite-de-Politica-Monetaria.aspx` trae en HTML ESTATICO una tabla con
todos los comunicados desde ene-2022 (fecha + titulo + link al detalle),
y el titulo casi siempre dice la tasa resultante ("...reduce la tasa de
interes en 75 puntos basicos hasta 5,75%"). Ya estaba archivada por
descubrir_fuentes.py desde el 3-sep-2026; nadie la habia parseado.
Reemplaza a la extraccion del IPOM (un punto por trimestre, con fecha
aproximada que llego a asignar 5,75% a ene-2026 cuando la tasa vigente a
fin de ese mes era 6,5%).

Si un titulo no trae la tasa (ej. 17-may-2022, "anuncia el ingreso a la
fase contractiva"), se busca en la pagina de detalle del comunicado; si
tampoco aparece, ese tramo queda sin dato en vez de arrastrar la tasa
anterior.

Serie mensual: TPM vigente al cierre de cada mes (ultima decision con
fecha <= fin de mes), desde el mes de la primera decision listada hasta
el mes de consulta.
"""

from __future__ import annotations

import datetime as dt
import html as html_lib
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
URL = "https://www.bcu.gub.uy/Politica-Economica-y-Mercados/Paginas/Comite-de-Politica-Monetaria.aspx"
BASE = "https://www.bcu.gub.uy"
DIR_ARCHIVO = ROOT / "data" / "raw" / "descubrimiento" / "tpm_historica_bcu"

_PATRON_FILA = re.compile(r'<tr>\s*<td data-order="\d+">(.*?)</tr>', re.S)
_PATRON_TITULO = re.compile(r'<h6 class="bcu-h">\s*(.*?)\s*</h6>', re.S)
_PATRON_FECHA = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s*</td>\s*$")
_PATRON_HREF = re.compile(r'href="([^"]+)"')
# "en 5,75%", "hasta 5,75%", "a 7,5%" -- excluye "meta de 4,5%"
_PATRON_TASA = re.compile(r"\b(?:en|a|hasta)\s+(\d{1,2}(?:[.,]\d{1,2})?)\s*%")


def _texto(fragmento: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def tasa_en_texto(texto: str) -> float | None:
    m = _PATRON_TASA.search(texto)
    return float(m.group(1).replace(",", ".")) if m else None


def decisiones(html: str) -> pd.DataFrame:
    """Una fila por comunicado: fecha, tasa (NaN si el titulo no la dice), titulo, url."""
    filas = []
    for f in _PATRON_FILA.findall(html):
        m_tit, m_fecha = _PATRON_TITULO.search(f), _PATRON_FECHA.search(f.strip())
        if not m_tit or not m_fecha:
            continue
        titulo = _texto(m_tit.group(1))
        d, m, a = m_fecha.groups()
        m_href = _PATRON_HREF.search(f)
        filas.append({
            "fecha": pd.Timestamp(int(a), int(m), int(d)),
            "tasa": tasa_en_texto(titulo),
            "titulo": titulo,
            "url": (BASE + m_href.group(1)) if m_href and m_href.group(1).startswith("/") else None,
        })
    if not filas:
        raise RuntimeError("no se encontro ninguna fila de comunicados en la pagina del Comite")
    return pd.DataFrame(filas).sort_values("fecha").reset_index(drop=True)


def completar_desde_detalle(dec: pd.DataFrame) -> pd.DataFrame:
    """Para comunicados sin tasa en el titulo, la busca en la pagina de detalle (requiere red)."""
    from src.etl import http_client

    dec = dec.copy()
    for i in dec.index[dec["tasa"].isna() & dec["url"].notna()]:
        try:
            cuerpo = _texto(http_client.get(dec.at[i, "url"], timeout=60).text)
        except Exception as e:                            # noqa: BLE001
            print(f"[tpm] detalle {dec.at[i, 'url']}: {e}")
            continue
        m = re.search(r"(?:TPM|[Tt]asa de [Pp]ol[ií]tica [Mm]onetaria|tasa de inter[eé]s)[^.]{0,160}", cuerpo)
        dec.at[i, "tasa"] = tasa_en_texto(m.group(0)) if m else None
    return dec


def serie_mensual(dec: pd.DataFrame, hasta: dt.date) -> pd.Series:
    """TPM vigente al cierre de cada mes (o a `hasta` para el mes en curso)."""
    meses = pd.date_range(dec["fecha"].min().to_period("M").to_timestamp(),
                          pd.Timestamp(hasta).to_period("M").to_timestamp(), freq="MS")
    valores = {}
    for mes in meses:
        corte = min(mes + pd.offsets.MonthEnd(0), pd.Timestamp(hasta))
        previas = dec[dec["fecha"] <= corte]
        if len(previas):
            valores[mes] = previas["tasa"].iloc[-1]
    return pd.Series(valores, dtype=float).dropna()


def obtener() -> tuple[pd.Series, str, str]:
    """(serie mensual, vintage 'YYYY-MM-DD', descripcion de la fuente). En vivo; si falla, archivo."""
    from src.etl import http_client

    try:
        dec = completar_desde_detalle(decisiones(http_client.get(URL, timeout=120).text))
        hoy = dt.date.today()
        return serie_mensual(dec, hoy), hoy.isoformat(), "BCU, comunicados del Comite de Politica Monetaria"
    except Exception as e:                                # noqa: BLE001
        archivos = sorted(DIR_ARCHIVO.glob("*_Comite-de-Politica-Monetaria.aspx"))
        if not archivos:
            raise RuntimeError(f"pagina del Comite inaccesible ({e}) y sin archivo local") from e
        ruta = archivos[-1]
        fecha = dt.date(int(ruta.name[:4]), int(ruta.name[4:6]), int(ruta.name[6:8]))
        dec = decisiones(ruta.read_text(encoding="utf-8", errors="replace"))
        return (serie_mensual(dec, fecha), fecha.isoformat(),
                f"BCU, comunicados del Comite de Politica Monetaria (pagina archivada {ruta.name})")


if __name__ == "__main__":
    s, vintage, fuente = obtener()
    print(f"{fuente} -- vintage {vintage}\n{s.to_string()}")
