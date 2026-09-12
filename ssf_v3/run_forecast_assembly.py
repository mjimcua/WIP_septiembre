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

from binomial_reference import binomial_se_pp
from config import Config, hash_key, join_columns
from techniques import predict

# ─── named constants ─────────────────────────────────────────────────────────────
PROJECTION_ROLE = "projection"
ORIGIN_SERIES, ORIGIN_CELL, ORIGIN_GLOBAL = "serie", "celda", "global"
TECH_DEFAULT = "default"
DEFAULT_TECHNIQUE = "T2_mean"
MIN_HISTORY_FOR_ACQUISITION_FACTOR = 3
# Per estimation id the band is monotone in h by construction. The TOTAL's relative band
# can still narrow from one month to the next when the mix of that month leans toward
# well-supported series (or toward simulated pipeline with a different composition). A
# narrowing beyond this many percentage points of the total is a signal to look at the
# mix; smaller wobbles are composition, not calibration.
BAND_NARROWING_TOLERANCE_PCT = 1.0
DEFAULT_ACQUISITION_FACTOR = 1.0


# ═══════════════════════════════════════════════════════════════════════════════════
# EXTENDED HORIZON
# ═══════════════════════════════════════════════════════════════════════════════════

def acquisition_factor_by_series(units: pd.DataFrame, configuration: Config) -> tuple:
    """Median of pipeline(t) / renewed(t − term) per series, and the global one.

    OUTPUT:  (Series fs_id → factor, global_factor). Series with fewer than
             MIN_HISTORY_FOR_ACQUISITION_FACTOR usable pairs fall back to the global.
    RULES:   a configured `acquisition_factor` overrides everything.
    """
    if configuration.acquisition_factor is not None:
        return pd.Series(dtype=float), float(configuration.acquisition_factor)
    term = configuration.renewal_term_months
    history = units[(units[configuration.dataset_role_col] != PROJECTION_ROLE) & (units["sintetica"] == 0)]
    factors, all_ratios = {}, []
    for series_id, rows in history.groupby("fs_id"):
        by_month = rows.set_index(configuration.period_col)[[configuration.pipeline_units_col, configuration.renewed_units_col]].sort_index()
        ratios = []
        for month, row in by_month.iterrows():
            earlier = month - term
            if earlier in by_month.index and by_month.loc[earlier, configuration.renewed_units_col] > 0:
                ratios.append(row[configuration.pipeline_units_col] / by_month.loc[earlier, configuration.renewed_units_col])
        all_ratios.extend(ratios)
        if len(ratios) >= MIN_HISTORY_FOR_ACQUISITION_FACTOR:
            factors[series_id] = float(np.median(ratios))
    global_factor = float(np.median(all_ratios)) if all_ratios else DEFAULT_ACQUISITION_FACTOR
    return pd.Series(factors, dtype=float), global_factor


def extend_forecast_units(fine_table: pd.DataFrame, units: pd.DataFrame, series_estimates: pd.DataFrame,
                          configuration: Config) -> pd.DataFrame:
    """Simulated future rows from the end of the known pipeline to `extended_horizon_end`.

    INPUT:   fine_table (phase 0, projection rows are the template) · units (history for
             the acquisition factor and the re-entry) · series_estimates (tasa_estimada
             gives the expected renewals of months not yet observed) · configuration.
    OUTPUT:  rows with the fine table's columns + simulada = 1, factor_adquisicion; empty
             when no extension is configured.
    RULES:   for month m beyond the known pipeline, per series and combination:
             units(m) = renewed(m − term) × factor, where renewed(m − term) is observed
             when m − term has truth, or expected (pipeline × tasa_estimada) when it is a
             projection month; pipeline$ = units × the combination's last known AUV.
    EDGE CASES: a series with no row at m − term contributes nothing at m.
    """
    if configuration.extended_horizon_end is None:
        return pd.DataFrame()
    period, role = configuration.period_col, configuration.dataset_role_col
    last_known = fine_table[period].max()
    end = pd.Period(configuration.extended_horizon_end, freq="M")
    if end <= last_known:
        return pd.DataFrame()
    factors, global_factor = acquisition_factor_by_series(units, configuration)
    rate_by_series = series_estimates.set_index("fs_id")["tasa_estimada"]
    template = fine_table.copy()
    template["fs_id"] = join_columns(template, configuration.rate_series_columns)
    term = configuration.renewal_term_months
    simulated = []
    known_by_key = {(row["fs_id"], row["comb_id"], row[period]): row for _, row in template.iterrows()}
    for month in pd.period_range(last_known + 1, end, freq="M"):
        source_month = month - term
        for (series_id, comb_id, m), source in list(known_by_key.items()):
            if m != source_month:
                continue
            if source[role] == PROJECTION_ROLE or source.get("simulada", 0) == 1:
                rate = rate_by_series.get(series_id, np.nan)
                renewed = source[configuration.pipeline_units_col] * (rate if np.isfinite(rate) else 0.0)
            else:
                renewed = source[configuration.renewed_units_col]
            if not np.isfinite(renewed) or renewed <= 0:
                continue
            factor = float(factors.get(series_id, global_factor))
            new_row = source.copy()
            new_row[period], new_row[role] = month, PROJECTION_ROLE
            auv = source[configuration.pipeline_usd_col] / max(source[configuration.pipeline_units_col], 1e-9)
            new_row[configuration.pipeline_units_col] = renewed * factor
            new_row[configuration.pipeline_usd_col] = renewed * factor * auv
            for column in (configuration.renewed_units_col, configuration.renewed_usd_col):
                new_row[column] = np.nan
            new_row[configuration.current_month_col] = 0
            new_row["simulada"], new_row["factor_adquisicion"] = 1, round(factor, 4)
            new_row["fu_id"] = f"{series_id}|{month}"
            new_row["fu_key"] = hash_key(new_row["fu_id"])
            new_row["fu_comb_key"] = hash_key(f"{new_row['fu_id']}||{comb_id}")
            known_by_key[(series_id, comb_id, month)] = new_row
            simulated.append(new_row)
    extended = pd.DataFrame(simulated)
    if len(extended):
        print(f"[5] extended horizon {last_known + 1} → {end}: {len(extended):,} simulated rows · "
              f"acquisition factor global {global_factor:.3f} (per-series for {len(factors)} series) · "
              f"re-entry after {term} months")
    return extended


