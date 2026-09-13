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
# (window, min history and max pairs are Config parameters: see config.py, phase 1.2)
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
    return decision, pairs.sort_values("interaccion", ascending=False).head(configuration.eta2_max_pairs)


# ═══════════════════════════════════════════════════════════════════════════════════
# 2 · MIX-SHIFT
# ═══════════════════════════════════════════════════════════════════════════════════

def counterfactual_and_decomposition(units: pd.DataFrame, configuration: Config) -> tuple:
    """Walk-forward Simpson counterfactual and Kitagawa decomposition per mandatory cell × month.

    INPUT:   units with tasa (history) · configuration.
    OUTPUT:  (counterfactual, decomposition).
             counterfactual: celda_id, mes, tasa_real, tasa_plano, tasa_seg, err_plano_pp,
             err_seg_pp, ahorro_usd, gana_segmentado (0/1), cota_celda_pp.
             decomposition: celda_id, mes, delta_agregado_pp, delta_comportamiento_pp,
             delta_composicion_pp (vs the previous month with truth).
    RULES:   for month t only data ≤ t−1 is used (cumulative sums shifted by one month);
             the weights of t are the real pipeline of t (known data). Saving =
             (|err_plano| − |err_seg|) × pipeline$ of t, signed. Kitagawa: Δ = Σ w̄·Δp +
             Σ p̄·Δw with midpoint weights/rates, vs the cell's previous month with truth.
    EDGE CASES: cells with fewer than `counterfactual_min_history_months` past months are skipped.
    NOTE:    vectorized (one pass of cumulative sums), so it scales with the number of
             rows, not with cells × months × groupby calls.
    """
    period, ren_col, pipe_col, usd_col = (configuration.period_col, configuration.renewed_units_col,
                                          configuration.pipeline_units_col, configuration.pipeline_usd_col)
    history = units[(units["universo"] == UNIVERSE_NORMAL) & units["tasa"].notna() & (units["sintetica"] == 0)].copy()
    history["celda_id"] = join_columns(history, configuration.business_mandatory_dims)
    empty = (pd.DataFrame(columns=["celda_id", "mes", "tasa_real", "tasa_plano", "tasa_seg", "err_plano_pp", "err_seg_pp",
                                   "ahorro_usd", "gana_segmentado", "cota_celda_pp"]),
             pd.DataFrame(columns=["celda_id", "mes", "delta_agregado_pp", "delta_comportamiento_pp", "delta_composicion_pp"]))
    if history.empty:
        return empty
    # [1] one row per (cell, series, month), with the series' PAST (≤ t−1) as shifted cumsums
    monthly = (history.groupby(["celda_id", "fs_id", period], as_index=False)
               .agg(ren=(ren_col, "sum"), pipe=(pipe_col, "sum"), usd=(usd_col, "sum")).sort_values([period]))
    grouped = monthly.groupby(["celda_id", "fs_id"])
    monthly["ren_past"] = grouped["ren"].cumsum() - monthly["ren"]
    monthly["pipe_past"] = grouped["pipe"].cumsum() - monthly["pipe"]
    # [2] the cell's past and its number of past months
    cell = monthly.groupby(["celda_id", period], as_index=False).agg(ren=("ren", "sum"), pipe=("pipe", "sum"), usd=("usd", "sum"))
    cell = cell.sort_values(period)
    cell_grouped = cell.groupby("celda_id")
    cell["ren_past"] = cell_grouped["ren"].cumsum() - cell["ren"]
    cell["pipe_past"] = cell_grouped["pipe"].cumsum() - cell["pipe"]
    cell["meses_pasados"] = cell_grouped.cumcount()
    cell["mes_anterior"] = cell_grouped[period].shift(1)
    cell["tasa_real"] = cell["ren"] / cell["pipe"].replace(0, np.nan)
    cell["tasa_plano"] = cell["ren_past"] / cell["pipe_past"].replace(0, np.nan)
    window = sorted(history[period].unique())[-configuration.counterfactual_window_months:]
    judged = cell[(cell["meses_pasados"] >= configuration.counterfactual_min_history_months) & cell[period].isin(window)]
    # [3] segmented: the past rate of each series, weighted by the real pipeline of t
    rows = monthly.merge(judged[["celda_id", period, "tasa_plano"]], on=["celda_id", period])
    rows["tasa_serie_pasada"] = (rows["ren_past"] / rows["pipe_past"].replace(0, np.nan)).fillna(rows["tasa_plano"])
    rows["peso_x_tasa"] = rows["pipe"] * rows["tasa_serie_pasada"]
    segmented = rows.groupby(["celda_id", period])["peso_x_tasa"].sum() / rows.groupby(["celda_id", period])["pipe"].sum()
    judged = judged.merge(segmented.rename("tasa_seg").reset_index(), on=["celda_id", period])
    judged["err_plano_pp"] = 100 * (judged["tasa_plano"] - judged["tasa_real"])
    judged["err_seg_pp"] = 100 * (judged["tasa_seg"] - judged["tasa_real"])
    judged["ahorro_usd"] = (judged["err_plano_pp"].abs() - judged["err_seg_pp"].abs()) / 100 * judged["usd"]
    judged["gana_segmentado"] = (judged["err_seg_pp"].abs() < judged["err_plano_pp"].abs()).astype(int)
    judged["cota_celda_pp"] = [binomial_se_pp(r, n) * configuration.z for r, n in zip(judged["tasa_real"], judged["pipe"])]
    counterfactual = judged.assign(mes=judged[period].astype(str))[
        ["celda_id", "mes", "tasa_real", "tasa_plano", "tasa_seg", "err_plano_pp", "err_seg_pp", "ahorro_usd", "gana_segmentado", "cota_celda_pp"]
    ].round({"tasa_real": 4, "tasa_plano": 4, "tasa_seg": 4, "err_plano_pp": 2, "err_seg_pp": 2, "ahorro_usd": 2, "cota_celda_pp": 2})
    # [4] Kitagawa vs the cell's previous month with truth: outer join of the series present now / before
    now = monthly.merge(judged[["celda_id", period, "mes_anterior"]], on=["celda_id", period]).dropna(subset=["mes_anterior"])
    now["p1"] = now["ren"] / now["pipe"].replace(0, np.nan)
    now["w1"] = now["pipe"] / now.groupby(["celda_id", period])["pipe"].transform("sum")
    before = monthly.rename(columns={period: "mes_anterior"})[["celda_id", "fs_id", "mes_anterior", "ren", "pipe"]]
    before["p0"] = before["ren"] / before["pipe"].replace(0, np.nan)
    before["w0"] = before["pipe"] / before.groupby(["celda_id", "mes_anterior"])["pipe"].transform("sum")
    keys = judged[["celda_id", period, "mes_anterior"]].dropna()
    before = before.merge(keys, on=["celda_id", "mes_anterior"])
    joined = now[["celda_id", "fs_id", period, "p1", "w1"]].merge(before[["celda_id", "fs_id", period, "p0", "w0"]],
                                                                on=["celda_id", "fs_id", period], how="outer")
    joined["p0"], joined["p1"] = joined["p0"].fillna(joined["p1"]), joined["p1"].fillna(joined["p0"])
    joined["w0"], joined["w1"] = joined["w0"].fillna(0), joined["w1"].fillna(0)
    joined["comportamiento"] = (joined["w0"] + joined["w1"]) / 2 * (joined["p1"] - joined["p0"])
    joined["composicion"] = (joined["p0"] + joined["p1"]) / 2 * (joined["w1"] - joined["w0"])
    terms = joined.groupby(["celda_id", period], as_index=False)[["comportamiento", "composicion"]].sum()
    decomposition = pd.DataFrame(dict(celda_id=terms["celda_id"], mes=terms[period].astype(str),
                                      delta_agregado_pp=(100 * (terms["comportamiento"] + terms["composicion"])).round(2),
                                      delta_comportamiento_pp=(100 * terms["comportamiento"]).round(2),
                                      delta_composicion_pp=(100 * terms["composicion"]).round(2)))
    return counterfactual.reset_index(drop=True), decomposition


def mix_risk_by_cell(decomposition: pd.DataFrame) -> pd.Series:
    """Per cell: the mean absolute composition term over the window — how much the cell's
    aggregate rate moves by composition alone. The `riesgo_mix_pp` attribute of the card."""
    if decomposition.empty:
        return pd.Series(dtype=float, name="riesgo_mix_pp")
    return decomposition.groupby("celda_id")["delta_composicion_pp"].apply(lambda s: float(np.mean(np.abs(s)))).rename("riesgo_mix_pp")


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
