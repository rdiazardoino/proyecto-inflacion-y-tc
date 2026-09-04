"""
Sesion 6 - Orquestador de la corrida mensual de analisis (plan Seccion 3.1
y 12). Corre DESPUES del ETL (que vive en GitHub Actions, ver
src/etl/run_etl.py) sobre los datos ya cargados en db/proyecto.db.

Pasos: backtest de benchmarks -> backtest de modelos economicos ->
ensemble + escenarios -> dashboard -> informe. Cada paso se aisla (si uno
falla, los siguientes igual se intentan) y queda registrado en
logs_actualizacion, mismo patron que src/etl/run_etl.py.

Uso: python src/forecast/run_forecast.py
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.etl import db  # noqa: E402


def _paso(con, nombre: str, fn) -> bool:
    t0 = time.time()
    try:
        fn()
        db.log(con, "modelos", "ok", var_id=nombre, duracion_seg=round(time.time() - t0, 1))
        print(f"[forecast] {nombre}: ok ({time.time()-t0:.1f}s)")
        return True
    except Exception as e:                                # noqa: BLE001
        db.log(con, "modelos", "error", var_id=nombre,
              mensaje=f"{type(e).__name__}: {e}", duracion_seg=round(time.time() - t0, 1))
        db.alerta(con, "error_alto", "critica", f"{nombre} fallo: {e}", modelo_id=nombre)
        print(f"[forecast] ERROR en {nombre}: {e}")
        traceback.print_exc()
        return False


def main() -> None:
    con = db.conectar()
    print("[forecast] corrida de analisis iniciada")

    from src.models import backtest, backtest_sesion4, run_sesion5
    from src.report import build_dashboard, build_informe

    ok = _paso(con, "backtest_benchmarks", backtest.main)
    ok &= _paso(con, "backtest_modelos_economicos", backtest_sesion4.main)
    ok &= _paso(con, "ensemble_escenarios", run_sesion5.main)
    ok &= _paso(con, "dashboard", build_dashboard.construir)
    ok &= _paso(con, "informe", build_informe.construir)

    db.log(con, "modelos", "ok" if ok else "warning",
          mensaje="corrida de analisis completa" + ("" if ok else " (con errores, ver arriba)"))
    con.close()
    print(f"[forecast] {'completa' if ok else 'completa con errores'}")


if __name__ == "__main__":
    main()