# ═══════════════════════════════════════════════════════════════════════════════════
# ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════════

def rate_forecast_by_estimation_id(monthly_series: dict, decision_technique: pd.DataFrame,
                                   decision_dynamics: pd.DataFrame, target_months: list) -> dict:
    """The rate predicted at every target month for every estimation id with its technique.

    OUTPUT:  dict (id_estimacion, month) → (rate, h, technique). h = months from the
             id's last month with truth.
    """
    technique_by_id = dict(zip(decision_technique["id_estimacion"], decision_technique["tecnica"]))
    labels = {row["id_estimacion"]: dict(estacional=int(row["estacional"]), tendencia=int(row["tendencia"]))
              for _, row in decision_dynamics.iterrows()}
    predictions = {}
    for estimation_id, monthly in monthly_series.items():
        valid = monthly[monthly["rate"].notna() & (monthly["pipe"] > 0)]
        if valid.empty:
            continue
        rates, months = valid["rate"].to_numpy(dtype=float), pd.PeriodIndex(valid.index)
        technique = technique_by_id.get(estimation_id, DEFAULT_TECHNIQUE)
        for month in target_months:
            h = int((month - months[-1]).n)
            if h < 1:
                continue
            value = predict(technique, rates, months, h, labels.get(estimation_id, {}))
            predictions[(estimation_id, month)] = (value, h, technique)
    return predictions


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
    """
    rows = future_rows.copy()
    rows["fs_id"] = join_columns(rows, configuration.rate_series_columns)
    rows["uplift_cell_id"] = join_columns(rows, configuration.uplift_cell_columns)
    rows["mandatory_cell_id"] = join_columns(rows, configuration.business_mandatory_dims)
    if "simulada" not in rows.columns:
        rows["simulada"] = 0
    rows["simulada"] = rows["simulada"].fillna(0).astype(int)
    estimation_of = dict(zip(decision_support["fs_id"], decision_support["id_estimacion"]))
    estimate_of = series_estimates.set_index("fs_id")["tasa_estimada"]
    cell_of = series_estimates.merge(decision_support[["fs_id"]], on="fs_id")
    technique_origin = dict(zip(decision_technique["id_estimacion"], decision_technique["tecnica_origen"]))
    target_months = sorted(rows[configuration.period_col].unique())
    predictions = rate_forecast_by_estimation_id(monthly_series, decision_technique, decision_dynamics, target_months)
    cell_mean = (series_estimates.assign(celda=series_estimates["fs_id"].str.split("|").str[:len(configuration.business_mandatory_dims)].str.join("|"))
                 .dropna(subset=["tasa_estimada"]).groupby("celda")["tasa_estimada"].mean())
    global_mean = float(series_estimates["tasa_estimada"].mean())
    uplift_of = dict(zip(decision_uplift["uplift_cell_id"], decision_uplift["uplift"]))
    uplift_origin = dict(zip(decision_uplift["uplift_cell_id"], decision_uplift["uplift_origen"]))
    rates, origins, ids, horizons, techniques, tech_origins = [], [], [], [], [], []
    for _, row in rows.iterrows():
        estimation_id = estimation_of.get(row["fs_id"], row["fs_id"])
        prediction = predictions.get((estimation_id, row[configuration.period_col]))
        if prediction is not None and np.isfinite(prediction[0]):
            rate, h, technique = prediction
            origin, tech_origin = ORIGIN_SERIES, technique_origin.get(estimation_id, TECH_DEFAULT)
        elif np.isfinite(estimate_of.get(row["fs_id"], np.nan)):
            rate, h, technique, origin, tech_origin = estimate_of[row["fs_id"]], np.nan, DEFAULT_TECHNIQUE, ORIGIN_SERIES, TECH_DEFAULT
        elif row["mandatory_cell_id"] in cell_mean.index:
            rate, h, technique, origin, tech_origin = cell_mean[row["mandatory_cell_id"]], np.nan, DEFAULT_TECHNIQUE, ORIGIN_CELL, TECH_DEFAULT
        else:
            rate, h, technique, origin, tech_origin = global_mean, np.nan, DEFAULT_TECHNIQUE, ORIGIN_GLOBAL, TECH_DEFAULT
        rates.append(min(float(rate), configuration.rate_cap)); origins.append(origin); ids.append(estimation_id)
        horizons.append(h); techniques.append(technique); tech_origins.append(tech_origin)
    rows["id_estimacion"], rows["h"], rows["tecnica"], rows["tecnica_origen"] = ids, horizons, techniques, tech_origins
    rows["tasa"], rows["tasa_origen"] = rates, origins
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
             side; clipped so the rate stays in [0, rate_cap]. Rows whose (id, h) has no
             band use the binomial error at z, flagged `banda_origen = "binomial"`.
    """
    band_lookup = {(r["id_estimacion"], int(r["h"])): (r["q_low_norm"], r["q_high_norm"], r["banda_origen"])
                   for _, r in decision_error_bands.iterrows()}
    max_h = {i: h for i, h in decision_error_bands.groupby("id_estimacion")["h"].max().items()}
    pool_info = decision_dynamics.set_index("id_estimacion")[["n_pool", "tasa_pool"]]
    lows, highs, origins = [], [], []
    for _, row in detail.iterrows():
        estimation_id, h = row["id_estimacion"], row["h"]
        se_row = binomial_se_pp(row["tasa"], max(float(row[configuration.pipeline_units_col]), 1.0))
        if estimation_id in pool_info.index:
            se_pool = binomial_se_pp(float(pool_info.loc[estimation_id, "tasa_pool"]) if np.isfinite(pool_info.loc[estimation_id, "tasa_pool"]) else row["tasa"],
                                     max(float(pool_info.loc[estimation_id, "n_pool"]), 1.0))
        else:
            se_pool = se_row
        key = (estimation_id, int(min(h, max_h.get(estimation_id, 0)))) if np.isfinite(h) and estimation_id in max_h else None
        if key in band_lookup:
            q_low, q_high, origin = band_lookup[key]
            if key[1] < h:
                origin = f"{origin}+extrapolada"
        else:
            q_low, q_high, origin = -configuration.z, configuration.z, "binomial"
        low = -np.sqrt((q_low * se_pool) ** 2 + (configuration.z * se_row) ** 2)
        high = np.sqrt((q_high * se_pool) ** 2 + (configuration.z * se_row) ** 2)
        low = max(low, -100 * row["tasa"])
        high = min(high, 100 * (configuration.rate_cap - row["tasa"]))
        lows.append(low); highs.append(high); origins.append(origin)
    bands = detail.copy()
    bands["banda_low_pp"], bands["banda_high_pp"], bands["banda_origen"] = np.round(lows, 3), np.round(highs, 3), origins
    money = bands[configuration.pipeline_usd_col] * bands["uplift"] / 100
    bands["banda_low_usd"], bands["banda_high_usd"] = (bands["banda_low_pp"] * money).round(2), (bands["banda_high_pp"] * money).round(2)
    return bands


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
    monthly["banda_monotona"] = (monthly["banda_rel_pct"].diff().fillna(0) >= -BAND_NARROWING_TOLERANCE_PCT).astype(int)
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
    extended = extend_forecast_units(fine_table, units, series_estimates, configuration)
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
    detail_columns = ["fu_key", "comb_key", "fu_comb_key", "fs_id", "id_estimacion", period, configuration.pipeline_units_col,
                      configuration.pipeline_usd_col, "h", "tecnica", "tecnica_origen", "tasa", "tasa_origen", "uplift",
                      "uplift_origen", "esperado_usd", "simulada", "nivel_riesgo"]
    band_columns = ["fu_key", "comb_key", "fu_comb_key", "id_estimacion", period, "h", "banda_low_pp", "banda_high_pp",
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
              f"simulated {row['pct_simulado']:5.1f}%  {'' if row['banda_monotona'] else '⚠ band narrowed'}")
    return dict(forecast_detail=bands[detail_columns], forecast_bands=bands[band_columns], horizon_report=horizon,
                forecast_by_level=by_level, forecast_units_extended=extended)
