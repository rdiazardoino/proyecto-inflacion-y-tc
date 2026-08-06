-- =====================================================================
-- Proyecto Inflacion y Tipo de Cambio Uruguay
-- Esquema SQLite. Diseño point-in-time: nunca se sobrescribe historia.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 1. METADATA DE VARIABLES
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS variables (
    var_id            TEXT PRIMARY KEY,          -- ej. 'ipc_general_idx'
    nombre            TEXT NOT NULL,
    descripcion       TEXT,
    unidad            TEXT,                      -- indice, %, UYU/USD, pbs
    frecuencia        TEXT NOT NULL,             -- D, W, M, Q, A
    fuente            TEXT NOT NULL,             -- INE, BCU, FRED, ...
    fuente_url        TEXT,
    fecha_inicio      TEXT,                      -- primera obs disponible
    rezago_dias       INTEGER,                   -- dias entre ref y publicacion
    transformacion    TEXT,                      -- log, dlog, pct_m, pct_yoy, nivel
    hipotesis_econ    TEXT,                      -- por que se incluye
    modelo_destino    TEXT,                      -- inflacion / tc / ambos
    prioridad         TEXT CHECK(prioridad IN ('indispensable','importante','complementaria')),
    activa            INTEGER DEFAULT 1,
    notas             TEXT
);

-- ---------------------------------------------------------------------
-- 2. OBSERVACIONES CON VINTAGE (point-in-time)
--    Una fila por (variable, fecha_ref, vintage). Las revisiones NO
--    pisan el dato anterior: se agrega una fila con vintage nuevo.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS observaciones (
    var_id            TEXT NOT NULL REFERENCES variables(var_id),
    fecha_ref         TEXT NOT NULL,             -- ISO. Mes -> primer dia
    vintage           TEXT NOT NULL,             -- fecha de corte del dato
    valor             REAL,
    fecha_publicacion TEXT,
    fecha_descarga    TEXT NOT NULL,
    fuente            TEXT,
    estado_validacion TEXT DEFAULT 'pendiente',  -- ok / sospechoso / revisado
    revision_de       REAL,                      -- valor previo si es revision
    PRIMARY KEY (var_id, fecha_ref, vintage)
);
CREATE INDEX IF NOT EXISTS ix_obs_var_fecha ON observaciones(var_id, fecha_ref);
CREATE INDEX IF NOT EXISTS ix_obs_vintage  ON observaciones(vintage);

-- Vista de conveniencia: ultimo vintage disponible de cada dato
CREATE VIEW IF NOT EXISTS v_series_actual AS
SELECT o.var_id, o.fecha_ref, o.valor, o.vintage, o.fecha_publicacion
FROM observaciones o
JOIN (
    SELECT var_id, fecha_ref, MAX(vintage) AS mv
    FROM observaciones GROUP BY var_id, fecha_ref
) u ON o.var_id = u.var_id AND o.fecha_ref = u.fecha_ref AND o.vintage = u.mv;

-- ---------------------------------------------------------------------
-- 3. SERIES TRANSFORMADAS (cache de features)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS series_transformadas (
    var_id            TEXT NOT NULL,
    transformacion    TEXT NOT NULL,
    fecha_ref         TEXT NOT NULL,
    valor             REAL,
    vintage           TEXT NOT NULL,
    PRIMARY KEY (var_id, transformacion, fecha_ref, vintage)
);

