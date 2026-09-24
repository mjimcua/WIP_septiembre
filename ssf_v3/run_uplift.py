"""run_uplift.py — SFF v3 · RUN · phase 4: the revaluation branch, simple and correct.

The uplift of a cell is the ratio of sums Σ renewed$ / Σ (renewed units × pipeline AUV):
what the renewers pay relative to what they paid, weighted by money. Its n is the number
of RENEWERS, not the pipeline: a renewal that did not happen has no price.

Support repair, deliberately minimal (the v2 credibility was a no-op and is dropped):
  · a cell with n_renovadores ≥ `uplift_floor` uses its own ratio;
  · below the floor, it takes its PARENT's: the same mandatory cell with the
    `uplift_parent_keep_columns` extras kept (the "starting point": e.g. newcust) and the
    other extras set to '*'; if the parent is also below the floor, the mandatory cell.
The error of a ratio has no clean formula: it is measured by BOOTSTRAP of the renewer
rows (resample, recompute the ratio, take p5/p95). Intuitive, no theory.

Output: `decision_uplift` (cell → uplift, n, band, origin) and `uplift_chain` (the trace).
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd

from config import COMBINED_ID_SEPARATOR, Config, hash_key, join_columns
from vocabulario import *  # the persisted labels (roles, signs, treatments, origins, levels)

# ─── named constants ─────────────────────────────────────────────────────────────
NEUTRAL_UPLIFT = 1.0
MIN_UPLIFT = 0.01
WILDCARD = "*"
ORIGIN_OWN = "propia"
ORIGIN_PARENT = "padre"
ORIGIN_CELL = "celda"
ORIGIN_NEUTRAL = "neutro"


def renewer_rows(fine_table: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """The rows that renewed, with per-row pipeline AUV and uplift; uplift cell ids."""
    renewers = fine_table[fine_table[configuration.renewed_units_col].fillna(0) > 0].copy()
    if configuration.uplift_window_months:
        recent = sorted(renewers[configuration.period_col].unique())[-int(configuration.uplift_window_months):]
        renewers = renewers[renewers[configuration.period_col].isin(recent)]
    renewers["auv_pipeline"] = renewers[configuration.pipeline_usd_col] / renewers[configuration.pipeline_units_col].clip(lower=1)
    renewers["uplift_fila"] = (renewers[configuration.renewed_usd_col] / renewers[configuration.renewed_units_col]) / renewers["auv_pipeline"]
    renewers["uplift_cell_id"] = join_columns(renewers, configuration.uplift_cell_columns)
    renewers["celda_id"] = join_columns(renewers, configuration.business_mandatory_dims)
    keep = set(configuration.uplift_parent_keep_columns)
    parent_fields = [renewers[c].astype(str) if c in keep or c in configuration.business_mandatory_dims
                     else pd.Series(WILDCARD, index=renewers.index) for c in configuration.uplift_cell_columns]
    renewers["uplift_parent_id"] = pd.concat(parent_fields, axis=1).agg("|".join, axis=1) if parent_fields else WILDCARD
    return renewers


def ratio_of_sums(rows: pd.DataFrame, configuration: Config) -> float:
    """Σ renewed$ / Σ (renewed units × pipeline AUV)."""
    denominator = float((rows[configuration.renewed_units_col] * rows["auv_pipeline"]).sum())
    return float(rows[configuration.renewed_usd_col].sum() / denominator) if denominator > 0 else np.nan


def bootstrap_band(rows: pd.DataFrame, configuration: Config, rng: np.random.Generator) -> tuple:
    """p5 / p95 of the ratio over resampled renewer rows.

    NOTE:    the resampling is done on two numpy arrays (renewed$ and renewed units ×
             pipeline AUV) with one index matrix of shape (samples × rows): no DataFrame
             is built per sample, so a cell with 50,000 renewer rows costs milliseconds.
    """
    if len(rows) < 2:
        return np.nan, np.nan
    numerator = rows[configuration.renewed_usd_col].to_numpy(dtype=float)
    denominator = (rows[configuration.renewed_units_col] * rows["auv_pipeline"]).to_numpy(dtype=float)
    picks = rng.integers(0, len(rows), size=(configuration.uplift_bootstrap_samples, len(rows)))
    sampled_denominator = denominator[picks].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        samples = np.where(sampled_denominator > 0, numerator[picks].sum(axis=1) / sampled_denominator, np.nan)
    return float(np.nanquantile(samples, 0.05)), float(np.nanquantile(samples, 0.95))


def estimate_uplift_cells(renewers: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per uplift cell: own ratio, n, parent ratio, cell ratio, decision and band.

    OUTPUT:  decision_uplift: uplift_cell_id, uplift_cell_key, celda_id,
             uplift_parent_id, n_renovadores, meses, uplift_propio, uplift_padre,
             uplift_celda, uplift, uplift_origen, banda_low, banda_high, recortado.
    """
    rng = np.random.default_rng(configuration.random_seed)
    by_parent = {pid: ratio_of_sums(g, configuration) for pid, g in renewers.groupby("uplift_parent_id")}
    n_parent = renewers.groupby("uplift_parent_id")[configuration.renewed_units_col].sum()
    by_cell = {cid: ratio_of_sums(g, configuration) for cid, g in renewers.groupby("celda_id")}
    rows = []
    for cell_id, group in renewers.groupby("uplift_cell_id"):
        n = float(group[configuration.renewed_units_col].sum())
        own = ratio_of_sums(group, configuration)
        parent_id, mandatory_id = group["uplift_parent_id"].iat[0], group["celda_id"].iat[0]
        parent, cell = by_parent.get(parent_id, np.nan), by_cell.get(mandatory_id, np.nan)
        if n >= configuration.uplift_floor and np.isfinite(own):
            chosen, origin, band_rows = own, ORIGIN_OWN, group
        elif n_parent.get(parent_id, 0) >= configuration.uplift_floor and np.isfinite(parent):
            chosen, origin, band_rows = parent, ORIGIN_PARENT, renewers[renewers["uplift_parent_id"] == parent_id]
        elif np.isfinite(cell):
            chosen, origin, band_rows = cell, ORIGIN_CELL, renewers[renewers["celda_id"] == mandatory_id]
        else:
            chosen, origin, band_rows = NEUTRAL_UPLIFT, ORIGIN_NEUTRAL, group.head(0)
        low, high = bootstrap_band(band_rows, configuration, rng)
        clipped = float(np.clip(chosen, MIN_UPLIFT, configuration.uplift_cap))
        rows.append(dict(uplift_cell_id=cell_id, uplift_cell_key=hash_key(cell_id), celda_id=mandatory_id,
                         uplift_parent_id=parent_id, n_renovadores=n, meses=int(group[configuration.period_col].nunique()),
                         uplift_propio=round(own, 4) if np.isfinite(own) else np.nan,
                         uplift_padre=round(parent, 4) if np.isfinite(parent) else np.nan,
                         uplift_celda=round(cell, 4) if np.isfinite(cell) else np.nan,
                         uplift=round(clipped, 4), uplift_origen=origin,
                         banda_low=round(low, 4) if np.isfinite(low) else np.nan,
                         banda_high=round(high, 4) if np.isfinite(high) else np.nan,
                         recortado=int(clipped != chosen)))
    return pd.DataFrame(rows)


