"""
IPC del INE.

El INE no tiene API. Publica planillas en paginas de "series historicas",
una por base del indice. Este modulo:
  1. descubre los enlaces a planillas en cada pagina de serie,
  2. descarga y guarda el archivo crudo en data/raw/ine/ con la fecha,
  3. parsea el indice general y sus aperturas,
  4. empalma las tres bases por VARIACION MENSUAL, no por nivel.

El empalme por variacion es lo correcto: reencadenar por nivel supone que
las canastas son comparables, y no lo son. Se reconstruye hacia atras desde
la base vigente aplicando las variaciones mensuales de cada base anterior.

Las planillas del INE cambian de layout sin aviso. Por eso el parseo es
tolerante: busca la fila de encabezado en vez de asumir una posicion fija,
y si no encuentra lo que espera levanta una alerta en vez de escribir basura.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from src.etl import http_client

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "ine"

# Cada base tiene una lista de URLs candidatas: gub.uy reorganiza rutas sin
# redirect. Se usa la primera que responda con planillas.
PAGINAS = {
    "base_2022_10": [
        "https://www.gub.uy/instituto-nacional-estadistica/datos-y-estadisticas/estadisticas/series-historicas-ipc-base-octubre-2022100",
    ],
    "base_2010_12": [
        "https://www.gub.uy/instituto-nacional-estadistica/datos-y-estadisticas/estadisticas/series-historicas-ipc-base-diciembre-2010100",
    ],
    "base_1997_03": [
        # la ruta /datos/ devolvio 404 el 6-ago-2026; se prueban variantes
        "https://www.gub.uy/instituto-nacional-estadistica/datos-y-estadisticas/estadisticas/series-historicas-ipc-base-marzo-1997100",
        "https://www.gub.uy/instituto-nacional-estadistica/datos/series-historicas-ipc-base-marzo-1997100",
        "https://www.gub.uy/instituto-nacional-estadistica/datos-y-estadisticas/estadisticas/serie-historica-ipc-base-marzo-1997100",
    ],
}

# Orden cronologico de las bases, de la mas vieja a la vigente
ORDEN_BASES = ["base_1997_03", "base_2010_12", "base_2022_10"]

HEADERS = {"User-Agent": "proyecto-inflacion-y-tc/1.0"}
EXT_VALIDAS = (".xls", ".xlsx", ".csv", ".ods")

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


# ---------------------------------------------------------------------
# Descubrimiento y descarga
# ---------------------------------------------------------------------
def descubrir_planillas(url: str, timeout: int = 60) -> list[str]:
    """Enlaces a planillas encontrados en una pagina de serie historica."""
    r = http_client.get(url, timeout=timeout)
    sopa = BeautifulSoup(r.text, "html.parser")
    enlaces = []
    for a in sopa.find_all("a", href=True):
        href = a["href"]
        if href.lower().split("?")[0].endswith(EXT_VALIDAS):
            enlaces.append(urljoin(url, href))
    # dedup conservando orden
    return list(dict.fromkeys(enlaces))


def descargar(url: str, destino_dir: Path, timeout: int = 120) -> Path:
    destino_dir.mkdir(parents=True, exist_ok=True)
    nombre = re.sub(r"[^\w.\-]", "_", url.split("/")[-1].split("?")[0])
    destino = destino_dir / f"{dt.date.today():%Y%m%d}_{nombre}"
    if destino.exists():
        return destino
    r = http_client.get(url, timeout=timeout)
    destino.write_bytes(r.content)
    return destino


def bajar_todo(bases: list[str] | None = None) -> dict[str, list[Path]]:
    """
    Descarga las planillas. Por defecto solo la base vigente (oct-2022):
    su planilla 'gral y variaciones' ya trae la serie oficial reexpresada
    desde 1937, y las bases viejas quedaron archivadas en data/raw/ine/.
    Pasar bases=list(PAGINAS) para re-descargar todo.
    """
    bases = bases or ["base_2022_10"]
    salida: dict[str, list[Path]] = {}
    for clave, candidatas in PAGINAS.items():
        if clave not in bases:
            continue
        urls: list[str] = []
        for url in candidatas:
            try:
                urls = descubrir_planillas(url)
            except Exception as e:                   # noqa: BLE001
                print(f"[ine] no se pudo leer {clave} en {url}: {e}")
                continue
            if urls:
                break
            print(f"[ine] AVISO: ninguna planilla en {url}")
        rutas = []
        for u in urls:
            try:
                rutas.append(descargar(u, RAW / clave))
            except Exception as e:                   # noqa: BLE001
                print(f"[ine] fallo descarga {u}: {e}")
        salida[clave] = rutas
        print(f"[ine] {clave}: {len(rutas)} archivos")
    return salida


# ---------------------------------------------------------------------
# Parsers especificos por planilla (calibrados contra los archivos reales
# commiteados en data/raw/ine/ el 2-sep-2026). La heuristica leer_indice()
# queda como fallback para archivos no reconocidos.
# ---------------------------------------------------------------------
def _normalizar(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def buscar_archivo(directorio: Path, *fragmentos: str) -> Path | None:
    """Archivo mas reciente cuyo nombre normalizado contiene todos los fragmentos."""
    candidatos = [p for p in sorted(directorio.glob("*"))
                  if all(f in _normalizar(p.name) for f in fragmentos)]
    return candidatos[-1] if candidatos else None


def _serie_anio_mes(df: pd.DataFrame, col_anio: str, col_mes: str,
                    col_valor: str) -> pd.Series:
    df = df.copy()
    df[col_anio] = pd.to_numeric(df[col_anio], errors="coerce")
    df[col_mes] = pd.to_numeric(df[col_mes], errors="coerce")
    df[col_valor] = pd.to_numeric(df[col_valor], errors="coerce")
    df = df.dropna(subset=[col_anio, col_mes, col_valor])
    idx = pd.to_datetime({"year": df[col_anio].astype(int),
                          "month": df[col_mes].astype(int), "day": 1})
    return pd.Series(df[col_valor].values, index=idx).sort_index()


def parsear_general_largo(ruta: Path) -> pd.Series:
    """
    'IPC gral y variaciones_base 2022.xlsx': serie oficial del IPC Total Pais
    reexpresada en base octubre 2022 = 100 DESDE JULIO 1937. Fechas datetime
    en col 0 (desde fila ~10), indice en col 1. Los valores iniciales son
    minusculos (1.5e-7 en 1937) pero reales, no ceros.
    """
    df = pd.read_excel(ruta, sheet_name=0, header=None)
    fechas = df.iloc[:, 0].map(_a_fecha)
    valores = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s = pd.Series(valores.values, index=fechas.values)
    s = s[s.index.notna()].dropna()
    s = s[s > 0]
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def parsear_general_regiones(ruta: Path) -> dict[str, pd.Series]:
    """
    'IPC General_Total Pais_Montevideo_Interior_base 2022.xlsx', hoja
    'Por región': Año | Mes | General Total Pais | Montevideo | Interior,
    desde diciembre 2010.
    """
    df = pd.read_excel(ruta, sheet_name=0, header=None, skiprows=1,
                       names=["anio", "mes", "tp", "mvd", "int"],
                       usecols=range(5))
    return {clave: _serie_anio_mes(df, "anio", "mes", col)
            for clave, col in [("total_pais", "tp"),
                               ("montevideo", "mvd"), ("interior", "int")]}


def parsear_divisiones(ruta: Path) -> pd.DataFrame:
    """
    'IPC_Division_País_desde 2010_base 2022.xlsx': formato tidy
    Año | Mes | División (1-13) | Indice Total País, desde diciembre 2010.
    Devuelve DataFrame [fecha, division, indice] con division '01'..'13'.
    """
    df = pd.read_excel(ruta, sheet_name=0, header=None, skiprows=1,
                       names=["anio", "mes", "div", "idx"], usecols=range(4))
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce")
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce")
    df["idx"] = pd.to_numeric(df["idx"], errors="coerce")
    df["div"] = pd.to_numeric(df["div"], errors="coerce")
    df = df.dropna(subset=["anio", "mes", "div", "idx"])
    fecha = pd.to_datetime({"year": df["anio"].astype(int),
                            "month": df["mes"].astype(int), "day": 1})
    return pd.DataFrame({
        "fecha": fecha.values,
        "division": df["div"].astype(int).astype(str).str.zfill(2).values,
        "indice": df["idx"].values,
    }).sort_values(["division", "fecha"]).reset_index(drop=True)


def parsear_subyacente(ruta: Path) -> pd.Series:
    """
    'IPC_Cuadro_inflación subyacente.xlsx': Año | Nombre_mes | Mes |
    IPC_CE VFC | Var. Mes | Var. AA, desde octubre 2022. El IPC-CE excluye
    frutas, verduras y combustibles. El mes en curso puede venir como fila
    vacia pre-creada: se descarta.
    """
    df = pd.read_excel(ruta, sheet_name=0, header=None, skiprows=1,
                       names=["anio", "nmes", "mes", "ipc_ce", "vm", "vaa"],
                       usecols=range(6))
    return _serie_anio_mes(df, "anio", "mes", "ipc_ce")


# ---------------------------------------------------------------------
# Parseo generico (fallback)
# ---------------------------------------------------------------------
def _a_fecha(valor) -> str | None:
    """Normaliza etiquetas de periodo del INE a primer dia del mes, ISO."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (dt.datetime, dt.date, pd.Timestamp)):
        return f"{valor.year:04d}-{valor.month:02d}-01"
    txt = str(valor).strip().lower()
    if not txt or txt in ("nan", "none"):
        return None
    # "Enero 2023", "ene-23", "2023-01", "01/2023", "Ene.2023"
    m = re.search(r"(\d{4})[-/](\d{1,2})", txt)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-01"
    m = re.search(r"(\d{1,2})[-/](\d{4})", txt)
    if m:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}-01"
    for nombre, num in MESES.items():
        if txt.startswith(nombre[:3]):
            a = re.search(r"(\d{4})", txt)
            if a:
                return f"{int(a.group(1)):04d}-{num:02d}-01"
            a = re.search(r"(\d{2})\b", txt)
            if a:
                anio = int(a.group(1))
                anio += 1900 if anio > 50 else 2000
                return f"{anio:04d}-{num:02d}-01"
    return None


