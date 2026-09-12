"""eval_harness.py — the equivalence gate, end to end.

Runs the project runner on the FROZEN INPUT (tests/golden/raw_golden.csv) and passes the
equivalence gate against the REFERENCE OUTPUT (tests/golden/sff_v2_golden.db).

USAGE:  python tests/eval_harness.py   →   EQUIVALENCE GATE 25/25 PASS, or the divergences.

Every table of the golden must be identical: same rows, same sums of every numeric
column, same key sets. `process_date` and `execution_id` are excluded (they change by
design). An intentional divergence (new table, renamed table, corrected bug) is declared
in ASUNCIONES first, and only then the golden is regenerated.

Run `python tests/test_config.py` before this one: it is faster and fails with a
sentence naming the broken contract instead of a table sum.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import subprocess
import sys

# ─── named constants ─────────────────────────────────────────────────────────────
TESTS_FOLDER = os.path.dirname(os.path.abspath(__file__))
REPOSITORY_ROOT = os.path.dirname(TESTS_FOLDER)
RUNNER_PATH = os.path.join(REPOSITORY_ROOT, "main.py")
GATE_PATH = os.path.join(TESTS_FOLDER, "equivalence_gate.py")
CANDIDATE_DATABASE_PATH = os.path.join(REPOSITORY_ROOT, "salida", "sff_v2.db")
GOLDEN_DATABASE_PATH = os.path.join(TESTS_FOLDER, "golden", "sff_v2_golden.db")
CONSOLE_TAIL_CHARACTERS = 1200


def main() -> int:
    """Run the pipeline on the golden input, then the gate; return the gate's exit code.

    STEPS:
      [1] Run `main.py --golden`; on failure show the tail of its console and stop.
      [2] Run the gate candidate vs golden and forward its exit code.
    """
    # [1] the pipeline must complete before anything is compared
    pipeline_result = subprocess.run([sys.executable, RUNNER_PATH, "--golden"],
                                     capture_output=True, text=True, cwd=REPOSITORY_ROOT)
    if pipeline_result.returncode != 0:
        print("PIPELINE FAILED — console tail:")
        print(pipeline_result.stdout[-CONSOLE_TAIL_CHARACTERS:])
        print(pipeline_result.stderr[-CONSOLE_TAIL_CHARACTERS:])
        return 1

    # [2] table by table against the reference
    gate_result = subprocess.run([sys.executable, GATE_PATH,
                                  CANDIDATE_DATABASE_PATH, GOLDEN_DATABASE_PATH])
    return gate_result.returncode


if __name__ == "__main__":
    sys.exit(main())