def build_uplift_chain(decision_uplift: pd.DataFrame) -> pd.DataFrame:
    """The trace per cell: stages 0_propio / 1_padre / 2_celda / 9_final."""
    rows = []
    for _, cell in decision_uplift.iterrows():
        for stage, value in (("0_propio", cell["uplift_propio"]), ("1_padre", cell["uplift_padre"]),
                             ("2_celda", cell["uplift_celda"]), ("9_final", cell["uplift"])):
            rows.append(dict(uplift_cell_id=cell["uplift_cell_id"], uplift_cell_key=cell["uplift_cell_key"], etapa=stage,
                             uplift=value, n_renovadores=cell["n_renovadores"], uplift_origen=cell["uplift_origen"]))
    return pd.DataFrame(rows)


def run_uplift(fine_table: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """Phase 4: the statistical uplift per cell (as before) and, when the discount column
    exists, the validation of the contract rule (`uplift_contract_check`). The contract
    path itself is applied row by row in the assembly. Persists decision_uplift and
    uplift_chain. Returns decision_uplift (with attrs["realization_ratio"] per cell)."""
    renewers = renewer_rows(fine_table, configuration)
    check = realization_check(renewers, configuration) if configuration.discount_value_column else pd.DataFrame(
        columns=["uplift_cell_id", "autorenew", "n_renovadores", "usd_renovado", "uplift_observado", "uplift_regla", "pct_usd_dentro_2pct", "ratio_realizacion", "aplicar"])
    configuration.write(check, "uplift_contract_check")
    if configuration.discount_value_column:
        known = known_discount(renewers, configuration)
        if len(check):
            weighted_within = float(np.average(check["pct_usd_dentro_2pct"], weights=np.maximum(check["usd_renovado"], 1e-9)))
            print(f"[4] contract rule check on past renewals with a known discount ({100 * known.mean():.0f}% of renewer rows): "
                  f"{weighted_within:.0f}% of renewed $ within ±2% of price_increase / (1 − discount) · realization ratio applied in "
                  f"{int(check['aplicar'].sum())} cell×autorenew groups (dollar-weighted mean {np.average(check.loc[check['aplicar'] == 1, 'ratio_realizacion'], weights=np.maximum(check.loc[check['aplicar'] == 1, 'usd_renovado'], 1e-9)) if check['aplicar'].any() else float('nan'):.3f})")
        if configuration.statistical_uplift_from_unknown_only:
            renewers = renewers[~known]
    decision = estimate_uplift_cells(renewers, configuration)
    ratios = realization_ratio_by_cell(check, configuration) if len(check) else {}
    decision["ratio_realizacion"] = decision["uplift_cell_id"].map(ratios).fillna(1.0).round(4)
    decision.attrs["realization_ratio"] = ratios
    configuration.write(decision, "decision_uplift")
    configuration.write(build_uplift_chain(decision), "uplift_chain")
    below = decision[decision["n_renovadores"] < configuration.uplift_floor]
    print(f"[4] uplift: {len(decision)} cells · range [{decision['uplift'].min():.2f}, {decision['uplift'].max():.2f}] · "
          f"{len(below)} cells below the floor ({decision['uplift_origen'].value_counts().to_dict()}) · "
          f"{int(decision['recortado'].sum())} clipped at the cap {configuration.uplift_cap}")
    return decision


# ═══════════════════════════════════════════════════════════════════════════════════
# THE CONTRACT PATH · where the discount is known, the renewal price is a rule
# ═══════════════════════════════════════════════════════════════════════════════════

def price_increase_factor(periods: pd.Series, configuration: Config) -> np.ndarray:
    """The list-price factor of every period: the product of the increases dated at or
    before it (`price_increase_by_period`, {"2027-01": 1.05}). 1.0 with no increases."""
    factors = np.ones(len(periods), dtype=float)
    if not configuration.price_increase_by_period:
        return factors
    months = pd.PeriodIndex(periods.astype(str), freq="M")
    for start, factor in configuration.price_increase_by_period.items():
        factors = np.where(months >= pd.Period(start, freq="M"), factors * float(factor), factors)
    return factors


def known_discount(rows: pd.DataFrame, configuration: Config) -> pd.Series:
    """True where the row's discount is informed and below the cap (the contract path)."""
    column = configuration.discount_value_column
    if column is None or column not in rows.columns:
        return pd.Series(False, index=rows.index)
    discount = pd.to_numeric(rows[column], errors="coerce")
    return discount.notna() & (discount >= 0) & (discount <= configuration.discount_cap)


def contract_uplift(rows: pd.DataFrame, configuration: Config) -> pd.Series:
    """uplift = price_increase(period) / (1 − discount), NaN where the discount is unknown."""
    discount = pd.to_numeric(rows[configuration.discount_value_column], errors="coerce") if configuration.discount_value_column in rows.columns else pd.Series(np.nan, index=rows.index)
    increase = price_increase_factor(rows[configuration.period_col], configuration)
    rule = increase / (1.0 - discount.clip(upper=0.999))
    return rule.where(known_discount(rows, configuration))


def realization_check(renewers: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """The validation of the rule on past renewals with a known discount, per uplift cell
    (and per autorenew value when that flag exists): the observed uplift, the rule uplift,
    the share of renewed dollars within ±2 % of the rule, and the realization ratio
    = Σ renewed$ / Σ (renewed units × pipeline AUV × rule), dollar-weighted.
    OUTPUT: uplift_contract_check (uplift_cell_id, autorenew, n_renovadores, usd_renovado,
            uplift_observado, uplift_regla, pct_usd_dentro_2pct, ratio_realizacion, aplicar)."""
    rows = renewers[known_discount(renewers, configuration)].copy()
    if rows.empty:
        return pd.DataFrame(columns=["uplift_cell_id", "autorenew", "n_renovadores", "usd_renovado", "uplift_observado", "uplift_regla",
                                     "pct_usd_dentro_2pct", "ratio_realizacion", "aplicar"])
    rows["uplift_regla"] = contract_uplift(rows, configuration)
    autorenew_column = next((c for c in configuration.structural_timevarying_dims if "autoren" in c.lower()), None)
    rows["autorenew"] = rows[autorenew_column].astype(str) if autorenew_column else "*"
    rows["within"] = (rows["uplift_fila"] / rows["uplift_regla"]).between(0.98, 1.02)
    rows["rule_denominator"] = rows[configuration.renewed_units_col] * rows["auv_pipeline"] * rows["uplift_regla"]
    out = []
    for (cell, autorenew), block in rows.groupby(["uplift_cell_id", "autorenew"]):
        renewed_usd = float(block[configuration.renewed_usd_col].sum())
        ratio = renewed_usd / float(block["rule_denominator"].sum()) if block["rule_denominator"].sum() > 0 else np.nan
        renewers_count = float(block[configuration.renewed_units_col].sum())
        out.append(dict(uplift_cell_id=cell, autorenew=autorenew, n_renovadores=renewers_count, usd_renovado=round(renewed_usd, 2),
                        uplift_observado=round(ratio_of_sums(block, configuration), 4),
                        uplift_regla=round(float(np.average(block["uplift_regla"], weights=np.maximum(block["rule_denominator"], 1e-9))), 4),
                        pct_usd_dentro_2pct=round(100 * float(block.loc[block["within"], configuration.renewed_usd_col].sum()) / max(renewed_usd, 1e-9), 1),
                        ratio_realizacion=round(ratio, 4) if np.isfinite(ratio) else np.nan,
                        aplicar=int(renewers_count >= configuration.uplift_floor and np.isfinite(ratio))))
    return pd.DataFrame(out)


def realization_ratio_by_cell(check: pd.DataFrame, configuration: Config) -> dict:
    """uplift_cell_id → realization ratio to apply (dollar-weighted over autorenew values),
    1.0 where the cell has no support or the correction is switched off."""
    if not configuration.contract_apply_realization_ratio or check is None or check.empty:
        return {}
    usable = check[check["aplicar"] == 1]
    ratios = {}
    for cell, block in usable.groupby("uplift_cell_id"):
        ratios[cell] = float(np.average(block["ratio_realizacion"], weights=np.maximum(block["usd_renovado"], 1e-9)))
    return ratios
