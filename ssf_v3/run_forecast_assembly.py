"""run_forecast_assembly.py — SFF v3 · RUN · phase 5: the forecast, its band, and the total
that comes from the parts.

Three pieces:

  EXTENDED HORIZON (`extend_forecast_units`). The known pipeline ends where the extract
  ends (e.g. 2026-12). To forecast 2027 the pipeline itself must be simulated: a contract
  that renews in month m re-enters the pipeline `renewal_term_months` later, plus the
  acquisitions that will also fall due. Per series:
      pipeline_units(m) = expected_renewed_units(m − term) × acquisition_factor
  where `acquisition_factor` = median over history of pipeline(t) / renewed(t − term)
  (= 1 + acquisitions / renewals; estimated per series when the history allows, else
  globally, or set in config). Simulated units carry `simulada = 1` and their own risk
  label; every number built on them is flagged. This is the declared assumption.

  ASSEMBLY (`assemble_forecast`). For every future row (known or simulated): its series →
  its estimation id (decision_support) → its technique (decision_technique) applied at
  the row's horizon h to the estimation id's monthly series → rate, saturated at
  rate_cap; its uplift cell → uplift (decision_uplift); expected$ = pipeline$ × rate ×
  uplift. Every lookup records its origin (serie / celda / global; campeon / retador /
  default; propia / padre / celda / neutro).

  BANDS AND AGGREGATION (`forecast_bands`, `aggregate_with_bands`). Band of a row =
  the asymmetric normalized quantiles of its estimation id at h (decision_error_bands)
  × the binomial error of the estimation id's typical month, combined in quadrature with
  the row's own sampling error p(1−p)/n_row (the month still samples). In dollars over
  the row's pipeline × uplift. Aggregation: rows sharing an estimation id and a month
  share the same rate, so their errors add LINEARLY; across estimation ids and months
  they add in QUADRATURE. The total's band never narrows with the horizon (checked).
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd

from binomial_reference import MIN_PROPORTION_VARIANCE
from config import Config, hash_key, join_columns
from techniques import month_numbers_of, predict

# ─── named constants ─────────────────────────────────────────────────────────────
PROJECTION_ROLE = "projection"
ORIGIN_SERIES, ORIGIN_CELL, ORIGIN_GLOBAL = "serie", "celda", "global"
TECH_DEFAULT = "default"
DEFAULT_TECHNIQUE = "T2_mean"
# (acquisition_min_pairs and band_narrowing_tolerance_pct are Config parameters)
DEFAULT_ACQUISITION_FACTOR = 1.0


# ═══════════════════════════════════════════════════════════════════════════════════
# EXTENDED HORIZON
# ═══════════════════════════════════════════════════════════════════════════════════

def term_months_of(frame: pd.DataFrame, configuration: Config) -> pd.Series:
    """The renewal term in months of every row: from `term_column` mapped through
    `term_months_by_value`, else the default `renewal_term_months`."""
    default = configuration.renewal_term_months
    if configuration.term_column and configuration.term_column in frame.columns and configuration.term_months_by_value:
        return frame[configuration.term_column].astype(str).map(
            {str(k): int(v) for k, v in configuration.term_months_by_value.items()}).fillna(default).astype(int)
    return pd.Series(default, index=frame.index, dtype=int)


def acquisition_factor_by_series(units: pd.DataFrame, configuration: Config) -> tuple:
    """Median of pipeline(t) / renewed(t − term) per series, and the global one.

    OUTPUT:  (Series fs_id → factor, global_factor). Series with fewer than
             `acquisition_min_pairs` usable pairs fall back to the global.
    RULES:   a configured `acquisition_factor` overrides everything. Vectorized: the
             monthly table is joined with itself shifted by `term` months.
    """
    if configuration.acquisition_factor is not None:
        return pd.Series(dtype=float), float(configuration.acquisition_factor)
    period = configuration.period_col
    history = units[(units[configuration.dataset_role_col] != PROJECTION_ROLE) & (units["sintetica"] == 0)].copy()
    history["_term"] = term_months_of(history, configuration)
    monthly = history.groupby(["fs_id", period], as_index=False).agg(
        pipe=(configuration.pipeline_units_col, "sum"), ren=(configuration.renewed_units_col, "sum"), term=("_term", "first"))
    earlier = monthly[["fs_id", period, "ren", "term"]].copy()
    earlier[period] = earlier[period] + earlier["term"].astype(int)
    earlier = earlier.drop(columns="term")
    pairs = monthly.merge(earlier.rename(columns={"ren": "ren_earlier"}), on=["fs_id", period])
    pairs = pairs[pairs["ren_earlier"] > 0]
    pairs["ratio"] = pairs["pipe"] / pairs["ren_earlier"]
    counts = pairs.groupby("fs_id")["ratio"].size()
    factors = pairs.groupby("fs_id")["ratio"].median()[counts >= configuration.acquisition_min_pairs]
    global_factor = float(pairs["ratio"].median()) if len(pairs) else DEFAULT_ACQUISITION_FACTOR
    return factors.astype(float), global_factor


def extend_forecast_units(fine_table: pd.DataFrame, units: pd.DataFrame, series_estimates: pd.DataFrame,
                          configuration: Config, decision_uplift: pd.DataFrame = None) -> pd.DataFrame:
    """Simulated future rows from the end of the known pipeline to `extended_horizon_end`.

    INPUT:   fine_table (phase 0, projection rows are the template) · units (history for
             the acquisition factor and the re-entry) · series_estimates (tasa_estimada
             gives the expected renewals of months not yet observed) · configuration.
    OUTPUT:  rows with the fine table's columns + simulada = 1, factor_adquisicion; empty
             when no extension is configured.
    RULES:   for month m beyond the known pipeline, per series and combination:
             units(m) = renewed(m − term) × factor, with the term of EACH ROW (term_column /
             term_months_by_value, else renewal_term_months); renewed(m − term) is observed
             when m − term has truth, or expected (pipeline × tasa_estimada) when it is a
             projection or an already simulated month; pipeline$ = units × the RENEWED
             price: the observed renewed AUV of the source row when it has truth, else its
             pipeline AUV × the uplift of its cell (decision_uplift). A contract renewed in
             2026 falls due in 2027 at the price it renewed at; the 2027 forecast applies
             rate × uplift again on top. Only rows matching `extension_row_filter` re-enter
             (e.g. term_level_2 = "1 year"): multi-year contracts renewed now fall due beyond
             the horizon and their known expirations are already in the pipeline.
    EDGE CASES: a series with no row at m − term contributes nothing at m.
    NOTE:    vectorized month by month (one frame operation per simulated month).
    """
    if configuration.extended_horizon_end is None:
        return pd.DataFrame()
    period, role = configuration.period_col, configuration.dataset_role_col
    pipe_units, pipe_usd = configuration.pipeline_units_col, configuration.pipeline_usd_col
    last_known = fine_table[period].max()
    end = pd.Period(configuration.extended_horizon_end, freq="M")
    if end <= last_known:
        return pd.DataFrame()
    factors, global_factor = acquisition_factor_by_series(units, configuration)
    rate_by_series = series_estimates.set_index("fs_id")["tasa_estimada"]
    known = fine_table.copy()
    known["fs_id"] = join_columns(known, configuration.rate_series_columns)      # same formula as phase 0
    known["simulada"] = 0
    known["_term"] = term_months_of(known, configuration)
    known["_due"] = known[period] + known["_term"]              # the month this row's renewals fall due again
    keep = pd.Series(True, index=known.index)
    for column, allowed in (configuration.extension_row_filter or {}).items():
        if column in known.columns:
            keep &= known[column].astype(str).isin([str(v) for v in allowed])
    known.loc[~keep, "_due"] = pd.NaT                           # filtered rows never re-enter
    uplift_of_cell = {}
    if decision_uplift is not None and len(decision_uplift):
        uplift_of_cell = dict(zip(decision_uplift["uplift_cell_id"], decision_uplift["uplift"]))
    known["_uplift_cell_id"] = join_columns(known, configuration.uplift_cell_columns)
    all_rows, simulated_frames = known, []
    for month in pd.period_range(last_known + 1, end, freq="M"):
        source = all_rows[all_rows["_due"] == month]
        if source.empty:
            continue
        expected = source[pipe_units] * source["fs_id"].map(rate_by_series).fillna(0.0)
        observed = source[configuration.renewed_units_col]
        use_expected = (source[role] == PROJECTION_ROLE) | (source["simulada"] == 1)
        renewed = np.where(use_expected, expected, observed.fillna(0.0))
        keep = np.isfinite(renewed) & (renewed > 0)
        source, renewed = source[keep], renewed[keep]
        if source.empty:
            continue
        factor = source["fs_id"].map(factors).fillna(global_factor).to_numpy(dtype=float)
        pipeline_auv = (source[pipe_usd] / source[pipe_units].clip(lower=1e-9)).to_numpy(dtype=float)
        observed_auv = (source[configuration.renewed_usd_col] / source[configuration.renewed_units_col].replace(0, np.nan)).to_numpy(dtype=float)
        cell_uplift = source["_uplift_cell_id"].map(uplift_of_cell).fillna(1.0).to_numpy(dtype=float)
        # the renewed price: observed where there is truth, pipeline AUV × uplift where there is not
        auv = np.where(np.isfinite(observed_auv) & ~use_expected[keep].to_numpy(), observed_auv, pipeline_auv * cell_uplift)
        new_rows = source.copy()
        new_rows[period], new_rows[role] = month, PROJECTION_ROLE
        new_rows[pipe_units] = renewed * factor
        new_rows[pipe_usd] = renewed * factor * auv
        for column in (configuration.renewed_units_col, configuration.renewed_usd_col):
            new_rows[column] = np.nan
        new_rows[configuration.current_month_col] = 0
        new_rows["simulada"], new_rows["factor_adquisicion"] = 1, np.round(factor, 4)
        new_rows["_due"] = new_rows[period] + new_rows["_term"]
        new_rows["fu_id"] = new_rows["fs_id"] + "|" + str(month)
        new_rows["fu_key"] = new_rows["fu_id"].map(hash_key)
        new_rows["fu_comb_key"] = (new_rows["fu_id"] + "||" + new_rows["comb_id"].astype(str)).map(hash_key)
        simulated_frames.append(new_rows)
        all_rows = pd.concat([all_rows, new_rows], ignore_index=True)
    if not simulated_frames:
        return pd.DataFrame()
    extended = pd.concat(simulated_frames, ignore_index=True)
    terms_used = sorted(extended["_term"].unique())
    extended = extended.drop(columns=["_term", "_due", "_uplift_cell_id"])
    print(f"[5] extended horizon {last_known + 1} → {end}: {len(extended):,} simulated rows · "
          f"acquisition factor global {global_factor:.3f} (per-series for {len(factors)} series) · "
          f"re-entry after {terms_used} months" + (f" (from '{configuration.term_column}')" if configuration.term_column else "")
          + (f" · only rows with {configuration.extension_row_filter}" if configuration.extension_row_filter else "")
          + " · valued at the renewed price (AUV × uplift)")
    return extended


# ═══════════════════════════════════════════════════════════════════════════════════
# ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════════

def rate_forecast_by_estimation_id(monthly_series: dict, decision_technique: pd.DataFrame,
                                   decision_dynamics: pd.DataFrame, target_months: list, requires_firm: bool = True) -> pd.DataFrame:
    """The rate predicted at every target month for every estimation id with its technique.

    OUTPUT:  DataFrame(id_estimacion, period, tasa_pred, h, tecnica). h = months from the
             id's last month with truth.
    """
    technique_by_id = dict(zip(decision_technique["id_estimacion"], decision_technique["tecnica"]))
    labels = {row["id_estimacion"]: dict(estacional=int(row["estacional"]), tendencia=int(row["tendencia"]), requiere_firme=requires_firm)
              for _, row in decision_dynamics.iterrows()}
    rows = []
    for estimation_id, monthly in monthly_series.items():
        valid = monthly[monthly["rate"].notna() & (monthly["pipe"] > 0)]
        if valid.empty:
            continue
        rates, months = valid["rate"].to_numpy(dtype=float), pd.PeriodIndex(valid.index)
        month_numbers = month_numbers_of(months)
        technique = technique_by_id.get(estimation_id, DEFAULT_TECHNIQUE)
        for month in target_months:
            h = int((month - months[-1]).n)
            if h < 1:
                continue
            value = predict(technique, rates, month_numbers, h, labels.get(estimation_id, {}))
            rows.append((estimation_id, month, value, h, technique))
    return pd.DataFrame(rows, columns=["id_estimacion", "period", "tasa_pred", "h", "tecnica"])


def assemble_forecast(future_rows: pd.DataFrame, series_estimates: pd.DataFrame, decision_support: pd.DataFrame,
                      decision_technique: pd.DataFrame, decision_dynamics: pd.DataFrame, monthly_series: dict,
                      decision_uplift: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """Every future row gets its rate, its uplift, its expected dollars and their origins.

    OUTPUT:  forecast_detail rows (future_rows + fs_id, id_estimacion, h, tecnica,
             tecnica_origen, tasa, tasa_origen, uplift, uplift_origen, esperado_usd,
             simulada) — not yet persisted (the bands come first).
    RULES:   rate cascade: technique prediction of the series' estimation id at h →
             tasa_estimada of the series → mean of the mandatory cell → global mean;
             each step records its origin. Saturated at rate_cap. Uplift: the cell's
             decision, else neutral 1.0.
    NOTE:    vectorized: one merge per step of the cascade, no per-row loop.
    """
    period = configuration.period_col
    rows = future_rows.copy()
    rows["fs_id"] = join_columns(rows, configuration.rate_series_columns)      # (re)derived: same formula everywhere
    rows["uplift_cell_id"] = join_columns(rows, configuration.uplift_cell_columns)
    rows["celda_id"] = join_columns(rows, configuration.business_mandatory_dims)
    if "simulada" not in rows.columns:
        rows["simulada"] = 0
    rows["simulada"] = rows["simulada"].fillna(0).astype(int)
    estimation_of = decision_support[["fs_id", "id_estimacion"]].drop_duplicates("fs_id")
    rows = rows.merge(estimation_of, on="fs_id", how="left")
    rows["id_estimacion"] = rows["id_estimacion"].fillna(rows["fs_id"])
    # step 1: the technique prediction of the estimation id at the row's month
    predictions = rate_forecast_by_estimation_id(monthly_series, decision_technique, decision_dynamics,
                                                 sorted(rows[period].unique()), configuration.seasonal_requires_firm)
    rows = rows.merge(predictions, on=["id_estimacion", period], how="left")
    technique_origin = dict(zip(decision_technique["id_estimacion"], decision_technique["tecnica_origen"]))
    # step 2-4: the series estimate, the cell mean, the global mean
    estimate_of = series_estimates[["fs_id", "tasa_estimada"]].drop_duplicates("fs_id")
    rows = rows.merge(estimate_of, on="fs_id", how="left")
    mandatory_count = len(configuration.business_mandatory_dims)
    cell_mean = (series_estimates.assign(celda_id=series_estimates["fs_id"].str.split("|").str[:mandatory_count].str.join("|"))
                 .dropna(subset=["tasa_estimada"]).groupby("celda_id")["tasa_estimada"].mean().rename("tasa_celda"))
    rows = rows.merge(cell_mean, on="celda_id", how="left")
    global_mean = float(series_estimates["tasa_estimada"].mean())
    from_technique = rows["tasa_pred"].notna()
    from_estimate = ~from_technique & rows["tasa_estimada"].notna()
    from_cell = ~from_technique & ~from_estimate & rows["tasa_celda"].notna()
    rows["tasa"] = np.select([from_technique, from_estimate, from_cell],
                             [rows["tasa_pred"], rows["tasa_estimada"], rows["tasa_celda"]], default=global_mean)
    rows["tasa"] = rows["tasa"].clip(upper=configuration.rate_cap)
    rows["tasa_origen"] = np.select([from_technique | from_estimate, from_cell], [ORIGIN_SERIES, ORIGIN_CELL], default=ORIGIN_GLOBAL)
    rows["tecnica"] = rows["tecnica"].where(from_technique, DEFAULT_TECHNIQUE)
    rows["tecnica_origen"] = rows["id_estimacion"].map(technique_origin).where(from_technique, TECH_DEFAULT).fillna(TECH_DEFAULT)
    rows["h"] = rows["h"].where(from_technique, np.nan)
    rows = rows.drop(columns=["tasa_pred", "tasa_estimada", "tasa_celda"])
    uplift_of = dict(zip(decision_uplift["uplift_cell_id"], decision_uplift["uplift"]))
    uplift_origin = dict(zip(decision_uplift["uplift_cell_id"], decision_uplift["uplift_origen"]))
    rows["uplift"] = rows["uplift_cell_id"].map(uplift_of).fillna(1.0)
    rows["uplift_origen"] = rows["uplift_cell_id"].map(uplift_origin).fillna("neutro")
    rows["esperado_usd"] = rows[configuration.pipeline_usd_col] * rows["tasa"] * rows["uplift"]
    return rows


def forecast_bands(detail: pd.DataFrame, decision_error_bands: pd.DataFrame, decision_dynamics: pd.DataFrame,
                   configuration: Config) -> pd.DataFrame:
    """The asymmetric band of every forecast row, in pp and dollars.

    RULES:   pool error at h: q_low_norm / q_high_norm × binomial se of the estimation
             id's typical month (n_pool, tasa_pool from decision_dynamics); row sampling
             error: binomial se with the row's own units; combined in quadrature on each
             side; clipped so the rate stays in [0, rate_cap]. When h itself was not
             judged, the band of the nearest judged horizon below it is used (monotone,
             so never optimistic) and flagged `+h<judged>`. Rows with no band at all use
             the binomial error at z, flagged `banda_origen = "binomial"`.
    NOTE:    vectorized: the nearest judged horizon is found with one merge_asof per row set.
    """
    bands = detail.copy()
    pool = decision_dynamics[["id_estimacion", "n_pool", "tasa_pool"]].drop_duplicates("id_estimacion")
    bands = bands.merge(pool, on="id_estimacion", how="left")
    bands["tasa_pool"] = bands["tasa_pool"].fillna(bands["tasa"])
    units = bands[configuration.pipeline_units_col].clip(lower=1.0).astype(float)
    se_row = (100 * np.sqrt(np.maximum(bands["tasa"] * (1 - bands["tasa"]), MIN_PROPORTION_VARIANCE) / units)).to_numpy()
    n_pool = bands["n_pool"].fillna(units).clip(lower=1.0).to_numpy(dtype=float)
    se_pool = 100 * np.sqrt(np.maximum(bands["tasa_pool"] * (1 - bands["tasa_pool"]), MIN_PROPORTION_VARIANCE) / n_pool)
    # nearest judged horizon at or below h, per estimation id
    judged = decision_error_bands[["id_estimacion", "h", "q_low_norm", "q_high_norm", "banda_origen"]].rename(columns={"h": "h_juzgado"})
    judged = judged.sort_values("h_juzgado")
    with_h = bands[bands["h"].notna()].copy()
    with_h["h_busqueda"] = with_h["h"].astype(int)
    with_h = with_h.sort_values("h_busqueda")
    matched = pd.merge_asof(with_h, judged, left_on="h_busqueda", right_on="h_juzgado", by="id_estimacion", direction="backward")
    # rows whose h is below every judged horizon take the first judged one (still monotone-safe)
    first = judged.drop_duplicates("id_estimacion").rename(columns={"h_juzgado": "h_primero", "q_low_norm": "q_low_primero",
                                                                     "q_high_norm": "q_high_primero", "banda_origen": "origen_primero"})
    matched = matched.merge(first, on="id_estimacion", how="left")
    missing = matched["h_juzgado"].isna() & matched["h_primero"].notna()
    for target, source in (("h_juzgado", "h_primero"), ("q_low_norm", "q_low_primero"), ("q_high_norm", "q_high_primero"), ("banda_origen", "origen_primero")):
        matched[target] = matched[target].where(~missing, matched[source])
    lookup = matched[["fu_comb_key", "h_juzgado", "q_low_norm", "q_high_norm", "banda_origen"]]
    bands = bands.merge(lookup, on="fu_comb_key", how="left")
    has_band = bands["q_low_norm"].notna()
    q_low = bands["q_low_norm"].fillna(-configuration.z).to_numpy(dtype=float)
    q_high = bands["q_high_norm"].fillna(configuration.z).to_numpy(dtype=float)
    origin = bands["banda_origen"].fillna("binomial")
    not_judged_at_h = has_band & (bands["h_juzgado"] != bands["h"])
    origin = origin.where(~not_judged_at_h, origin + "+h" + bands["h_juzgado"].fillna(0).astype(int).astype(str))
    low = -np.sqrt((q_low * se_pool) ** 2 + (configuration.z * se_row) ** 2)
    high = np.sqrt((q_high * se_pool) ** 2 + (configuration.z * se_row) ** 2)
    low = np.maximum(low, -100 * bands["tasa"].to_numpy())
    high = np.minimum(high, 100 * (configuration.rate_cap - bands["tasa"].to_numpy()))
    bands["banda_low_pp"], bands["banda_high_pp"], bands["banda_origen"] = np.round(low, 3), np.round(high, 3), origin
    money = bands[configuration.pipeline_usd_col] * bands["uplift"] / 100
    bands["banda_low_usd"], bands["banda_high_usd"] = (bands["banda_low_pp"] * money).round(2), (bands["banda_high_pp"] * money).round(2)
    return bands.drop(columns=["n_pool", "tasa_pool", "h_juzgado", "q_low_norm", "q_high_norm"])


def aggregate_with_bands(bands: pd.DataFrame, grouping: list, configuration: Config) -> pd.DataFrame:
    """Aggregate expected dollars and their band to any grouping, correctly.

    RULES:   within (id_estimacion, month) the rate is shared → band dollars add
             LINEARLY; across (id_estimacion, month) → in QUADRATURE.
    OUTPUT:  grouping + esperado_usd, banda_low_usd, banda_high_usd, pct_low, pct_high.
    """
    period = configuration.period_col
    shared = bands.groupby(grouping + ["id_estimacion", period], as_index=False).agg(
        esperado_usd=("esperado_usd", "sum"), low=("banda_low_usd", "sum"), high=("banda_high_usd", "sum"))
    aggregated = shared.groupby(grouping, as_index=False).agg(
        esperado_usd=("esperado_usd", "sum"),
        banda_low_usd=("low", lambda s: -float(np.sqrt((s ** 2).sum()))),
        banda_high_usd=("high", lambda s: float(np.sqrt((s ** 2).sum()))))
    aggregated["pct_low"] = (100 * aggregated["banda_low_usd"] / aggregated["esperado_usd"].replace(0, np.nan)).round(2)
    aggregated["pct_high"] = (100 * aggregated["banda_high_usd"] / aggregated["esperado_usd"].replace(0, np.nan)).round(2)
    return aggregated


def horizon_report(bands: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """Per month: total, band, % of money by rate origin, % simulated; band monotone check."""
    period = configuration.period_col
    monthly = aggregate_with_bands(bands, [period], configuration)
    monthly["pct_simulado"] = bands.groupby(period).apply(
        lambda g: 100 * g.loc[g["simulada"] == 1, "esperado_usd"].sum() / max(g["esperado_usd"].sum(), 1e-9),
        include_groups=False).reindex(monthly[period]).round(1).values
    monthly["pct_tasa_serie"] = bands.groupby(period).apply(
        lambda g: 100 * g.loc[g["tasa_origen"] == ORIGIN_SERIES, "esperado_usd"].sum() / max(g["esperado_usd"].sum(), 1e-9),
        include_groups=False).reindex(monthly[period]).round(1).values
    monthly["banda_rel_pct"] = ((monthly["banda_high_usd"] - monthly["banda_low_usd"]) / 2 / monthly["esperado_usd"].replace(0, np.nan) * 100).round(2)
    monthly["banda_monotona"] = (monthly["banda_rel_pct"].diff().fillna(0) >= -configuration.band_narrowing_tolerance_pct).astype(int)
    monthly[period] = monthly[period].astype(str)
    return monthly


def run_forecast_assembly(fine_table: pd.DataFrame, units: pd.DataFrame, series_estimates: pd.DataFrame,
                          series_card: pd.DataFrame, decisions: dict, monthly_series: dict,
                          configuration: Config) -> dict:
    """Phase 5 end to end. Persists forecast_units_extended, forecast_detail, forecast_bands,
    horizon_report_total, forecast_by_level."""
    period = configuration.period_col
    known_future = fine_table[fine_table[configuration.dataset_role_col] == PROJECTION_ROLE].copy()
    known_future["simulada"] = 0
    extended = extend_forecast_units(fine_table, units, series_estimates, configuration, decisions["decision_uplift"])
    if len(extended):
        configuration.write(extended.assign(**{period: extended[period].astype(str)}), "forecast_units_extended")
        future = pd.concat([known_future, extended], ignore_index=True)
    else:
        future = known_future
    detail = assemble_forecast(future, series_estimates, decisions["decision_support"], decisions["decision_technique"],
                               decisions["decision_dynamics"], monthly_series, decisions["decision_uplift"], configuration)
    bands = forecast_bands(detail, decisions["decision_error_bands"], decisions["decision_dynamics"], configuration)
    level_of = series_card.set_index("fs_id")["nivel_riesgo"]
    bands["nivel_riesgo"] = bands["fs_id"].map(level_of).fillna("D_sin_historia")
    detail_columns = ["fu_key", "comb_key", "fu_comb_key", "fs_id", "id_estimacion", "uplift_cell_id", "celda_id",
                      period, configuration.pipeline_units_col, configuration.pipeline_usd_col, "h", "tecnica", "tecnica_origen",
                      "tasa", "tasa_origen", "uplift", "uplift_origen", "esperado_usd", "simulada", "nivel_riesgo"]
    band_columns = ["fu_key", "comb_key", "fu_comb_key", "fs_id", "id_estimacion", period, "h", "banda_low_pp", "banda_high_pp",
                    "banda_low_usd", "banda_high_usd", "banda_origen", "esperado_usd"]
    configuration.write(bands[detail_columns].assign(**{period: bands[period].astype(str)}), "forecast_detail")
    configuration.write(bands[band_columns].assign(**{period: bands[period].astype(str)}), "forecast_bands")
    horizon = horizon_report(bands, configuration)
    configuration.write(horizon, "horizon_report_total")
    by_level = aggregate_with_bands(bands, ["nivel_riesgo"], configuration)
    configuration.write(by_level, "forecast_by_level")
    print(f"[5] forecast: ${bands['esperado_usd'].sum():,.0f} over {bands[period].nunique()} months · rate origin "
          f"{bands.groupby('tasa_origen')['esperado_usd'].sum().div(bands['esperado_usd'].sum()).mul(100).round(1).to_dict()} · "
          f"technique origin {bands.groupby('tecnica_origen')['esperado_usd'].sum().div(bands['esperado_usd'].sum()).mul(100).round(1).to_dict()}")
    print("[5] month · expected · band (asymmetric) · % from simulated pipeline")
    for _, row in horizon.iterrows():
        print(f"   {row[period]}  ${row['esperado_usd']:>11,.0f}  {row['pct_low']:+6.1f}% / {row['pct_high']:+5.1f}%  "
              f"simulated {row['pct_simulado']:5.1f}%  {'' if row['banda_monotona'] else 'band narrowed beyond tolerance'}")
    return dict(forecast_detail=bands[detail_columns], forecast_bands=bands[band_columns], horizon_report=horizon,
                forecast_by_level=by_level, forecast_units_extended=extended)
