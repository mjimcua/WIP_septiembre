"""main.py — SFF v2 · project runner during the refactor.

WHAT IT RUNS. The full pipeline end to end, on the synthetic dataset or on the golden
input, and writes the 25 star-schema tables to `salida/sff_v2.db`. It is the runner the
equivalence gate executes (`tests/eval_harness.py`) and the one to run by hand to see
the console of every phase.

TRANSITIONAL WIRING. The refactor rewrites one phase per chat (DISENO_SPLIT §7). Until
every phase lives in `run/` and `analysis/`, this runner mixes:
  · `run/`     the modules already rewritten in verbose style (config, then phase 0...)
  · `sff_v3/`  the legacy modules not yet rewritten (the numerical reference)
`run/` is placed FIRST on sys.path, so `import config` resolves to `run/config.py` for
every module — legacy phases included, which keep working through the legacy aliases
(`grano_tasa`, `medidas`, `validar_columnas`...). When a phase is rewritten, its import
below moves from the legacy module to the `run/` module; nothing else changes.

USAGE:
    python main.py            synthetic dataset, seed 7
    python main.py 11         synthetic dataset, seed 11
    python main.py --golden   the frozen input tests/golden/raw_golden.csv (for the gate)

The numbers must be identical to the legacy runner's: the gate checks it.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import sys

REPOSITORY_ROOT = os.path.dirname(os.path.abspath(__file__))
RUN_FOLDER = os.path.join(REPOSITORY_ROOT, "run")
LEGACY_FOLDER = os.path.join(REPOSITORY_ROOT, "sff_v3")
sys.path.insert(0, LEGACY_FOLDER)
sys.path.insert(0, RUN_FOLDER)          # first: `config` must resolve to run/config.py

import pandas as pd                      # noqa: E402
from sqlalchemy import create_engine     # noqa: E402

from config import Config                # noqa: E402  (run/config.py)
from synthetic import build_raw          # noqa: E402  (legacy, test tooling)
import fase0 as phase0                   # noqa: E402  (legacy until phase 0 is validated)
import fase1 as phase1                   # noqa: E402  (legacy)
import fase2 as phase2                   # noqa: E402  (legacy)
import fase3_assembly as phase3          # noqa: E402  (legacy)
import fase4_backtest as phase4          # noqa: E402  (legacy)
import validation                        # noqa: E402  (legacy)


# ─── named constants ─────────────────────────────────────────────────────────────
OUTPUT_FOLDER = os.path.join(REPOSITORY_ROOT, "salida")
OUTPUT_DATABASE_URL = "sqlite:///" + os.path.join(OUTPUT_FOLDER, "sff_v2.db")
GOLDEN_INPUT_PATH = os.path.join(REPOSITORY_ROOT, "tests", "golden", "raw_golden.csv")
DEFAULT_SYNTHETIC_SEED = 7
SECTION_RULE = "═" * 70

# The taxonomy of the synthetic / golden dataset (NOT production: production is
# `Config()` with no arguments). One mandatory dimension on purpose — the multi-dim
# case is covered by tests/smoke_multidim.py.
GOLDEN_TAXONOMY = dict(
    business_mandatory_dims=["region"],
    structural_timevarying_dims={"dormant": "negative", "softcancel": "negative",
                                 "no_instalado": "negative", "autorenew": "positive"},
    extra_renovacion=["product", "channel"],
    extra_revalorizacion=["discount", "newcust"])


def load_raw(arguments: list) -> pd.DataFrame:
    """Return the raw to run on: the golden input or a synthetic dataset.

    INPUT:   arguments — sys.argv without the program name.
    OUTPUT:  the raw DataFrame.
    RULES:   `--golden` reads the frozen input with `keep_default_na=False`: the region
             "NA" is North America, not a missing value (bug caught in ASUNCIONES).
             Otherwise a synthetic dataset with the seed given, or the default seed.
    EDGE CASES: a non-numeric seed raises ValueError from int().
    CONSOLE: nothing.
    STEPS:
      [1] Golden input when asked.
      [2] Synthetic dataset otherwise.
    """
    # [1] the frozen input of the equivalence gate
    if "--golden" in arguments:
        return pd.read_csv(GOLDEN_INPUT_PATH, keep_default_na=False, na_values=[""])

    # [2] a synthetic dataset, seeded
    if arguments:
        synthetic_seed = int(arguments[0])
    else:
        synthetic_seed = DEFAULT_SYNTHETIC_SEED
    return build_raw(synthetic_seed)


def main(arguments: list) -> None:
    """Run the five phases and the validation, writing every table.

    INPUT:   arguments — sys.argv without the program name.
    OUTPUT:  none; 25 tables in `salida/sff_v2.db`.
    RULES:   the order of calls and of writes is the legacy runner's, so the gate
             compares like with like. Phase 0 writes fact_fu, fact_fine and the two
             lookups from here (the phase functions return them; the runner persists).
    EDGE CASES: any blocking validation inside a phase raises and stops the run.
    CONSOLE: one banner per phase plus the console of every function.
    STEPS:
      [0] Config on the golden taxonomy, sqlite engine, raw.
      [1] Phase 0: contract, split and keys, universe and routes, immutable reference.
      [2] Phase 1: series and gaps, diagnosis round 1, support repair, round 2.
      [3] Phase 2: uplift per cell, diagnosis, improvement.
      [4] Phase 3: key bridge and assembly.
      [5] Phase 4: backtest, rolling, bands, per-FU tables, horizon report.
      [6] Validation panel.
    """
    # [0] the execution context
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    sqlite_engine = create_engine(OUTPUT_DATABASE_URL)
    configuration = Config(sql_engine=sqlite_engine, sql_schema=None, outdir=OUTPUT_FOLDER,
                           **GOLDEN_TAXONOMY)
    raw = load_raw(arguments)

    # [1] PHASE 0 — contract, load, reference
    print(SECTION_RULE, "\nPHASE 0 — contract, load, reference")
    validated_raw = phase0.f0_load_and_validate(raw, configuration)
    fu_view, fine_grain_table, fu_lookup, comb_lookup = phase0.f0_split_and_key(validated_raw, configuration)
    configuration.write(fu_view, "fact_fu")
    configuration.write(fine_grain_table, "fact_fine")
    configuration.write(fu_lookup, "lookup_fu")
    configuration.write(comb_lookup, "lookup_comb")
    labeled_view = phase0.f0_universe_routes(fu_view, configuration)
    # the immutable reference: persisted here, consumed by no phase
    phase0.f0_fu_summary(labeled_view, configuration)

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


if __name__ == "__main__":
    main(sys.argv[1:])
