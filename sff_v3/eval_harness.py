"""eval_harness.py — Framework verification harness.

Runs the full pipeline on the FROZEN INPUT (raw_golden.csv) and passes the
equivalence gate against the REFERENCE OUTPUT (sff_v2_golden.db).
USAGE: python eval_harness.py   →   PASS 16/16 or the list of divergences.
Complements (does not replace) the invariant asserts embedded in the phases:
exact conservation, exhaustive config, rate and uplift guardrails.
"""
import subprocess
import sys

pipeline_result = subprocess.run([sys.executable, "main.py", "--golden"], capture_output=True, text=True)
if pipeline_result.returncode != 0:
    print(pipeline_result.stdout[-800:]); print(pipeline_result.stderr[-800:]); sys.exit(1)
gate_result = subprocess.run([sys.executable, "equivalence_gate.py",
                              "salida/sff_v2.db", "salida/sff_v2_golden.db"])
sys.exit(gate_result.returncode)
