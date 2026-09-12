"""test_pipeline.py — the test main of the whole pipeline (SFF v2).

WHAT IT DOES. Subclasses Config, overrides `read_raw` with the synthetic dataset
(tests/synthetic.py, seed 7), runs the full pipeline into a throw-away sqlite database
and checks the result. No parameters, no files to pass:

    python tests/test_pipeline.py     →  exit 0 if healthy, 1 with the list of failures

TWO KINDS OF CHECKS, kept apart on purpose:

  LOGIC (permanent)      properties the output must have whatever the code looks like:
                         money conserved from the raw to the reference table, one row
                         per key, every raw row reaching the bridge, no future row
                         without a rate, the validation panel with 0 FAIL, and the same
                         properties with SEVERAL mandatory dimensions (the case a single
                         dimension hides — ASUNCIONES 19). These are the tests that
                         describe the framework; they are the ones a regeneration prompt
                         points to as acceptance criterion.

  REFERENCE (temporary)  the 25 tables compared with `tests/reference_output.db`, the
                         output of the legacy code on the same synthetic input. It
                         answers "did the rewrite change a number?" while the legacy is
                         still the reference. It disappears when the first definitive
                         version is closed: the reference will be obsolete by then.

The production main (`main.py`) is the same three lines with a different `read_raw`.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import sqlite3
import sys

import numpy as np
import pandas as pd
from sqlalchemy import create_engine

TESTS_FOLDER = os.path.dirname(os.path.abspath(__file__))
REPOSITORY_ROOT = os.path.dirname(TESTS_FOLDER)
sys.path.insert(0, TESTS_FOLDER)
sys.path.insert(0, os.path.join(REPOSITORY_ROOT, "run"))

from config import Config          # noqa: E402
from pipeline import run_pipeline  # noqa: E402
from synthetic import build_raw    # noqa: E402


# ─── named constants ─────────────────────────────────────────────────────────────
SYNTHETIC_SEED = 7
TEST_OUTPUT_FOLDER = os.path.join(REPOSITORY_ROOT, "salida_test")
TEST_DATABASE_PATH = os.path.join(TEST_OUTPUT_FOLDER, "sff_v2_test.db")
MULTIDIM_OUTPUT_FOLDER = os.path.join(REPOSITORY_ROOT, "salida_test_multidim")
REFERENCE_DATABASE_PATH = os.path.join(TESTS_FOLDER, "reference_output.db")

# Money conservation tolerance: floating sums over a few hundred rows.
MONEY_TOLERANCE_USD = 1e-6
# Relative tolerance when comparing column sums with the reference.
REFERENCE_RELATIVE_TOLERANCE = 1e-6
# Columns that change on every run by design, excluded from the reference comparison.
TRACEABILITY_COLUMNS = {"process_date", "execution_id"}
# Key columns compared as sets, not as sums.
KEY_COLUMNS = {"fu_key", "fs_key", "comb_key"}

# The taxonomy of the synthetic dataset with ONE mandatory dimension (the reference
# was produced with it) and with TWO (the case that catches positional parsing).
SYNTHETIC_TIMEVARYING = {"dormant": "negative", "softcancel": "negative",
                         "no_instalado": "negative", "autorenew": "positive"}
SINGLE_MANDATORY_TAXONOMY = dict(business_mandatory_dims=["region"],
                                 structural_timevarying_dims=dict(SYNTHETIC_TIMEVARYING),
                                 extra_renovacion=["product", "channel"],
                                 extra_revalorizacion=["discount", "newcust"])
TWO_MANDATORY_TAXONOMY = dict(business_mandatory_dims=["region", "product"],
                              structural_timevarying_dims=dict(SYNTHETIC_TIMEVARYING),
                              extra_renovacion=["channel"],
                              extra_revalorizacion=["discount", "newcust"])


# ═══════════════════════════════════════════════════════════════════════════════════
# THE TEST CONFIG: Config + read_raw overridden with the synthetic dataset
# ═══════════════════════════════════════════════════════════════════════════════════

class SyntheticConfig(Config):
    """A Config whose raw is the synthetic dataset. Everything else is inherited."""

    def read_raw(self) -> pd.DataFrame:
        """The synthetic dataset, seed 7 — identical on every run."""
        return build_raw(SYNTHETIC_SEED)


# ─── harness ─────────────────────────────────────────────────────────────────────
FAILURES: list = []


def check(condition: bool, message: str) -> None:
    """Print one check and remember it if it failed; never stop the run."""
    print(("  ✓ " if condition else "  ✗ ") + message)
    if not condition:
        FAILURES.append(message)


def read_table(database_path: str, physical_table_name: str) -> pd.DataFrame:
    """Read one persisted table from a sqlite database."""
    with sqlite3.connect(database_path) as connection:
        return pd.read_sql(f"SELECT * FROM [{physical_table_name}]", connection)


def list_framework_tables(database_path: str) -> list:
    """Every `sff_*` table in a sqlite database, sorted."""
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sff_%'")
        return sorted(row[0] for row in rows)


# ═══════════════════════════════════════════════════════════════════════════════════
# LOGIC CHECKS (permanent)
# ═══════════════════════════════════════════════════════════════════════════════════

def check_pipeline_logic(results: dict, configuration: Config, database_path: str,
                         label: str) -> None:
    """Properties every run must satisfy, whatever the taxonomy.

    INPUT:   results — the dict returned by run_pipeline · configuration — the Config it
             ran with · database_path — where it wrote · label — for the console.
    OUTPUT:  none; records through `check`.
    RULES:   these are the properties that DEFINE a correct run. A change of code that
             breaks one of them is a bug, not a divergence.
    EDGE CASES: none.
    CONSOLE: one line per check.
    STEPS:
      [1] Money: the raw pipeline USD equals the fine table's and the reference's.
      [2] Keys: fu_key unique in fact_fu; fu_comb_key unique in the bridge.
      [3] Coverage: every raw row reaches the key bridge.
      [4] Forecast: every future row has a rate, an uplift and an expected USD; nobody
          falls to the global fallback.
      [5] The mandatory cell derived from fs_id matches the bridge's (positional bug).
      [6] Validation panel: 0 FAIL.
    """
    print(f"\nLOGIC · {label}")
    fine_grain_table = results["fine_grain_table"]
    key_bridge = results["key_bridge"]
    future_rows = results["future_rows"]
    series_estimates = results["series_estimates"]
    raw = configuration.read_raw()

    # [1] money is conserved from the raw down to the immutable reference
    raw_pipeline_usd = float(raw[configuration.pipeline_usd_col].sum())
    fine_pipeline_usd = float(fine_grain_table[configuration.pipeline_usd_col].sum())
    reference_table = read_table(database_path, "sff_fu_summary")
    reference_pipeline_usd = float(reference_table[configuration.pipeline_usd_col].sum())
    check(abs(raw_pipeline_usd - fine_pipeline_usd) < MONEY_TOLERANCE_USD,
          f"pipeline USD conserved raw → fine table (${raw_pipeline_usd:,.2f})")
    check(abs(raw_pipeline_usd - reference_pipeline_usd) < MONEY_TOLERANCE_USD,
          f"pipeline USD conserved raw → fu_summary (${reference_pipeline_usd:,.2f})")

    # [2] one row per key
    fact_fu = read_table(database_path, "sff_fact_fu")
    check(fact_fu["fu_key"].is_unique, "fu_key is unique in fact_fu")
    check(key_bridge["fu_comb_key"].is_unique, "fu_comb_key is unique in the key bridge")

    # [3] every raw row can be joined to the bridge
    check(fine_grain_table["fu_comb_key"].isin(key_bridge["fu_comb_key"]).all(),
          "every raw row reaches the key bridge")

    # [4] the forecast is complete and never falls to the global mean
    check(not future_rows["esperado_usd"].isna().any(), "no future row without expected USD")
    check(not future_rows["tasa"].isna().any(), "no future row without a rate")
    check((future_rows["tasa_origen"] != "global").all(),
          "no future row falls to the global fallback (the cascade resolves before)")
    check((future_rows["tasa"] <= configuration.rate_cap + 1e-12).all(),
          f"no rate above the cap ({configuration.rate_cap})")

    # [5] the mandatory cell derived from fs_id must match the bridge's celda_id
    mandatory_count = len(configuration.business_mandatory_dims)
    cell_from_series_id = (series_estimates["fs_id"].str.split("|")
                           .str[:mandatory_count].str.join("|"))
    check(set(cell_from_series_id).issubset(set(key_bridge["celda_id"])),
          "the mandatory cell parsed from fs_id matches the bridge (all mandatory dims)")

    # [6] the validation panel of the run itself
    validation_report = read_table(database_path, "sff_validation_report")
    failed_checks = validation_report[validation_report["estado"] == "FAIL"]
    check(len(failed_checks) == 0,
          f"validation panel: 0 FAIL (found {len(failed_checks)})")


# ═══════════════════════════════════════════════════════════════════════════════════
# REFERENCE COMPARISON (temporary — removed when the reference is obsolete)
# ═══════════════════════════════════════════════════════════════════════════════════

def compare_table_with_reference(candidate: pd.DataFrame, reference: pd.DataFrame) -> list:
    """Differences between a candidate table and its reference, as sentences.

    INPUT:   candidate, reference — the same table from the two databases.
    OUTPUT:  list of problems; empty when identical in rows, sums and key sets.
    RULES:   row count; every numeric column by sum (relative tolerance); key columns
             by set. Traceability columns are skipped.
    EDGE CASES: a column missing from the candidate is a problem; an extra column in
             the candidate is not (the reference's column set is the contract).
    CONSOLE: nothing.
    STEPS:
      [1] Rows.
      [2] Column by column: missing, key set, numeric sum.
    """
    problems = []

    # [1] row count
    if len(candidate) != len(reference):
        problems.append(f"rows {len(candidate)} vs {len(reference)}")

    # [2] columns of the reference
    for column_name in reference.columns:
        if column_name in TRACEABILITY_COLUMNS:
            continue
        if column_name not in candidate.columns:
            problems.append(f"missing column {column_name}")
            continue
        if column_name in KEY_COLUMNS:
            if set(candidate[column_name]) != set(reference[column_name]):
                problems.append(f"different keys in {column_name}")
            continue
        if pd.api.types.is_numeric_dtype(reference[column_name]):
            candidate_sum = candidate[column_name].sum()
            reference_sum = reference[column_name].sum()
            sums_match = np.isclose(candidate_sum, reference_sum,
                                    rtol=REFERENCE_RELATIVE_TOLERANCE, equal_nan=True)
            if not sums_match:
                problems.append(f"Σ{column_name}: {candidate_sum:.4f} vs {reference_sum:.4f}")
    return problems


def check_against_reference(database_path: str) -> None:
    """Every table of the reference must come out identical from the new code."""
    print("\nREFERENCE (temporary) · candidate vs tests/reference_output.db")
    reference_tables = list_framework_tables(REFERENCE_DATABASE_PATH)
    candidate_tables = set(list_framework_tables(database_path))
    identical_count = 0
    for table_name in reference_tables:
        if table_name not in candidate_tables:
            check(False, f"{table_name}: missing in the candidate")
            continue
        problems = compare_table_with_reference(read_table(database_path, table_name),
                                                read_table(REFERENCE_DATABASE_PATH, table_name))
        check(not problems, table_name + ("" if not problems else ": " + "; ".join(problems)))
        if not problems:
            identical_count += 1
    print(f"  → {identical_count}/{len(reference_tables)} tables identical to the reference")


# ═══════════════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════════════

def run_test_pipeline(taxonomy: dict, output_folder: str, database_file_name: str) -> tuple:
    """Run the pipeline on the synthetic raw with a given taxonomy into a fresh sqlite."""
    os.makedirs(output_folder, exist_ok=True)
    database_path = os.path.join(output_folder, database_file_name)
    if os.path.exists(database_path):
        os.remove(database_path)
    sqlite_engine = create_engine(f"sqlite:///{database_path}")
    configuration = SyntheticConfig(sql_engine=sqlite_engine, sql_schema=None,
                                    outdir=output_folder, **taxonomy)
    results = run_pipeline(configuration)
    return results, configuration, database_path


def main() -> int:
    """Two runs of the pipeline on the synthetic raw, then the checks.

    STEPS:
      [1] One mandatory dimension: logic checks + reference comparison.
      [2] Two mandatory dimensions: logic checks only (no reference exists for it).
      [3] Verdict.
    """
    # [1] the configuration the reference was produced with
    single_results, single_configuration, single_database = run_test_pipeline(
        SINGLE_MANDATORY_TAXONOMY, TEST_OUTPUT_FOLDER, "sff_v2_test.db")
    check_pipeline_logic(single_results, single_configuration, single_database,
                         "one mandatory dimension (region)")
    check_against_reference(single_database)

    # [2] several mandatory dimensions: the case one dimension hides
    multi_results, multi_configuration, multi_database = run_test_pipeline(
        TWO_MANDATORY_TAXONOMY, MULTIDIM_OUTPUT_FOLDER, "sff_v2_test_multidim.db")
    check_pipeline_logic(multi_results, multi_configuration, multi_database,
                         "two mandatory dimensions (region, product)")

    # [3] verdict
    print("\n" + "─" * 74)
    if FAILURES:
        print(f"PIPELINE TEST FAIL ✗ — {len(FAILURES)} failed checks:")
        for failure_message in FAILURES:
            print(f"  - {failure_message}")
        return 1
    print("PIPELINE TEST PASS ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
