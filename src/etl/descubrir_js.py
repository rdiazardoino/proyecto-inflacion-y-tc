"""
Descubrimiento de fuentes que requieren renderizado JavaScript: Encuesta de
Expectativas Economicas y ITCR del BCU (ver docs/manifest_fuentes.md,
hallazgo del 3-sep-2026 -- ninguna URL alternativa resuelve esto con
requests.get(), las tres plataformas nuevas del BCU exigen ejecutar JS
para mostrar el dato).

Corre en GitHub Actions con Chromium instalado via `playwright install`
(ver .github/workflows/etl.yml). El sandbox de analisis no tiene salida a
bcu.gub.uy, asi que esto no se pudo probar contra las paginas reales antes
de commitear -- se prueba aca la mecanica (Playwright funciona en este
sandbox) y se calibra el parseo real cuando GitHub Actions archive las
primeras capturas.

Por pagina se archiva:
  1. el HTML ya renderizado (para calibrar selectores despues, sin red),
  2. cualquier planilla enlazada que solo aparece en el DOM post-render,
  3. las tablas HTML visibles, volcadas a CSV via pandas.read_html --
     frecuente en portales Liferay que muestran el dato en una tabla en
     vez de ofrecer una planilla descargable.

No asume la estructura final del dato: eso se calibra en una iteracion
futura contra los archivos reales.
"""

from __future__ import annotations

import datetime as dt
import io
import re
from pathlib import Path
from urllib.parse import unquote

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "descubrimiento"

EXT_PLANILLA = (".xls", ".xlsx", ".csv", ".ods")

# Las mismas paginas ya identificadas en descubrir_fuentes.py como
# estructuralmente bloqueadas para requests.get(); aca se abren con un
# navegador real.
FUENTES_JS: dict[str, str] = {
    "expectativas_bcu_js": "https://subsitio.bcu.gub.uy/politica-monetaria/",
    "itcr_bcu_js": "https://ganges.bcu.gub.uy:8443/eportal/web/guest/tcre",
    # IMAE: URL sin confirmar (ver descubrir_fuentes.py). Se prueba tambien
    # aca por si vive en el mismo subsitio SPA que TPM/expectativas -- el
    # candidato clasico .aspx de descubrir_fuentes.py cubre la otra hipotesis.
    "imae_bcu_js": "https://subsitio.bcu.gub.uy/estadisticas/",
}


def _nombre_seguro(url: str) -> str:
    nombre = unquote(url.split("/")[-1].split("?")[0]) or "index.html"
    return re.sub(r"[^\w.\-]", "_", nombre)[:120]


def _archivar_js(clave: str, url: str, timeout_ms: int = 45_000) -> dict:
    """Renderiza `url` con Chromium headless y archiva HTML + planillas + tablas."""
    from playwright.sync_api import sync_playwright  # import diferido: pesado, solo hace falta aca

    subdir = RAW / clave
    subdir.mkdir(parents=True, exist_ok=True)
    resumen = {"clave": clave, "html": None, "planillas": 0, "tablas": 0}

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        try:
            pagina.goto(url, timeout=timeout_ms, wait_until="networkidle")
        except Exception as e:                            # noqa: BLE001
            print(f"[desc-js] {clave}: fallo goto {url}: {e}")
            navegador.close()
            return resumen

        # margen extra para AJAX lento (el eportal Liferay es lento en frio)
        pagina.wait_for_timeout(3000)

        html = pagina.content()
        destino_html = subdir / f"{dt.date.today():%Y%m%d}_render.html"
        destino_html.write_text(html, encoding="utf-8")
        resumen["html"] = str(destino_html)

        # enlaces a planillas visibles DESPUES del render -- antes del JS
        # estos <a> no existen en el DOM, por eso requests.get() no los ve.
        enlaces = pagina.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        planillas = [u for u in dict.fromkeys(enlaces)
                     if u.lower().split("?")[0].endswith(EXT_PLANILLA)]
        for u in planillas[:12]:
            try:
                resp = pagina.request.get(u, timeout=timeout_ms)
                destino = subdir / f"{dt.date.today():%Y%m%d}_{_nombre_seguro(u)}"
                destino.write_bytes(resp.body())
                resumen["planillas"] += 1
            except Exception as e:                        # noqa: BLE001
                print(f"[desc-js] {clave}: fallo descarga {u}: {e}")

        # tablas HTML renderizadas: el dato puede vivir directo en una
        # tabla del portal (comun en Liferay) y no en una planilla aparte
        try:
            # pandas >=2.1 dejo de aceptar un string HTML literal (lo trata
            # como ruta/URL); hay que envolverlo en StringIO. Bug real
            # encontrado probando este modulo contra una pagina de prueba
            # local antes de commitear -- read_html(html) tira
            # FileNotFoundError con el HTML entero como "nombre de archivo".
            tablas = pd.read_html(io.StringIO(html))
            for i, t in enumerate(tablas):
                if t.shape[0] < 2:
                    continue
                destino = subdir / f"{dt.date.today():%Y%m%d}_tabla_{i}.csv"
                t.to_csv(destino, index=False)
                resumen["tablas"] += 1
        except ValueError:
            pass  # sin tablas parseables por pandas.read_html

        navegador.close()

    print(f"[desc-js] {clave}: html={'OK' if resumen['html'] else 'FALLO'}, "
          f"planillas={resumen['planillas']}, tablas={resumen['tablas']}")
    return resumen


def descubrir_todo_js() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    resultados = []
    for clave, url in FUENTES_JS.items():
        try:
            resultados.append(_archivar_js(clave, url))
        except Exception as e:                            # noqa: BLE001
            print(f"[desc-js] {clave}: fallo total: {e}")
            resultados.append({"clave": clave, "html": None, "planillas": 0, "tablas": 0})
    return resultados


if __name__ == "__main__":
    descubrir_todo_js()
