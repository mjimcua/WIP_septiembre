"""test_phase2_3.py — checks for the binomial reference, the dynamics (phase 2), the
technique catalogue and the backtest (phase 3) of SFF v3.

    python test_phase2_3.py   →  exit 0 if healthy, 1 with the failures

Blocks:
  ref   binomial_reference     se, Wilson, the dial, logit round trip, φ on a designed series
  2     diagnose_dynamics      a seasonal series is 'estacional', a trending one 'tendencia',
                               a flat big one 'apto_promedio', a small one 'soporte'
  T     techniques             eligibility by history and labels · every technique returns a
                               rate in (0, 1) · seasonal index recovers the season · damped
                               trend saturates
  3     backtest               only history ≤ origin · errors normalized · the challenger
                               wins on a flat series · a seasonal technique wins on the
                               seasonal series · bands monotone in h · hold-out ≥ test start
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import sys
import tempfile

import numpy as np
import pandas as pd

PROJECT_FOLDER = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, PROJECT_FOLDER)

from checks import CheckRecorder                                                   # noqa: E402
from test_fixtures import ladder_config, phase_0_units, quiet                      # noqa: E402
import binomial_reference as ref                                                   # noqa: E402
import run_rate_series                                                             # noqa: E402
import analysis_dimensions                                                         # noqa: E402
import run_support_ladder                                                          # noqa: E402
import analysis_dynamics                                                           # noqa: E402
import analysis_backtest                                                           # noqa: E402
import techniques                                                                  # noqa: E402

RECORDER = CheckRecorder()


def run_to_dynamics(configuration):
    fine, labeled = phase_0_units(configuration)
    with quiet():
        units, summary = run_rate_series.build_rate_series(labeled, configuration)
        dims = analysis_dimensions.run_dimension_analysis(units, summary, configuration)
        estimates, card, decision, ladder = run_support_ladder.run_support_ladder(units, summary, dims["decision_eta2"], configuration)
        dynamics, series = analysis_dynamics.run_dynamics_analysis(units, decision, ladder, configuration)
    return dict(units=units, decision=decision, ladder=ladder, dynamics=dynamics, series=series)


# ═══════════════════════════════════════════════════════════════════════════════════

def test_binomial_reference() -> None:
    RECORDER.start_block("ref · binomial_reference")
    RECORDER.check(abs(ref.binomial_se_pp(0.8, 100) - 4.0) < 1e-9, "se(p=.8, n=100) = 4.0 pp")
    RECORDER.check(ref.binomial_se(1.0, 10) > 0, "p = 1 does not claim zero error (variance floor)")
    low, high = ref.wilson_interval(0.95, 20, 1.645)
    RECORDER.check(high <= 1.0 and (0.95 - low) > (high - 0.95), "Wilson stays inside [0, 1] and is asymmetric near the edge")
    RECORDER.check(round(ref.support_for_half_width(15, 1.645)) == 30 and round(ref.support_for_half_width(5, 1.645)) == 271,
                   "the dial: ±15 pp ↔ 30, ±5 pp ↔ 271")
    RECORDER.check(np.allclose(ref.inverse_logit(ref.logit([0.1, 0.5, 0.9])), [0.1, 0.5, 0.9]), "logit round trip")
    rng = np.random.default_rng(1)
    flat = rng.binomial(300, 0.8, size=36) / 300
    phi_flat, _, _ = ref.overdispersion_phi(flat, np.full(36, 300))
    moving = np.clip(0.8 + 0.1 * np.sin(np.arange(36) / 2) + rng.normal(0, 0.02, 36), 0, 1)
    phi_moving, _, _ = ref.overdispersion_phi(moving, np.full(36, 300))
    RECORDER.check(0.5 < phi_flat < 2.0 and phi_moving > 5, f"φ ≈ 1 on a binomial series ({phi_flat:.2f}), ≫ 1 with an engine ({phi_moving:.1f})")


def test_dynamics() -> None:
    RECORDER.start_block("2 · diagnose_dynamics")
    with tempfile.TemporaryDirectory() as folder:
        configuration = ladder_config(folder, seasonal_series=True, trend_series=True)
        results = run_to_dynamics(configuration)
        dynamics = results["dynamics"].set_index("id_estimacion")
        RECORDER.check(dynamics.loc["NA|0|0|web", "gate"] == "estacional" and dynamics.loc["NA|0|0|web", "estacional"] == 2,
                       "a seasonal series with 2 full cycles is 'estacional' (firm)")
        RECORDER.check(dynamics.loc["NA|0|0|web", "phi"] > 3, "…and its φ says there is an engine")
        RECORDER.check(dynamics.loc["NA|0|0|tele", "gate"] == "tendencia" and dynamics.loc["NA|0|0|tele", "tendencia"] == -1,
                       "a declining series is 'tendencia' with direction −1")
        RECORDER.check(dynamics.loc["NA|0|0|tele", "horizonte_max_tendencia"] > 0, "…with a horizon cap for the trend")
        RECORDER.check(dynamics.loc["EU|0|0|web", "gate"] == "apto_promedio" and abs(dynamics.loc["EU|0|0|web", "phi"] - 1) < 1.0,
                       "a flat big series is 'apto_promedio' with φ ≈ 1")
        RECORDER.check(dynamics.loc["EU|1|1|web", "gate"] == "soporte", "a series under the floor is gated by 'soporte'")
        profile = dict(item.split(":") for item in dynamics.loc["NA|0|0|web", "perfil_estacional"].split("|"))
        RECORDER.check(float(profile["4"]) > 1.05 and float(profile["10"]) < 0.95,
                       "the seasonal profile peaks in April and troughs in October (sine from January)")
        pooled = results["series"]["EU|SIG=neutral|*"]
        RECORDER.check(abs(pooled["pipe"].median() - 210) < 1, "the monthly series of a relative sums EVERY matching series (210 = S1 + S2)")


def test_techniques() -> None:
    RECORDER.start_block("T · techniques")
    RECORDER.check("T7_seasonal_idx" not in techniques.eligible_techniques(24, dict(estacional=1, tendencia=0))
                   and "T7_seasonal_idx" in techniques.eligible_techniques(24, dict(estacional=2, tendencia=0)),
                   "seasonal techniques need FIRM seasonality (2 cycles) by default; tentative (1 cycle) is not enough")
    RECORDER.check("T7_seasonal_idx" in techniques.eligible_techniques(24, dict(estacional=1, tendencia=0, requiere_firme=False)),
                   "…unless seasonal_requires_firm is off")
    RECORDER.check("T11_holt_winters" not in techniques.eligible_techniques(20, dict(estacional=2, tendencia=0))
                   and "T11_holt_winters" in techniques.eligible_techniques(24, dict(estacional=2, tendencia=0)),
                   "Holt-Winters needs 24 months even when seasonal")
    RECORDER.check("T2_mean" in techniques.eligible_techniques(1, {}), "the challenger is always eligible")
    months = pd.period_range("2023-01", periods=36, freq="M")
    seasonal = 0.7 + 0.1 * np.sin(2 * np.pi * (months.month - 1) / 12)
    labels = dict(estacional=2, tendencia=0, intermitente=0)
    for technique_id in techniques.CATALOGUE:
        value = techniques.predict(technique_id, seasonal, months, 3, labels)
        RECORDER.check(np.isfinite(value) and 0 < value < 1, f"{technique_id} returns a rate in (0, 1)")
    april_prediction = techniques.predict("T7_seasonal_idx", seasonal, months, 4, labels)   # last = 2025-12 → h=4 = April
    RECORDER.check(abs(april_prediction - 0.8) < 0.01, f"the seasonal index recovers April's .80 ({april_prediction:.3f})")
    trending = np.clip(0.9 - 0.01 * np.arange(36), 0.01, 0.99)
    far = techniques.predict("T8_damped_trend", trending, months, 24, dict(tendencia=-1))
    linear_extrapolation = trending[-1] - 0.01 * 24
    RECORDER.check(far > linear_extrapolation + 0.05, "the damped trend saturates: far horizon stays above the linear extrapolation")
    near_one = np.full(36, 0.99)
    RECORDER.check(techniques.predict("T2_mean", near_one, months, 1, {}) < 1.0, "the logit keeps predictions below 100 %")


def test_backtest() -> None:
    RECORDER.start_block("3 · backtest, technique, bands, hold-out")
    with tempfile.TemporaryDirectory() as folder:
        configuration = ladder_config(folder, seasonal_series=True, trend_series=True, backtest_test_start="2025-07")
        results = run_to_dynamics(configuration)
        with quiet():
            backtest = analysis_backtest.run_backtest_analysis(results["series"], results["dynamics"], configuration, [1, 2, 3, 4])
        long = backtest["backtest_long"]
        RECORDER.check((pd.PeriodIndex(long["origen"], freq="M") + long["h"] == pd.PeriodIndex(long["mes_objetivo"], freq="M")).all(),
                       "origin + h = target for every prediction (only history ≤ origin is used)")
        RECORDER.check(np.allclose(long["err_norm"], long["err_pp"] / long["se_binom_pp"], atol=1e-2),
                       "err_norm = err_pp / binomial se of the target month")
        RECORDER.check(long["tecnica_id"].nunique() >= 10, "many techniques compete where the history allows")
        seasonal_id = long[long["id_estimacion"] == "NA|0|0|web"]
        RECORDER.check("T7_seasonal_idx" in set(seasonal_id["tecnica_id"]) and "T7_seasonal_idx" not in set(long[long["id_estimacion"] == "EU|0|0|web"]["tecnica_id"]),
                       "seasonal techniques compete on the seasonal series only")
        decision = backtest["decision_technique"]
        RECORDER.check(set(decision["tramo_h"]) == {"corto", "medio", "largo"} and (decision.groupby("id_estimacion").size() == 3).all(),
                       "one champion per estimation id AND horizon band (corto / medio / largo)")
        chosen = decision[decision["tramo_h"] == "corto"].set_index("id_estimacion")
        RECORDER.check(chosen.loc["EU|0|0|web", "tecnica"] == "T2_mean" and chosen.loc["EU|0|0|web", "tecnica_origen"] == "retador",
                       "on a flat series nobody beats the challenger by the margin → T2_mean, origin 'retador'")
        RECORDER.check(chosen.loc["NA|0|0|web", "tecnica_origen"] == "campeon"
                       and techniques.CATALOGUE[chosen.loc["NA|0|0|web", "tecnica"]][3] == "estacional",
                       f"on the seasonal series a seasonal champion wins ({chosen.loc['NA|0|0|web', 'tecnica']})")
        RECORDER.check(chosen.loc["NA|0|0|tele", "tecnica_origen"] == "campeon", "on the trending series a champion beats the mean")
        inherited = decision[decision["tecnica_origen"].str.endswith("_heredado")]
        RECORDER.check((inherited["tramo_h"] != "corto").all(), "a band with no screen horizon inside inherits the previous band's champion")
        bands = backtest["decision_error_bands"]
        widths = bands.assign(w=bands["q_high_norm"] - bands["q_low_norm"]).groupby("id_estimacion")["w"]
        RECORDER.check(all((group.diff().dropna() >= -1e-9).all() for _, group in widths), "band width never narrows with h")
        RECORDER.check((bands["q_low_norm"] <= 0).all() and (bands["q_high_norm"] >= 0).all(), "bands contain zero")
        holdout = backtest["backtest_holdout"]
        RECORDER.check(holdout["mes_objetivo"].min() >= "2025-07", "the hold-out contains only months ≥ backtest_test_start")
        RECORDER.check(set(holdout["tecnica"]) <= set(decision["tecnica"]), "the hold-out uses the chosen technique per id and band")
        inside = holdout["dentro_banda"].mean()
        RECORDER.check(0.75 <= inside <= 1.0, f"hold-out calibration: {inside:.0%} inside the band (target ≈ 90 %)")


ALL_TESTS = [test_binomial_reference, test_dynamics, test_techniques, test_backtest]


def main() -> int:
    print("═" * 74 + "\nTEST phases 2-3 · dynamics, techniques, backtest\n" + "═" * 74)
    for test in ALL_TESTS:
        test()
    return RECORDER.print_panel("PHASES 2-3 TEST")


if __name__ == "__main__":
    sys.exit(main())
