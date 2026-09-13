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
               horizon after which a trend must be fully damped (the inference cap). Also
               the slope of the LAST 12 months (`pendiente_12m_pp_ano`): "is it rising now?".
  volume       seasonality of the pipeline UNITS (`amp_volumen_pct`) and its correlation
               with the rate (`corr_unidades_tasa`): where the season lives — in how many
               contracts fall due, or in how many renew.
  level change the biggest level shift of the rate (`cambio_nivel_mes`, `_pp`, `_fuerza`
               in binomial units): a regime change the whole-history mean does not see.

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


def volume_seasonality(monthly: pd.DataFrame) -> tuple:
    """Seasonality of the PIPELINE UNITS (not the rate): amplitude of the calendar-month
    profile of the units as % of their mean, and the correlation between monthly units
    and monthly rate. A portfolio with two volume peaks a year shows here; if the rate
    correlates with the units, the months that shrink also change WHO renews (composition).
    OUTPUT: (amp_volumen_pct, corr_unidades_tasa); NaN below 13 months."""
    valid = monthly[monthly["rate"].notna() & (monthly["pipe"] > 0)]
    if len(valid) < 13:
        return float("nan"), float("nan")
    units = valid["pipe"].to_numpy(dtype=float)
    by_month = pd.Series(units, index=valid.index.month).groupby(level=0).mean()
    amplitude_pct = 100 * float((by_month.max() - by_month.min()) / max(units.mean(), 1e-9))
    correlation = float(np.corrcoef(units, valid["rate"].to_numpy(dtype=float))[0, 1]) if units.std() > 0 else float("nan")
    return amplitude_pct, correlation


def level_change(monthly: pd.DataFrame, min_segment: int = 6) -> tuple:
    """The single biggest LEVEL SHIFT of the rate (binary segmentation): the month where
    splitting the history into before/after maximizes the difference of pooled rates,
    measured in binomial errors of the two segments.
    OUTPUT: (month or None, shift_pp, shift_in_binomial_units). A shift ≥ 3 binomial
    units is a regime change, not noise."""
    valid = monthly[monthly["rate"].notna() & (monthly["pipe"] > 0)]
    if len(valid) < 2 * min_segment:
        return None, float("nan"), float("nan")
    ren, pipe = valid["ren"].to_numpy(dtype=float), valid["pipe"].to_numpy(dtype=float)
    best = (None, 0.0, 0.0)
    for cut in range(min_segment, len(valid) - min_segment + 1):
        p_before, p_after = ren[:cut].sum() / pipe[:cut].sum(), ren[cut:].sum() / pipe[cut:].sum()
        n_before, n_after = pipe[:cut].sum(), pipe[cut:].sum()
        se = np.sqrt(max(p_before * (1 - p_before), 0.0475) / n_before + max(p_after * (1 - p_after), 0.0475) / n_after)
        strength = abs(p_after - p_before) / max(se, 1e-9)
        if strength > best[2]:
            best = (str(valid.index[cut]), 100 * (p_after - p_before), strength)
    return best


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
             Seasonality and trend need an ENGINE first (φ > phi_engine_threshold): with
             φ ≈ 1 every amplitude or slope measured is sampling noise.
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
    slope_recent_pp = yearly_slope_pp(monthly[monthly["rate"].notna()].tail(12))
    volume_amp_pct, volume_rate_corr = volume_seasonality(monthly)
    # the level change is searched on the DESEASONALIZED rate: on a seasonal series the
    # biggest "shift" would otherwise be the season itself
    deseasonalized = monthly.copy()
    if profile and np.isfinite(pooled_rate):
        deviation = deseasonalized.index.month.map(lambda m: pooled_rate * (profile.get(int(m), 1.0) - 1.0))
        deseasonalized["ren"] = deseasonalized["pipe"] * (deseasonalized["rate"] - np.asarray(deviation, dtype=float)).clip(0, 1)
    change_month, change_pp, change_strength = level_change(deseasonalized)
    gate = GATE_MEAN
    seasonal_flag, trend_flag = 0, 0
    if support < configuration.support_floor:
        gate = GATE_SUPPORT
    elif len(valid) < configuration.seasonality_min_months:
        gate = GATE_TIME
    else:
        has_engine = np.isfinite(phi) and phi > configuration.phi_engine_threshold
        if has_engine and amplitude_pp > configuration.signal_multiple_of_bound * bound_pp:
            seasonal_flag = 2 if cycles >= 2 else 1
        if has_engine and abs(slope_pp) > configuration.signal_multiple_of_bound * bound_pp:
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
                tendencia=trend_flag, pendiente_pp_ano=round(slope_pp, 2), pendiente_12m_pp_ano=round(slope_recent_pp, 2),
                horizonte_max_tendencia=configuration.trend_horizon_months if trend_flag else 0,
                amp_volumen_pct=round(volume_amp_pct, 1) if np.isfinite(volume_amp_pct) else np.nan,
                corr_unidades_tasa=round(volume_rate_corr, 3) if np.isfinite(volume_rate_corr) else np.nan,
                cambio_nivel_mes=change_month or "", cambio_nivel_pp=round(change_pp, 2) if np.isfinite(change_pp) else np.nan,
                cambio_nivel_fuerza=round(change_strength, 2) if np.isfinite(change_strength) else np.nan)


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
    if len(with_history):
        regime = with_history[with_history["cambio_nivel_fuerza"] >= 3]
        print(f"[2] where the season lives: rate amplitude median {with_history['amp_estacional_pp'].median():.1f} pp vs "
              f"VOLUME amplitude median {with_history['amp_volumen_pct'].median():.0f} % of mean units · "
              f"corr(units, rate) median {with_history['corr_unidades_tasa'].median():+.2f} · "
              f"{len(regime)} ids with a level change ≥ 3 binomial units (regime, not noise)")
    moving = decision[decision["gate"].isin([GATE_SEASONAL, GATE_TREND])]
    firm = int((moving["estacional"] == 2).sum())
    print(f"[2] {len(moving)} ids seasonal/trending ({firm} firm, ≥ 2 cycles) · top {configuration.console_top_rows} by support "
          f"(the full list is decision_dynamics):")
    for _, row in moving.sort_values("n_pool", ascending=False).head(configuration.console_top_rows).iterrows():
        print(f"   {row['id_estimacion'][:60]:<60} {row['gate']:<10} n={row['n_pool']:>7.0f} phi={row['phi']:>6}  "
              f"amp={row['amp_estacional_pp']}pp slope={row['pendiente_pp_ano']}pp/yr cycles={row['ciclos_completos']}")
    return decision, series
