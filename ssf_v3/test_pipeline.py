"""test_pipeline.py — system-level checks of SFF v3 on the synthetic dataset.

    python test_pipeline.py   →  exit 0 if healthy, 1 with the failures

No reference database, no numeric regression: the synthetic raw was DESIGNED with one
scenario per feature (see synthetic_v3.py), so every scenario has an expected
behaviour that can be asserted as logic. When the code changes and a check fails, the
question is "is the new behaviour right?", not "does it match the old number?".

Blocks:
  A  run_analysis end to end on taxonomy 1 (mandatory = [region]) · 32 tables written ·
     every scenario lands where it should · hold-out 2026 · extended 2027 · validation PASS
  B  run_pipeline (decisions read from SQL) reproduces the analysis' forecast
  C  taxonomy 2 (mandatory = [region, product]) changes the ladder, not the totals' order of magnitude
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import sys
import tempfile

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, inspect

# make the flat project folder importable before the sibling imports below
PROJECT_FOLDER = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, PROJECT_FOLDER)

from checks import CheckRecorder
from config import PHYSICAL_TABLE_NAMES, Config
from pipeline import run_analysis, run_pipeline
from synthetic_v3 import build_raw
from test_fixtures import quiet

RECORDER = CheckRecorder()
TIMEVARYING = {"dormant": "negative", "softcancel": "negative", "no_instalado": "negative", "autorenew": "positive"}


class SyntheticConfig(Config):
    def read_raw(self) -> pd.DataFrame:
        return build_raw(7)


def synthetic_config(folder: str, mandatory: list, extras: list) -> Config:
    engine = create_engine(f"sqlite:///{os.path.join(folder, 'v3.db')}")
    return SyntheticConfig(sql_engine=engine, sql_schema=None, outdir=folder, business_mandatory_dims=mandatory,
                           structural_timevarying_dims=TIMEVARYING, extra_renovacion=extras,
                           extra_revalorizacion=["discount", "newcust"], backtest_test_start="2026-01",
                           extended_horizon_end="2027-12", uplift_parent_keep_columns=["newcust"],
                           benchmark_group_dims=["region", "product"], benchmark_min_support=100,
                           signed_ladder_max_loss=0.0, challenger_technique="T2_mean",
                           backtest_max_targets=24, backtest_screen_horizons=[1, 2, 3, 6, 12], backtest_horizon_cap=12,
                           backtest_horizons=[1, 2, 3, 4, 6, 9, 12],
                           backtest_horizon_bands={"h1": [1, 1], "corto": [2, 3], "medio": [4, 6], "largo": [7, 12]},
                           challenger_margin_by_band={"h1": 0.10, "corto": 0.10, "medio": 0.05, "largo": 0.0})


def test_analysis_taxonomy_1() -> dict:
    RECORDER.start_block("A · run_analysis · taxonomy 1 (mandatory = region)")
    folder = tempfile.mkdtemp()
    configuration = synthetic_config(folder, ["region"], ["product", "channel"])
    with quiet():
        results = run_analysis(configuration)
    written = set(inspect(configuration.engine).get_table_names())
    expected = {configuration._resolve_physical_table_name(name) for name in PHYSICAL_TABLE_NAMES}
    RECORDER.check(expected <= written, f"all {len(PHYSICAL_TABLE_NAMES)} registered tables are written ({len(expected - written)} missing)")
    card = results["series_card"].set_index("fs_id")
    # scenarios
    RECORDER.check(card.loc["EU|0|0|0|0|A|tele", "peldano"] == 2 and card.loc["EU|0|0|0|0|A|tele", "n_efectivo"] > 600,
                   "mute channel: EU|A tele (n=12) annuls channel and pools with EU|A web")
    negatives = card.loc[["EU|1|0|0|0|A|web", "EU|0|1|0|0|A|web", "EU|0|0|1|0|A|web"]]
    RECORDER.check((negatives["id_estimacion"] == "EU|SIG=neg|A|web").all() and (negatives["n_efectivo"] > 30).all(),
                   "sign grouping: the three small negatives (15/12/10) pool as 'EU|SIG=neg|A|web' ≥ 30")
    RECORDER.check(card.loc["EU|0|0|0|1|A|web", "nivel_riesgo"] == "S_signo_bajo_suelo", "the minority positive stays in its sign under the floor (S)")
    RECORDER.check(card.loc["EU|1|0|0|1|B|web", "nivel_riesgo"] == "M_signo_mixto", "the mixed-sign series is alone (M)")
    RECORDER.check(card.loc["NA|0|0|0|0|A|tele", "peldano"] == 2 and card.loc["NA|0|0|0|0|A|tele", "id_estimacion"] == "NA|SIG=neutral|A|*",
                   "a neutral small series borrows from its cell's neutrals")
    RECORDER.check(card.loc["NA|0|0|0|0|B|tele", "huecos"] in (10, 11), "gaps: NA|B tele has ~11 synthetic months with undefined rate (2026-08 is pending, not history)")
    RECORDER.check(card.loc["NA|0|0|0|0|A|kiosk", "nivel_riesgo"] == "N_sin_impacto" and card.loc["EU|0|0|0|0|B|tienda", "nivel_riesgo"] == "D_sin_historia"
                   and card.loc["EU|0|0|0|0|A|kiosk", "nivel_riesgo"] == "T_universo_ts",
                   "routes and universes: no_impact → N, projection-only → D, time_series → T")
    benchmark = results["decisions"]["decision_estacionalidad"].set_index("fs_id")
    RECORDER.check(benchmark.loc["EU|0|0|0|0|A|web", "veredicto_estacional"] == 1 and benchmark.loc["EU|0|0|0|0|A|web", "phi"] > 3,
                   "the benchmark declares EU|A seasonal (φ > 3, shape beats the level)")
    reference = results["decisions"]["pool_reference"].set_index("id_estimacion")
    RECORDER.check(reference.loc["EU|0|0|0|0|A|web", "estacional"] == 1, "…and the pool reference carries it")
    technique = results["decisions"]["decision_technique"]
    technique = technique[technique["tramo_h"] == "h1"].set_index("id_estimacion")
    RECORDER.check(technique.loc["EU|0|0|0|0|A|web", "tecnica_origen"] == "campeon" and technique.loc["NA|0|0|0|0|A|web", "tecnica"] == "T2_mean",
                   "a champion on the seasonal series; the challenger on a flat one")
    decomposition = results["composition"]["mix_shift_decomposition"]
    na = decomposition[decomposition["celda_id"] == "NA"]
    RECORDER.check(na["delta_composicion_pp"].abs().mean() > 0.05, "the NA cell (product weights shifting) shows a composition term in the Kitagawa decomposition")
    holdout = results["backtest"]["backtest_holdout"]
    RECORDER.check(holdout["mes_objetivo"].min() == "2026-01" and holdout["mes_objetivo"].max() == "2026-07",
                   "hold-out = the closed months from backtest_test_start (2026-01) to the last closed one (2026-07; 2026-08 is pending)")
    h1 = holdout[holdout["h"] == 1]
    RECORDER.check(h1["err_pp"].abs().mean() < 8 and 0.8 <= h1["dentro_banda"].mean() <= 1.0,
                   f"hold-out h=1: mean |error| {h1['err_pp'].abs().mean():.1f} pp, {h1['dentro_banda'].mean():.0%} inside the band")
    horizon = results["forecast"]["horizon_report"]
    RECORDER.check(horizon["period"].min() == "2026-08" and horizon["period"].max() == "2027-12" and len(horizon) == 17,
                   "the forecast covers the pending month (2026-08), the current month and 2027 (17 months)")
    RECORDER.check((horizon.loc[horizon["period"] >= "2027-01", "pct_simulado"] == 100).all(), "2027 is built entirely on simulated pipeline")
    # the sheet resolves any key to a series and returns its tables and summary
    from sheet import sheet
    from config import hash_key
    with quiet():
        by_id = sheet("EU|0|0|0|0|A|tele", results=results, figure=False)
        by_estimation = sheet(hash_key("EU|SIG=neg|A|web"), results=results, figure=False)
    RECORDER.check(by_id["keys"]["kind"] == "fs_key" and "SERIES EU|0|0|0|0|A|tele" in by_id["summary"] and len(by_id["tables"]["parent_ladder"]) >= 3,
                   "sheet(fs_id): the series' tables and summary")
    RECORDER.check(by_estimation["keys"]["kind"] == "estimacion_key" and len(by_estimation["keys"]["members"]) == 4,
                   "sheet(estimacion_key): resolves the pool and lists its 4 member series")
    validation = results["validation"]
    RECORDER.check(not ((validation["estado"] == "FAIL") & validation["familia"].isin(["INTEGRITY", "DOCTRINE"])).any(),
                   "the validation panel has no INTEGRITY / DOCTRINE failure")
    return dict(folder=folder, configuration=configuration, results=results)


def test_monthly_run(context: dict) -> None:
    RECORDER.start_block("B · run_pipeline reads the decisions and reproduces the forecast")
    with quiet():
        monthly = run_pipeline(context["configuration"])
    analysis_total = context["results"]["forecast"]["forecast_detail"]["esperado_usd"].sum()
    monthly_total = monthly["forecast"]["forecast_detail"]["esperado_usd"].sum()
    RECORDER.check(abs(analysis_total - monthly_total) < 0.01, f"same total: ${analysis_total:,.0f} (analysis) vs ${monthly_total:,.0f} (monthly run)")
    left = context["results"]["forecast"]["forecast_detail"].set_index("fu_comb_key")["tasa"]
    right = monthly["forecast"]["forecast_detail"].set_index("fu_comb_key")["tasa"]
    RECORDER.check(np.allclose(left.sort_index(), right.reindex(left.sort_index().index)), "same rate on every row")
    # the monthly run refuses to start without decisions
    empty = synthetic_config(tempfile.mkdtemp(), ["region"], ["product", "channel"])
    refused = False
    try:
        with quiet():
            run_pipeline(empty)
    except RuntimeError as error:
        refused = "missing" in str(error)
    RECORDER.check(refused, "without decision tables the monthly run refuses to run and says which is missing")


def test_analysis_taxonomy_2() -> None:
    RECORDER.start_block("C · taxonomy 2 (mandatory = region, product)")
    folder = tempfile.mkdtemp()
    configuration = synthetic_config(folder, ["region", "product"], ["channel"])
    with quiet():
        results = run_analysis(configuration)
    card = results["series_card"].set_index("fs_id")
    RECORDER.check(card.loc["EU|A|0|0|0|0|tele", "id_estimacion"] == "EU|A|SIG=neutral|*", "with product mandatory the tele series pools inside the EU|A cell")
    RECORDER.check(card.loc["EU|A|0|1|0|0|web", "id_estimacion"] == "EU|A|SIG=neg|web", "sign grouping still happens inside the finer cell")
    total_1 = 548_000
    total_2 = results["forecast"]["forecast_detail"]["esperado_usd"].sum()
    RECORDER.check(0.8 * total_1 < total_2 < 1.2 * total_1, f"the total stays in the same range (${total_2:,.0f})")
    RECORDER.check(not ((results["validation"]["estado"] == "FAIL")).any(), "validation passes on the second taxonomy")


def main() -> int:
    print("═" * 74 + "\nTEST pipeline · SFF v3 on the synthetic dataset\n" + "═" * 74)
    context = test_analysis_taxonomy_1()
    test_monthly_run(context)
    test_analysis_taxonomy_2()
    return RECORDER.print_panel("PIPELINE TEST")


if __name__ == "__main__":
    sys.exit(main())
