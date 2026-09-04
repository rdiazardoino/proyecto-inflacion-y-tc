"""
Sesion 6 - Dashboard HTML interactivo (plan Seccion 11.1). Archivo unico
autonomo (Plotly embebido inline, sin llamadas a red para verlo).

Uso: python src/report/build_dashboard.py
Salida: outputs/dashboards/YYYY-MM/dashboard.html (+ forecasts.csv al lado)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.report import datos_dashboard as dd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

MESES_ES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
           7: "julio", 8: "agosto", 9: "setiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
MESES_ES_ABR = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
               7: "jul", 8: "ago", 9: "set", 10: "oct", 11: "nov", 12: "dic"}


def _fmes(fecha: pd.Timestamp) -> str:
    """'julio de 2026' -- strftime %B da el nombre en ingles en este sistema."""
    return f"{MESES_ES[fecha.month]} de {fecha.year}"


def _fmes_abr(fecha: pd.Timestamp) -> str:
    return f"{MESES_ES_ABR[fecha.month]}-{fecha.strftime('%y')}"


def _fdia(fecha: pd.Timestamp) -> str:
    return f"{fecha.day:02d} de {MESES_ES[fecha.month]} de {fecha.year}"

# Paleta del skill de dataviz del proyecto (light mode; ver docs/eda_sesion2.md)
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
GRID = "#e8e7e3"
S1, S2, S3, S4, S8 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e34948"
GOOD, WARN, BAD = "#1baf7a", "#eda100", "#e34948"

LAYOUT_BASE = dict(
    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
    font=dict(color=INK, size=12, family="system-ui, -apple-system, sans-serif"),
    margin=dict(l=55, r=25, t=55, b=45),
    xaxis=dict(gridcolor=GRID, zeroline=False, linecolor=INK2),
    yaxis=dict(gridcolor=GRID, zeroline=False, linecolor=INK2),
    legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.18),
)


def _fig_fan(df: pd.DataFrame, titulo: str, ylab: str, meta: float | None = None,
            rango: tuple[float, float] | None = None) -> go.Figure:
    fig = go.Figure()
    if rango:
        fig.add_hrect(y0=rango[0], y1=rango[1], fillcolor=S3, opacity=0.08, line_width=0,
                      annotation_text="rango meta BCU", annotation_position="top left",
                      annotation_font_size=10, annotation_font_color=INK2)
    if meta:
        fig.add_hline(y=meta, line_dash="dot", line_color=INK2, line_width=1)
    h = df["horizonte_meses"]
    fig.add_trace(go.Scatter(x=list(h) + list(h[::-1]), y=list(df["ls_95"]) + list(df["li_95"][::-1]),
                             fill="toself", fillcolor="rgba(42,120,214,0.08)",
                             line=dict(width=0), name="banda 95%", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=list(h) + list(h[::-1]), y=list(df["ls_80"]) + list(df["li_80"][::-1]),
                             fill="toself", fillcolor="rgba(42,120,214,0.20)",
                             line=dict(width=0), name="banda 80%", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=h, y=df["valor"], mode="lines+markers",
                             line=dict(color=S1, width=3), marker=dict(size=8),
                             name="Ensemble v1", hovertemplate="h=%{x}m: %{y:.2f}<extra></extra>"))
    fig.update_layout(**LAYOUT_BASE, title=dict(text=titulo, x=0, font=dict(size=13)),
                      xaxis_title="horizonte (meses)", yaxis_title=ylab, height=380)
    return fig


def _fig_trayectoria_estacional(ensemble_ipc: pd.DataFrame, est_hist: pd.Series,
                                origen: pd.Timestamp) -> go.Figure:
    fig = go.Figure()
    meses = [(origen + pd.DateOffset(months=h)).month for h in ensemble_ipc["horizonte_meses"]]
    fig.add_trace(go.Scatter(x=ensemble_ipc["horizonte_meses"], y=ensemble_ipc["valor"],
                             mode="lines+markers", name="Ensemble v1 (proyectado)",
                             line=dict(color=S1, width=3), marker=dict(size=8)))
    fig.add_trace(go.Scatter(x=ensemble_ipc["horizonte_meses"],
                             y=[est_hist.get(m, np.nan) for m in meses],
                             mode="markers", name="Estacionalidad histórica 2017+ (mismo mes)",
                             marker=dict(color=S2, size=10, symbol="diamond")))
    fig.update_layout(**LAYOUT_BASE, title=dict(text="Trayectoria proyectada vs. estacionalidad histórica del mismo mes calendario",
                                                x=0, font=dict(size=13)),
                      xaxis_title="horizonte (meses)", yaxis_title="inflación m/m (%)", height=360)
    return fig


def _fig_heatmap(divs: pd.DataFrame) -> go.Figure:
    cols = [f"{c} {dd.DIV_NOMBRE[c][:22]}" for c in divs.columns]
    z = divs.T.values
    lim = np.nanmax(np.abs(z))
    fig = go.Figure(go.Heatmap(
        z=z, x=[_fmes_abr(d) for d in divs.index], y=cols,
        colorscale=[[0, S1], [0.5, "#f0efec"], [1, S8]], zmid=0, zmin=-lim, zmax=lim,
        colorbar=dict(title="% m/m", tickfont=dict(color=INK2)),
        hovertemplate="%{y}<br>%{x}: %{z:.2f}%<extra></extra>"))
    base = {**LAYOUT_BASE, "xaxis": {**LAYOUT_BASE["xaxis"], "tickangle": -45}}
    fig.update_layout(**base, title=dict(text="IPC por división — variación m/m, últimos 24 meses",
                                         x=0, font=dict(size=13)), height=460)
    return fig


def _fig_performance(errores_h1: pd.DataFrame, met: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=1, cols=2, subplot_titles=(
        "RW estacional: pronóstico vs. observado (h=1, backtest)",
        "MAE por horizonte — inflación (todos los modelos)"))
    fig.add_trace(go.Scatter(x=errores_h1["fecha_objetivo"], y=errores_h1["valor_observado"],
                             mode="lines", name="Observado", line=dict(color=INK2, width=1.5)), 1, 1)
    fig.add_trace(go.Scatter(x=errores_h1["fecha_objetivo"], y=errores_h1["valor_pronosticado"],
                             mode="lines", name="Pronosticado (h=1)", line=dict(color=S1, width=1.5, dash="dot")), 1, 1)
    ipc_m = met[met["objetivo"] == "ipc_m"]
    colores = {"bench_rw_estacional": S1, "bench_media_movil_12m": S2, "bench_naive": S3,
              "bench_estacional_historica": S4, "phillips_reducida": S8,
              "sarimax_topdown": "#4a3aa7", "var2_reducido": "#008300"}
    for modelo in ipc_m["modelo_id"].unique():
        s = ipc_m[ipc_m["modelo_id"] == modelo].sort_values("horizonte_meses")
        fig.add_trace(go.Scatter(x=s["horizonte_meses"], y=s["mae"], mode="lines+markers",
                                 name=modelo.replace("bench_", ""), line=dict(color=colores.get(modelo, INK2))),
                     1, 2)
    fig.update_layout(**LAYOUT_BASE, height=380, showlegend=True,
                      title=dict(text="", x=0))
    fig.update_xaxes(gridcolor=GRID)
    fig.update_yaxes(gridcolor=GRID)
    return fig


def _fig_pesos(pesos: pd.DataFrame, objetivo: str, titulo: str) -> go.Figure:
    sub = pesos[pesos["objetivo"] == objetivo]
    fig = go.Figure()
    colores = {"bench_rw_estacional": S1, "bench_media_movil_12m": S2, "bench_naive": S3,
              "bench_rw": S1, "bench_rw_drift": S2}
    for modelo in sorted(sub["modelo_id"].unique()):
        s = sub[sub["modelo_id"] == modelo].sort_values("horizonte_meses")
        fig.add_trace(go.Scatter(x=s["horizonte_meses"], y=s["peso_ensemble"], mode="lines",
                                 stackgroup="uno", name=modelo.replace("bench_", ""),
                                 line=dict(width=0.5, color=colores.get(modelo, INK2))))
    base = {**LAYOUT_BASE, "yaxis": {**LAYOUT_BASE["yaxis"], "range": [0, 1]}}
    fig.update_layout(**base, title=dict(text=titulo, x=0, font=dict(size=13)),
                      xaxis_title="horizonte (meses)", yaxis_title="peso", height=320)
    return fig


def _fig_escenarios(escenarios: pd.DataFrame) -> go.Figure:
    colores = {"base": S1, "benigno": S3, "adverso": S8}
    fig = go.Figure(go.Bar(
        x=escenarios["nombre"], y=escenarios["probabilidad"] * 100,
        marker_color=[colores.get(e, INK2) for e in escenarios["escenario_id"]],
        text=[f"{p*100:.0f}%" for p in escenarios["probabilidad"]], textposition="outside"))
    base = {**LAYOUT_BASE, "yaxis": {**LAYOUT_BASE["yaxis"], "range": [0, 80]}}
    fig.update_layout(**base, title=dict(text="Probabilidad de cada escenario (juicio documentado)",
                                         x=0, font=dict(size=13)),
                      yaxis_title="probabilidad (%)", height=320)
    return fig


def _kpi_card(titulo: str, valor: str, detalle: str, color: str = INK) -> str:
    return f"""<div class="kpi">
      <div class="kpi-titulo">{titulo}</div>
      <div class="kpi-valor" style="color:{color}">{valor}</div>
      <div class="kpi-detalle">{detalle}</div>
    </div>"""


def _semaforo(criticas: int, warnings: int) -> tuple[str, str]:
    if criticas > 0:
        return BAD, f"{criticas} crítica(s), {warnings} warning(s)"
    if warnings > 0:
        return WARN, f"0 críticas, {warnings} warning(s)"
    return GOOD, "sin alertas abiertas"


def construir(mes: str | None = None) -> Path:
    mes = mes or pd.Timestamp.today().strftime("%Y-%m")
    out_dir = ROOT / "outputs" / "dashboards" / mes
    out_dir.mkdir(parents=True, exist_ok=True)

    d = dd.cargar()

    kpis = []
    kpis.append(_kpi_card("Inflación m/m",
        f"{d['ipc_mm']:.2f}%", f"IPC total país, {_fmes_abr(d['fecha_corte_ipc'])}, NSA. Sorpresa: N/D (primera corrida)"))
    color_meta = GOOD if abs(d["desvio_vs_meta"]) <= 1.5 else WARN
    kpis.append(_kpi_card("Inflación a/a vs. meta",
        f"{d['ipc_aa']:.2f}%", f"Meta BCU 4,5% (rango 3-6%). Desvío: {d['desvio_vs_meta']:+.2f} p.p.", color_meta))
    kpis.append(_kpi_card("Núcleo (IPC-CE)",
        f"{d['nucleo_aa']:.2f}% a/a", f"3m anualizada SA (STL): {d['nucleo_3m_anualizada_sa']:.2f}%"))
    kpis.append(_kpi_card("Nowcast del mes en curso",
        f"{d['nowcast_mm']:.2f}%", f"Ensemble v1, h=1 desde {_fmes_abr(d['origen_pronostico'])}"))
    kpis.append(_kpi_card("TC spot",
        f"{d['tc_spot']:.2f}", f"{_fdia(d['tc_spot_fecha'])}. Var. m/m {d['tc_var_mm']:+.2f}% · a/a {d['tc_var_aa']:+.2f}%"))
    kpis.append(_kpi_card("ITCR (desvío vs. media 5a)",
        "N/D", "Bloqueado: portal del BCU requiere JavaScript (ver manifest_fuentes.md)", INK2))
    kpis.append(_kpi_card("Break-even 12m (BEVSA)",
        "N/D", "Fuera de alcance v1 (plan, decisión #2)", INK2))
    kpis.append(_kpi_card("Tasa real ex ante",
        f"{d['tasa_real_ex_ante']:.2f} p.p." if d["tasa_real_ex_ante"] is not None else "N/D",
        f"TPM {d['tpm']:.2f}% ({_fmes_abr(d['tpm_fecha'])}, IPOM) − meta 4,5% (proxy de Eπ12m, encuesta bloqueada)"))
    prob_adverso = d["escenarios"].set_index("escenario_id")["probabilidad"].get("adverso", np.nan)
    kpis.append(_kpi_card("Prob. escenario adverso",
        f"{prob_adverso*100:.0f}%", "Juicio documentado (config/scenarios.yaml)", WARN))
    color_sem, txt_sem = _semaforo(d["alertas_criticas"], d["alertas_warning"])
    kpis.append(_kpi_card("Calidad de datos", "●", txt_sem, color_sem))

    fig_fan_ipc = _fig_fan(d["ensemble_ipc"], "Inflación m/m — ensemble v1 (nodos 1/6/12/24)",
                          "inflación m/m (%)", meta=None, rango=None)
    fig_fan_tc = _fig_fan(d["ensemble_tc"], "TC promedio — ensemble v1 (nodos 1/6/12/24)", "UYU/USD")
    fig_trayectoria = _fig_trayectoria_estacional(d["ensemble_ipc"], d["estacional_historica_mes"], d["origen_pronostico"])
    fig_heatmap = _fig_heatmap(d["divisiones_mm"])
    fig_performance = _fig_performance(d["errores_h1_ipc"], d["metricas_backtest"])
    fig_pesos_ipc = _fig_pesos(d["pesos_ensemble"], "ipc_m", "Pesos del ensemble — inflación")
    fig_pesos_tc = _fig_pesos(d["pesos_ensemble"], "tc_prom", "Pesos del ensemble — TC")
    fig_escenarios = _fig_escenarios(d["escenarios"])

    # tabla central + CSV
    tabla = d["ensemble_ipc"][["horizonte_meses", "fecha_objetivo", "valor", "li_80", "ls_80"]].copy()
    tabla.columns = ["horizonte_meses", "fecha_objetivo", "inflacion_mm", "li_80", "ls_80"]
    tabla_tc = d["ensemble_tc"][["horizonte_meses", "valor", "li_80", "ls_80"]].copy()
    tabla_tc.columns = ["horizonte_meses", "tc_prom", "tc_li_80", "tc_ls_80"]
    tabla_final = tabla.merge(tabla_tc, on="horizonte_meses")
    tabla_final.to_csv(out_dir / "forecasts.csv", index=False)
    tabla_html = tabla_final.round(3).to_html(index=False, classes="tabla-central", border=0)

    figs_html = {}
    primero = True
    for nombre, fig in [("fan_ipc", fig_fan_ipc), ("fan_tc", fig_fan_tc),
                        ("trayectoria", fig_trayectoria), ("heatmap", fig_heatmap),
                        ("performance", fig_performance), ("pesos_ipc", fig_pesos_ipc),
                        ("pesos_tc", fig_pesos_tc), ("escenarios", fig_escenarios)]:
        figs_html[nombre] = fig.to_html(full_html=False, include_plotlyjs="inline" if primero else False,
                                        config={"displaylogo": False})
        primero = False

    escenarios_tabla = "".join(
        f"<tr><td>{r['nombre']}</td><td>{r['probabilidad']*100:.0f}%</td>"
        f"<td><pre>{r['supuestos']}</pre></td><td><pre>{r['senales_monitoreo']}</pre></td></tr>"
        for _, r in d["escenarios"].iterrows())

    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>Inflación y TC Uruguay — {mes}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; background:{SURFACE}; color:{INK};
         margin:0; padding:24px 32px 60px; }}
  h1 {{ font-size:22px; margin-bottom:2px; }}
  .subtitulo {{ color:{INK2}; font-size:13px; margin-bottom:24px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:32px; }}
  .kpi {{ border:1px solid {GRID}; border-radius:10px; padding:14px; background:#fff; }}
  .kpi-titulo {{ font-size:11px; color:{INK2}; text-transform:uppercase; letter-spacing:.02em; }}
  .kpi-valor {{ font-size:24px; font-weight:600; margin:4px 0; }}
  .kpi-detalle {{ font-size:11px; color:{INK2}; line-height:1.4; }}
  .panel {{ border:1px solid {GRID}; border-radius:10px; padding:12px; margin-bottom:20px; background:#fff; }}
  .fila {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  h2 {{ font-size:15px; margin:32px 0 12px; border-bottom:2px solid {GRID}; padding-bottom:6px; }}
  table.tabla-central {{ width:100%; border-collapse:collapse; font-size:13px; }}
  table.tabla-central th, table.tabla-central td {{ padding:6px 10px; border-bottom:1px solid {GRID}; text-align:right; }}
  table.tabla-central th {{ text-align:right; color:{INK2}; font-weight:600; }}
  table.escenarios td {{ vertical-align:top; padding:8px; border-bottom:1px solid {GRID}; font-size:12px; }}
  table.escenarios pre {{ white-space:pre-wrap; font-family:inherit; font-size:11px; color:{INK2}; margin:0; }}
  a.descarga {{ color:{S1}; text-decoration:none; font-size:13px; }}
  .footer {{ color:{INK2}; font-size:11px; margin-top:40px; border-top:1px solid {GRID}; padding-top:12px; }}
</style></head>
<body>
  <h1>Inflación y Tipo de Cambio — Uruguay</h1>
  <div class="subtitulo">Corrida {mes} · IPC al {_fmes(d['fecha_corte_ipc'])} · TC al {_fdia(d['tc_spot_fecha'])} ·
    Origen del pronóstico: {_fmes(d['origen_pronostico'])}</div>

  <div class="kpis">{"".join(kpis)}</div>

  <h2>Proyección — ensemble v1 (pronóstico oficial)</h2>
  <div class="fila">
    <div class="panel">{figs_html['fan_ipc']}</div>
    <div class="panel">{figs_html['fan_tc']}</div>
  </div>
  <div class="panel">{figs_html['trayectoria']}</div>

  <h2>Composición del ensemble</h2>
  <div class="fila">
    <div class="panel">{figs_html['pesos_ipc']}</div>
    <div class="panel">{figs_html['pesos_tc']}</div>
  </div>

  <h2>Escenarios</h2>
  <div class="panel">{figs_html['escenarios']}</div>
  <div class="panel">
    <table class="escenarios">
      <tr><th>Escenario</th><th>Prob.</th><th>Supuestos</th><th>Señales de confirmación</th></tr>
      {escenarios_tabla}
    </table>
  </div>

  <h2>Divisiones del IPC</h2>
  <div class="panel">{figs_html['heatmap']}</div>

  <h2>Performance del modelo (backtest, sesiones 3-4)</h2>
  <div class="panel">{figs_html['performance']}</div>

  <h2>Tabla central de pronósticos</h2>
  <div class="panel">
    {tabla_html}
    <p><a class="descarga" href="forecasts.csv" download>⬇ descargar forecasts.csv</a></p>
  </div>

  <div class="footer">
    Generado automáticamente. Definiciones: inflación m/m y a/a = variación del IPC total país
    base oct-2022=100, sin desestacionalizar salvo que se indique SA. Núcleo = IPC-CE oficial del INE.
    TC = promedio simple del interbancario fondo. Intervalos 80/95% = banda empírica v1 (desvío histórico
    de errores del backtest + dispersión entre modelos admitidos), no Monte Carlo paramétrico (v2, plan §8.5).
    Metodología completa en docs/backtest_sesion3.md, docs/backtest_sesion4.md, docs/ensemble_escenarios_sesion5.md.
  </div>
</body></html>"""

    destino = out_dir / "dashboard.html"
    destino.write_text(html, encoding="utf-8")
    print(f"Dashboard: {destino} ({destino.stat().st_size / 1e6:.1f} MB)")
    print(f"CSV: {out_dir / 'forecasts.csv'}")
    return destino


if __name__ == "__main__":
    construir()
