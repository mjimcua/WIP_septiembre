"""analysis_dimensions.py — SFF v3 · ANALYSIS · phase 1.2: what separates behaviour, and
what it costs not to segment.

Three things are decided or measured here, all at the level of the forecast series:

  1. DIMENSION SEPARATION → `decision_eta2`. Which dimensions separate the renewal rate
     and in which order they should collapse when a series needs a relative. Three
     figures per dimension, not one:
       · η² individual  — how much the dimension explains ALONE (weighted by support).
                          Confounded when dimensions are correlated.
       · unique contribution (type II) — R²(all dims) − R²(all dims but this one): what
                          is LOST if this dimension is annulled while the others stay.
                          This is the ladder's question, so this fixes the order.
       · ω²              — η² discounted by the number of groups (many categories with
                          few series look like signal by chance).
     Plus pairs: η² of the joint key vs the individuals → interactions.
     Timevarying dims are OUT (doctrine: they are handled by sign, not by η²).
     Method: weighted least squares of the series rate on the dimensions as categoricals
     (a weighted factorial ANOVA), numpy only. ANCOVA is not needed: everything is
     categorical (continuous discounts are binned by doctrine).

  2. MIX-SHIFT → `simpson_contrafactual`, `mix_shift_decomposition`. Per mandatory cell
     and month (walk-forward over the last months with truth): flat method vs segmented
     method with the REAL weights of the month, both against what happened; the saving
     in dollars. And the Kitagawa decomposition of the change of the aggregate rate into
     a behaviour term (Σ w·Δp) and a composition term (Σ p·Δw): the quiet version of
     Simpson, with own numbers, no case hunting.

  3. TIMEVARYING CALIBRATION → `timevarying_calibration`. The realized rate per flag
     and per sign, month by month, with its binomial error: the audit of every model
     that produces a flag, for free.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import itertools

import numpy as np
import pandas as pd

from binomial_reference import binomial_se_pp
from config import Config, join_columns
from run_rate_series import PROJECTION_ROLE, ROUTE_TRAINABLE, UNIVERSE_NORMAL

# ─── named constants ─────────────────────────────────────────────────────────────
COUNTERFACTUAL_WINDOW_MONTHS = 12      # months with truth judged by the walk-forward
MIN_HISTORY_FOR_COUNTERFACTUAL = 6     # a cell needs this much past to be judged
MAX_PAIRS = 15                         # pairs explode combinatorially: the top by money
RATE_BRANCH = "tasa"


# ═══════════════════════════════════════════════════════════════════════════════════
# 1 · DIMENSION SEPARATION
# ═══════════════════════════════════════════════════════════════════════════════════

def weighted_eta2(frame: pd.DataFrame, group_column: str, value_column: str, weight_column: str) -> float:
    """η² of one grouping: between-group weighted sum of squares / total. 0 when no variance."""
    weights = frame[weight_column].to_numpy(dtype=float)
    values = frame[value_column].to_numpy(dtype=float)
    grand_mean = np.average(values, weights=weights)
    total = float(np.sum(weights * (values - grand_mean) ** 2))
    if total <= 0:
        return 0.0
    between = 0.0
    for _, group in frame.groupby(group_column, observed=True):
        gw = group[weight_column].to_numpy(dtype=float)
        between += float(np.sum(gw)) * (np.average(group[value_column], weights=gw) - grand_mean) ** 2
    return float(between / total)


def weighted_omega2(frame: pd.DataFrame, group_column: str, value_column: str, weight_column: str) -> float:
    """ω² = (SSB − (k−1)·MSW) / (SST + MSW): η² corrected for the number of groups k."""
    weights = frame[weight_column].to_numpy(dtype=float)
    values = frame[value_column].to_numpy(dtype=float)
    grand_mean = np.average(values, weights=weights)
    total = float(np.sum(weights * (values - grand_mean) ** 2))
    n = len(frame)
    groups = frame.groupby(group_column, observed=True)
    k = groups.ngroups
    if total <= 0 or n <= k:
        return 0.0
    between = sum(float(np.sum(g[weight_column])) * (np.average(g[value_column], weights=g[weight_column]) - grand_mean) ** 2
                  for _, g in groups)
    within = total - between
    mean_square_within = within / (n - k)
    return float(max(0.0, (between - (k - 1) * mean_square_within) / (total + mean_square_within)))


def weighted_r2_factorial(frame: pd.DataFrame, dimensions: list, value_column: str, weight_column: str) -> float:
    """R² of a weighted least-squares fit of the value on the dimensions as categoricals
    (additive factorial model). Numpy only; rank-deficient designs are handled by lstsq."""
    if not dimensions:
        return 0.0
    design = pd.get_dummies(frame[dimensions].astype(str), drop_first=True).astype(float)
    design.insert(0, "intercept", 1.0)
    weights = np.sqrt(frame[weight_column].to_numpy(dtype=float))
    values = frame[value_column].to_numpy(dtype=float)
    coefficients, _, _, _ = np.linalg.lstsq(design.to_numpy() * weights[:, None], values * weights, rcond=None)
    fitted = design.to_numpy() @ coefficients
    grand_mean = np.average(values, weights=weights ** 2)
    total = float(np.sum(weights ** 2 * (values - grand_mean) ** 2))
    residual = float(np.sum(weights ** 2 * (values - fitted) ** 2))
    return float(max(0.0, 1 - residual / total)) if total > 0 else 0.0


def dimension_separation(series_summary: pd.DataFrame, units: pd.DataFrame, configuration: Config,
                         branch: str = RATE_BRANCH) -> tuple:
    """The three figures per dimension and the pairs, for the rate branch.

    INPUT:   series_summary (tasa_propia, n_propio, signo) · units (dimension values per
             fs_id) · configuration.
    OUTPUT:  (decision_eta2, decision_eta2_pairs).
             decision_eta2: rama, dimension, grupo (mandatory/extra_renovacion),
             eta2_individual, contribucion_unica, omega2, anulable (0/1: extras only).
    RULES:   base = trainable series with history, NEUTRAL sign only (timevarying are out
             by doctrine and their series would contaminate the rates); weights = n_propio.
    EDGE CASES: fewer than 3 series → every figure 0 (no evidence, declared).
    """
    dims = configuration.business_mandatory_dims + configuration.extra_renovacion
    values = units.drop_duplicates("fs_id")[["fs_id"] + dims]
    base = series_summary[(series_summary["ruta"] == ROUTE_TRAINABLE) & series_summary["tasa_propia"].notna()
                          & (series_summary["signo"] == "neutral") & (series_summary["n_propio"] > 0)]
    base = base.merge(values, on="fs_id")
    rows = []
    r2_all = weighted_r2_factorial(base, dims, "tasa_propia", "n_propio") if len(base) >= 3 else 0.0
    for dim in dims:
        if len(base) < 3:
            individual = unique = omega = 0.0
        else:
            individual = weighted_eta2(base, dim, "tasa_propia", "n_propio")
            omega = weighted_omega2(base, dim, "tasa_propia", "n_propio")
            unique = max(0.0, r2_all - weighted_r2_factorial(base, [d for d in dims if d != dim], "tasa_propia", "n_propio"))
        rows.append(dict(rama=branch, dimension=dim,
                         grupo="mandatory" if dim in configuration.business_mandatory_dims else "extra_renovacion",
                         eta2_individual=round(individual, 4), contribucion_unica=round(unique, 4),
                         omega2=round(omega, 4), anulable=int(dim in configuration.extra_renovacion)))
    decision = pd.DataFrame(rows)
    pair_rows = []
    if len(base) >= 3:
        for a, b in itertools.combinations(dims, 2):
            joint = base.assign(_pair=base[a].astype(str) + "|" + base[b].astype(str))
            eta_pair = weighted_eta2(joint, "_pair", "tasa_propia", "n_propio")
            eta_a = decision.set_index("dimension").loc[a, "eta2_individual"]
            eta_b = decision.set_index("dimension").loc[b, "eta2_individual"]
            pair_rows.append(dict(rama=branch, par=f"{a}×{b}", eta2_par=round(eta_pair, 4),
                                  interaccion=round(eta_pair - max(eta_a, eta_b), 4)))
    pairs = pd.DataFrame(pair_rows, columns=["rama", "par", "eta2_par", "interaccion"])
    return decision, pairs.sort_values("interaccion", ascending=False).head(MAX_PAIRS)


# ═══════════════════════════════════════════════════════════════════════════════════
# 2 · MIX-SHIFT
# ═══════════════════════════════════════════════════════════════════════════════════

def counterfactual_and_decomposition(units: pd.DataFrame, configuration: Config) -> tuple:
    """Walk-forward Simpson counterfactual and Kitagawa decomposition per mandatory cell × month.

    INPUT:   units with tasa (history) · configuration.
    OUTPUT:  (counterfactual, decomposition).
             counterfactual: celda, mes, tasa_real, tasa_plano, tasa_seg, err_plano_pp,
             err_seg_pp, ahorro_usd, gana_segmentado (0/1), cota_celda_pp.
             decomposition: celda, mes, delta_agregado_pp, delta_comportamiento_pp,
             delta_composicion_pp (vs the previous month with truth).
    RULES:   for month t only data ≤ t−1 is used; the weights of t are the real pipeline
             of t (known data). Saving = (|err_plano| − |err_seg|) × pipeline$ of t,
             signed. Kitagawa: Δ = Σ w̄·Δp + Σ p̄·Δw with midpoint weights/rates.
    EDGE CASES: cells with fewer than MIN_HISTORY_FOR_COUNTERFACTUAL past months are skipped.
    """
    period, ren_col, pipe_col, usd_col = (configuration.period_col, configuration.renewed_units_col,
                                          configuration.pipeline_units_col, configuration.pipeline_usd_col)
    history = units[(units["universo"] == UNIVERSE_NORMAL) & units["tasa"].notna() & (units["sintetica"] == 0)].copy()
    history["celda"] = join_columns(history, configuration.business_mandatory_dims)
    months = sorted(history[period].unique())[-COUNTERFACTUAL_WINDOW_MONTHS:]
    cf_rows, kit_rows = [], []
    for cell, cell_rows in history.groupby("celda"):
        cell_months = sorted(cell_rows[period].unique())
        for t in months:
            past, now = cell_rows[cell_rows[period] < t], cell_rows[cell_rows[period] == t]
            if past[period].nunique() < MIN_HISTORY_FOR_COUNTERFACTUAL or now.empty:
                continue
            real = now[ren_col].sum() / now[pipe_col].sum()
            flat = past[ren_col].sum() / past[pipe_col].sum()
            series_rates = past.groupby("fs_id").apply(lambda s: s[ren_col].sum() / max(s[pipe_col].sum(), 1), include_groups=False)
            weights = now.groupby("fs_id")[pipe_col].sum()
            segmented = float(np.average(series_rates.reindex(weights.index).fillna(flat), weights=weights))
            pipeline_usd = now[usd_col].sum()
            bound = binomial_se_pp(real, now[pipe_col].sum()) * configuration.z
            cf_rows.append(dict(celda=cell, mes=str(t), tasa_real=round(real, 4), tasa_plano=round(flat, 4),
                                tasa_seg=round(segmented, 4), err_plano_pp=round(100 * (flat - real), 2),
                                err_seg_pp=round(100 * (segmented - real), 2),
                                ahorro_usd=round((abs(flat - real) - abs(segmented - real)) * pipeline_usd, 2),
                                gana_segmentado=int(abs(segmented - real) < abs(flat - real)), cota_celda_pp=round(bound, 2)))
            # Kitagawa vs the previous month with truth
            previous_months = [m for m in cell_months if m < t]
            if not previous_months:
                continue
            before = cell_rows[cell_rows[period] == previous_months[-1]]
            p0 = before.groupby("fs_id").apply(lambda s: s[ren_col].sum() / max(s[pipe_col].sum(), 1), include_groups=False)
            p1 = now.groupby("fs_id").apply(lambda s: s[ren_col].sum() / max(s[pipe_col].sum(), 1), include_groups=False)
            w0 = before.groupby("fs_id")[pipe_col].sum() / before[pipe_col].sum()
            w1 = weights / weights.sum()
            ids = p0.index.union(p1.index)
            p0, p1 = p0.reindex(ids).fillna(p1.reindex(ids)), p1.reindex(ids).fillna(p0.reindex(ids))
            w0, w1 = w0.reindex(ids).fillna(0), w1.reindex(ids).fillna(0)
            behaviour = float(np.sum((w0 + w1) / 2 * (p1 - p0)))
            composition = float(np.sum((p0 + p1) / 2 * (w1 - w0)))
            kit_rows.append(dict(celda=cell, mes=str(t), delta_agregado_pp=round(100 * (behaviour + composition), 2),
                                 delta_comportamiento_pp=round(100 * behaviour, 2),
                                 delta_composicion_pp=round(100 * composition, 2)))
    return pd.DataFrame(cf_rows), pd.DataFrame(kit_rows)


def mix_risk_by_cell(decomposition: pd.DataFrame) -> pd.Series:
    """Per cell: the mean absolute composition term over the window — how much the cell's
    aggregate rate moves by composition alone. The `riesgo_mix_pp` attribute of the card."""
    if decomposition.empty:
        return pd.Series(dtype=float, name="riesgo_mix_pp")
    return decomposition.groupby("celda")["delta_composicion_pp"].apply(lambda s: float(np.mean(np.abs(s)))).rename("riesgo_mix_pp")


# ═══════════════════════════════════════════════════════════════════════════════════
# 3 · TIMEVARYING CALIBRATION
# ═══════════════════════════════════════════════════════════════════════════════════

def timevarying_calibration(units: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """Realized rate per active flag and per sign, month by month, with its binomial error.

    OUTPUT:  DataFrame(tipo ("flag"/"signo"), nombre, mes, n, tasa_realizada, error_pp,
             version_modelo). The audit of every model that produces a flag.
    """
    period, ren_col, pipe_col = configuration.period_col, configuration.renewed_units_col, configuration.pipeline_units_col
    history = units[(units["universo"] == UNIVERSE_NORMAL) & units["tasa"].notna() & (units["sintetica"] == 0)]
    rows = []
    for flag, sign in configuration.structural_timevarying_dims.items():
        active = history[history[flag].isin(configuration.timevarying_positive_values)]
        for month, month_rows in active.groupby(period):
            n, rate = month_rows[pipe_col].sum(), month_rows[ren_col].sum() / max(month_rows[pipe_col].sum(), 1)
            rows.append(dict(tipo="flag", nombre=flag, signo=sign, mes=str(month), n=float(n), tasa_realizada=round(rate, 4),
                             error_pp=round(binomial_se_pp(rate, n) * configuration.z, 2),
                             version_modelo=configuration.timevarying_model_version.get(flag, "")))
    for sign_value, sign_rows in history.merge(
            units.drop_duplicates("fs_id")[["fs_id"]], on="fs_id").assign(
            _sign=lambda f: f["fs_id"].map(_sign_lookup(units, configuration))).groupby("_sign"):
        for month, month_rows in sign_rows.groupby(period):
            n, rate = month_rows[pipe_col].sum(), month_rows[ren_col].sum() / max(month_rows[pipe_col].sum(), 1)
            rows.append(dict(tipo="signo", nombre=sign_value, signo=sign_value, mes=str(month), n=float(n),
                             tasa_realizada=round(rate, 4), error_pp=round(binomial_se_pp(rate, n) * configuration.z, 2),
                             version_modelo=""))
    return pd.DataFrame(rows, columns=["tipo", "nombre", "signo", "mes", "n", "tasa_realizada", "error_pp", "version_modelo"])


def _sign_lookup(units: pd.DataFrame, configuration: Config) -> pd.Series:
    from run_rate_series import series_sign_table
    table = series_sign_table(units, configuration)
    return table.set_index("fs_id")["signo"]


# ═══════════════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════════════

def run_dimension_analysis(units: pd.DataFrame, series_summary: pd.DataFrame, configuration: Config) -> dict:
    """Phase 1.2 end to end. Persists decision_eta2, decision_eta2_pairs,
    simpson_contrafactual, mix_shift_decomposition, timevarying_calibration."""
    decision, pairs = dimension_separation(series_summary, units, configuration)
    counterfactual, decomposition = counterfactual_and_decomposition(units, configuration)
    calibration = timevarying_calibration(units, configuration)
    configuration.write(decision, "decision_eta2")
    configuration.write(pairs, "decision_eta2_pairs")
    configuration.write(counterfactual, "simpson_contrafactual")
    configuration.write(decomposition, "mix_shift_decomposition")
    configuration.write(calibration, "timevarying_calibration")
    print("[1.2] dimension separation (neutral series, weights = support):")
    for _, row in decision.iterrows():
        print(f"   {row['dimension']:<26} η²={row['eta2_individual']:.3f}  unique={row['contribucion_unica']:.3f}  ω²={row['omega2']:.3f}"
              f"  {'(annullable)' if row['anulable'] else ''}")
    if len(counterfactual):
        print(f"[1.2] Simpson counterfactual: saving of the segmented method ${counterfactual['ahorro_usd'].sum():,.0f} "
              f"over {counterfactual['mes'].nunique()} walk-forward months · segmented wins in "
              f"{counterfactual['gana_segmentado'].mean():.0%} of cell-months")
    if len(decomposition):
        composition_share = (decomposition["delta_composicion_pp"].abs().sum()
                             / max((decomposition["delta_composicion_pp"].abs() + decomposition["delta_comportamiento_pp"].abs()).sum(), 1e-9))
        print(f"[1.2] mix-shift: {composition_share:.0%} of the month-to-month movement of cell rates is composition, not behaviour")
    return dict(decision_eta2=decision, decision_eta2_pairs=pairs, simpson_contrafactual=counterfactual,
                mix_shift_decomposition=decomposition, timevarying_calibration=calibration)
