"""
Cotizaciones del BCU via web service SOAP publico.

Endpoint : https://cotizaciones.bcu.gub.uy/wscotizaciones/servlet/awsbcucotizaciones
WSDL     : mismo endpoint + ?wsdl
Metodo   : wsbcucotizaciones.Execute
Namespace: "Cotiza"
Codigos de moneda: https://www.bcu.gub.uy/Documents/cotizacion.txt (tercera columna)

No se usa zeep a proposito: el WSDL de GeneXus es fragil y el envelope
es simple. requests + lxml alcanza y tiene menos superficie de falla.

El servicio devuelve solo dias habiles. El BCU tiene tope practico de
rango por consulta, asi que se pide por tramos.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Iterator

import requests
from lxml import etree

ENDPOINT = "https://cotizaciones.bcu.gub.uy/wscotizaciones/servlet/awsbcucotizaciones"

# Codigos ISO internos del BCU
MONEDAS = {
    "USD": 2225,   # Dolar USA
    "EUR": 1111,
    "BRL": 1023,
    "ARS": 501,
    "UI": 9800,    # Unidad Indexada
    "UP": 9900,    # Unidad Previsional  (VERIFICAR en cotizacion.txt)
    "UR": 9500,    # Unidad Reajustable  (VERIFICAR)
}

# Grupo 0 = todas las cotizaciones; 1 = solo las de cierre del interbancario
GRUPO_DEFAULT = 0

_PLANTILLA = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:cot="Cotiza">
  <soapenv:Header/>
  <soapenv:Body>
    <cot:wsbcucotizaciones.Execute>
      <cot:Entrada>
        <cot:Moneda>
          <cot:item>{moneda}</cot:item>
        </cot:Moneda>
        <cot:FechaDesde>{desde}</cot:FechaDesde>
        <cot:FechaHasta>{hasta}</cot:FechaHasta>
        <cot:Grupo>{grupo}</cot:Grupo>
      </cot:Entrada>
    </cot:wsbcucotizaciones.Execute>
  </soapenv:Body>
</soapenv:Envelope>"""

HEADERS = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": "Cotiza",
    "User-Agent": "proyecto-inflacion-y-tc/1.0",
}


def _tramos(desde: dt.date, hasta: dt.date,
            dias: int = 365) -> Iterator[tuple[dt.date, dt.date]]:
    cur = desde
    while cur <= hasta:
        fin = min(cur + dt.timedelta(days=dias - 1), hasta)
        yield cur, fin
        cur = fin + dt.timedelta(days=1)


def _texto(nodo, tag: str) -> str | None:
    for hijo in nodo.iter():
        if etree.QName(hijo).localname == tag:
            return (hijo.text or "").strip()
    return None


def _consultar(moneda: int, desde: dt.date, hasta: dt.date,
               grupo: int, timeout: int, reintentos: int) -> bytes:
    cuerpo = _PLANTILLA.format(moneda=moneda, desde=desde.isoformat(),
                               hasta=hasta.isoformat(), grupo=grupo)
    ultimo_error = None
    for intento in range(reintentos):
        try:
            r = requests.post(ENDPOINT, data=cuerpo.encode("utf-8"),
                              headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.content
        except Exception as e:          # noqa: BLE001
            ultimo_error = e
            time.sleep(2 ** intento)
    raise RuntimeError(
        f"BCU SOAP fallo para {moneda} {desde}..{hasta}: {ultimo_error}")


def cotizaciones(moneda: str = "USD",
                 desde: dt.date | str = dt.date(1997, 1, 1),
                 hasta: dt.date | str | None = None,
                 grupo: int = GRUPO_DEFAULT,
                 timeout: int = 90,
                 reintentos: int = 3) -> list[dict]:
    """
    Devuelve [{fecha, moneda, compra, venta, arbitraje, emisor}, ...]
    ordenado por fecha. Solo dias habiles.
    """
    if isinstance(desde, str):
        desde = dt.date.fromisoformat(desde)
    hasta = hasta or dt.date.today()
    if isinstance(hasta, str):
        hasta = dt.date.fromisoformat(hasta)
    cod = MONEDAS.get(moneda.upper())
    if cod is None:
        raise KeyError(f"Moneda desconocida: {moneda}. Ver {MONEDAS.keys()}")

    salida: list[dict] = []
    for ini, fin in _tramos(desde, hasta):
        xml = _consultar(cod, ini, fin, grupo, timeout, reintentos)
        raiz = etree.fromstring(xml)

        # Los items vienen como <cot:datoscotizaciones.dato> o similar segun
        # version. Se busca por localname para no depender del prefijo.
        for nodo in raiz.iter():
            nombre = etree.QName(nodo).localname
            if nombre not in ("dato", "datoscotizaciones.dato"):
                continue
            fecha = _texto(nodo, "Fecha")
            tcc = _texto(nodo, "TCC")   # compra
            tcv = _texto(nodo, "TCV")   # venta
            if not fecha or tcv in (None, ""):
                continue
            try:
                salida.append({
                    "fecha": fecha[:10],
                    "moneda": moneda.upper(),
                    "compra": float(tcc) if tcc else None,
                    "venta": float(tcv),
                    "arbitraje": (lambda v: float(v) if v else None)(
                        _texto(nodo, "ArbAll")),
                    "emisor": _texto(nodo, "Emisor"),
                })
            except ValueError:
                continue
        time.sleep(0.5)   # cortesia con el servidor

    vistos = set()
    unicos = []
    for d in sorted(salida, key=lambda x: x["fecha"]):
        if d["fecha"] in vistos:
            continue
        vistos.add(d["fecha"])
        unicos.append(d)
    return unicos


def punto_medio(registros: list[dict]) -> list[tuple[str, float]]:
    """(fecha, TC) usando el promedio compra-venta cuando hay ambos."""
    out = []
    for r in registros:
        if r["compra"] and r["venta"]:
            out.append((r["fecha"], (r["compra"] + r["venta"]) / 2))
        elif r["venta"]:
            out.append((r["fecha"], r["venta"]))
    return out


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "2026-07-01"
    datos = cotizaciones("USD", desde=d)
    print(f"{len(datos)} observaciones")
    for r in datos[-5:]:
        print(r)
