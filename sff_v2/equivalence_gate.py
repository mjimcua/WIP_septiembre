"""equivalence_gate.py — Equivalence gate between two framework runs.
USAGE: python equivalence_gate.py <candidate.sqlite> <golden.sqlite>
Compares every sff_* table: row count, sum of every numeric column (1e-6 relative
tolerance) and key sets (fu_key/fs_key) — excluding process_date and execution_id,
which change by design. Any intentional divergence must be declared in ASUNCIONES."""
import sys, sqlite3
import pandas as pd
import numpy as np

EXCLUDED_COLUMNS = {"process_date", "execution_id"}
KEY_COLUMNS = {"fu_key", "fs_key", "comb_key"}

def load_tables(db_path):
    con = sqlite3.connect(db_path)
    names = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sff_%'")]
    return {n: pd.read_sql(f"SELECT * FROM [{n}]", con) for n in names}

def compare_table(candidate, golden):
    problems = []
    if len(candidate) != len(golden):
        problems.append(f"rows {len(candidate)} vs {len(golden)}")
    for col in golden.columns:
        if col in EXCLUDED_COLUMNS or col not in candidate.columns:
            if col not in candidate.columns and col not in EXCLUDED_COLUMNS:
                problems.append(f"missing column {col}")
            continue
        if col in KEY_COLUMNS:
            if set(candidate[col]) != set(golden[col]):
                problems.append(f"different keys in {col}")
        elif pd.api.types.is_numeric_dtype(golden[col]):
            sc, sg = candidate[col].sum(), golden[col].sum()
            if not np.isclose(sc, sg, rtol=1e-6, equal_nan=True):
                problems.append(f"Σ{col}: {sc:.4f} vs {sg:.4f}")
    return problems

def main(candidate_path, golden_path):
    candidate_tables = load_tables(candidate_path)
    golden_tables = load_tables(golden_path)
    passed = 0
    for name, golden_df in sorted(golden_tables.items()):
        if name not in candidate_tables:
            print(f"  ✗ {name}: MISSING in the candidate"); continue
        problems = compare_table(candidate_tables[name], golden_df)
        if problems:
            print(f"  ✗ {name}: " + "; ".join(problems))
        else:
            passed += 1; print(f"  ✓ {name}")
    total = len(golden_tables)
    print(f"\nEQUIVALENCE GATE: {passed}/{total} identical tables"
          + (" — PASS ✓" if passed == total else " — FAIL ✗"))
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
