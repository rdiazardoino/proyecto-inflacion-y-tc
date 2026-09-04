"""
Cliente HTTP con reparacion de cadenas SSL incompletas.

Problema real (corrida del 6-ago-2026): www5.ine.gub.uy y www.bcu.gub.uy
no envian los certificados intermedios en el handshake TLS. OpenSSL no
persigue AIA, asi que requests falla con CERTIFICATE_VERIFY_FAILED aunque
el certificado sea valido.

Solucion: ante ese error puntual se hace "AIA chasing" — se toma el
certificado hoja del servidor, se descargan los intermedios desde la URL
"CA Issuers" que el propio certificado declara, se VERIFICA que cada
eslabon este firmado por el siguiente y que el ultimo este firmado por
una raiz del bundle de certifi, y recien entonces se agregan a un bundle
local con el que se reintenta. Nunca se desactiva la verificacion.

Los intermedios verificados se cachean en data/raw/certs/ y se commitean:
quedan auditables y las corridas siguientes no repiten el proceso.
"""

from __future__ import annotations

import socket
import ssl
from pathlib import Path

import certifi
import requests
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import AuthorityInformationAccessOID, ExtensionOID

ROOT = Path(__file__).resolve().parents[2]
CERTS_DIR = ROOT / "data" / "raw" / "certs"
BUNDLE = CERTS_DIR / "bundle.pem"

HEADERS = {"User-Agent": "proyecto-inflacion-y-tc/1.0"}


# ---------------------------------------------------------------------
# Construccion y verificacion de la cadena
# ---------------------------------------------------------------------
def _raices_certifi() -> dict[bytes, x509.Certificate]:
    """Raices de confianza indexadas por subject DER."""
    raices = {}
    pem = Path(certifi.where()).read_bytes()
    for cert in x509.load_pem_x509_certificates(pem):
        raices[cert.subject.public_bytes()] = cert
    return raices


def _leaf_del_servidor(host: str, port: int = 443, timeout: int = 30) -> bytes:
    """Certificado hoja tal como lo presenta el servidor (DER).

    La conexion es sin verificar A PROPOSITO: solo se usa para leer el
    certificado y perseguir su cadena AIA; la confianza se establece
    despues, verificando firmas contra las raices de certifi.
    """
    ctx = ssl._create_unverified_context()          # noqa: SLF001
    with socket.create_connection((host, port), timeout=timeout) as s:
        with ctx.wrap_socket(s, server_hostname=host) as ss:
            return ss.getpeercert(binary_form=True)


def _cargar_cert(data: bytes) -> x509.Certificate:
    try:
        return x509.load_der_x509_certificate(data)
    except ValueError:
        return x509.load_pem_x509_certificate(data)


def _url_ca_issuers(cert: x509.Certificate) -> str | None:
    try:
        aia = cert.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
    except x509.ExtensionNotFound:
        return None
    for desc in aia:
        if desc.access_method == AuthorityInformationAccessOID.CA_ISSUERS:
            return desc.access_location.value
    return None


def cadena_intermedia_verificada(host: str) -> list[x509.Certificate]:
    """
    Descarga via AIA los intermedios del certificado de `host` y devuelve
    solo una cadena cuya firma completa cierra contra una raiz de certifi.
    Lanza RuntimeError si la cadena no se puede verificar.
    """
    raices = _raices_certifi()
    cert = _cargar_cert(_leaf_del_servidor(host))
    intermedios: list[x509.Certificate] = []

    for _ in range(5):  # profundidad maxima razonable
        if cert.issuer.public_bytes() in raices:
            cert.verify_directly_issued_by(raices[cert.issuer.public_bytes()])
            return intermedios
        url = _url_ca_issuers(cert)
        if not url:
            raise RuntimeError(
                f"{host}: el certificado de '{cert.subject.rfc4514_string()}' "
                f"no declara CA Issuers y su emisor no es raiz de certifi")
        r = requests.get(url, timeout=60)  # repositorio de la CA, cadena aparte
        r.raise_for_status()
        emisor = _cargar_cert(r.content)
        cert.verify_directly_issued_by(emisor)      # firma valida o excepcion
        intermedios.append(emisor)
        cert = emisor

    raise RuntimeError(f"{host}: cadena AIA demasiado larga, no cierra en raiz")


def _reconstruir_bundle() -> Path:
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    partes = [Path(certifi.where()).read_bytes()]
    for pem in sorted(CERTS_DIR.glob("intermedio_*.pem")):
        partes.append(pem.read_bytes())
    BUNDLE.write_bytes(b"\n".join(partes))
    return BUNDLE


def reparar_confianza(host: str) -> Path:
    """Agrega al bundle local los intermedios verificados de `host`."""
    for cert in cadena_intermedia_verificada(host):
        nombre = "".join(c if c.isalnum() else "_"
                         for c in cert.subject.rfc4514_string())[:80]
        destino = CERTS_DIR / f"intermedio_{nombre}.pem"
        if not destino.exists():
            CERTS_DIR.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(cert.public_bytes(Encoding.PEM))
            print(f"[ssl] intermedio verificado y cacheado: {destino.name}")
    return _reconstruir_bundle()


# ---------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------
def _verify_actual():
    return str(BUNDLE) if BUNDLE.exists() else True


def get(url: str, timeout: int = 120, **kw) -> requests.Response:
    """requests.get con reintento unico tras reparar la cadena SSL."""
    kw.setdefault("headers", HEADERS)
    try:
        r = requests.get(url, timeout=timeout, verify=_verify_actual(), **kw)
        r.raise_for_status()
        return r
    except requests.exceptions.SSLError:
        host = requests.utils.urlparse(url).hostname
        print(f"[ssl] {host}: cadena incompleta; intentando reparar via AIA")
        bundle = reparar_confianza(host)
        r = requests.get(url, timeout=timeout, verify=str(bundle), **kw)
        r.raise_for_status()
        return r


def post(url: str, timeout: int = 120, **kw) -> requests.Response:
    kw.setdefault("headers", HEADERS)
    try:
        r = requests.post(url, timeout=timeout, verify=_verify_actual(), **kw)
        r.raise_for_status()
        return r
    except requests.exceptions.SSLError:
        host = requests.utils.urlparse(url).hostname
        print(f"[ssl] {host}: cadena incompleta; intentando reparar via AIA")
        bundle = reparar_confianza(host)
        r = requests.post(url, timeout=timeout, verify=str(bundle), **kw)
        r.raise_for_status()
        return r


def sesion() -> requests.Session:
    """
    Sesion con cookies persistentes, para flujos de varios pedidos
    encadenados donde el servidor exige la misma sesion HTTP en todos
    (ver bcu_itcr.py: guest -> render_portlet -> processCommands). Usa
    el mismo bundle de verificacion que get()/post(); no repara la
    cadena SSL sola -- si hace falta, el llamador dispara la reparacion
    con get()/post() una vez y reintenta con la sesion ya creada.
    """
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = _verify_actual()
    return s
