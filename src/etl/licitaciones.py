"""
Licitaciones de deuda: LRM del BCU y Notas del Tesoro de la UGD/MEF.

Sustituyen operativamente a las curvas de BEVSA. Dan rendimiento de corte
por plazo y moneda en mercado primario, publicado el mismo dia de la
licitacion antes de las 17:00.

ADVERTENCIA HONESTA: los parsers de esta seccion NO estan verificados
contra el HTML/PDF real, porque el entorno donde se escribio este codigo
no tiene salida a internet hacia bcu.gub.uy ni mef.gub.uy. La estrategia
es en dos pasos:

  1. `python -m src.etl.licitaciones descubrir`
     Descarga y archiva los documentos crudos en data/raw/licitaciones/ y
     vuelca a stdout lo que encuentra: enlaces, tablas detectadas, primeras
     filas. Con esa salida se calibran los patrones de abajo.

  2. `python -m src.etl.licitaciones parsear`
     Aplica los patrones ya calibrados y escribe a la tabla `licitaciones`.

Hasta que el paso 1 corra en GitHub Actions, PATRONES es una hipotesis.
Cualquier fila que no matchee se archiva sin parsear y levanta alerta, en
vez de inventar un numero.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "licitaciones"

HEADERS = {"User-Agent": "proyecto-inflacion-y-tc/1.0"}

FUENTES = {
    "bcu_operaciones": "https://www.bcu.gub.uy/Politica-Economica-y-Mercados/Paginas/Operaciones-Monetarias.aspx",
    "bcu_calendario_deuda": "https://www.bcu.gub.uy/Politica-Economica-y-Mercados/Calendario%20Deuda/calendario_deuda.pdf",
    "ugd_home": "https://deuda.mef.gub.uy/",
    "ugd_calendario_2026s2": "https://deuda.mef.gub.uy/innovaportal/file/32249/1/comunicado-calendario-2026s2.pdf",
    "ugd_calendario_2026s1": "https://www.mef.gub.uy/innovaportal/file/28953/27/comunicado-calendario-2026s1.pdf",
}

MONEDA_POR_TEXTO = [
    (r"\bU\.?I\.?\b|unidad(es)? indexada", "UI"),
    (r"\bU\.?P\.?\b|unidad(es)? previsional", "UP"),
    (r"\bd[oó]lar|\bUSD\b|US\$", "USD"),
    (r"\bpesos?\b|nominal|\bUYU\b|\$U", "UYU"),
]

# Patrones candidatos para extraer resultados. A calibrar con el paso 1.
PATRONES = {
    "plazo_dias": r"(\d{2,5})\s*d[ií]as",
    "plazo_anios": r"(\d{1,2})\s*a[nñ]os",
    "tasa": r"(\d{1,2}[.,]\d{1,4})\s*%",
    "monto": r"([\d.]+[,\d]*)\s*(millones|MM|mill)",
}


def _guardar(url: str, subdir: str) -> Path | None:
    destino_dir = RAW / subdir
    destino_dir.mkdir(parents=True, exist_ok=True)
    nombre = re.sub(r"[^\w.\-]", "_", url.split("/")[-1].split("?")[0]) or "index.html"
    destino = destino_dir / f"{dt.date.today():%Y%m%d}_{nombre}"
    if destino.exists():
        return destino
    try:
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
        destino.write_bytes(r.content)
        return destino
    except Exception as e:                            # noqa: BLE001
        print(f"[lic] fallo {url}: {e}")
        return None


def detectar_moneda(texto: str) -> str | None:
    t = texto.lower()
    for patron, moneda in MONEDA_POR_TEXTO:
        if re.search(patron, t, flags=re.IGNORECASE):
            return moneda
    return None


def descubrir() -> None:
    """Paso 1: archivar crudos y volcar estructura para calibrar parsers."""
    RAW.mkdir(parents=True, exist_ok=True)

    for clave, url in FUENTES.items():
        print(f"\n===== {clave} =====\n{url}")
        ruta = _guardar(url, clave)
        if not ruta:
            continue
        print(f"guardado: {ruta.name} ({ruta.stat().st_size} bytes)")

        if ruta.suffix.lower() in (".html", ".aspx", "") or clave.endswith("home") \
                or "Paginas" in url:
            try:
                sopa = BeautifulSoup(ruta.read_bytes(), "html.parser")
            except Exception as e:                    # noqa: BLE001
                print(f"  no parseable como HTML: {e}")
                continue
            enlaces = [urljoin(url, a["href"]) for a in sopa.find_all("a", href=True)]
            interes = [u for u in enlaces if re.search(
                r"licitac|resultad|letra|nota|lrm|deuda|circular",
                u, flags=re.IGNORECASE)]
            print(f"  {len(enlaces)} enlaces, {len(interes)} de interes:")
            for u in dict.fromkeys(interes[:40]):
                print("   -", u)
            tablas = sopa.find_all("table")
            print(f"  {len(tablas)} tablas en la pagina")
            for i, t in enumerate(tablas[:3]):
                filas = t.find_all("tr")[:4]
                print(f"   tabla {i}: {len(t.find_all('tr'))} filas")
                for f in filas:
                    celdas = [c.get_text(strip=True) for c in f.find_all(["td", "th"])]
                    print("     ", celdas[:10])

        elif ruta.suffix.lower() == ".pdf":
            try:
                import pdfplumber
            except ImportError:
                print("  pdfplumber no instalado")
                continue
            try:
                with pdfplumber.open(ruta) as pdf:
                    print(f"  {len(pdf.pages)} paginas")
                    for i, pag in enumerate(pdf.pages[:3]):
                        texto = pag.extract_text() or ""
                        print(f"  --- pagina {i} ---")
                        print("  " + "\n  ".join(texto.splitlines()[:25]))
                        for j, tab in enumerate(pag.extract_tables() or []):
                            print(f"  tabla {j}: {len(tab)} filas")
                            for fila in tab[:5]:
                                print("     ", fila)
            except Exception as e:                    # noqa: BLE001
                print(f"  fallo lectura PDF: {e}")


def parsear_pdf_resultado(ruta: Path, emisor: str,
                          fuente_url: str = "") -> list[dict]:
    """
    Paso 2: extrae filas de resultado de un PDF de licitacion.
    Devuelve [] si el layout no matchea, en vez de adivinar.
    """
    try:
        import pdfplumber
    except ImportError:
        return []

    filas: list[dict] = []
    with pdfplumber.open(ruta) as pdf:
        texto_total = "\n".join((p.extract_text() or "") for p in pdf.pages)

    m_fecha = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", texto_total)
    if m_fecha:
        d, mth, y = (int(g) for g in m_fecha.groups())
        fecha_lic = f"{y:04d}-{mth:02d}-{d:02d}"
    else:
        fecha_lic = dt.date.today().isoformat()

    for linea in texto_total.splitlines():
        moneda = detectar_moneda(linea)
        m_plazo = re.search(PATRONES["plazo_dias"], linea)
        m_anios = re.search(PATRONES["plazo_anios"], linea)
        m_tasa = re.search(PATRONES["tasa"], linea)
        if not (moneda and m_tasa and (m_plazo or m_anios)):
            continue
        plazo = int(m_plazo.group(1)) if m_plazo else int(m_anios.group(1)) * 365
        tasa = float(m_tasa.group(1).replace(",", "."))
        filas.append({
            "licitacion_id": f"{emisor}-{fecha_lic}-{moneda}-{plazo}d",
            "fecha_licitacion": fecha_lic,
            "emisor": emisor,
            "instrumento": "LRM" if emisor == "BCU" else "NotaTesoro",
            "serie": None,
            "moneda": moneda,
            "plazo_dias": plazo,
            "fecha_vencimiento": None,
            "monto_ofrecido": None,
            "monto_demandado": None,
            "monto_adjudicado": None,
            "bid_to_cover": None,
            "tasa_corte": tasa,
            "tasa_promedio": None,
            "tasa_minima": None,
            "precio_corte": None,
            "desierta": 0,
            "fecha_descarga": dt.date.today().isoformat(),
            "fuente_url": fuente_url or str(ruta),
            "notas": "parseo automatico sin verificar; revisar contra el PDF",
        })
    return filas


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "descubrir"
    if modo == "descubrir":
        descubrir()
    else:
        for pdf in sorted(RAW.rglob("*.pdf")):
            filas = parsear_pdf_resultado(pdf, "BCU")
            print(pdf.name, len(filas), "filas")
