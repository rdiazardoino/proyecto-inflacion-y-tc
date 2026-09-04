"""
Glosario y nombres legibles compartidos entre dashboard e informe -- pedido
explicito del usuario (4-sep-2026): "el dashboard y el informe deben ser
mas explicativos y descriptivos [...] ayudate en base a como hacen en
Exante". Un solo lugar para las definiciones evita que las dos salidas
expliquen el mismo termino con palabras distintas.
"""

from __future__ import annotations

# var_id / modelo_id -> nombre para mostrar (leyendas de graficos, tablas)
NOMBRE_MODELO: dict[str, str] = {
    "ensemble_v1": "Ensemble (pronóstico oficial)",
    "bench_rw": "Random Walk",
    "bench_rw_drift": "Random Walk con tendencia",
    "bench_rw_estacional": "Random Walk estacional",
    "bench_media_movil_12m": "Media móvil 12 meses",
    "bench_naive": "Naive (repite el mes anterior)",
    "bench_estacional_historica": "Estacional histórico",
    "phillips_reducida": "Curva de Phillips (corrección de error)",
    "sarimax_topdown": "SARIMAX top-down",
    "var2_reducido": "VAR(2) inflación-TC",
}


def nombre_modelo(modelo_id: str) -> str:
    return NOMBRE_MODELO.get(modelo_id, modelo_id.replace("bench_", "").replace("_", " "))


# (termino, definicion) en el orden en que conviene leerlos -- no alfabetico.
GLOSARIO: list[tuple[str, str]] = [
    ("Ensemble (pronóstico oficial)",
     "El número que este sistema entrega como pronóstico no sale de un solo modelo: es un promedio "
     "de varios, ponderado según qué tan bien acertó cada uno en el pasado (ver «backtest» y «MAE» "
     "más abajo). Un modelo que se equivocó menos en la prueba histórica pesa más en el promedio."),
    ("Random Walk (RW)",
     "El modelo más simple posible: supone que el valor del próximo mes va a ser igual al de este mes "
     "(o sigue una tendencia constante, «RW con tendencia»). No usa ninguna teoría económica. Sirve "
     "como vara de comparación obligatoria — un modelo más sofisticado solo vale la pena si le gana "
     "de forma consistente, y en la práctica eso es sorprendentemente difícil de lograr, sobre todo "
     "en tipo de cambio."),
    ("Benchmark",
     "Cualquiera de los modelos «de referencia» (Random Walk, media móvil, naive, estacional "
     "histórico) contra los que se miden los modelos con más contenido económico (Phillips, SARIMAX, "
     "VAR). Si un modelo económico no le gana a su benchmark, el sistema lo dice explícitamente en "
     "vez de mostrarlo como si fuera superior."),
    ("Backtest",
     "Una prueba histórica honesta: se simula, mes a mes desde 2016, qué hubiera pronosticado cada "
     "modelo usando ÚNICAMENTE los datos que existían hasta ese momento (nunca información posterior "
     "al mes que se está pronosticando). Así se mide qué tan bien funciona cada modelo en condiciones "
     "reales, no con el diario del lunes."),
    ("MAE (error absoluto medio)",
     "El promedio de cuánto se equivocó un modelo, en valor absoluto, a lo largo de todo el backtest. "
     "Un MAE de 0,40 en inflación mensual quiere decir que, en promedio, el pronóstico erró por 0,40 "
     "puntos porcentuales. Menor MAE = modelo más preciso históricamente (no garantiza que lo siga "
     "siendo)."),
    ("Banda de confianza (80% / 95%)",
     "El rango donde se espera, con 80% o 95% de probabilidad, que caiga el valor real — calculado a "
     "partir de qué tan dispersos fueron los errores de los modelos en el backtest. Una banda ancha "
     "no es un defecto del sistema: es información real sobre cuánta incertidumbre hay a ese "
     "horizonte."),
    ("Nowcast",
     "La estimación del mes que todavía no cerró (horizonte de 1 mes) — el número más next-day-live "
     "que da el sistema, antes de que el INE publique el dato oficial."),
    ("Núcleo (IPC-CE)",
     "El índice de precios excluyendo frutas, verduras y combustibles — los componentes más volátiles "
     "del IPC. Sirve para ver la tendencia de fondo de la inflación sin el ruido de shocks puntuales "
     "(una helada, un cambio en el precio del petróleo)."),
    ("SA / NSA",
     "«Desestacionalizado» (SA) o «sin desestacionalizar» (NSA): si a la serie se le quitó o no el "
     "efecto de patrones que se repiten todos los años en la misma época (por ejemplo, ajustes "
     "tarifarios que siempre ocurren en enero)."),
    ("TPM (Tasa de Política Monetaria)",
     "La tasa de interés de referencia que fija el Banco Central — la principal herramienta con la "
     "que intenta influir sobre la inflación y el tipo de cambio."),
    ("Tasa real ex ante",
     "TPM menos la inflación que se espera hacia adelante. Si es alta, la política monetaria está "
     "siendo contractiva (frena la economía); si es baja o negativa, es expansiva."),
    ("ITCR (Índice de Tipo de Cambio Real)",
     "Mide competitividad cambiaria: compara el tipo de cambio nominal contra la inflación relativa "
     "de Uruguay frente a sus socios comerciales. Un ITCR bajo sugiere que el peso está \"caro\" en "
     "términos reales frente al resto del mundo."),
    ("Brecha de producto",
     "La diferencia entre el nivel real de actividad económica (medido acá con el IMAE) y su nivel "
     "\"potencial\" o de tendencia de largo plazo. Positiva = la economía está por encima de su "
     "potencial (presión inflacionaria); negativa = hay capacidad ociosa."),
    ("Escenario",
     "Una trayectoria alternativa de variables externas (el dólar frente al real brasileño, el dólar "
     "global) que se le impone a un modelo para ver qué pronosticaría si el contexto regional/global "
     "fuera distinto al más probable (escenario base). No es un ajuste manual del resultado — es el "
     "mismo modelo corriendo con otro insumo."),
]
