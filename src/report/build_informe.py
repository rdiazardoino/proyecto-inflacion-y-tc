"""
Sesion 6 - Informe mensual (plan Seccion 20). Misma fuente de datos que el
dashboard (src/report/datos_dashboard.py) -- nunca se recalculan cifras
distintas entre los dos.

Uso: python src/report/build_informe.py
Salida: outputs/informes/YYYY-MM/informe.html (+ informe.pdf si weasyprint
esta disponible en el entorno).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.report import datos_dashboard as dd  # noqa: E402
from src.report import glosario as glos  # noqa: E402
from src.report.build_dashboard import _fdia, _fmes, _fmes_abr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

CSS = """
@page { size: A4; margin: 2cm 1.8cm; }
body { font-family: Georgia, 'Times New Roman', serif; color:#0b0b0b; font-size:10.5pt; line-height:1.45; }
h1 { font-size:20pt; margin-bottom:2pt; font-family: system-ui, sans-serif; }
h2 { font-size:13pt; margin-top:22pt; border-bottom:1.5pt solid #0a3470; padding-bottom:3pt;
     font-family: system-ui, sans-serif; color:#0a3470; }
h3 { font-size:11pt; margin-top:14pt; font-family: system-ui, sans-serif; }
.subtitulo { color:#52514e; font-size:10pt; margin-bottom:18pt; font-family: system-ui, sans-serif; }
table { width:100%; border-collapse:collapse; margin:8pt 0; font-size:9.5pt; }
th, td { border-bottom:0.75pt solid #ccc; padding:4pt 6pt; text-align:right; }
th { text-align:right; background:#f5f5f3; font-family: system-ui, sans-serif; font-size:9pt; }
td:first-child, th:first-child { text-align:left; }
.kpi-fila { display:flex; gap:14pt; margin:10pt 0; }
.kpi-box { border:0.75pt solid #ccc; border-radius:4pt; padding:8pt 10pt; flex:1; }
.kpi-box .t { font-size:8pt; color:#52514e; text-transform:uppercase; font-family: system-ui, sans-serif; }
.kpi-box .v { font-size:15pt; font-weight:600; font-family: system-ui, sans-serif; }
.nota { color:#52514e; font-size:9pt; font-style:italic; }
.disclaimer { background:#f5f5f3; border-left:3pt solid #0a3470; padding:8pt 10pt; font-size:9pt; margin:10pt 0; }
.pendiente { color:#a3402a; }
.resumen-narrativo { font-size:11pt; line-height:1.55; margin:8pt 0 14pt; }
.glosario { columns:2; column-gap:16pt; font-size:8.5pt; line-height:1.4; margin:8pt 0 4pt; }
.glosario .gt { break-inside:avoid; margin-bottom:8pt; }
.glosario .gt b { font-family: system-ui, sans-serif; font-size:9pt; }
.glosario .gt p { margin:1pt 0 0; color:#333; }
.aviso-manual { background:#fdf6e3; border-left:3pt solid #a3402a; padding:8pt 10pt; font-size:9pt; margin:10pt 0; }
.aviso-manual table { font-size:8.5pt; }
"""


def _tabla_nodos(ipc: pd.DataFrame, tc: pd.DataFrame) -> str:
    filas = ""
    for h in ipc["horizonte_meses"]:
        ri = ipc[ipc["horizonte_meses"] == h].iloc[0]
        rt = tc[tc["horizonte_meses"] == h].iloc[0]
        fecha = _fmes_abr(pd.Timestamp(ri["fecha_objetivo"]))
        filas += (f"<tr><td>h={h} ({fecha})</td>"
                 f"<td>{ri['valor']:.2f}%</td><td>[{ri['li_80']:.2f}%, {ri['ls_80']:.2f}%]</td>"
                 f"<td>{rt['valor']:.2f}</td><td>[{rt['li_80']:.2f}, {rt['ls_80']:.2f}]</td></tr>")
    return (f"<table><tr><th>Nodo</th><th>Inflación m/m</th><th>IC 80%</th>"
           f"<th>TC promedio</th><th>IC 80%</th></tr>{filas}</table>")


def construir(mes: str | None = None) -> Path:
    mes = mes or pd.Timestamp.today().strftime("%Y-%m")
    out_dir = ROOT / "outputs" / "informes" / mes
    out_dir.mkdir(parents=True, exist_ok=True)
    d = dd.cargar()

    prob = d["escenarios"].set_index("escenario_id")["probabilidad"]
    met = d["metricas_backtest"]
    tabla_mae = "".join(
        f"<tr><td>{glos.nombre_modelo(r['modelo_id'])}</td>"
        f"<td>{r['mae']:.3f}</td><td>{r['bias']:+.3f}</td>"
        f"<td>{r['dir_accuracy']*100:.0f}%</td><td>{r['n_obs']}</td></tr>"
        for _, r in met[met["objetivo"] == "ipc_m"].sort_values("horizonte_meses").iterrows()
        if r["horizonte_meses"] == 1)

    glosario_html = "".join(
        f"<div class='gt'><b>{termino}</b><p>{definicion}</p></div>"
        for termino, definicion in glos.GLOSARIO)

    aviso_manual_html = ""
    if len(d["datos_manuales"]):
        filas_manual = "".join(
            f"<tr><td>{r['nombre']}</td><td>{_fmes(pd.Timestamp(r['fecha_ref']))}</td>"
            f"<td>{_fdia(pd.Timestamp(r['fecha_descarga']))}</td><td>{r['fuente']}</td></tr>"
            for _, r in d["datos_manuales"].iterrows())
        aviso_manual_html = f"""<div class="aviso-manual"><b>Datos cargados a mano en esta corrida
        ({len(d['datos_manuales'])}):</b> no vienen del pipeline automático (ver
        <code>src/etl/cargar_manual.py</code>) y no se actualizan solos.
        <table><tr><th>Serie</th><th>Dato de</th><th>Cargado el</th><th>Fuente</th></tr>{filas_manual}</table>
        </div>"""

    ETIQUETA_SUPUESTO = {"dbrl_mensual": "Δ USD/BRL mensual", "ddxy_mensual": "Δ DXY mensual"}

    def _render_escenario(r) -> str:
        supuestos = yaml.safe_load(r["supuestos"]) or {}
        senales = yaml.safe_load(r["senales_monitoreo"]) or []
        sup_txt = " · ".join(f"{ETIQUETA_SUPUESTO.get(k, k)}: {v:+.1f}%" for k, v in supuestos.items())
        sen_txt = " · ".join(senales)
        return (f"<h3>{r['nombre']} ({r['probabilidad']*100:.0f}%)</h3>"
               f"<p>{sup_txt}</p><p class='nota'>Señales: {sen_txt}</p>")

    escenarios_html = "".join(_render_escenario(r) for _, r in d["escenarios"].iterrows())

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<title>Informe mensual — {mes}</title><style>{CSS}</style></head><body>

<h1>Inflación y Tipo de Cambio — Uruguay</h1>
<div class="subtitulo">Informe mensual · corrida {mes} · IPC al {_fmes(d['fecha_corte_ipc'])} ·
TC al {_fdia(d['tc_spot_fecha'])} · Origen del pronóstico: {_fmes(d['origen_pronostico'])}</div>

<div class="disclaimer">Documento de uso interno. Las proyecciones son estimaciones estadísticas con
incertidumbre explícita (ver bandas de los nodos) y no constituyen asesoramiento financiero ni una
garantía de resultado. Metodología completa y limitaciones en la sección final y en
<code>docs/</code> del repositorio.</div>

{aviso_manual_html}

<h2>Cómo leer este informe</h2>
<p class="nota">Los términos técnicos (ensemble, Random Walk, MAE, backtest, banda de confianza, etc.)
se explican la primera vez que aparecen y se repiten acá, todos juntos, para consulta rápida.</p>
<div class="glosario">{glosario_html}</div>

<h2>Resumen ejecutivo</h2>
<p class="resumen-narrativo">
La inflación se mantiene dentro del rango de tolerancia de la meta del BCU (3%–6% anual): el IPC subió
{d['ipc_mm']:.2f}% en {_fmes_abr(d['fecha_corte_ipc'])} y acumula {d['ipc_aa']:.2f}% en los últimos doce
meses, {abs(d['desvio_vs_meta']):.2f} p.p. {'por debajo' if d['desvio_vs_meta']<0 else 'por encima'} de la
meta puntual (4,5%). El núcleo — que excluye frutas, verduras y combustibles para aislar la tendencia de
fondo — corre en {d['nucleo_aa']:.2f}% interanual, con una dinámica de más corto plazo (3 meses,
anualizada) de {d['nucleo_3m_anualizada_sa']:.2f}% que {'no muestra señales de aceleración' if d['nucleo_3m_anualizada_sa'] <= d['nucleo_aa'] + 0.5 else 'sugiere una aceleración a vigilar'}.
El tipo de cambio cerró en {d['tc_spot']:.2f} UYU/USD, y la proyección del sistema para los próximos 24
meses es prácticamente plana (ver tabla de nodos) — <b>una lectura honesta de ese resultado, no una
casualidad</b>: en el backtest de este sistema, ningún modelo con contenido económico logró vencer de
forma sostenida al Random Walk (el modelo que asume "sin cambio"), así que el pronóstico oficial
refleja esa falta de señal direccional en vez de inventar una. El principal riesgo a vigilar es el
escenario adverso (depreciación regional/global sostenida), con una probabilidad asignada por juicio del
analista de {prob.get('adverso',0)*100:.0f}% (ver sección de Escenarios).
</p>

<h3>Tabla de nodos — pronóstico oficial (ensemble v1)</h3>
{_tabla_nodos(d['ensemble_ipc'], d['ensemble_tc'])}
<p class="nota">Definiciones: inflación m/m del IPC total país base oct-2022=100, sin desestacionalizar,
del mes del nodo indicado. TC = promedio simple del interbancario fondo del mismo mes. Intervalos 80% =
banda empírica v1 (desvío histórico de errores del backtest + dispersión entre modelos admitidos del
ensemble), no Monte Carlo paramétrico.</p>

<h2>Qué cambió</h2>
<p class="pendiente">Esta sección todavía no está implementada: falta la comparación automática entre el
dato efectivamente publicado y lo que el sistema había proyectado el mes anterior (la "sorpresa" del
nowcast). La base ya guarda cada corrida mensual con su propio vintage de datos, así que el historial
para hacer esta comparación se va acumulando corrida a corrida.</p>

<h2>Inflación observada</h2>
<div class="kpi-fila">
  <div class="kpi-box"><div class="t">m/m</div><div class="v">{d['ipc_mm']:.2f}%</div></div>
  <div class="kpi-box"><div class="t">a/a</div><div class="v">{d['ipc_aa']:.2f}%</div></div>
  <div class="kpi-box"><div class="t">Núcleo a/a</div><div class="v">{d['nucleo_aa']:.2f}%</div></div>
  <div class="kpi-box"><div class="t">Núcleo 3m anualizada SA</div><div class="v">{d['nucleo_3m_anualizada_sa']:.2f}%</div></div>
</div>
<p>La inflación interanual está {abs(d['desvio_vs_meta']):.2f} p.p. {'por debajo' if d['desvio_vs_meta']<0 else 'por encima'}
de la meta puntual del BCU (4,5%), dentro del rango de tolerancia (3-6%). La tendencia de 3 meses
anualizada del núcleo ({d['nucleo_3m_anualizada_sa']:.2f}%) {'está por debajo del' if d['nucleo_3m_anualizada_sa']<d['nucleo_aa'] else 'supera al'}
registro interanual, sin señal de aceleración de corto plazo.</p>

<h2>Nowcast y proyección</h2>
<p>Nowcast del mes en curso ({_fmes(d['origen_pronostico'] + pd.DateOffset(months=1))}): <b>{d['nowcast_mm']:.2f}%</b> m/m
(ensemble v1, h=1). La trayectoria completa a 1/6/12/24 meses está en la tabla de nodos del resumen
ejecutivo; el salto en h=6 corresponde a enero, mes con fuerte estacionalidad administrada (Vivienda y
Enseñanza, ver <code>docs/eda_sesion2.md</code>) que el propio benchmark estacional captura.</p>

<h2>Tipo de cambio</h2>
<p>TC spot {d['tc_spot']:.2f} UYU/USD ({_fdia(d['tc_spot_fecha'])}), variación m/m {d['tc_var_mm']:+.2f}%,
a/a {d['tc_var_aa']:+.2f}%. La proyección del ensemble (ver tabla de nodos) muestra una senda
prácticamente plana a 24 meses ({d['ensemble_tc'].iloc[-1]['valor']:.2f}), reflejo de que ningún
benchmark de TC evaluado le gana de forma sostenida al random walk (ver <code>docs/backtest_sesion3.md</code>
y <code>docs/backtest_sesion4.md</code>).</p>

<h2>Política monetaria</h2>
<p>TPM vigente: <b>{d['tpm']:.2f}%</b>, según el Informe de Política Monetaria del BCU
({_fmes_abr(d['tpm_fecha'])}) — <span class="pendiente">único punto histórico disponible por ahora: la
serie mensual completa de todas las decisiones del Copom todavía no está cargada (ver
<code>docs/manifest_fuentes.md</code>)</span>. Tasa real ex ante:
<b>{d['tasa_real_ex_ante']:.2f} p.p.</b> = TPM menos {'la expectativa de inflación a 12 meses de la Encuesta del BCU (' + f"{d['expectativa_inflacion_12m']:.1f}%" + ', ' + _fmes_abr(d['expectativa_inflacion_12m_fecha']) + ')' if not d['tasa_real_ex_ante_es_proxy'] else 'la meta puntual del BCU (proxy, la Encuesta de Expectativas no está disponible este mes)'}.
Una tasa real positiva indica una política monetaria contractiva.</p>

<h2>Contexto regional y global</h2>
<p>{'Brecha de producto (IMAE, filtro HP): <b>' + f"{d['brecha_producto']:+.2f}" + '</b> (' + _fmes_abr(d['brecha_producto_fecha']) + ') — ' + ('positiva, actividad por encima de su tendencia de largo plazo (presión inflacionaria desde el lado real de la economía).' if d['brecha_producto'] > 0 else 'negativa, la economía opera con capacidad ociosa (presión inflacionaria acotada desde el lado real).') if d['brecha_producto'] is not None else '<span class="pendiente">Brecha de producto todavía no disponible: hace falta más historia de IMAE cargada.</span>'}
{('ITCR global: <b>' + f"{d['itcr_global']:.1f}" + '</b> (base 2017=100, ' + _fmes_abr(d['itcr_global_fecha']) + ').') if d['itcr_global'] is not None else '<span class="pendiente">ITCR todavía no disponible: el ingestor está en prueba contra el BCU real (ver docs/manifest_fuentes.md).</span>'}
No hay datos fiscales cargados (resultado del sector público). Lo disponible como exógenas de los modelos:
USD/BRL, DXY, Brent, CPI EEUU y la curva de rendimientos del Tesoro americano (2a/3m/10a).</p>

<h2>Escenarios</h2>
<p>Tres escenarios definidos como sendas de USD/BRL y DXY (no como ajustes del resultado), corridos sobre
el mismo modelo (VAR(2) reducido) para que la coherencia interna entre TC e inflación sea automática.
Probabilidades por juicio documentado (no hay BVAR con TPM histórica ni encuesta de expectativas para
calibrarlas de otra forma).</p>
{escenarios_html}

<h2>Riesgos</h2>
<ul>
<li><b>De modelo:</b> ningún modelo económico (SARIMAX top-down, Phillips reducida, VAR(2)) le gana al
benchmark random-walk/estacional en backtest — el pronóstico oficial depende de modelos simples que no
capturan mecanismos económicos explícitos. Ver <code>docs/backtest_sesion4.md</code>.</li>
<li><b>De datos:</b> ITCR e historia completa de la TPM todavía no cargados; las probabilidades de
escenario siguen siendo juicio del analista, no una salida de un modelo calibrado con esas series
(ver <code>docs/manifest_fuentes.md</code>). Expectativas de inflación e IMAE (brecha de producto) sí
se incorporaron este mes.</li>
<li><b>De mercado (escenario adverso, {prob.get('adverso',0)*100:.0f}%):</b> depreciación regional/global
sostenida — ver señales de confirmación arriba.</li>
</ul>

<h2>Implicancias de inversión</h2>
<p class="pendiente">Sección limitada por ahora: no hay curva de rendimientos en UI ni
datos de BEVSA cargados, así que no se puede comparar el retorno esperado nominal vs. indexado a
inflación con el rigor que el plan pide (breakeven, carry). Lectura direccional únicamente, sujeta a
revisión cuando esas fuentes se incorporen: con inflación dentro del rango meta y una proyección de TC
prácticamente plana en el escenario base, el diferencial nominal-UI depende sobre todo de la curva de
tasas vigente en cada momento, no de una sorpresa inflacionaria esperada por este sistema. El escenario
adverso ({prob.get('adverso',0)*100:.0f}% de probabilidad) es el que más afecta la comparación en dólares,
por la depreciación del TC más que por la inflación en sí (ver sección de escenarios).</p>

<h2>Performance del modelo</h2>
<p>Métricas de backtest en expanding window, corte completo dic-2016 a jul-2024, horizonte 1 mes,
objetivo inflación m/m:</p>
<table><tr><th>Modelo</th><th>MAE</th><th>Bias</th><th>Dir. accuracy</th><th>n</th></tr>{tabla_mae}</table>
<p class="nota">Tabla completa de todos los horizontes y ambos objetivos en
<code>docs/backtest_sesion3.md</code> y <code>docs/backtest_sesion4.md</code>.</p>

<h2>Apéndice metodológico</h2>
<p><b>Datos:</b> ETL automático en GitHub Actions (INE, BCU, FRED), point-in-time con vintages — nunca
se pisa un dato ya publicado, se agrega una revisión nueva (<code>docs/manifest_fuentes.md</code>).
<b>EDA:</b> estacionalidad, quiebres estructurales (Chow, confirmados sep-2020 y oct-2022), pass-through
preliminar (<code>docs/eda_sesion2.md</code>). <b>Benchmarks:</b> Random Walk, Random Walk estacional,
media móvil 12m, naive, RW con tendencia — evaluados con un backtest honesto (ver glosario)
(<code>docs/backtest_sesion3.md</code>). <b>Modelos económicos:</b> SARIMAX top-down, curva de Phillips
(corrección de error hacia la meta BCU, con brecha de producto vía IMAE desde este mes), VAR(2)
inflación-TC — todos en ventana rolling de 96 meses, ninguno supera al benchmark de forma sostenida
(<code>docs/backtest_sesion4.md</code>). <b>Ensemble:</b> promedio ponderado por inverso del MAE del
régimen 2022+, piso de 10% por modelo admitido (<code>docs/ensemble_escenarios_sesion5.md</code>).</p>

<h2>Fuentes y fecha de corte</h2>
<p>IPC: INE, base oct-2022=100, corte {_fmes(d['fecha_corte_ipc'])}. TC: BCU (SOAP cotizaciones), corte
{_fdia(d['tc_spot_fecha'])}. TPM: Informe de Política Monetaria del BCU, {_fmes_abr(d['tpm_fecha'])}.
Externas: FRED (BRL, DXY, Brent, CPI EEUU, curva UST). Inventario completo, rezagos medidos y fuentes
bloqueadas documentadas en <code>docs/manifest_fuentes.md</code>.</p>

</body></html>"""

    destino_html = out_dir / "informe.html"
    destino_html.write_text(html, encoding="utf-8")
    print(f"Informe HTML: {destino_html}")

    try:
        import weasyprint
        destino_pdf = out_dir / "informe.pdf"
        weasyprint.HTML(string=html, base_url=str(out_dir)).write_pdf(destino_pdf)
        print(f"Informe PDF: {destino_pdf}")
    except ImportError:
        print("weasyprint no instalado -- se genero solo el HTML (pip install weasyprint)")

    return destino_html


if __name__ == "__main__":
    construir()
