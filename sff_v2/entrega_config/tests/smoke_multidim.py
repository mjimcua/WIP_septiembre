"""smoke_multidim.py — Guard against the class of bug that ONE mandatory dim hides.

The golden runs with a single mandatory dimension, so any code that parses `fs_id`
by position (e.g. taking only the first field as the cell key) works there by pure
luck and breaks against production, where there are ten. This smoke test runs the
pipeline with SEVERAL mandatory dims and asserts the lookups still resolve.
USAGE: python tests/smoke_multidim.py   →   exit 0 if healthy.
"""
import os
import sys

import pandas as pd

TESTS_FOLDER = os.path.dirname(os.path.abspath(__file__))
REPOSITORY_ROOT = os.path.dirname(TESTS_FOLDER)
sys.path.insert(0, os.path.join(REPOSITORY_ROOT, "sff_v3"))   # legacy phases
sys.path.insert(0, os.path.join(REPOSITORY_ROOT, "run"))      # first: run/config.py

from config import Config
from synthetic import build_raw
import fase0 as f0
import fase1 as f1
import fase2 as f2
import fase3_assembly as f3

FAILURES = []


def check(condition, message):
    print(("  ✓ " if condition else "  ✗ ") + message)
    if not condition:
        FAILURES.append(message)


def main():
    # TWO mandatory dims (region, product) — enough to break positional parsing
    cfg = Config(business_mandatory_dims=["region", "product"],
                 structural_timevarying_dims={"dormant": "negative", "softcancel": "negative",
                                              "no_instalado": "negative", "autorenew": "positive"},
                 extra_renovacion=["channel"], extra_revalorizacion=["discount", "newcust"],
                 outdir=os.path.join(REPOSITORY_ROOT, "salida_smoke"))
    print("SMOKE multidim · mandatory:", cfg.business_mandatory_dims)
    raw = build_raw(7)
    df = f0.f0_load_and_validate(raw, cfg)
    fu_view, fine_grain_table, _, _ = f0.f0_split_and_key(df, cfg)
    labeled_view = f0.f0_universe_routes(fu_view, cfg)
    labeled_view, series_summary = f1.f1_series_and_gaps(labeled_view, cfg)
    eta2_by_dim, _, _ = f1.f1_diagnose_round1(labeled_view, series_summary, cfg)
    v2, series_estimates, _ = f1.f1_improve_support(labeled_view, series_summary, eta2_by_dim, cfg)
    uplift_cells, renewer_rows = f2.f2_uplift_fine(fine_grain_table, cfg)
    uplift_eta2 = f2.f2_diagnose(uplift_cells, renewer_rows, cfg)
    uplift_cells, _ = f2.f2_improve(uplift_cells, uplift_eta2, cfg)
    key_bridge = f3.f3_build_key_bridge(fine_grain_table, v2, series_estimates, cfg)
    future_rows = f3.f3_ensamblaje(fine_grain_table, v2, series_estimates, uplift_cells, cfg)

    print("\nCHECKS:")
    check(not future_rows["esperado_usd"].isna().any(), "forecast sin NaN con varias dims obligatorias")
    check(not future_rows["tasa"].isna().any(), "toda fila futura tiene tasa")
    check((future_rows["tasa_origen"] != "global").all(),
          "ninguna fila cae al promedio global (la cascada resuelve antes)")
    check(key_bridge["fu_comb_key"].is_unique, "clave del puente única")
    check(fine_grain_table["fu_comb_key"].isin(key_bridge["fu_comb_key"]).all(),
          "todo el raw alcanza el puente")
    mandatory_count = len(cfg.business_mandatory_dims)
    cell_from_id = series_estimates["fs_id"].str.split("|").str[:mandatory_count].str.join("|")
    cell_from_dims = key_bridge["celda_id"]
    check(set(cell_from_id).issubset(set(cell_from_dims)),
          "la celda derivada del fs_id coincide con la del puente")
    print(f"\n{'SMOKE PASS ✓' if not FAILURES else 'SMOKE FAIL ✗ ' + str(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
