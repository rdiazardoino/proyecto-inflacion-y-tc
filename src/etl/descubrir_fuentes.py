"""
Descubrimiento de fuentes pendientes de ingesta (prioridad A sin ingestor).

Mismo patron que resolvio el IPC: este modulo corre en GitHub Actions (que
tiene internet), archiva las paginas y planillas crudas en
data/raw/descubrimiento/ (versionadas), y con esos archivos reales se
calibran los parsers en el entorno de analisis, que no tiene salida a
estos hosts.

Fuentes y donde viven:
  expectativas_bcu  Encuesta de Expectativas Economicas del BCU (mediana de
                    inflacion 12/24m y TC). Pagina de la encuesta + XLS.
  itcr_bcu          Indice de Tipo de Cambio Real Efectivo del BCU (global,
                    extrarregional, bilaterales). XLS mensual.
  tpm_bcu           Tasa de politica monetaria: pagina de gestion de la
                    politica monetaria y comunicados del Copom.
  ims_ine           Indice Medio de Salarios del INE (planillas como el IPC).
  combustibles_miem Precios de combustibles (MIEM/ANCAP), por evento.

Cada clave lista URLs candidatas (los sitios .gub.uy reorganizan sin
redirect). Se archiva el HTML de la primera que responda y hasta
MAX_PLANILLAS planillas enlazadas.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from urllib.parse import urljoin, unquote

from bs4 import BeautifulSoup

from src.etl import http_client

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "descubrimiento"

MAX_PLANILLAS = 12
MAX_BYTES = 15_000_000

EXT_PLANILLA = (".xls", ".xlsx", ".csv", ".ods")

# URLs verificadas por busqueda web el 3-sep-2026. Nota operativa: el BCU
# saca sus servicios web de noche (connect timeout ~22:30 Montevideo del
# 2-sep); correr el descubrimiento en horario habil de Uruguay.
FUENTES: dict[str, list[str]] = {
    "expectativas_bcu": [
        "https://www.bcu.gub.uy/Estadisticas-e-Indicadores/Paginas/Expectativas-Economicas.aspx",
    ],
    "itcr_bcu": [
        "https://www.bcu.gub.uy/Estadisticas-e-Indicadores/Paginas/Tipo-de-cambio-real-efectivo.aspx",
    ],
    "tpm_bcu": [
        # la TPM se anuncia por comunicado del Copom; estas paginas enlazan
        # los comunicados y el IPOM (que trae la serie)
        "https://www.bcu.gub.uy/Politica-Economica-y-Mercados/Paginas/default.aspx",
        "https://www.bcu.gub.uy/Politica-Economica-y-Mercados/Paginas/Comite-de-Politica-Monetaria.aspx",
    ],
    "ims_ine": [
        "https://www.gub.uy/instituto-nacional-estadistica/datos-y-estadisticas/estadisticas/series-historicas-indice-medio-salarios-ims-base-julio-2008100",
        "https://www.ine.gub.uy/ims-indice-medio-de-salarios",
        "https://www3.ine.gub.uy/rraa/ims.html",
    ],
    "combustibles_miem": [
        "https://www.gub.uy/unidad-reguladora-servicios-energia-agua/comunicacion/publicaciones/precios-venta-publico-referencia-para-gasolinas-gasoil-50-s-pmit-2",
        "https://www.gub.uy/ministerio-industria-energia-mineria/tematica/tarifas",
        "https://www.ine.gub.uy/precios-de-servicios-publicos",
    ],
}

# Que enlaces valen la pena ademas de planillas, por fuente
PATRON_INTERES = re.compile(
    r"expectativa|itcr|tcr|tipo.?de.?cambio.?real|salario|ims|copom|"
    r"politica.?monetaria|comunicado|combustible|precio", re.IGNORECASE)


def _nombre_seguro(url: str) -> str:
    nombre = unquote(url.split("/")[-1].split("?")[0]) or "index.html"
    return re.sub(r"[^\w.\-]", "_", nombre)[:120]


def _archivar(url: str, subdir: Path) -> Path | None:
    subdir.mkdir(parents=True, exist_ok=True)
    destino = subdir / f"{dt.date.today():%Y%m%d}_{_nombre_seguro(url)}"
    if destino.exists():
        return destino
    try:
        r = http_client.get(url, timeout=120)
        contenido = r.content
        if len(contenido) > MAX_BYTES:
            print(f"[desc] {url}: {len(contenido)} bytes, supera el tope; se omite")
            return None
        destino.write_bytes(contenido)
        return destino
    except Exception as e:                            # noqa: BLE001
        print(f"[desc] fallo {url}: {e}")
        return None


def descubrir_fuente(clave: str, candidatas: list[str]) -> dict:
    """Archiva la pagina y sus planillas. Devuelve resumen para el log."""
    subdir = RAW / clave
    resumen = {"clave": clave, "pagina": None, "planillas": 0, "enlaces_interes": []}

    for url in candidatas:
        ruta = _archivar(url, subdir)
        if ruta is None:
            continue
        resumen["pagina"] = url
        try:
            sopa = BeautifulSoup(ruta.read_bytes(), "html.parser")
        except Exception as e:                        # noqa: BLE001
            print(f"[desc] {clave}: HTML no parseable: {e}")
            break

        enlaces = [urljoin(url, a["href"]) for a in sopa.find_all("a", href=True)]
        planillas = [u for u in dict.fromkeys(enlaces)
                     if u.lower().split("?")[0].endswith(EXT_PLANILLA)]
        interes = [u for u in dict.fromkeys(enlaces)
                   if PATRON_INTERES.search(unquote(u)) and u not in planillas]
        resumen["enlaces_interes"] = interes[:25]

        for u in planillas[:MAX_PLANILLAS]:
            if _archivar(u, subdir):
                resumen["planillas"] += 1
        break  # primera pagina que respondio alcanza

    print(f"[desc] {clave}: pagina={'OK' if resumen['pagina'] else 'FALLO'}, "
          f"planillas={resumen['planillas']}, "
          f"enlaces de interes={len(resumen['enlaces_interes'])}")
    for u in resumen["enlaces_interes"][:10]:
        print(f"        - {u}")
    return resumen


def descubrir_todo() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    return [descubrir_fuente(clave, urls) for clave, urls in FUENTES.items()]


if __name__ == "__main__":
    descubrir_todo()
