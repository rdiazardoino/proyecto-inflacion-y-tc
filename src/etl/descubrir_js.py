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
     vez de ofrecer una planilla descargable,
  4. una captura de pantalla full-page y un listado de elementos
     clickeables (texto + posicion) -- el sandbox de analisis no puede
     VER el render real (solo el HTML crudo), asi que para calibrar un
     click en algo que no es un <a href> (un icono de exportar dibujado
     en <canvas>, un menu que requiere hover) hace falta la imagen.

No asume la estructura final del dato: eso se calibra en una iteracion
futura contra los archivos reales.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re
from pathlib import Path
from urllib.parse import unquote

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "descubrimiento"

EXT_PLANILLA = (".xls", ".xlsx", ".csv", ".ods")

# Las mismas paginas ya identificadas en descubrir_fuentes.py como
# estructuralmente bloqueadas para requests.get(); aca se abren con un
# navegador real. `clic_texto`, si esta, es un texto visible a clickear
# DESPUES del primer render -- para paginas SPA que enrutan por JS (sin
# <a href> real) en vez de link estatico: confirmado el 3-sep-2026 que
# subsitio.bcu.gub.uy/estadisticas/ es asi (el render trae el texto "IMAE"
# en un blob de datos de la app, no un href navegable).
FUENTES_JS: dict[str, dict] = {
    "expectativas_bcu_js": {"url": "https://subsitio.bcu.gub.uy/politica-monetaria/"},
    # confirmado por screenshot real el 4-sep-2026: el grafico SI trae la
    # serie (TCRE Global/Extrarregional/Regional), pero el icono de
    # exportar es un dibujo sobre <canvas> sin hook de DOM -- coordenadas
    # calibradas contra ese screenshot (esquina superior izquierda del
    # primer grafico). Paso 1: solo confirmar que el click abre un menu
    # real (DOM) antes de intentar navegar el submenu "Herramientas".
    "itcr_bcu_js": {"url": "https://ganges.bcu.gub.uy:8443/eportal/web/guest/tcre",
                    "clic_coordenadas": (478, 160)},
    "imae_bcu_js": {"url": "https://subsitio.bcu.gub.uy/estadisticas/", "clic_texto": "IMAE"},
}


def _nombre_seguro(url: str) -> str:
    nombre = unquote(url.split("/")[-1].split("?")[0]) or "index.html"
    return re.sub(r"[^\w.\-]", "_", nombre)[:120]


