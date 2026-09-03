"""
Tasa de Politica Monetaria (TPM) extraida del Informe de Politica Monetaria
(IPOM) del BCU.

El IPOM es trimestral y NO tiene una serie descargable en tabla: la TPM
vigente se menciona en prosa en el Resumen Ejecutivo ("...resolvio mantener
la Tasa de Politica Monetaria (TPM) en 5,75%..."). Este modulo extrae ese
valor por regex sobre el texto de las primeras paginas.

Limitacion honesta: el IPOM no siempre da la fecha exacta de la reunion del
Copom que fijo la tasa, asi que fecha_ref es el primer mes del trimestre
que cubre el informe (deducido del nombre de archivo "IPOM_{anio}-{trim}"),
no la fecha de la decision. Es una aproximacion aceptable para un valor que
cambia pocas veces al año (~8 reuniones), documentada en la fuente.

Con cada nuevo IPOM archivado (uno por trimestre) se suma un punto mas;
la serie queda sparse/escalonada en vez de mensual, que es lo que
efectivamente es la TPM entre reuniones.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "descubrimiento" / "tpm_bcu"

_PATRON_TPM = re.compile(
    r"Tasa de Pol[ií]tica Monetaria\s*\(TPM\)\s*(?:en|a)\s*(\d+[.,]\d+)\s*%")
_PATRON_ARCHIVO = re.compile(r"IPOM[_-](\d{4})[_-](\d)")


def fecha_ref_de_nombre(nombre: str) -> str | None:
    """'IPOM_2026-1.pdf' -> '2026-01-01' (primer mes del trimestre)."""
    m = _PATRON_ARCHIVO.search(nombre)
    if not m:
        return None
    anio, trimestre = int(m.group(1)), int(m.group(2))
    if not (1 <= trimestre <= 4):
        return None
    mes = (trimestre - 1) * 3 + 1
    return f"{anio:04d}-{mes:02d}-01"


def extraer_tpm(ruta: Path, paginas_max: int = 8) -> float | None:
    """Busca el valor de la TPM vigente en las primeras paginas del IPOM."""
    import pdfplumber

    with pdfplumber.open(ruta) as pdf:
        texto = "\n".join((p.extract_text() or "") for p in pdf.pages[:paginas_max])
    plano = re.sub(r"\s+", " ", texto)
    m = _PATRON_TPM.search(plano)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def ultimo_ipom(directorio: Path | None = None) -> Path | None:
    """El IPOM mas reciente archivado, por nombre de trimestre (no por fecha de descarga)."""
    directorio = directorio or RAW
    if not directorio.exists():
        return None
    candidatos = [p for p in directorio.glob("*IPOM*.pdf")
                 if fecha_ref_de_nombre(p.name)]
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: fecha_ref_de_nombre(p.name))


def valor_vigente(directorio: Path | None = None) -> tuple[str, float, Path] | None:
    """(fecha_ref, valor_tpm, ruta) del IPOM mas reciente, o None si no hay/no parsea."""
    ruta = ultimo_ipom(directorio)
    if ruta is None:
        return None
    fecha_ref = fecha_ref_de_nombre(ruta.name)
    valor = extraer_tpm(ruta)
    if fecha_ref is None or valor is None:
        return None
    return fecha_ref, valor, ruta


if __name__ == "__main__":
    r = valor_vigente()
    print(r if r else "no se encontro TPM en ningun IPOM archivado")
