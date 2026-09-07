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
from src.report import glosario as glos  # noqa: E402

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
                             name=glos.nombre_modelo("ensemble_v1"),
                             hovertemplate="h=%{x}m: %{y:.2f}<extra></extra>"))
    fig.update_layout(**LAYOUT_BASE, title=dict(text=titulo, x=0, font=dict(size=13)),
                      xaxis_title="horizonte (meses)", yaxis_title=ylab, height=380)
    return fig


def _fig_trayectoria_estacional(ensemble_ipc: pd.DataFrame, est_hist: pd.Series,
                                origen: pd.Timestamp) -> go.Figure:
    fig = go.Figure()
    meses = [(origen + pd.DateOffset(months=h)).month for h in ensemble_ipc["horizonte_meses"]]
    fig.add_trace(go.Scatter(x=ensemble_ipc["horizonte_meses"], y=ensemble_ipc["valor"],
                             mode="lines+markers", name=glos.nombre_modelo("ensemble_v1") + " (proyectado)",
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


# excluido de la comparacion visual de MAE (no del backtest en si, que
# queda completo en metricas_backtest): su error es varias veces mayor
# al resto y aplasta la escala del grafico -- el mismo motivo por el que
# ensemble.py lo excluye del ensemble (EXCLUIDOS). Sesion 3: es sesgo
# puro, no una prediccion competitiva.
_MODELO_FUERA_DE_ESCALA = "bench_estacional_historica"


def _fig_performance(errores_h1: pd.DataFrame, met: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=1, cols=2, subplot_titles=(
        f"{glos.nombre_modelo('bench_rw_estacional')}: pronóstico vs. observado (h=1, backtest)",
        "MAE por horizonte — inflación (menor es mejor)"))
    fig.add_trace(go.Scatter(x=errores_h1["fecha_objetivo"], y=errores_h1["valor_observado"],
                             mode="lines", name="Observado", line=dict(color=INK2, width=1.5)), 1, 1)
    fig.add_trace(go.Scatter(x=errores_h1["fecha_objetivo"], y=errores_h1["valor_pronosticado"],
                             mode="lines", name="Pronosticado (h=1)", line=dict(color=S1, width=1.5, dash="dot")), 1, 1)
    ipc_m = met[(met["objetivo"] == "ipc_m") & (met["modelo_id"] != _MODELO_FUERA_DE_ESCALA)]
    colores = {"bench_rw_estacional": S1, "bench_media_movil_12m": S2, "bench_naive": S3,
              "phillips_reducida": S8, "sarimax_topdown": "#4a3aa7", "var2_reducido": "#008300"}
    for modelo in ipc_m["modelo_id"].unique():
        s = ipc_m[ipc_m["modelo_id"] == modelo].sort_values("horizonte_meses")
        fig.add_trace(go.Scatter(x=s["horizonte_meses"], y=s["mae"], mode="lines+markers",
                                 name=glos.nombre_modelo(modelo), line=dict(color=colores.get(modelo, INK2))),
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
                                 stackgroup="uno", name=glos.nombre_modelo(modelo),
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
    kpis.append(_kpi_card("Inflación del mes (m/m)",
        f"{d['ipc_mm']:.2f}%", f"IPC total país, dato de {_fmes_abr(d['fecha_corte_ipc'])}, sin desestacionalizar (NSA)."))
    color_meta = GOOD if abs(d["desvio_vs_meta"]) <= 1.5 else WARN
    kpis.append(_kpi_card("Inflación interanual (a/a) vs. meta",
        f"{d['ipc_aa']:.2f}%",
        f"La meta del BCU es 4,5% anual (rango tolerado 3–6%). Hoy está "
        f"{abs(d['desvio_vs_meta']):.2f} p.p. {'por debajo' if d['desvio_vs_meta']<0 else 'por encima'}.",
        color_meta))
    kpis.append(_kpi_card("Núcleo (excluye precios volátiles)",
        f"{d['nucleo_aa']:.2f}% a/a",
        f"Tendencia de fondo (últimos 3 meses, anualizada y desestacionalizada): {d['nucleo_3m_anualizada_sa']:.2f}%."))
    kpis.append(_kpi_card("Nowcast del mes en curso",
        f"{d['nowcast_mm']:.2f}%",
        f"Lo que el {glos.nombre_modelo('ensemble_v1').lower()} estima para "
        f"{_fmes_abr(d['origen_pronostico'] + pd.DateOffset(months=1))}, antes de que el INE publique el dato oficial."))
    kpis.append(_kpi_card("Tipo de cambio (spot)",
        f"{d['tc_spot']:.2f}",
        f"UYU por USD, {_fdia(d['tc_spot_fecha'])}. Variación del mes {d['tc_var_mm']:+.2f}% · del año {d['tc_var_aa']:+.2f}%."))
    if d["itcr_global"] is not None:
        kpis.append(_kpi_card("ITCR global (competitividad cambiaria)",
            f"{d['itcr_global']:.1f}", f"Base 2017=100, dato de {_fmes_abr(d['itcr_global_fecha'])}. Por debajo de 100 sugiere el peso \"caro\" en términos reales."))
    else:
        kpis.append(_kpi_card("ITCR global (competitividad cambiaria)",
            "N/D", "Ingestor en prueba contra el BCU real (ver docs/manifest_fuentes.md) — todavía sin confirmar.", INK2))
    if d["brecha_producto"] is not None:
        color_brecha = WARN if abs(d["brecha_producto"]) > 2 else INK
        kpis.append(_kpi_card("Brecha de producto (IMAE)",
            f"{d['brecha_producto']:+.2f}",
            f"Dato de {_fmes_abr(d['brecha_producto_fecha'])}. Positiva = actividad por encima de su tendencia "
            f"(presión inflacionaria); negativa = capacidad ociosa.", color_brecha))
    else:
        kpis.append(_kpi_card("Brecha de producto (IMAE)", "N/D", "Todavía no hay suficiente historia de IMAE cargada.", INK2))
    detalle_tasa = (f"TPM {d['tpm']:.2f}% ({_fmes_abr(d['tpm_fecha'])}) menos la expectativa de inflación "
                    f"a 12 meses de la Encuesta del BCU ({d['expectativa_inflacion_12m']:.1f}%, "
                    f"{_fmes_abr(d['expectativa_inflacion_12m_fecha'])})."
                    if not d["tasa_real_ex_ante_es_proxy"] else
                    f"TPM {d['tpm']:.2f}% ({_fmes_abr(d['tpm_fecha'])}) menos la meta del BCU (4,5%) — "
                    f"proxy: la Encuesta de Expectativas no está disponible este mes.")
    kpis.append(_kpi_card("Tasa real ex ante",
        f"{d['tasa_real_ex_ante']:.2f} p.p." if d["tasa_real_ex_ante"] is not None else "N/D",
        detalle_tasa))
    prob_adverso = d["escenarios"].set_index("escenario_id")["probabilidad"].get("adverso", np.nan)
    kpis.append(_kpi_card("Probabilidad del escenario adverso",
        f"{prob_adverso*100:.0f}%", "Juicio del analista, documentado en config/scenarios.yaml (no sale de un modelo estadístico).", WARN))
    color_sem, txt_sem = _semaforo(d["alertas_criticas"], d["alertas_warning"])
    kpis.append(_kpi_card("Calidad de los datos de esta corrida", "●", txt_sem, color_sem))

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
    tabla_legible = tabla_final.round(3).rename(columns={
        "horizonte_meses": "Horizonte (meses)", "fecha_objetivo": "Mes",
        "inflacion_mm": "Inflación m/m (%)", "li_80": "Piso banda 80%", "ls_80": "Techo banda 80%",
        "tc_prom": "TC promedio", "tc_li_80": "TC piso 80%", "tc_ls_80": "TC techo 80%"})
    tabla_html = tabla_legible.to_html(index=False, classes="tabla-central", border=0)

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

    glosario_html = "".join(
        f"<div class='gterm'><b>{termino}</b><p>{definicion}</p></div>"
        for termino, definicion in glos.GLOSARIO)

    aviso_manual_html = ""
    if len(d["datos_manuales"]):
        filas_manual = "".join(
            f"<tr><td>{r['nombre']}</td><td>{_fmes(pd.Timestamp(r['fecha_ref']))}</td>"
            f"<td>{_fdia(pd.Timestamp(r['fecha_descarga']))}</td><td>{r['fuente']}</td></tr>"
            for _, r in d["datos_manuales"].iterrows())
        aviso_manual_html = f"""<div class="aviso-manual">
      <b>⚠ Este informe incluye {len(d['datos_manuales'])} dato(s) cargado(s) a mano</b>, no por el
      pipeline automático (ver <code>src/etl/cargar_manual.py</code>) — el resto de las series se
      actualiza solo todos los meses, estos no.
      <table><tr><th>Serie</th><th>Dato de</th><th>Cargado el</th><th>Fuente</th></tr>{filas_manual}</table>
    </div>"""

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
  .caption {{ color:{INK2}; font-size:12px; line-height:1.5; margin:6px 2px 18px; }}
  .h2-intro {{ color:{INK2}; font-size:13px; line-height:1.5; margin:-4px 0 14px; max-width:900px; }}
  details.glosario {{ border:1px solid {GRID}; border-radius:10px; background:#fff; margin-bottom:28px; }}
  details.glosario summary {{ cursor:pointer; padding:14px 16px; font-size:14px; font-weight:600;
                              list-style:none; display:flex; align-items:center; gap:8px; }}
  details.glosario summary::before {{ content:"▸"; color:{S1}; font-size:12px; }}
  details.glosario[open] summary::before {{ content:"▾"; }}
  details.glosario summary::-webkit-details-marker {{ display:none; }}
  .glosario-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:14px 24px;
                    padding:0 16px 18px; }}
  .gterm {{ font-size:12.5px; line-height:1.5; }}
  .gterm b {{ color:{INK}; }}
  .gterm p {{ margin:2px 0 0; color:{INK2}; }}
  .aviso-manual {{ border:1px solid #e8c67a; background:#fdf6e3; border-radius:10px;
                   padding:12px 16px; margin-bottom:20px; font-size:12.5px; color:#6b5417; }}
  .aviso-manual b {{ color:#4a3900; }}
  .aviso-manual table {{ width:100%; border-collapse:collapse; margin-top:8px; font-size:12px; }}
  .aviso-manual td, .aviso-manual th {{ padding:3px 8px 3px 0; text-align:left; }}
</style></head>
<body>
  <h1>Inflación y Tipo de Cambio — Uruguay</h1>
  <div class="subtitulo">Corrida {mes} · IPC al {_fmes(d['fecha_corte_ipc'])} · TC al {_fdia(d['tc_spot_fecha'])} ·
    Origen del pronóstico: {_fmes(d['origen_pronostico'])}</div>

  {aviso_manual_html}

  <details class="glosario">
    <summary>¿Cómo leer este dashboard? — glosario de términos</summary>
    <div class="glosario-grid">{glosario_html}</div>
  </details>

  <div class="kpis">{"".join(kpis)}</div>

  <h2>Proyección: ¿qué espera el sistema para los próximos meses?</h2>
  <p class="h2-intro">La línea sólida es el {glos.nombre_modelo('ensemble_v1').lower()} — la combinación
    de modelos que mejor funcionó en el backtest (ver glosario). Las bandas de color no son un adorno:
    son el rango de incertidumbre real a cada horizonte, más ancho cuanto más lejos se proyecta.</p>
  <div class="fila">
    <div class="panel">{figs_html['fan_ipc']}</div>
    <div class="panel">{figs_html['fan_tc']}</div>
  </div>
  <div class="panel">{figs_html['trayectoria']}</div>
  <p class="caption">Este último gráfico compara la trayectoria proyectada contra el promedio histórico
    de cada mes calendario desde 2017 — sirve para distinguir un salto que es pura estacionalidad
    (ej. ajustes de tarifas que siempre ocurren en enero) de una aceleración genuina.</p>

  <h2>Composición del pronóstico oficial</h2>
  <p class="h2-intro">Cada franja de color es el peso (0 a 100%) que aporta un modelo al ensemble en
    ese horizonte. <b>Hoy el 100% del peso está en los benchmarks</b> (ver glosario) — ningún modelo con
    contenido económico (Phillips, SARIMAX, VAR) le ganó de forma significativa en el backtest, así que
    el sistema no les da peso en vez de fingir que aportan algo que no está probado. Ver la sección de
    Performance más abajo.</p>
  <div class="fila">
    <div class="panel">{figs_html['pesos_ipc']}</div>
    <div class="panel">{figs_html['pesos_tc']}</div>
  </div>

  <h2>Escenarios: ¿y si el contexto externo es distinto?</h2>
  <p class="h2-intro">No son ajustes manuales del resultado: es el mismo modelo (VAR(2) inflación-TC)
    corriendo tres veces, cada vez con una trayectoria distinta de dólar/real brasileño y dólar global.
    La probabilidad de cada uno es un juicio documentado del analista, no una salida estadística del
    modelo — se explicita así para no confundir un supuesto con un resultado.</p>
  <div class="panel">{figs_html['escenarios']}</div>
  <div class="panel">
    <table class="escenarios">
      <tr><th>Escenario</th><th>Prob.</th><th>Supuestos</th><th>Señales de confirmación</th></tr>
      {escenarios_tabla}
    </table>
  </div>

  <h2>Divisiones del IPC</h2>
  <p class="h2-intro">Variación mensual de cada una de las 13 divisiones del IPC, últimos 24 meses.
    Colores más intensos = variaciones más grandes ese mes, positivas (naranja) o negativas (verde).</p>
  <div class="panel">{figs_html['heatmap']}</div>

  <h2>Performance del modelo: ¿qué tan bien funcionó en el pasado?</h2>
  <p class="h2-intro">Panel izquierdo: lo que el {glos.nombre_modelo('bench_rw_estacional').lower()}
    pronosticaba un mes antes, comparado contra lo que realmente pasó — si las dos líneas se despegan
    mucho, el modelo viene fallando. Panel derecho: el error promedio (MAE, ver glosario) de cada modelo
    por horizonte — la línea más abajo es la más precisa históricamente. Esta es la prueba que decide
    cuánto peso recibe cada modelo en el ensemble (se excluye del gráfico el
    «{glos.nombre_modelo('bench_estacional_historica').lower()}»: su error es varias veces mayor al
    resto y aplastaría la escala — por eso tampoco recibe peso en el ensemble).</p>
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