def _archivar_js(clave: str, url: str, timeout_ms: int = 45_000,
                 clic_texto: str | None = None,
                 clic_coordenadas: tuple[int, int] | None = None) -> dict:
    """Renderiza `url` con Chromium headless y archiva HTML + planillas + tablas.

    Si `clic_texto` viene dado, despues del primer render busca un elemento
    visible con ese texto y lo clickea (paginas SPA que enrutan por JS, sin
    <a href> navegable) antes de archivar -- el archivo resultante es el de
    la pagina DESTINO, no la de aterrizaje.

    Si `clic_coordenadas` viene dado (x, y en pixeles de viewport), hace un
    click ahi DESPUES de archivar el estado inicial, y archiva un segundo
    screenshot + mapa de clickeables con el sufijo "_post_click" -- para
    iconos dibujados sobre <canvas> sin ningun hook de DOM (ver ITCR en
    manifest_fuentes.md: el icono de "Herramientas" del grafico Ext JS no
    aparece en el mapa de clickeables porque no es un <a>/<button> real,
    asi que la unica forma de activarlo es un click por coordenadas
    calibradas visualmente contra un screenshot real).
    """
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

        if clic_texto:
            try:
                pagina.get_by_text(clic_texto, exact=False).first.click(timeout=timeout_ms)
                pagina.wait_for_load_state("networkidle", timeout=timeout_ms)
                pagina.wait_for_timeout(3000)
            except Exception as e:                        # noqa: BLE001
                print(f"[desc-js] {clave}: no se pudo clickear '{clic_texto}': {e}"
                      f" -- se archiva la pagina de aterrizaje igual")

        html = pagina.content()
        destino_html = subdir / f"{dt.date.today():%Y%m%d}_render.html"
        destino_html.write_text(html, encoding="utf-8")
        resumen["html"] = str(destino_html)

        # captura visual + mapa de elementos clickeables: unica forma de
        # calibrar un click en algo que no es <a href> (icono en canvas,
        # menu por hover) sin poder ver el render real desde el sandbox.
        try:
            destino_png = subdir / f"{dt.date.today():%Y%m%d}_screenshot.png"
            pagina.screenshot(path=str(destino_png), full_page=True, timeout=timeout_ms)
        except Exception as e:                            # noqa: BLE001
            print(f"[desc-js] {clave}: fallo screenshot: {e}")

        try:
            clickeables = pagina.eval_on_selector_all(
                "a, button, [role=button], [onclick], [title], [aria-label]",
                """els => els.filter(e => {
                    const r = e.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                }).map(e => {
                    const r = e.getBoundingClientRect();
                    return {tag: e.tagName, texto: (e.innerText || e.getAttribute('title') ||
                            e.getAttribute('aria-label') || '').trim().slice(0, 80),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)};
                })""")
            destino_json = subdir / f"{dt.date.today():%Y%m%d}_clickeables.json"
            destino_json.write_text(json.dumps(clickeables, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
        except Exception as e:                            # noqa: BLE001
            print(f"[desc-js] {clave}: fallo mapa de clickeables: {e}")

        if clic_coordenadas:
            try:
                x, y = clic_coordenadas
                pagina.mouse.click(x, y)
                pagina.wait_for_timeout(1500)
                destino_png2 = subdir / f"{dt.date.today():%Y%m%d}_screenshot_post_click.png"
                pagina.screenshot(path=str(destino_png2), full_page=True, timeout=timeout_ms)
                clickeables2 = pagina.eval_on_selector_all(
                    "a, button, [role=button], [onclick], [title], [aria-label], li, div",
                    """els => els.filter(e => {
                        const r = e.getBoundingClientRect();
                        return r.width > 0 && r.height > 0 && r.width < 400 && r.height < 60;
                    }).map(e => {
                        const r = e.getBoundingClientRect();
                        return {tag: e.tagName, texto: (e.innerText || e.getAttribute('title') ||
                                e.getAttribute('aria-label') || '').trim().slice(0, 80),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height)};
                    }).filter(e => e.texto)""")
                destino_json2 = subdir / f"{dt.date.today():%Y%m%d}_clickeables_post_click.json"
                destino_json2.write_text(json.dumps(clickeables2, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
                print(f"[desc-js] {clave}: click en ({x},{y}) -- "
                      f"{len(clickeables2)} elementos chicos visibles despues")
            except Exception as e:                        # noqa: BLE001
                print(f"[desc-js] {clave}: fallo click en coordenadas {clic_coordenadas}: {e}")

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
        except Exception as e:                            # noqa: BLE001
            # una dependencia opcional de read_html (lxml/html5lib) puede
            # faltar o fallar sobre HTML real mal formado -- no debe tirar
            # abajo el archivado (que ya se guardo arriba). Real: en la
            # primera corrida contra el BCU real, read_html sobre un HTML
            # que lxml no pudo parsear intento el flavor html5lib, que no
            # estaba instalado, y abortaba toda la funcion antes de cerrar
            # el navegador.
            print(f"[desc-js] {clave}: fallo extraccion de tablas: {e}")

        navegador.close()

    print(f"[desc-js] {clave}: html={'OK' if resumen['html'] else 'FALLO'}, "
          f"planillas={resumen['planillas']}, tablas={resumen['tablas']}")
    return resumen


def descubrir_todo_js() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    resultados = []
    for clave, cfg in FUENTES_JS.items():
        try:
            resultados.append(_archivar_js(clave, cfg["url"], clic_texto=cfg.get("clic_texto"),
                                           clic_coordenadas=cfg.get("clic_coordenadas")))
        except Exception as e:                            # noqa: BLE001
            print(f"[desc-js] {clave}: fallo total: {e}")
            resultados.append({"clave": clave, "html": None, "planillas": 0, "tablas": 0})
    return resultados


if __name__ == "__main__":
    descubrir_todo_js()