-- ---------------------------------------------------------------------
-- 4. COMPONENTES DEL IPC (ponderaciones y aperturas)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ipc_componentes (
    componente_id     TEXT PRIMARY KEY,
    nombre            TEXT NOT NULL,
    nivel             TEXT,                      -- division / grupo / clase
    padre_id          TEXT,
    clasif_transable  TEXT,                      -- transable / no_transable
    clasif_bien_serv  TEXT,                      -- bien / servicio
    administrado      INTEGER DEFAULT 0,
    volatil           INTEGER DEFAULT 0,
    sensible_usd      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ipc_ponderaciones (
    componente_id     TEXT NOT NULL REFERENCES ipc_componentes(componente_id),
    vigencia_desde    TEXT NOT NULL,
    ponderacion       REAL NOT NULL,             -- en % del indice general
    base_indice       TEXT,                      -- ej. 'Dic 2022 = 100'
    PRIMARY KEY (componente_id, vigencia_desde)
);

-- ---------------------------------------------------------------------
-- 5. MODELOS Y PARAMETROS
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS modelos (
    modelo_id         TEXT PRIMARY KEY,          -- ej. 'sarima_ipc_v1'
    familia           TEXT,                      -- benchmark/ts/econ/ml/ensemble
    objetivo          TEXT,                      -- ipc_m / tc_prom / tc_cierre
    descripcion       TEXT,
    version           TEXT,
    fecha_alta        TEXT,
    activo            INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS parametros (
    modelo_id         TEXT NOT NULL REFERENCES modelos(modelo_id),
    fecha_estimacion  TEXT NOT NULL,
    parametro         TEXT NOT NULL,
    valor             REAL,
    error_std         REAL,
    p_valor           REAL,
    PRIMARY KEY (modelo_id, fecha_estimacion, parametro)
);

-- ---------------------------------------------------------------------
-- 6. PRONOSTICOS (registro en tiempo real, nunca se reescribe)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pronosticos (
    pronostico_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_generacion  TEXT NOT NULL,             -- cuando se corrio
    vintage_datos     TEXT NOT NULL,             -- corte de datos usado
    modelo_id         TEXT NOT NULL REFERENCES modelos(modelo_id),
    objetivo          TEXT NOT NULL,             -- ipc_m, ipc_yoy, tc_prom...
    fecha_objetivo    TEXT NOT NULL,             -- mes pronosticado
    horizonte_meses   INTEGER NOT NULL,
    escenario         TEXT DEFAULT 'base',       -- base / favorable / adverso
    valor             REAL NOT NULL,
    li_80             REAL, ls_80 REAL,
    li_95             REAL, ls_95 REAL,
    peso_ensemble     REAL,
    ajuste_experto    REAL DEFAULT 0,
    valor_pre_ajuste  REAL
);
CREATE INDEX IF NOT EXISTS ix_pron_obj ON pronosticos(objetivo, fecha_objetivo, fecha_generacion);

-- ---------------------------------------------------------------------
-- 7. ERRORES Y BACKTESTING
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS errores (
    modelo_id         TEXT NOT NULL,
    objetivo          TEXT NOT NULL,
    horizonte_meses   INTEGER NOT NULL,
    fecha_objetivo    TEXT NOT NULL,
    valor_pronosticado REAL,
    valor_observado   REAL,
    error             REAL,
    error_abs         REAL,
    error_cuad        REAL,
    acierto_direccion INTEGER,
    dentro_ic80       INTEGER,
    subperiodo        TEXT,                      -- normal / shock / cambio_regimen
    PRIMARY KEY (modelo_id, objetivo, horizonte_meses, fecha_objetivo)
);

CREATE TABLE IF NOT EXISTS metricas_backtest (
    modelo_id         TEXT NOT NULL,
    objetivo          TEXT NOT NULL,
    horizonte_meses   INTEGER NOT NULL,
    ventana           TEXT NOT NULL,             -- rolling / expanding
    periodo_desde     TEXT, periodo_hasta TEXT,
    mae REAL, rmse REAL, mape REAL, bias REAL, medae REAL,
    dir_accuracy REAL, cobertura_ic80 REAL, cobertura_ic95 REAL,
    dm_stat_vs_rw REAL, dm_pvalor_vs_rw REAL,
    n_obs INTEGER,
    fecha_calculo     TEXT,
    PRIMARY KEY (modelo_id, objetivo, horizonte_meses, ventana, periodo_desde)
);

-- ---------------------------------------------------------------------
-- 8. ESCENARIOS
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS escenarios (
    escenario_id      TEXT NOT NULL,
    fecha_generacion  TEXT NOT NULL,
    nombre            TEXT,
    probabilidad      REAL,
    supuestos         TEXT,                      -- JSON
    senales_monitoreo TEXT,                      -- JSON: que confirmaria el escenario
    PRIMARY KEY (escenario_id, fecha_generacion)
);

-- ---------------------------------------------------------------------
-- 9. AJUSTES DE JUICIO EXPERTO (siempre visibles, nunca ocultos)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ajustes_expertos (
    ajuste_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_generacion  TEXT NOT NULL,
    objetivo          TEXT NOT NULL,
    fecha_objetivo    TEXT NOT NULL,
    magnitud          REAL NOT NULL,             -- en pp o en pesos
    justificacion     TEXT NOT NULL,
    tipo_evento       TEXT,                      -- tarifa/impuesto/clima/regulatorio
    riesgo_error      TEXT,                      -- bajo/medio/alto
    responsable       TEXT
);

-- ---------------------------------------------------------------------
-- 9bis. LICITACIONES DE DEUDA (mercado primario)
--       Sustituye operativamente a las curvas de BEVSA.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS licitaciones (
    licitacion_id     TEXT PRIMARY KEY,          -- ej. 'LRM-2026-08-05-91d'
    fecha_licitacion  TEXT NOT NULL,
    emisor            TEXT NOT NULL,             -- BCU / UGD
    instrumento       TEXT NOT NULL,             -- LRM / NotaTesoro / LetraTesoro
    serie             TEXT,
    moneda            TEXT NOT NULL,             -- UYU / UI / UP / USD
    plazo_dias        INTEGER NOT NULL,
    fecha_vencimiento TEXT,
    monto_ofrecido    REAL,                      -- en millones de la moneda
    monto_demandado   REAL,
    monto_adjudicado  REAL,
    bid_to_cover      REAL,                      -- demandado / ofrecido
    tasa_corte        REAL,                      -- % anual. Real si moneda = UI/UP
    tasa_promedio     REAL,
    tasa_minima       REAL,
    precio_corte      REAL,
    desierta          INTEGER DEFAULT 0,
    fecha_descarga    TEXT NOT NULL,
    fuente_url        TEXT,
    notas             TEXT
);
CREATE INDEX IF NOT EXISTS ix_lic_fecha ON licitaciones(fecha_licitacion, moneda, plazo_dias);

-- Curva construida a plazos homogeneos a partir de las licitaciones
CREATE TABLE IF NOT EXISTS curva_primaria (
    fecha_ref         TEXT NOT NULL,
    moneda            TEXT NOT NULL,             -- UYU / UI / UP
    plazo_meses       INTEGER NOT NULL,          -- 3, 6, 12, 24, 36, 60...
    tasa              REAL NOT NULL,
    metodo_interp     TEXT,                      -- lineal / nelson_siegel / spline
    n_puntos_base     INTEGER,                   -- cuantas licitaciones alimentan el punto
    vintage           TEXT NOT NULL,
    PRIMARY KEY (fecha_ref, moneda, plazo_meses, vintage)
);

-- Break-even y forward derivados
CREATE TABLE IF NOT EXISTS metricas_mercado (
    fecha_ref         TEXT NOT NULL,
    metrica           TEXT NOT NULL,             -- breakeven_inflacion / forward_usduyu / carry_neto
    plazo_meses       INTEGER NOT NULL,
    valor             REAL,
    insumos           TEXT,                      -- JSON: que tasas y que TC spot se usaron
    vintage           TEXT NOT NULL,
    PRIMARY KEY (fecha_ref, metrica, plazo_meses, vintage)
);

-- ---------------------------------------------------------------------
-- 9ter. CAMBIOS MATERIALES (alimenta la seccion de novedades del informe semanal)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eventos (
    evento_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha             TEXT NOT NULL,
    tipo              TEXT NOT NULL,             -- tpm / tarifa / impuesto / licitacion /
                                                 -- publicacion / revision_serie / regulatorio /
                                                 -- externo
    titulo            TEXT NOT NULL,
    detalle           TEXT,
    impacto_esperado  TEXT,                      -- inflacion / tc / ambos / ninguno
    magnitud_estimada REAL,                      -- en pp si aplica
    fuente_url        TEXT,
    incluido_en_informe TEXT                     -- fecha del informe que lo reporto
);
CREATE INDEX IF NOT EXISTS ix_eventos_fecha ON eventos(fecha, tipo);

-- ---------------------------------------------------------------------
-- 10. CALENDARIO DE PUBLICACIONES
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calendario_publicaciones (
    var_id            TEXT NOT NULL,
    periodo_ref       TEXT NOT NULL,
    fecha_prevista    TEXT,
    fecha_efectiva    TEXT,
    PRIMARY KEY (var_id, periodo_ref)
);

-- ---------------------------------------------------------------------
-- 11. LOGS Y ALERTAS DE CALIDAD
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS logs_actualizacion (
    log_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha             TEXT NOT NULL,
    proceso           TEXT NOT NULL,             -- etl / modelos / reporte
    var_id            TEXT,
    estado            TEXT,                      -- ok / warning / error
    filas_nuevas      INTEGER,
    mensaje           TEXT,
    duracion_seg      REAL
);

CREATE TABLE IF NOT EXISTS alertas (
    alerta_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha             TEXT NOT NULL,
    tipo              TEXT NOT NULL,             -- serie_desactualizada / outlier /
                                                 -- fuera_de_rango / error_alto /
                                                 -- revision_importante / estructura
    severidad         TEXT,                      -- info / warning / critica
    var_id            TEXT,
    modelo_id         TEXT,
    detalle           TEXT,
    resuelta          INTEGER DEFAULT 0
);
