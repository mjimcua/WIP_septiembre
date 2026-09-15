"""pipeline.py — SFF v3 · the two runners.

  run_analysis(configuration)   ANALYSIS. Phases 0-5 with every diagnostic, writes the
                                decision tables (`decision_*`) and the analysis tables,
                                and — because the decisions are in memory — also produces
                                the forecast. This is the run of the evaluation period,
                                the one the analyst keeps.
  run_pipeline(configuration)   RUN. Phases 0, 1.1, 1.3 (ladder), 4, 5 reading the
                                decisions from the persisted `decision_*` tables written
                                by the last analysis. No η², no backtest, no bands are
                                computed: they are read. This is the monthly run, the
                                one that can be delegated. It refuses to run if a decision
                                table is missing, and warns when it is older than
                                `decision_max_age_months`.

Both call `configuration.read_raw()` (overridden by the caller) and write through
`configuration.write`. No file, no query, no legacy in this module.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import datetime
import os
import sys
import time

import pandas as pd

# The project is a flat folder imported from notebooks and scripts alike: make sure the
# folder of this file is importable BEFORE importing the sibling modules below (that is
# why those imports come after this block, not at the top).
PROJECT_FOLDER = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
if PROJECT_FOLDER not in sys.path:
    sys.path.insert(0, PROJECT_FOLDER)

import analysis_backtest
import analysis_baseline
import analysis_data_profile
import analysis_dimensions
import analysis_seasonality_benchmark
import raw_data_validation
import run_forecast_assembly
import run_rate_series
import run_support_ladder
import run_uplift
import run_validation
import support_reference
from config import Config, hash_key, join_columns

# ─── named constants ─────────────────────────────────────────────────────────────
SECTION_RULE = "═" * 74


def section(title: str, started_at: float) -> None:
    """Print the section header with the seconds the previous section took."""
    print(SECTION_RULE, f"\n{title}   (previous section {time.time() - started_at:.1f} s)")
DECISION_TABLES = ("decision_eta2", "decision_support", "decision_estacionalidad", "pool_reference", "decision_technique",
                   "decision_error_bands", "decision_uplift", "decision_aggregate_bands")


# ═══════════════════════════════════════════════════════════════════════════════════
# SHARED STEPS
# ═══════════════════════════════════════════════════════════════════════════════════

REQUIRED_CONFIG_FIELDS = ("timevarying_model_version", "uplift_floor", "backtest_test_start", "extended_horizon_end",
                          "backtest_horizons", "benchmark_min_support", "acquisition_min_pairs", "test_months")


def check_configuration_version(configuration: Config) -> None:
    """Stop with a clear message when config.py is older than the phases that read it."""
    missing = [name for name in REQUIRED_CONFIG_FIELDS if not hasattr(configuration, name)]
    if missing:
        raise AttributeError(f"config.py is outdated: Config has no {missing}. Replace config.py with the one of this "
                             f"delivery (your subclass with read_raw keeps working) and restart the kernel.")


def phase_0(configuration: Config) -> dict:
    """Raw → validated, conditioned, the two tables, keys, labels, reference."""
    check_configuration_version(configuration)
    started = time.time()
    print(SECTION_RULE, "\nPHASE 0 — raw data validation")
    raw = configuration.read_raw()
    print(f"[0] raw read in {time.time() - started:.1f} s · {len(raw):,} rows")
    validated = raw_data_validation.validate_raw(raw, configuration)
    conditioned = raw_data_validation.apply_current_month_doctrine(validated, configuration)
    fine_table = raw_data_validation.build_fine_table(conditioned, configuration)
    forecast_units = raw_data_validation.aggregate_to_forecast_units(fine_table, configuration)
    fu_lookup, comb_lookup = raw_data_validation.build_key_lookups(forecast_units, fine_table)
    labeled_units = raw_data_validation.label_universe_and_routes(forecast_units, configuration)
    # both fact tables carry the series id (fs_id; write stamps fs_key) so the BI joins
    # unit -> series without deriving it from fu_id
    fine_table["fs_id"] = join_columns(fine_table, configuration.rate_series_columns)
    configuration.write(labeled_units, "fact_fu")
    configuration.write(fine_table, "fact_fine")
    configuration.write(fu_lookup, "lookup_fu")
    configuration.write(comb_lookup, "lookup_comb")
    support_reference.build_support_reference(labeled_units, configuration)
    return dict(fine_table=fine_table, labeled_units=labeled_units, conditioned=conditioned)


def build_key_bridge(fine_table: pd.DataFrame, units: pd.DataFrame, decision_support: pd.DataFrame,
                     configuration: Config) -> pd.DataFrame:
    """One thin spine from every raw row to its series, its estimation id, its uplift cell
    and its mandatory cell. Persisted as `key_bridge`."""
    columns = list(dict.fromkeys(["fu_comb_key", "fu_id", "fu_key", "comb_id", "comb_key"]
                                 + configuration.uplift_cell_columns + configuration.business_mandatory_dims))
    bridge = fine_table.drop_duplicates("fu_comb_key")[columns].copy()
    bridge["fs_id"] = bridge["fu_id"].str.rsplit("|", n=1).str[0]
    bridge["fs_key"] = bridge["fs_id"].map(hash_key)
    bridge = bridge.merge(decision_support[["fs_id", "id_estimacion", "peldano", "signo"]], on="fs_id", how="left")
    bridge["id_estimacion"] = bridge["id_estimacion"].fillna(bridge["fs_id"])
    bridge["uplift_cell_id"] = join_columns(bridge, configuration.uplift_cell_columns)
    bridge["uplift_cell_key"] = bridge["uplift_cell_id"].map(hash_key)
    bridge["celda_id"] = join_columns(bridge, configuration.business_mandatory_dims)
    labels = units.drop_duplicates("fs_id")[["fs_id", "universo", "ruta"]]
    bridge = bridge.merge(labels, on="fs_id", how="left")
    keep = ["fu_comb_key", "fu_id", "fu_key", "comb_id", "comb_key", "fs_id", "fs_key", "id_estimacion", "peldano",
            "signo", "uplift_cell_id", "uplift_cell_key", "celda_id", "universo", "ruta"]
    configuration.write(bridge[keep], "key_bridge")
    return bridge[keep]


def forecast_horizons(fine_table: pd.DataFrame, units: pd.DataFrame, configuration: Config) -> list:
    """1..H, with H = months from the last month with truth to the end of the forecast
    (known projection or extended horizon), or `max_forecast_horizon` if configured."""
    if configuration.max_forecast_horizon is not None:
        return list(range(1, configuration.max_forecast_horizon + 1))
    last_truth = units[units["tasa"].notna()][configuration.period_col].max()
    end = fine_table[configuration.period_col].max()
    if configuration.extended_horizon_end is not None:
        end = max(end, pd.Period(configuration.extended_horizon_end, freq="M"))
    return list(range(1, max(int((end - last_truth).n), 1) + 1))


def draw_top_sheets(results: dict, configuration: Config) -> list:
    """The sheets of the `sheets_top_series` series with the most projected money, drawn
    into <outdir>/diagnostics/ at the end of every analysis. Never stops the run."""
    if not configuration.sheets_top_series:
        return []
    from sheet import sheet
    card = results["series_card"]
    top = card[card["ruta"] == "trainable"].sort_values("usd_proyectado", ascending=False).head(int(configuration.sheets_top_series))
    print(SECTION_RULE, f"\nSHEETS — the {len(top)} series with the most projected money")
    paths = []
    for _, row in top.iterrows():
        try:
            drawn = sheet(row["fs_id"], configuration, results=results, figure=True, verbose=False)
            paths.append(drawn["figure"])
            print(f"   {row['fs_id'][:70]:<70} ${row['usd_proyectado']:>13,.0f}  →  {drawn['figure']}")
        except Exception as error:
            print(f"   {row['fs_id'][:70]:<70} sheet failed: {type(error).__name__}: {error}")
    return paths


def validate(results: dict, configuration: Config, started: float) -> pd.DataFrame:
    section("VALIDATION", started)
    return run_validation.run_validation(results, configuration)


# ═══════════════════════════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════════

def run_analysis(configuration: Config) -> dict:
    """The evaluation run: every diagnostic, every decision written, the forecast produced."""
    started = time.time()
    results = phase_0(configuration)
    fine_table, labeled_units = results["fine_table"], results["labeled_units"]
    profiles = analysis_data_profile.run_raw_profile(results["conditioned"], configuration)

    section("PHASE 1 — rate series, dimensions, support ladder", started); started = time.time()
    units, series_summary = run_rate_series.build_rate_series(labeled_units, configuration)
    profiles.update(analysis_data_profile.run_fu_profile(units, fine_table, configuration))
    dimensions = analysis_dimensions.run_dimension_analysis(units, series_summary, configuration)
    series_estimates, series_card, decision_support, parent_ladder = run_support_ladder.run_support_ladder(
        units, series_summary, dimensions["decision_eta2"], configuration)
    key_bridge = build_key_bridge(fine_table, units, decision_support, configuration)
    composition = analysis_dimensions.run_composition_analysis(units, configuration)

    section("PHASE 2 — seasonality benchmark (big series) and pool reference", started); started = time.time()
    test_months = units.loc[units[configuration.dataset_role_col] == "test", configuration.period_col]
    first_test_month = str(test_months.min()) if len(test_months) else None
    benchmark = analysis_seasonality_benchmark.run_seasonality_benchmark(series_card, units, fine_table, configuration)
    monthly_series = analysis_backtest.monthly_series_by_estimation_id(units, decision_support, parent_ladder, configuration)
    pool_reference = analysis_backtest.build_pool_reference(monthly_series, benchmark["decision_estacionalidad"], configuration)

    section("PHASE 3 — backtest, technique, bands", started); started = time.time()
    forecast_horizon = min(forecast_horizons(fine_table, units, configuration)[-1], configuration.backtest_horizon_cap)
    judged_horizons = sorted({h for h in configuration.backtest_horizons if h <= forecast_horizon} | {forecast_horizon})
    backtest = analysis_backtest.run_backtest_analysis(monthly_series, pool_reference, configuration, judged_horizons, first_test_month)

    section("PHASE 4 — uplift", started); started = time.time()
    decision_uplift = run_uplift.run_uplift(fine_table, configuration)

    section("PHASE 5 — assembly, extended horizon, bands", started); started = time.time()
    decisions = dict(decision_eta2=dimensions["decision_eta2"], decision_support=decision_support,
                     decision_estacionalidad=benchmark["decision_estacionalidad"], pool_reference=pool_reference,
                     decision_technique=backtest["decision_technique"],
                     decision_error_bands=backtest["decision_error_bands"], decision_uplift=decision_uplift,
                     backtest_holdout_aggregate=backtest["backtest_holdout_aggregate"],
                     decision_aggregate_bands=backtest["decision_aggregate_bands"])
    forecast = run_forecast_assembly.run_forecast_assembly(fine_table, units, series_estimates, series_card,
                                                           decisions, monthly_series, configuration, backtest["backtest_holdout"],
                                                           composition["mix_shift_decomposition"])
    baseline = analysis_baseline.run_baseline(fine_table, forecast["forecast_units_extended"], forecast["business_summary"], configuration)
    results_so_far = dict(fine_table=fine_table, units=units, series_summary=series_summary, series_estimates=series_estimates,
                          series_card=series_card, key_bridge=key_bridge, parent_ladder=parent_ladder, monthly_series=monthly_series,
                          decisions=decisions, backtest=backtest, dimensions=dimensions, composition=composition, forecast=forecast)
    sheets = draw_top_sheets(results_so_far, configuration)
    report = validate(dict(
        fine_table=fine_table, forecast_units=units, key_bridge=key_bridge, forecast_detail=forecast["forecast_detail"],
        forecast_bands=forecast["forecast_bands"], horizon_report=forecast["horizon_report"], series_card=series_card,
        decision_support=decision_support, parent_ladder=parent_ladder, backtest_holdout=backtest["backtest_holdout"],
        decision_uplift=decision_uplift), configuration, started)
    print(SECTION_RULE, "\nanalysis complete · decisions and tables in", configuration.outdir)
    return dict(fine_table=fine_table, units=units, series_summary=series_summary, series_estimates=series_estimates,
                series_card=series_card, key_bridge=key_bridge, parent_ladder=parent_ladder, monthly_series=monthly_series,
                decisions=decisions, backtest=backtest, dimensions=dimensions, forecast=forecast, validation=report,
                profiles=profiles, baseline=baseline, benchmark=benchmark, composition=composition, sheets=sheets)


# ═══════════════════════════════════════════════════════════════════════════════════
# RUN (monthly, delegable)
# ═══════════════════════════════════════════════════════════════════════════════════

def read_decisions(configuration: Config) -> dict:
    """Read the decision tables from the configured engine; refuse if any is missing."""
    if configuration.engine is None:
        raise RuntimeError("run_pipeline needs an engine with the decision tables written by run_analysis")
    decisions = {}
    for logical_name in DECISION_TABLES:
        physical = configuration._resolve_physical_table_name(logical_name)
        try:
            table = pd.read_sql(f"SELECT * FROM {configuration._qualified_table_name(physical)}", configuration.engine)
        except Exception as error:
            raise RuntimeError(f"decision table '{logical_name}' ({physical}) is missing: run the analysis first") from error
        if "process_date" in table.columns and len(table):
            written = pd.to_datetime(table["process_date"].iloc[0])
            age_months = (datetime.datetime.now() - written).days / 30.4
            if age_months > configuration.decision_max_age_months:
                print(f"[run] WARNING decision '{logical_name}' is {age_months:.1f} months old "
                      f"(max {configuration.decision_max_age_months}): the analysis has expired")
        decisions[logical_name] = table.drop(columns=[c for c in ("process_date", "execution_id") if c in table.columns])
    return decisions


def run_pipeline(configuration: Config) -> dict:
    """The monthly run: read decisions, apply them, produce the forecast. No decision is taken."""
    started = time.time()
    decisions = read_decisions(configuration)
    results = phase_0(configuration)
    fine_table, labeled_units = results["fine_table"], results["labeled_units"]
    section("PHASE 1 — rate series and support (decisions read)", started); started = time.time()
    units, series_summary = run_rate_series.build_rate_series(labeled_units, configuration)
    series_estimates, series_card, decision_support, parent_ladder = run_support_ladder.run_support_ladder(
        units, series_summary, decisions["decision_eta2"], configuration)
    key_bridge = build_key_bridge(fine_table, units, decision_support, configuration)
    monthly_series = analysis_backtest.monthly_series_by_estimation_id(units, decision_support, parent_ladder, configuration)
    section("PHASE 4 — uplift", started); started = time.time()
    decision_uplift = run_uplift.run_uplift(fine_table, configuration)
    section("PHASE 5 — assembly (decisions read)", started); started = time.time()
    applied = dict(decisions, decision_support=decision_support, decision_uplift=decision_uplift)
    forecast = run_forecast_assembly.run_forecast_assembly(fine_table, units, series_estimates, series_card,
                                                           applied, monthly_series, configuration)
    report = validate(dict(
        fine_table=fine_table, forecast_units=units, key_bridge=key_bridge, forecast_detail=forecast["forecast_detail"],
        forecast_bands=forecast["forecast_bands"], horizon_report=forecast["horizon_report"], series_card=series_card,
        decision_support=decision_support, parent_ladder=parent_ladder, decision_uplift=decision_uplift), configuration, started)
    print(SECTION_RULE, "\nmonthly run complete · tables in", configuration.outdir)
    return dict(fine_table=fine_table, units=units, series_card=series_card, forecast=forecast, validation=report)