def leer_indice(ruta: Path, hoja: int | str = 0,
                col_valor: int | None = None) -> pd.Series:
    """
    Lee una planilla del INE y devuelve una serie mensual indice.

    Heuristica: recorre la planilla buscando la primera columna cuyas celdas
    parseen como periodo mensual, y la usa de indice. Como valor toma
    col_valor si se indica, o la primera columna numerica a su derecha.
    Si no encuentra nada usable devuelve serie vacia; el orquestador lo
    convierte en alerta.
    """
    try:
        df = pd.read_excel(ruta, sheet_name=hoja, header=None)
    except Exception as e:                           # noqa: BLE001
        print(f"[ine] no se pudo abrir {ruta.name}: {e}")
        return pd.Series(dtype=float)

    col_fecha = None
    for j in range(min(df.shape[1], 8)):
        parsed = df.iloc[:, j].map(_a_fecha)
        if parsed.notna().sum() >= 24:
            col_fecha = j
            fechas = parsed
            break
    if col_fecha is None:
        print(f"[ine] {ruta.name}: no se identifico columna de periodo")
        return pd.Series(dtype=float)

    if col_valor is None:
        for j in range(col_fecha + 1, df.shape[1]):
            v = pd.to_numeric(df.iloc[:, j], errors="coerce")
            if v.notna().sum() >= 24 and v.dropna().between(0.1, 1e6).all():
                col_valor = j
                break
    if col_valor is None:
        print(f"[ine] {ruta.name}: no se identifico columna de valores")
        return pd.Series(dtype=float)

    valores = pd.to_numeric(df.iloc[:, col_valor], errors="coerce")
    s = pd.Series(valores.values, index=fechas.values)
    s = s[s.index.notna()].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()[~s.sort_index().index.duplicated(keep="last")]


