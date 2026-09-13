"""techniques.py — SFF v3 · the catalogue of forecasting techniques (shared by ANALYSIS and RUN).

Every technique predicts the rate of a monthly series at horizon h. They work on the
LOGIT of the rate: no technique can predict above 100 % or below 0 %, intervals become
asymmetric when transformed back (narrower near the ceiling), and a trend damps by
itself as it approaches 1. Point forecasts are transformed back to rate units.

Every technique declares its ELIGIBILITY: the minimum months of history and which
dynamics label it needs (`estacional`, `tendencia`, or nothing). A series without
seasonality never competes with a seasonal technique; a series with 14 months never
competes with a technique that needs two full cycles. That is how time-series methods
are used WHEN THEY CAN BE, and the champion is not chosen by luck when they cannot.

Families (for tie-breaking, richer first): time_series > smoothing > average > naive.

Numpy only. Additional techniques (SARIMA, ETS auto...) plug in by adding an entry to
CATALOGUE with the same signature: f(logit_series: np.ndarray, month_numbers: np.ndarray
of calendar months 1..12, horizon: int, dynamics: dict) → float (logit). Calendar months
are plain integers (not a PeriodIndex) so a technique costs microseconds: the backtest
calls them millions of times.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd

from binomial_reference import inverse_logit, logit

# ─── named constants ─────────────────────────────────────────────────────────────
MONTHS_PER_CYCLE = 12
EWMA_HALFLIFE_MONTHS = 3.0
SES_ALPHA = 0.3
HOLT_ALPHA, HOLT_BETA, HOLT_DAMPING = 0.3, 0.1, 0.9
HW_ALPHA, HW_BETA, HW_GAMMA = 0.3, 0.05, 0.2
THETA_WEIGHT = 0.5
CROSTON_ZERO_SHARE = 0.30
TEMPORAL_CREDIBILITY_K = 6.0
RECENT_WINDOW_MONTHS = 6
FAMILY_RANK = {"time_series": 3, "smoothing": 2, "average": 1, "naive": 0}


# ─── helpers ─────────────────────────────────────────────────────────────────────

def damping_weight(horizon: int, damping: float) -> float:
    """Σ_{i=1..h} φ^i: how much of the trend survives at horizon h (damped Holt)."""
    return float(sum(damping ** i for i in range(1, horizon + 1)))


def target_calendar_month(month_numbers: np.ndarray, horizon: int) -> int:
    """The calendar month h months after the last observed one."""
    return int((month_numbers[-1] - 1 + horizon) % MONTHS_PER_CYCLE + 1)


def seasonal_index_logit(month_numbers: np.ndarray, values: np.ndarray, target_month: int) -> float:
    """Additive seasonal index on the logit scale: mean of the target calendar month
    minus the overall mean. 0 when the calendar month was never observed."""
    same = values[month_numbers == target_month]
    if len(same) == 0:
        return 0.0
    return float(np.mean(same) - np.mean(values))


def seasonal_profile_logit(month_numbers: np.ndarray, values: np.ndarray) -> np.ndarray:
    """The 12 additive indices at once (index 0 = January)."""
    overall = float(np.mean(values))
    profile = np.zeros(MONTHS_PER_CYCLE)
    for month in range(1, MONTHS_PER_CYCLE + 1):
        same = values[month_numbers == month]
        profile[month - 1] = float(np.mean(same) - overall) if len(same) else 0.0
    return profile


# ─── techniques (all: logit series, months, horizon, dynamics → logit prediction) ──

def t0_naive(y, months, h, dyn):
    return float(y[-1])


def t2_mean(y, months, h, dyn):
    return float(np.mean(y))


def t3_moving_average_3(y, months, h, dyn):
    return float(np.mean(y[-3:]))


def t3_moving_average_6(y, months, h, dyn):
    return float(np.mean(y[-6:]))


def t4_ewma(y, months, h, dyn):
    weights = 0.5 ** (np.arange(len(y))[::-1] / EWMA_HALFLIFE_MONTHS)
    return float(np.sum(weights * y) / np.sum(weights))


def t5_drift_damped(y, months, h, dyn):
    drift = (y[-1] - y[0]) / max(len(y) - 1, 1)
    return float(y[-1] + drift * damping_weight(h, HOLT_DAMPING))


def t6_same_month_mean(y, months, h, dyn):
    target = target_calendar_month(months, h)
    same = y[months == target]
    return float(np.mean(same)) if len(same) else float(np.mean(y))


def t7_seasonal_index(y, months, h, dyn):
    return float(np.mean(y) + seasonal_index_logit(months, y, target_calendar_month(months, h)))


def t8_damped_trend(y, months, h, dyn):
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    return float(intercept + slope * (len(y) - 1) + slope * damping_weight(h, HOLT_DAMPING))


def t9_ses(y, months, h, dyn):
    level = y[0]
    for value in y[1:]:
        level = SES_ALPHA * value + (1 - SES_ALPHA) * level
    return float(level)


def t10_holt_damped(y, months, h, dyn):
    level, trend = y[0], (y[1] - y[0]) if len(y) > 1 else 0.0
    for value in y[1:]:
        previous_level = level
        level = HOLT_ALPHA * value + (1 - HOLT_ALPHA) * (level + HOLT_DAMPING * trend)
        trend = HOLT_BETA * (level - previous_level) + (1 - HOLT_BETA) * HOLT_DAMPING * trend
    return float(level + trend * damping_weight(h, HOLT_DAMPING))


def t11_holt_winters_additive(y, months, h, dyn):
    """Additive Holt-Winters on the logit, seasonal period 12, damped trend."""
    season = seasonal_profile_logit(months[:MONTHS_PER_CYCLE], y[:MONTHS_PER_CYCLE])
    level, trend = float(np.mean(y[:MONTHS_PER_CYCLE])), 0.0
    for index in range(MONTHS_PER_CYCLE, len(y)):
        month = int(months[index])
        previous_level = level
        level = HW_ALPHA * (y[index] - season[month - 1]) + (1 - HW_ALPHA) * (level + HOLT_DAMPING * trend)
        trend = HW_BETA * (level - previous_level) + (1 - HW_BETA) * HOLT_DAMPING * trend
        season[month - 1] = HW_GAMMA * (y[index] - level) + (1 - HW_GAMMA) * season[month - 1]
    return float(level + trend * damping_weight(h, HOLT_DAMPING) + season[target_calendar_month(months, h) - 1])


def t12_theta(y, months, h, dyn):
    """Theta (Assimakopoulos & Nikolopoulos 2000), simple form: average of the
    damped linear extrapolation and SES."""
    return float(THETA_WEIGHT * t8_damped_trend(y, months, h, dyn) + (1 - THETA_WEIGHT) * t9_ses(y, months, h, dyn))


def t13_croston_sba(y, months, h, dyn):
    """SBA for intermittent series: mean of the non-zero-ish months times the share of
    active months, bias-corrected (Syntetos-Boylan). Works on the rate scale."""
    rates = inverse_logit(y)
    active = rates > 0.02
    if active.sum() == 0:
        return float(logit(0.01))
    mean_active = float(np.mean(rates[active]))
    share = float(np.mean(active))
    return float(logit(np.clip(mean_active * share * (1 - 0.5 * (1 - share)), 1e-3, 1 - 1e-3)))


def t14_temporal_credibility(y, months, h, dyn):
    """Recent window vs whole history, blended with z = n/(n+k) on the number of recent months."""
    recent = y[-RECENT_WINDOW_MONTHS:]
    z = len(recent) / (len(recent) + TEMPORAL_CREDIBILITY_K)
    return float(z * np.mean(recent) + (1 - z) * np.mean(y))


# ─── catalogue ───────────────────────────────────────────────────────────────────
# id → (family, description, min_history_months, required label, function)
CATALOGUE = {
    "T0_naive":         ("naive",       "last observed month",                        1,  None,         t0_naive),
    "T2_mean":          ("average",     "mean of the whole history (challenger)",     1,  None,         t2_mean),
    "T3_ma3":           ("average",     "moving average, 3 months",                   3,  None,         t3_moving_average_3),
    "T3_ma6":           ("average",     "moving average, 6 months",                   6,  None,         t3_moving_average_6),
    "T4_ewma":          ("smoothing",   "exponentially weighted mean, half-life 3",   4,  None,         t4_ewma),
    "T5_drift":         ("smoothing",   "damped drift from first to last",            6,  "tendencia",  t5_drift_damped),
    "T6_same_month":    ("average",     "mean of the same calendar month",            13, "estacional", t6_same_month_mean),
    "T7_seasonal_idx":  ("time_series", "mean + additive seasonal index (logit)",     13, "estacional", t7_seasonal_index),
    "T8_damped_trend":  ("time_series", "linear trend, damped extrapolation",         12, "tendencia",  t8_damped_trend),
    "T9_ses":           ("smoothing",   "simple exponential smoothing",               4,  None,         t9_ses),
    "T10_holt_damped":  ("time_series", "Holt damped trend",                          12, "tendencia",  t10_holt_damped),
    "T11_holt_winters": ("time_series", "Holt-Winters additive on logit, damped",     24, "estacional", t11_holt_winters_additive),
    "T12_theta":        ("time_series", "Theta: damped trend + SES",                  12, None,         t12_theta),
    "T13_croston_sba":  ("smoothing",   "SBA for intermittent series",                8,  "intermitente", t13_croston_sba),
    "T14_temporal_cred":("average",     "recent window with temporal credibility",    6,  None,         t14_temporal_credibility),
}


def technique_dimension() -> pd.DataFrame:
    """The master table of techniques (`dim_tecnica`)."""
    return pd.DataFrame([dict(tecnica_id=tid, familia=fam, descripcion=desc, historia_minima=mh, requiere=req or "")
                         for tid, (fam, desc, mh, req, _) in CATALOGUE.items()])


def eligible_techniques(history_months: int, dynamics: dict) -> list:
    """The technique ids a series may compete with, given its history and its labels.

    INPUT:   history_months · dynamics — dict with estacional (0/1/2), tendencia (−1/0/1),
             intermitente (0/1); missing keys count as 0.
    RULES:   min history; `estacional` techniques need estacional ≥ 1; `tendencia`
             techniques need tendencia ≠ 0; `intermitente` techniques need intermitente = 1.
             The challenger T2_mean is always eligible.
    """
    labels = {"estacional": int(dynamics.get("estacional", 0) or 0) >= 1,
              "tendencia": int(dynamics.get("tendencia", 0) or 0) != 0,
              "intermitente": int(dynamics.get("intermitente", 0) or 0) == 1}
    eligible = []
    for tid, (_, _, min_history, required, _) in CATALOGUE.items():
        if history_months < min_history:
            continue
        if required is not None and not labels[required]:
            continue
        eligible.append(tid)
    return eligible


def month_numbers_of(months: pd.PeriodIndex) -> np.ndarray:
    """PeriodIndex → integer calendar months (1..12), the form the techniques take."""
    return np.asarray(pd.PeriodIndex(months).month, dtype=int)


def predict(technique_id: str, rates: np.ndarray, months: pd.PeriodIndex, horizon: int, dynamics: dict) -> float:
    """Point forecast of the RATE at horizon h with one technique. Returns NaN if it fails.
    `months` may be a PeriodIndex or an integer array of calendar months."""
    clean = np.isfinite(rates)
    month_numbers = months if isinstance(months, np.ndarray) else month_numbers_of(months)
    y, m = logit(np.asarray(rates, dtype=float)[clean]), month_numbers[clean]
    if len(y) == 0:
        return float("nan")
    try:
        value = CATALOGUE[technique_id][4](y, m, int(horizon), dynamics or {})
    except Exception:
        return float("nan")
    return float(inverse_logit(value)) if np.isfinite(value) else float("nan")


def family_rank(technique_id: str) -> int:
    return FAMILY_RANK[CATALOGUE[technique_id][0]]
