"""pipeline.py — SFF v2 · RUN · the sequence of phases.

`run_pipeline(configuration)` executes the whole framework once: it asks the Config for
the raw (`configuration.read_raw()`, overridden by the caller), runs phases 0 to 4 and
the validation, and writes every table through `configuration.write`. It contains no
loading code and no knowledge of where the raw comes from or where the tables go: both
are decided by the Config the caller built.

TRANSITIONAL WIRING. The refactor rewrites one phase per chat (DISENO_SPLIT §7). Until
every phase lives in `run/` and `analysis/`, this module imports:
  · from `run/` and `analysis/`  the modules already rewritten (config, phase 0)
  · from `sff_v3/`  the legacy modules not yet rewritten (the numerical reference)
`run/` goes FIRST on sys.path so `import config` resolves to `run/config.py` for every
module, legacy phases included (they keep working through the legacy aliases). When a
phase is rewritten, its import below moves from the legacy module to the `run/` module;
nothing else changes. When the last phase moves, the sys.path lines disappear.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import sys

RUN_FOLDER = os.path.dirname(os.path.abspath(__file__))
REPOSITORY_ROOT = os.path.dirname(RUN_FOLDER)
LEGACY_FOLDER = os.path.join(REPOSITORY_ROOT, "sff_v3")
ANALYSIS_FOLDER = os.path.join(REPOSITORY_ROOT, "analysis")
sys.path.insert(0, LEGACY_FOLDER)
sys.path.insert(0, ANALYSIS_FOLDER)
sys.path.insert(0, RUN_FOLDER)          # first: `config` must resolve to run/config.py

from config import Config                # noqa: E402  (run/config.py)
import raw_data_validation               # noqa: E402  (run/, phase 0 RUN)
import support_reference                 # noqa: E402  (analysis/, phase 0 ANALYSIS)
import fase1 as phase1                   # noqa: E402  (legacy)
import fase2 as phase2                   # noqa: E402  (legacy)
import fase3_assembly as phase3          # noqa: E402  (legacy)
import fase4_backtest as phase4          # noqa: E402  (legacy)
import validation                        # noqa: E402  (legacy)


# ─── named constants ─────────────────────────────────────────────────────────────
SECTION_RULE = "═" * 70


def run_pipeline(configuration: Config) -> dict:
    """Run the five phases and the validation, writing every table.

    INPUT:   configuration — a Config subclass with `read_raw()` overridden and, if the
             tables go to SQL, an engine configured or injected.
    OUTPUT:  a dict with the main in-memory results, for tests and notebooks:
             fine_grain_table, labeled_view, series_estimates, uplift_cells,
             key_bridge, future_rows, forecast_bands. Every table is also persisted.
    RULES:   the order of calls and of writes is fixed: later phases consume what
             earlier phases return, and the persisted tables are the contract of the BI.
    EDGE CASES: a blocking validation inside a phase raises and stops the run; nothing
             after it is written.
    CONSOLE: one banner per phase plus the console of every function.
    STEPS:
      [0] The raw, from the caller's `read_raw`.
      [1] Phase 0 RUN: contract, doctrine, the two tables and keys, labels;
          then phase 0 ANALYSIS: the immutable reference.
      [2] Phase 1: series and gaps, diagnosis round 1, support repair, round 2.
      [3] Phase 2: uplift per cell, diagnosis, improvement.
      [4] Phase 3: key bridge and assembly.
      [5] Phase 4: backtest, rolling, bands, per-FU tables, horizon report.
      [6] Validation panel.
    """
    # [0] the raw: where it comes from is the caller's business
    raw = configuration.read_raw()

    # [1] PHASE 0 · RUN — raw data validation: contract, doctrine, tables, keys, labels
    print(SECTION_RULE, "\nPHASE 0 — raw data validation")
    validated_raw = raw_data_validation.validate_raw(raw, configuration)
    conditioned_raw = raw_data_validation.apply_current_month_doctrine(validated_raw, configuration)
    fine_grain_table = raw_data_validation.build_fine_table(conditioned_raw, configuration)
    forecast_units = raw_data_validation.aggregate_to_forecast_units(fine_grain_table, configuration)
    fu_lookup, comb_lookup = raw_data_validation.build_key_lookups(forecast_units, fine_grain_table)
    configuration.write(forecast_units, "fact_fu")
    configuration.write(fine_grain_table, "fact_fine")
    configuration.write(fu_lookup, "lookup_fu")
    configuration.write(comb_lookup, "lookup_comb")
    labeled_view = raw_data_validation.label_universe_and_routes(forecast_units, configuration)

    # [1b] PHASE 0 · ANALYSIS — the immutable reference (reported, consumed by no phase)
    support_reference.build_support_reference(labeled_view, configuration)

    # [2] PHASE 1 — renewal branch
    print(SECTION_RULE, "\nPHASE 1 — renewal branch")
    labeled_view, series_summary = phase1.f1_series_and_gaps(labeled_view, configuration)
    # gap-filler rows (sintetica=1) persisted so BI can see WHICH months were imputed
    gap_row_columns = (["fu_key", "fu_id", "fs_id", configuration.period_col,
                        configuration.dataset_role_col]
                       + configuration.core_measures + ["sintetica"])
    gap_rows = labeled_view[labeled_view["sintetica"] == 1][gap_row_columns].copy()
    gap_rows[configuration.period_col] = gap_rows[configuration.period_col].astype(str)
    configuration.write(gap_rows, "fact_fu_gaps")
    eta2_by_dim, eta2_pairs, counterfactual_table = phase1.f1_diagnose_round1(
        labeled_view, series_summary, configuration)
    repaired_view, series_estimates, support_chain_rows = phase1.f1_improve_support(
        labeled_view, series_summary, eta2_by_dim, configuration)
    phase1.f1_support_chain(support_chain_rows, configuration)
    dynamics_diagnosis = phase1.f1_diagnose_round2(repaired_view, series_estimates, configuration)

    # [3] PHASE 2 — revaluation branch
    print(SECTION_RULE, "\nPHASE 2 — revaluation branch")
    uplift_cells, renewer_rows = phase2.f2_uplift_fine(fine_grain_table, configuration)
    uplift_eta2_by_axis = phase2.f2_diagnose(uplift_cells, renewer_rows, configuration)
    uplift_cells, uplift_chain_rows = phase2.f2_improve(uplift_cells, uplift_eta2_by_axis, configuration)

    # [4] PHASE 3 — assembly
    print(SECTION_RULE, "\nPHASE 3 — assembly")
    key_bridge = phase3.f3_build_key_bridge(fine_grain_table, repaired_view, series_estimates, configuration)
    future_rows = phase3.f3_ensamblaje(fine_grain_table, repaired_view, series_estimates,
                                       uplift_cells, configuration)

    # [5] PHASE 4 — backtest by horizon
    print(SECTION_RULE, "\nPHASE 4 — backtest by horizon")
    backtest_long, technique_selection, rate_series_by_pool = phase4.f4_backtest(
        repaired_view, series_estimates, configuration)
    rolling_table, rolling_summary = phase4.f4_rolling_next_month(repaired_view, configuration)
    forecast_bands = phase4.f4_forecast_bands(future_rows, rolling_table, technique_selection,
                                              series_estimates, rate_series_by_pool, configuration)
    technique_dim, backtest_per_fu, forecast_per_fu = phase4.f4_tablas_fu(
        repaired_view, fine_grain_table, series_estimates, uplift_cells, backtest_long,
        rate_series_by_pool, configuration)
    horizon_series, horizon_total = phase4.f4_horizon_report(
        rolling_table, technique_selection, forecast_bands, future_rows, configuration)

    # [6] validation
    validation.run_validation(dict(fine_grain_table=fine_grain_table, fu_view=labeled_view,
                                   key_bridge=key_bridge, future_rows=future_rows,
                                   support_chain_rows=support_chain_rows,
                                   rolling_table=rolling_table,
                                   technique_selection=technique_selection,
                                   forecast_bands=forecast_bands,
                                   dynamics_diagnosis=dynamics_diagnosis,
                                   uplift_cells=uplift_cells), configuration)
    print(SECTION_RULE, "\n✓ full run complete · tables in", configuration.outdir)

    return dict(fine_grain_table=fine_grain_table, labeled_view=labeled_view,
                series_estimates=series_estimates, uplift_cells=uplift_cells,
                key_bridge=key_bridge, future_rows=future_rows, forecast_bands=forecast_bands)