def empalmar(series_por_base: dict[str, pd.Series]) -> pd.Series:
    """
    Encadena las bases por variacion mensual, anclando en la base vigente.

    Se recorre de la base vigente hacia atras. Para cada base anterior se
    calcula su variacion mensual y se aplica retroactivamente al primer
    nivel conocido de la base siguiente. El resultado es un indice continuo
    expresado en la base vigente (octubre 2022 = 100).
    """
    bases = [b for b in ORDEN_BASES
             if b in series_por_base and not series_por_base[b].empty]
    if not bases:
        return pd.Series(dtype=float)

    resultado = series_por_base[bases[-1]].copy()
    for clave in reversed(bases[:-1]):
        vieja = series_por_base[clave]
        anteriores = vieja.index[vieja.index < resultado.index.min()]
        if len(anteriores) == 0:
            continue
        var = vieja.pct_change()
        ancla = resultado.iloc[0]
        # nivel_t = nivel_{t+1} / (1 + var_{t+1})
        niveles = {}
        siguiente = ancla
        fechas_desc = sorted(anteriores, reverse=True)
        # variacion del primer mes de 'resultado' respecto del ultimo de 'vieja'
        for f in fechas_desc:
            f_post = vieja.index[vieja.index > f]
            if len(f_post) == 0:
                break
            v = var.get(f_post[0])
            if v is None or pd.isna(v):
                break
            siguiente = siguiente / (1 + v)
            niveles[f] = siguiente
        if niveles:
            resultado = pd.concat(
                [pd.Series(niveles).sort_index(), resultado]).sort_index()
    return resultado


if __name__ == "__main__":
    archivos = bajar_todo()
    for clave, rutas in archivos.items():
        for r in rutas:
            s = leer_indice(r)
            print(f"{clave} / {r.name}: {len(s)} obs "
                  f"{s.index.min().date() if len(s) else '-'} .. "
                  f"{s.index.max().date() if len(s) else '-'}")
