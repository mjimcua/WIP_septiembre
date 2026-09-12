-- SFF v2 — DDL del modelo (PK/FK declaradas para herramientas de modelado).
-- Importable en DBeaver, SchemaSpy, pgModeler, MySQL Workbench.
-- Regenerar con: python generate_model.py <ruta_db>

-- El juez: tecnica x horizonte x origen.
CREATE TABLE [sff_backtest_pred] (
    [fs_id_L2] NVARCHAR(255) NULL,
    [tecnica] NVARCHAR(255) NULL,
    [h] BIGINT NULL,
    [origen] NVARCHAR(255) NULL,
    [mes_objetivo] NVARCHAR(255) NULL,
    [pred] FLOAT NULL,
    [real] FLOAT NULL,
    [abs_err_pp] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

CREATE TABLE [sff_backtest_pred_fu] (
    [fu_key] BIGINT NULL,
    [fs_id] NVARCHAR(255) NULL,
    [fs_id_L2] NVARCHAR(255) NULL,
    [period] NVARCHAR(255) NULL,
    [h] BIGINT NULL,
    [tecnica_id] NVARCHAR(255) NULL,
    [tasa_pred] FLOAT NULL,
    [tasa_real_fu] FLOAT NULL,
    [abs_err_pp] FLOAT NULL,
    [err_usd] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

-- Gate y phi por pool: hay motor o es la moneda.
CREATE TABLE [sff_diag_dinamica] (
    [fs_id_L2] NVARCHAR(255) NOT NULL,
    [meses] BIGINT NULL,
    [n_pool] FLOAT NULL,
    [cota_pp] FLOAT NULL,
    [amp_estacional_pp] FLOAT NULL,
    [pendiente_pp_ano] FLOAT NULL,
    [gate] NVARCHAR(255) NULL,
    [sd_obs_pp] FLOAT NULL,
    [sd_binom_pp] FLOAT NULL,
    [phi] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL,
    CONSTRAINT [PK_sff_diag_dinamica] PRIMARY KEY ([fs_id_L2])
);

CREATE TABLE [sff_dim_tecnica] (
    [tecnica_id] NVARCHAR(255) NOT NULL,
    [familia] NVARCHAR(255) NULL,
    [descripcion] NVARCHAR(255) NULL,
    [elegibilidad_min] NVARCHAR(255) NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL,
    CONSTRAINT [PK_sff_dim_tecnica] PRIMARY KEY ([tecnica_id])
);

-- El ancla: el raw con claves. Todo dinero se suma aquí.
CREATE TABLE [sff_fact_fine] (
    [period] NVARCHAR(255) NULL,
    [dataset_role] NVARCHAR(255) NULL,
    [total_tr_units] BIGINT NULL,
    [total_tr_usd] FLOAT NULL,
    [total_renewed_units] FLOAT NULL,
    [total_renewed_usd] FLOAT NULL,
    [is_current_month] BIGINT NULL,
    [flag_time_series] BIGINT NULL,
    [region] NVARCHAR(255) NULL,
    [product] NVARCHAR(255) NULL,
    [channel] NVARCHAR(255) NULL,
    [dormant] BIGINT NULL,
    [softcancel] BIGINT NULL,
    [no_instalado] BIGINT NULL,
    [autorenew] BIGINT NULL,
    [discount] NVARCHAR(255) NULL,
    [newcust] BIGINT NULL,
    [fu_id] NVARCHAR(255) NULL,
    [comb_id] NVARCHAR(255) NULL,
    [fu_key] BIGINT NULL,
    [comb_key] BIGINT NULL,
    [fu_comb_key] BIGINT NOT NULL,
    [period_date] DATETIME2 NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL,
    CONSTRAINT [PK_sff_fact_fine] PRIMARY KEY ([fu_comb_key])
);

CREATE TABLE [sff_fact_fu] (
    [region] NVARCHAR(255) NULL,
    [dormant] BIGINT NULL,
    [softcancel] BIGINT NULL,
    [no_instalado] BIGINT NULL,
    [autorenew] BIGINT NULL,
    [product] NVARCHAR(255) NULL,
    [channel] NVARCHAR(255) NULL,
    [period] NVARCHAR(255) NULL,
    [dataset_role] NVARCHAR(255) NULL,
    [is_current_month] BIGINT NULL,
    [flag_time_series] BIGINT NULL,
    [total_tr_units] BIGINT NULL,
    [total_tr_usd] FLOAT NULL,
    [total_renewed_units] FLOAT NULL,
    [total_renewed_usd] FLOAT NULL,
    [fu_id] NVARCHAR(255) NULL,
    [fu_key] BIGINT NOT NULL,
    [period_date] DATETIME2 NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL,
    CONSTRAINT [PK_sff_fact_fu] PRIMARY KEY ([fu_key])
);

CREATE TABLE [sff_fact_fu_gaps] (
    [fu_key] BIGINT NULL,
    [fu_id] NVARCHAR(255) NULL,
    [fs_id] NVARCHAR(255) NULL,
    [period] NVARCHAR(255) NULL,
    [dataset_role] NVARCHAR(255) NULL,
    [total_tr_units] FLOAT NULL,
    [total_tr_usd] FLOAT NULL,
    [total_renewed_units] FLOAT NULL,
    [total_renewed_usd] FLOAT NULL,
    [sintetica] BIGINT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

-- La incertidumbre medida de cada fila del forecast.
CREATE TABLE [sff_forecast_bands] (
    [fu_key] BIGINT NULL,
    [comb_key] BIGINT NULL,
    [fs_id_L2] NVARCHAR(255) NULL,
    [tecnica_id] NVARCHAR(255) NULL,
    [h] BIGINT NULL,
    [banda_pp] FLOAT NULL,
    [banda_usd] FLOAT NULL,
    [esperado_usd] FLOAT NULL,
    [banda_fallback] BIGINT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

-- El forecast fila a fila.
CREATE TABLE [sff_forecast_detail] (
    [fu_key] BIGINT NULL,
    [comb_key] BIGINT NULL,
    [fs_id] NVARCHAR(255) NULL,
    [period] NVARCHAR(255) NULL,
    [total_tr_usd] FLOAT NULL,
    [tasa] FLOAT NULL,
    [uplift] FLOAT NULL,
    [esperado_usd] FLOAT NULL,
    [etiqueta] NVARCHAR(255) NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

CREATE TABLE [sff_forecast_pred_fu] (
    [fu_key] BIGINT NULL,
    [fs_id] NVARCHAR(255) NULL,
    [fs_id_L2] NVARCHAR(255) NULL,
    [period] NVARCHAR(255) NULL,
    [h] BIGINT NULL,
    [tecnica_id] NVARCHAR(255) NULL,
    [tasa_pred] FLOAT NULL,
    [uplift_pred] FLOAT NULL,
    [forecast_usd] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

CREATE TABLE [sff_forecast_seleccion] (
    [fs_id_L2] NVARCHAR(255) NOT NULL,
    [tecnica_elegida] NVARCHAR(255) NULL,
    [err_bt] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL,
    CONSTRAINT [PK_sff_forecast_seleccion] PRIMARY KEY ([fs_id_L2])
);

-- Salud de cada serie: soporte, huecos, moe en $.
CREATE TABLE [sff_fs_summary] (
    [fs_id] NVARCHAR(255) NULL,
    [fs_key] BIGINT NOT NULL,
    [n_avg] FLOAT NULL,
    [meses] BIGINT NULL,
    [huecos] BIGINT NULL,
    [ren] FLOAT NULL,
    [pipe] FLOAT NULL,
    [tasa_hist] FLOAT NULL,
    [se_pp] FLOAT NULL,
    [usd_proj] FLOAT NULL,
    [moe_usd] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL,
    CONSTRAINT [PK_sff_fs_summary] PRIMARY KEY ([fs_key])
);

-- Referencia inmutable: error binomial peor caso por FU-mes.
CREATE TABLE [sff_fu_summary] (
    [fu_key] BIGINT NOT NULL,
    [fu_id] NVARCHAR(255) NULL,
    [period] NVARCHAR(255) NULL,
    [dataset_role] NVARCHAR(255) NULL,
    [is_current_month] BIGINT NULL,
    [universo] NVARCHAR(255) NULL,
    [ruta] NVARCHAR(255) NULL,
    [total_tr_units] BIGINT NULL,
    [total_tr_usd] FLOAT NULL,
    [se_pp_max] FLOAT NULL,
    [moe_pp_max] FLOAT NULL,
    [moe_usd_max] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL,
    CONSTRAINT [PK_sff_fu_summary] PRIMARY KEY ([fu_key])
);

CREATE TABLE [sff_horizon_report_series] (
    [fs_id_L2] NVARCHAR(255) NULL,
    [tecnica_elegida] NVARCHAR(255) NULL,
    [h] BIGINT NULL,
    [n_predicciones] BIGINT NULL,
    [err_pp_medio] FLOAT NULL,
    [err_pp_p90] FLOAT NULL,
    [cobertura_cota_pct] FLOAT NULL,
    [degradacion_pp] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

CREATE TABLE [sff_horizon_report_total] (
    [h] BIGINT NULL,
    [mes_proyectado] NVARCHAR(255) NULL,
    [esperado_usd] FLOAT NULL,
    [banda_usd] FLOAT NULL,
    [banda_pct] FLOAT NULL,
    [err_pp_ponderado] FLOAT NULL,
    [filas] BIGINT NULL,
    [pct_banda_medida] FLOAT NULL,
    [degradacion_vs_h1_pct] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

-- El pegamento: de una fila del raw a todos sus linajes.
CREATE TABLE [sff_key_bridge] (
    [fu_comb_key] BIGINT NOT NULL,
    [fu_id] NVARCHAR(255) NULL,
    [fu_key] BIGINT NULL,
    [comb_id] NVARCHAR(255) NULL,
    [comb_key] BIGINT NULL,
    [fs_id] NVARCHAR(255) NULL,
    [fs_key] FLOAT NULL,
    [fs_id_L1] NVARCHAR(255) NULL,
    [fs_id_L2] NVARCHAR(255) NULL,
    [gu] NVARCHAR(255) NULL,
    [uplift_cell_key] BIGINT NULL,
    [celda_id] NVARCHAR(255) NULL,
    [universo] NVARCHAR(255) NULL,
    [ruta] NVARCHAR(255) NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL,
    CONSTRAINT [PK_sff_key_bridge] PRIMARY KEY ([fu_comb_key])
);

CREATE TABLE [sff_lookup_comb] (
    [comb_id] NVARCHAR(255) NULL,
    [comb_key] BIGINT NOT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL,
    CONSTRAINT [PK_sff_lookup_comb] PRIMARY KEY ([comb_key])
);

CREATE TABLE [sff_lookup_fu] (
    [fu_id] NVARCHAR(255) NULL,
    [fu_key] BIGINT NOT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL,
    CONSTRAINT [PK_sff_lookup_fu] PRIMARY KEY ([fu_key])
);

-- Escalera de padres: peldanos y el elegido.
CREATE TABLE [sff_parent_ladder] (
    [fs_id] NVARCHAR(255) NULL,
    [peldano] BIGINT NULL,
    [dims_colapsadas] NVARCHAR(255) NULL,
    [padre_id] NVARCHAR(255) NULL,
    [n_padre] FLOAT NULL,
    [tasa_padre] FLOAT NULL,
    [elegido] BIGINT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

CREATE TABLE [sff_rolling_next_month] (
    [fs_id_L2] NVARCHAR(255) NULL,
    [mes_objetivo] NVARCHAR(255) NULL,
    [h] BIGINT NULL,
    [tecnica_id] NVARCHAR(255) NULL,
    [tasa_pred] FLOAT NULL,
    [tasa_real] FLOAT NULL,
    [abs_err_pp] FLOAT NULL,
    [err_units] FLOAT NULL,
    [pipeline_units] FLOAT NULL,
    [dentro_de_cota] BIGINT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

CREATE TABLE [sff_rolling_nm_resumen] (
    [tecnica_id] NVARCHAR(255) NULL,
    [h] BIGINT NULL,
    [wape_units_pct] FLOAT NULL,
    [err_pp_ponderado] FLOAT NULL,
    [cobertura_cota_pct] FLOAT NULL,
    [n_predicciones] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

CREATE TABLE [sff_simpson_contrafactual] (
    [celda] NVARCHAR(255) NULL,
    [mes] NVARCHAR(255) NULL,
    [err_plano_pp] FLOAT NULL,
    [err_seg_pp] FLOAT NULL,
    [ahorro_usd] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

-- Waterfall de reparacion: una fila por serie y etapa.
CREATE TABLE [sff_support_chain] (
    [fs_id] NVARCHAR(255) NULL,
    [fs_key] BIGINT NULL,
    [etapa] NVARCHAR(255) NULL,
    [id_efectivo] NVARCHAR(255) NULL,
    [n_efectivo] FLOAT NULL,
    [tasa] FLOAT NULL,
    [se_pp] FLOAT NULL,
    [usd_proj] FLOAT NULL,
    [peldanos_padre] BIGINT NULL,
    [moe_usd] FLOAT NULL,
    [actuo] BIGINT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

CREATE TABLE [sff_uplift_chain] (
    [gu] NVARCHAR(255) NULL,
    [comb_id] NVARCHAR(255) NULL,
    [uplift_cell_key] BIGINT NULL,
    [etapa] NVARCHAR(255) NULL,
    [uplift] FLOAT NULL,
    [se] FLOAT NULL,
    [n_ren] FLOAT NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

-- Auditoria de la ejecucion: 17 checks.
CREATE TABLE [sff_validation_report] (
    [check] NVARCHAR(255) NULL,
    [familia] NVARCHAR(255) NULL,
    [valor] NVARCHAR(255) NULL,
    [esperado] NVARCHAR(255) NULL,
    [estado] NVARCHAR(255) NULL,
    [detalle] NVARCHAR(255) NULL,
    [process_date] NVARCHAR(255) NULL,
    [execution_id] NVARCHAR(255) NULL
);

-- ─── Relaciones ───
ALTER TABLE [sff_fact_fine] ADD CONSTRAINT [FK_sff_fact_fine_sff_key_bridge] FOREIGN KEY ([fu_comb_key]) REFERENCES [sff_key_bridge] ([fu_comb_key]);
ALTER TABLE [sff_fact_fine] ADD CONSTRAINT [FK_sff_fact_fine_sff_fact_fu] FOREIGN KEY ([fu_key]) REFERENCES [sff_fact_fu] ([fu_key]);
ALTER TABLE [sff_fu_summary] ADD CONSTRAINT [FK_sff_fu_summary_sff_fact_fu] FOREIGN KEY ([fu_key]) REFERENCES [sff_fact_fu] ([fu_key]);
ALTER TABLE [sff_key_bridge] ADD CONSTRAINT [FK_sff_key_bridge_sff_fs_summary] FOREIGN KEY ([fs_key]) REFERENCES [sff_fs_summary] ([fs_key]);
-- lógica (el padre no tiene PK única): sff_support_chain.fs_id → sff_fs_summary.fs_id
-- lógica (el padre no tiene PK única): sff_parent_ladder.fs_id → sff_fs_summary.fs_id
ALTER TABLE [sff_key_bridge] ADD CONSTRAINT [FK_sff_key_bridge_sff_diag_dinamica] FOREIGN KEY ([fs_id_L2]) REFERENCES [sff_diag_dinamica] ([fs_id_L2]);
ALTER TABLE [sff_backtest_pred] ADD CONSTRAINT [FK_sff_backtest_pred_sff_diag_dinamica] FOREIGN KEY ([fs_id_L2]) REFERENCES [sff_diag_dinamica] ([fs_id_L2]);
ALTER TABLE [sff_rolling_next_month] ADD CONSTRAINT [FK_sff_rolling_next_month_sff_diag_dinamica] FOREIGN KEY ([fs_id_L2]) REFERENCES [sff_diag_dinamica] ([fs_id_L2]);
ALTER TABLE [sff_horizon_report_series] ADD CONSTRAINT [FK_sff_horizon_report_series_sff_diag_dinamica] FOREIGN KEY ([fs_id_L2]) REFERENCES [sff_diag_dinamica] ([fs_id_L2]);
ALTER TABLE [sff_forecast_seleccion] ADD CONSTRAINT [FK_sff_forecast_seleccion_sff_diag_dinamica] FOREIGN KEY ([fs_id_L2]) REFERENCES [sff_diag_dinamica] ([fs_id_L2]);
-- lógica (el padre no tiene PK única): sff_key_bridge.uplift_cell_key → sff_uplift_chain.uplift_cell_key
ALTER TABLE [sff_forecast_detail] ADD CONSTRAINT [FK_sff_forecast_detail_sff_fact_fu] FOREIGN KEY ([fu_key]) REFERENCES [sff_fact_fu] ([fu_key]);
ALTER TABLE [sff_forecast_bands] ADD CONSTRAINT [FK_sff_forecast_bands_sff_fact_fu] FOREIGN KEY ([fu_key]) REFERENCES [sff_fact_fu] ([fu_key]);
ALTER TABLE [sff_backtest_pred] ADD CONSTRAINT [FK_sff_backtest_pred_sff_dim_tecnica] FOREIGN KEY ([tecnica]) REFERENCES [sff_dim_tecnica] ([tecnica_id]);
ALTER TABLE [sff_forecast_seleccion] ADD CONSTRAINT [FK_sff_forecast_seleccion_sff_dim_tecnica] FOREIGN KEY ([tecnica_elegida]) REFERENCES [sff_dim_tecnica] ([tecnica_id]);
ALTER TABLE [sff_forecast_bands] ADD CONSTRAINT [FK_sff_forecast_bands_sff_dim_tecnica] FOREIGN KEY ([tecnica_id]) REFERENCES [sff_dim_tecnica] ([tecnica_id]);
ALTER TABLE [sff_rolling_next_month] ADD CONSTRAINT [FK_sff_rolling_next_month_sff_dim_tecnica] FOREIGN KEY ([tecnica_id]) REFERENCES [sff_dim_tecnica] ([tecnica_id]);
ALTER TABLE [sff_backtest_pred_fu] ADD CONSTRAINT [FK_sff_backtest_pred_fu_sff_fact_fu] FOREIGN KEY ([fu_key]) REFERENCES [sff_fact_fu] ([fu_key]);
ALTER TABLE [sff_forecast_pred_fu] ADD CONSTRAINT [FK_sff_forecast_pred_fu_sff_fact_fu] FOREIGN KEY ([fu_key]) REFERENCES [sff_fact_fu] ([fu_key]);
ALTER TABLE [sff_lookup_fu] ADD CONSTRAINT [FK_sff_lookup_fu_sff_fact_fu] FOREIGN KEY ([fu_key]) REFERENCES [sff_fact_fu] ([fu_key]);