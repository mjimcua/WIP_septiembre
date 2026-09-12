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

import pandas as pd

PROJECT_FOLDER = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
if PROJECT_FOLDER not in sys.path:
    sys.path.insert(0, PROJECT_FOLDER)

import analysis_backtest                  # noqa: E402
import analysis_dimensions                # noqa: E402
import analysis_dynamics                  # noqa: E402
import raw_data_validation                # noqa: E402
import run_forecast_assembly              # noqa: E402
import run_rate_series                    # noqa: E402
import run_support_ladder                 # noqa: E402
import run_uplift                         # noqa: E402
import run_validation                     # noqa: E402
import support_reference                  # noqa: E402
from config import Config, hash_key, join_columns   # noqa: E402

# ─── named constants ─────────────────────────────────────────────────────────────
SECTION_RULE = "═" * 74
DECISION_TABLES = ("decision_eta2", "decision_support", "decision_dynamics", "decision_technique",
                   "decision_error_bands", "decision_uplift")


# ═══════════════════════════════════════════════════════════════════════════════════
# SHARED STEPS
# ═══════════════════════════════════════════════════════════════════════════════════

def phase_0(configuration: Config) -> dict:
    """Raw → validated, conditioned, the two tables, keys, labels, reference."""
    print(SECTION_RULE, "\nPHASE 0 — raw data validation")
    raw = configuration.read_raw()
    validated = raw_data_validation.validate_raw(raw, configuration)
    conditioned = raw_data_validation.apply_current_month_doctrine(validated, configuration)
    fine_table = raw_data_validation.build_fine_table(conditioned, configuration)
    forecast_units = raw_data_validation.aggregate_to_forecast_units(fine_table, configuration)
    fu_lookup, comb_lookup = raw_data_validation.build_key_lookups(forecast_units, fine_table)
    configuration.write(forecast_units, "fact_fu")
    configuration.write(fine_table, "fact_fine")
    configuration.write(fu_lookup, "lookup_fu")
    configuration.write(comb_lookup, "lookup_comb")
    labeled_units = raw_data_validation.label_universe_and_routes(forecast_units, configuration)
    support_reference.build_support_reference(labeled_units, configuration)
    return dict(fine_table=fine_table, labeled_units=labeled_units)


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


def validate(results: dict, configuration: Config) -> pd.DataFrame:
    print(SECTION_RULE)
    return run_validation.run_validation(results, configuration)


# ═══════════════════════════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════════

def run_analysis(configuration: Config) -> dict:
    """The evaluation run: every diagnostic, every decision written, the forecast produced."""
    results = phase_0(configuration)
    fine_table, labeled_units = results["fine_table"], results["labeled_units"]

    print(SECTION_RULE, "\nPHASE 1 — rate series, dimensions, support ladder")
    units, series_summary = run_rate_series.build_rate_series(labeled_units, configuration)
    dimensions = analysis_dimensions.run_dimension_analysis(units, series_summary, configuration)
    series_estimates, series_card, decision_support, parent_ladder = run_support_ladder.run_support_ladder(
        units, series_summary, dimensions["decision_eta2"], configuration)
    key_bridge = build_key_bridge(fine_table, units, decision_support, configuration)

    print(SECTION_RULE, "\nPHASE 2 — dynamics")
    decision_dynamics, monthly_series = analysis_dynamics.run_dynamics_analysis(units, decision_support, parent_ladder, configuration)

    print(SECTION_RULE, "\nPHASE 3 — backtest, technique, bands")
    horizons = forecast_horizons(fine_table, units, configuration)
    backtest = analysis_backtest.run_backtest_analysis(monthly_series, decision_dynamics, configuration, horizons)

    print(SECTION_RULE, "\nPHASE 4 — uplift")
    decision_uplift = run_uplift.run_uplift(fine_table, configuration)

    print(SECTION_RULE, "\nPHASE 5 — assembly, extended horizon, bands")
    decisions = dict(decision_eta2=dimensions["decision_eta2"], decision_support=decision_support,
                     decision_dynamics=decision_dynamics, decision_technique=backtest["decision_technique"],
                     decision_error_bands=backtest["decision_error_bands"], decision_uplift=decision_uplift)
    forecast = run_forecast_assembly.run_forecast_assembly(fine_table, units, series_estimates, series_card,
                                                           decisions, monthly_series, configuration)
    report = validate(dict(
        fine_table=fine_table, forecast_units=units, key_bridge=key_bridge, forecast_detail=forecast["forecast_detail"],
        forecast_bands=forecast["forecast_bands"], horizon_report=forecast["horizon_report"], series_card=series_card,
        decision_support=decision_support, parent_ladder=parent_ladder, backtest_holdout=backtest["backtest_holdout"],
        decision_uplift=decision_uplift), configuration)
    print(SECTION_RULE, "\n✓ analysis complete · decisions and tables in", configuration.outdir)
    return dict(fine_table=fine_table, units=units, series_summary=series_summary, series_estimates=series_estimates,
                series_card=series_card, key_bridge=key_bridge, parent_ladder=parent_ladder, monthly_series=monthly_series,
                decisions=decisions, backtest=backtest, dimensions=dimensions, forecast=forecast, validation=report)


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
                print(f"[run] ⚠ decision '{logical_name}' is {age_months:.1f} months old "
                      f"(max {configuration.decision_max_age_months}): the analysis has expired")
        decisions[logical_name] = table.drop(columns=[c for c in ("process_date", "execution_id") if c in table.columns])
    return decisions


def run_pipeline(configuration: Config) -> dict:
    """The monthly run: read decisions, apply them, produce the forecast. No decision is taken."""
    decisions = read_decisions(configuration)
    results = phase_0(configuration)
    fine_table, labeled_units = results["fine_table"], results["labeled_units"]
    print(SECTION_RULE, "\nPHASE 1 — rate series and support (decisions read)")
    units, series_summary = run_rate_series.build_rate_series(labeled_units, configuration)
    series_estimates, series_card, decision_support, parent_ladder = run_support_ladder.run_support_ladder(
        units, series_summary, decisions["decision_eta2"], configuration)
    key_bridge = build_key_bridge(fine_table, units, decision_support, configuration)
    monthly_series = analysis_dynamics.monthly_series_by_estimation_id(units, decision_support, parent_ladder, configuration)
    print(SECTION_RULE, "\nPHASE 4 — uplift")
    decision_uplift = run_uplift.run_uplift(fine_table, configuration)
    print(SECTION_RULE, "\nPHASE 5 — assembly (decisions read)")
    applied = dict(decisions, decision_support=decision_support, decision_uplift=decision_uplift)
    forecast = run_forecast_assembly.run_forecast_assembly(fine_table, units, series_estimates, series_card,
                                                           applied, monthly_series, configuration)
    report = validate(dict(
        fine_table=fine_table, forecast_units=units, key_bridge=key_bridge, forecast_detail=forecast["forecast_detail"],
        forecast_bands=forecast["forecast_bands"], horizon_report=forecast["horizon_report"], series_card=series_card,
        decision_support=decision_support, parent_ladder=parent_ladder, decision_uplift=decision_uplift), configuration)
    print(SECTION_RULE, "\n✓ monthly run complete · tables in", configuration.outdir)
    return dict(fine_table=fine_table, units=units, series_card=series_card, forecast=forecast, validation=report)
