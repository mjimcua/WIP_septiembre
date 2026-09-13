"""analysis_dynamics.py — SFF v3 · ANALYSIS · phase 2: does this series move, and how?

Measured on the monthly series of each ESTIMATION id (the series itself when it has
support, the chosen relative when it borrowed): dynamics measured on a series without
support is noise (P9). Every test is made against the series' own binomial reference:

  φ (phi)      observed variance of the monthly rate / variance the binomial predicts.
               φ ≈ 1: the rate does not move, it samples; the mean is the best technique.
               φ > 1: an engine (season, trend, regime, internal mix) moves the rate
               beyond luck; a time-series technique has something to capture.
  seasonality  the profile by calendar month on the DETRENDED series (index = month
               mean / overall mean) and
               whether the amplitude exceeds 2× the binomial bound. Firm with ≥ 2 full
               cycles, tentative with 1, not declared with < 13 months.
  trend        the yearly slope vs 2× the binomial bound; direction −1/0/+1; and the
               horizon after which a trend must be fully damped (the inference cap).

Output: `decision_dynamics`, one row per estimation id, stamped on every member series
by the backtest and the assembly. The labels decide WHICH techniques are eligible for a
series (a series without seasonality never competes with a seasonal technique).
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd

from binomial_reference import binomial_se_pp, overdispersion_phi
from config import Config
from run_rate_series import UNIVERSE_NORMAL

# ─── named constants ─────────────────────────────────────────────────────────────
MONTHS_PER_CYCLE = 12
# (seasonality_min_months, signal_multiple_of_bound, phi_engine_threshold and
#  trend_horizon_months are Config parameters: see config.py, phase 2)
# Gate values are persisted data (Spanish, as in v2)
GATE_SUPPORT = "soporte"
GATE_TIME = "temporal"
GATE_SEASONAL = "estacional"
GATE_TREND = "tendencia"
GATE_MEAN = "apto_promedio"


def monthly_series_by_estimation_id(units: pd.DataFrame, decision_support: pd.DataFrame,
                                    parent_ladder: pd.DataFrame, configuration: Config) -> dict:
    """The monthly (rate, support) series of every estimation id.

    INPUT:   units with tasa · decision_support (the chosen ids) · parent_ladder (every
             fs_id × rung pattern: the MEMBERSHIP of each pattern) · configuration.
    OUTPUT:  dict id_estimacion → DataFrame(index=Period, columns ren, pipe, rate),
             built by SUMMING, month by month, EVERY series that matches the pattern —
             big siblings included, whether or not they chose that relative themselves.
             The pattern decides who computes the number; the ladder decides who
             receives it.
    RULES:   history rows of the normal universe with a defined rate.
    """
    history = units[(units["universo"] == UNIVERSE_NORMAL) & units["tasa"].notna()]
    chosen_ids = set(decision_support["id_estimacion"])
    membership = parent_ladder[parent_ladder["padre_id"].isin(chosen_ids)][["fs_id", "padre_id"]].drop_duplicates()
    membership = membership.rename(columns={"padre_id": "id_estimacion"})
    # ids that are a series itself (rung 0) and were never a rung of anybody else
    own_ids = decision_support[~decision_support["id_estimacion"].isin(membership["id_estimacion"])][["fs_id", "id_estimacion"]]
    membership = pd.concat([membership, own_ids], ignore_index=True).drop_duplicates()
    joined = history.merge(membership, on="fs_id")
    series = {}
    for estimation_id, rows in joined.groupby("id_estimacion"):
        monthly = rows.groupby(configuration.period_col).agg(
            ren=(configuration.renewed_units_col, "sum"), pipe=(configuration.pipeline_units_col, "sum")).sort_index()
        monthly["rate"] = np.where(monthly["pipe"] > 0, monthly["ren"] / monthly["pipe"].replace(0, np.nan), np.nan)
        series[estimation_id] = monthly
    return series


def seasonal_profile(monthly: pd.DataFrame, min_months: int = 13) -> tuple:
    """Index by calendar month (1..12) = mean DETRENDED rate of that month / overall mean.

    OUTPUT:  (profile: dict month → index, amplitude_pp, full_cycles).
    RULES:   the linear trend is removed first: over two years a falling series would
             otherwise look "seasonal" (its Januaries are higher than its Decembers).
             With the trend out, only the calendar pattern is left.
    """
    valid = monthly[monthly["rate"].notna()]
    if len(valid) < min_months:
        return {}, 0.0, 0
    overall = float(np.average(valid["rate"], weights=np.maximum(valid["pipe"], 1)))
    x = np.arange(len(valid), dtype=float)
    slope, intercept = np.polyfit(x, valid["rate"].to_numpy(dtype=float), 1)
    detrended = valid["rate"].to_numpy(dtype=float) - (slope * x + intercept) + overall
    by_month = pd.Series(detrended, index=valid.index.month).groupby(level=0).mean()
    profile = {int(m): float(by_month[m] / overall) if overall > 0 else 1.0 for m in by_month.index}
    amplitude_pp = 100 * float(by_month.max() - by_month.min())
    full_cycles = len(valid) // MONTHS_PER_CYCLE
    return profile, amplitude_pp, full_cycles


def yearly_slope_pp(monthly: pd.DataFrame) -> float:
    """Slope of a weighted linear fit of the rate on time, in pp per year."""
    valid = monthly[monthly["rate"].notna()]
    if len(valid) < 6:
        return 0.0
    x = np.arange(len(valid), dtype=float)
    weights = np.sqrt(np.maximum(valid["pipe"].to_numpy(dtype=float), 1))
    design = np.vstack([np.ones_like(x), x]).T * weights[:, None]
    slope = np.linalg.lstsq(design, valid["rate"].to_numpy(dtype=float) * weights, rcond=None)[0][1]
    return float(100 * MONTHS_PER_CYCLE * slope)


def diagnose_dynamics(estimation_id: str, monthly: pd.DataFrame, configuration: Config) -> dict:
    """The dynamics row of one estimation id: φ, gate, seasonality, trend, horizon cap.

    RULES:   gate in order: soporte (n_pool < floor) → temporal (< 13 months) →
             estacional (amplitude > 2·bound) → tendencia (|slope| > 2·bound) → apto_promedio.
             The bound is the binomial half-width of the pool's typical month at z.
             `estacional` is 2 (firm) with ≥ 2 cycles, 1 (tentative) with 1 cycle, 0 otherwise.
    """
    valid = monthly[monthly["rate"].notna()]
    support = float(valid["pipe"].median()) if len(valid) else 0.0
    pooled_rate = float(valid["ren"].sum() / max(valid["pipe"].sum(), 1)) if len(valid) else np.nan
    bound_pp = configuration.z * binomial_se_pp(pooled_rate if np.isfinite(pooled_rate) else 0.5, support)
    phi, sd_obs, sd_bin = overdispersion_phi(valid["rate"].to_numpy(), valid["pipe"].to_numpy())
    profile, amplitude_pp, cycles = seasonal_profile(monthly, configuration.seasonality_min_months)
    slope_pp = yearly_slope_pp(monthly)
    gate = GATE_MEAN
    seasonal_flag, trend_flag = 0, 0
    if support < configuration.support_floor:
        gate = GATE_SUPPORT
    elif len(valid) < configuration.seasonality_min_months:
        gate = GATE_TIME
    else:
        if amplitude_pp > configuration.signal_multiple_of_bound * bound_pp:
            seasonal_flag = 2 if cycles >= 2 else 1
        if abs(slope_pp) > configuration.signal_multiple_of_bound * bound_pp:
            trend_flag = int(np.sign(slope_pp))
        gate = GATE_SEASONAL if seasonal_flag else (GATE_TREND if trend_flag else GATE_MEAN)
    high = [m for m, v in profile.items() if 100 * (v - 1) * max(pooled_rate, 0.01) > bound_pp] if profile else []
    low = [m for m, v in profile.items() if 100 * (1 - v) * max(pooled_rate, 0.01) > bound_pp] if profile else []
    return dict(id_estimacion=estimation_id, meses=len(valid), n_pool=round(support, 1),
                tasa_pool=round(pooled_rate, 4) if np.isfinite(pooled_rate) else np.nan,
                cota_pp=round(bound_pp, 2), phi=round(phi, 2) if np.isfinite(phi) else np.nan,
                sd_obs_pp=round(sd_obs, 2) if np.isfinite(sd_obs) else np.nan,
                sd_binom_pp=round(sd_bin, 2) if np.isfinite(sd_bin) else np.nan,
                gate=gate, estacional=seasonal_flag, amp_estacional_pp=round(amplitude_pp, 1),
                ciclos_completos=cycles, perfil_estacional="|".join(f"{m}:{profile[m]:.3f}" for m in sorted(profile)),
                meses_alto="|".join(map(str, high)), meses_bajo="|".join(map(str, low)),
                tendencia=trend_flag, pendiente_pp_ano=round(slope_pp, 2),
                horizonte_max_tendencia=configuration.trend_horizon_months if trend_flag else 0)


def run_dynamics_analysis(units: pd.DataFrame, decision_support: pd.DataFrame, parent_ladder: pd.DataFrame,
                          configuration: Config) -> tuple:
    """Phase 2 end to end. Persists `decision_dynamics`. Returns (decision_dynamics, monthly series dict)."""
    series = monthly_series_by_estimation_id(units, decision_support, parent_ladder, configuration)
    rows = [diagnose_dynamics(estimation_id, monthly, configuration) for estimation_id, monthly in series.items()]
    decision = pd.DataFrame(rows)
    configuration.write(decision, "decision_dynamics")
    with_history = decision[decision["gate"] != GATE_SUPPORT]
    engines = with_history[with_history["phi"] > configuration.phi_engine_threshold]
    print(f"[2] dynamics on {len(decision)} estimation ids · gates {decision['gate'].value_counts().to_dict()} · "
          f"phi median {with_history['phi'].median():.2f} · {len(engines)} with an engine (phi > {configuration.phi_engine_threshold})")
    for _, row in decision[decision["gate"].isin([GATE_SEASONAL, GATE_TREND])].iterrows():
        print(f"   {row['id_estimacion']:<28} {row['gate']:<10} phi={row['phi']}  amp={row['amp_estacional_pp']}pp "
              f"slope={row['pendiente_pp_ano']}pp/yr  cycles={row['ciclos_completos']}")
    return decision, series
