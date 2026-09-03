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
    mae_ipc_completo = met[(met["objetivo"] == "ipc_m") & (met["horizonte_meses"] == 1)]
    tabla_mae = "".join(
        f"<tr><td>{r['modelo_id'].replace('bench_','')}</td>"
        f"<td>{r['mae']:.3f}</td><td>{r['bias']:+.3f}</td>"
        f"<td>{r['dir_accuracy']*100:.0f}%</td><td>{r['n_obs']}</td></tr>"
        for _, r in met[met["objetivo"] == "ipc_m"].sort_values("horizonte_meses").iterrows()
        if r["horizonte_meses"] == 1)

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

<h2>Resumen ejecutivo</h2>
<p>Inflación m/m {d['ipc_mm']:.2f}% ({_fmes_abr(d['fecha_corte_ipc'])}, IPC total país base oct-2022=100, NSA),
a/a {d['ipc_aa']:.2f}% ({d['desvio_vs_meta']:+.2f} p.p. vs. meta BCU 4,5%, rango 3-6%). Núcleo (IPC-CE) a/a
{d['nucleo_aa']:.2f}%, tendencia 3m anualizada SA {d['nucleo_3m_anualizada_sa']:.2f}%. TC spot {d['tc_spot']:.2f}
({_fdia(d['tc_spot_fecha'])}), TPM vigente {d['tpm']:.2f}% (IPOM {_fmes_abr(d['tpm_fecha'])}).</p>

<h3>Tabla de nodos — pronóstico oficial (ensemble v1)</h3>
{_tabla_nodos(d['ensemble_ipc'], d['ensemble_tc'])}
<p class="nota">Definiciones: inflación m/m del IPC total país base oct-2022=100, sin desestacionalizar,
del mes del nodo indicado. TC = promedio simple del interbancario fondo del mismo mes. Intervalos 80% =
banda empírica v1 (desvío histórico de errores del backtest + dispersión entre modelos admitidos del
ensemble), no Monte Carlo paramétrico.</p>

<h2>Qué cambió</h2>
<p class="pendiente">Esta es la primera corrida real del sistema (sesión 6): no hay una corrida anterior
con la que comparar el pronóstico ni calcular la "sorpresa" del dato observado contra el nowcast previo.
A partir de la próxima corrida mensual esta sección compara el dato efectivamente publicado contra lo
que el sistema había proyectado el mes anterior.</p>

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
({_fmes_abr(d['tpm_fecha'])}) — <span class="pendiente">único punto histórico disponible: la serie
mensual completa de la TPM está bloqueada (ver <code>docs/manifest_fuentes.md</code>)</span>. Tasa real
ex ante (proxy): TPM − meta BCU = <b>{d['tasa_real_ex_ante']:.2f} p.p.</b> (sustituye la expectativa de
inflación a 12 meses de la Encuesta del BCU, no disponible, por la meta puntual — una aproximación, no
un dato de mercado).</p>

<h2>Contexto regional y global</h2>
<p class="pendiente">Sección parcial: no hay datos fiscales cargados (resultado del sector público) ni
indicador de actividad (IMAE) para caracterizar la brecha de producto regional. Lo disponible: USD/BRL,
DXY, Brent, CPI EEUU y la curva de rendimientos del Tesoro americano (2a/3m/10a), usados como exógenas
de los modelos de las sesiones 4-5. Ampliar esta sección requiere cargar series fiscales y de actividad
(tarea de ingesta, no de modelado).</p>

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
<li><b>De datos:</b> Encuesta de Expectativas del BCU, ITCR e IMAE bloqueados o no cargados; la Phillips
y las probabilidades de escenario son aproximaciones mientras eso no se resuelva.</li>
<li><b>De mercado (escenario adverso, {prob.get('adverso',0)*100:.0f}%):</b> depreciación regional/global
sostenida — ver señales de confirmación arriba.</li>
</ul>

<h2>Implicancias de inversión</h2>
<p class="pendiente">Sección limitada en esta primera corrida: no hay curva de rendimientos en UI ni
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
<p><b>Datos:</b> ETL en GitHub Actions (33 series: INE, BCU, FRED), point-in-time con vintages
(<code>docs/manifest_fuentes.md</code>). <b>EDA:</b> estacionalidad, quiebres estructurales (Chow,
confirmados sep-2020 y oct-2022), pass-through preliminar (<code>docs/eda_sesion2.md</code>).
<b>Benchmarks:</b> random walk, random walk estacional, media móvil 12m, naive, RW+drift
(<code>docs/backtest_sesion3.md</code>). <b>Modelos económicos:</b> SARIMAX top-down, Phillips reducida
(corrección de error hacia la meta BCU), VAR(2) reducido TC-inflación — todos en ventana rolling de 96
meses, ninguno supera al benchmark (<code>docs/backtest_sesion4.md</code>). <b>Ensemble:</b> promedio
ponderado por inverso del MAE del régimen 2022+, piso de 10% por modelo admitido
(<code>docs/ensemble_escenarios_sesion5.md</code>).</p>

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
