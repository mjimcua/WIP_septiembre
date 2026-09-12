"""fase2.py — PHASE 2 · Revaluation branch: the continuous path (DISENO_V2 §7).

Uplift conditional on renewing (n = renewers, not pipeline); yardstick s/√n̄; the
starting point determines the journey — credibility shrinks toward the parent with
the SAME starting point, never toward the veteran neighbor.
  2.1 f2_uplift_fine · 2.2 f2_diagnose · 2.3 f2_improve (+uplift_chain)
"""
import numpy as np, pandas as pd
from config import hash_key, join_columns

def f2_uplift_fine(fine_grain_table, cfg):
    """GOAL: estimate the uplift (renewed AUV / pipeline AUV) at the finest grain,
    conditional on renewing — the starting point determines the journey.

    INPUT:  fine_grain_table (0.2) · cfg (uses: renewed_*_col, pipeline_*_col,
            grano_uplift, period_col).
    OUTPUT: uplift_cells (gu × comb_id: $-weighted uplift, measured s, se=s/√months,
            n_ren) and renewer_rows (the base rows).
    STEPS:
      [1] Filter ONLY renewers (ren_units>0): the uplift's n is them, not the pipeline.
      [2] Per-row uplift = (ren_usd/ren_units) / (pipe_usd/pipe_units).
      [3] Aggregate by uplift grain × combination: uplift weighted by renewed money.
      [4] Measure s (internal dispersion) — the continuous yardstick must be MEASURED.
      [5] Yardstick = s/√months."""
    # [1] renewers only
    r = fine_grain_table[(fine_grain_table[cfg.renewed_units_col].fillna(0) > 0)].copy()
    # [2] per-row uplift
    r["auv_p"] = r[cfg.pipeline_usd_col] / r[cfg.pipeline_units_col].clip(lower=1)
    r["uplift_lookup"] = (r[cfg.renewed_usd_col] / r[cfg.renewed_units_col]) / r["auv_p"]
    r["uplift_cells"] = join_columns(r, cfg.grano_uplift)
    series_summary = r.groupby(["uplift_cells", "comb_id"], as_index=False).agg(
        n_ren=(cfg.renewed_units_col, "sum"), meses=(cfg.period_col, "nunique"),
        upl_w=(cfg.renewed_usd_col, "sum"), base=(cfg.renewed_units_col, lambda s: 1))
    den = r.groupby(["uplift_cells", "comb_id"]).apply(lambda x: (x[cfg.renewed_units_col] * x["auv_p"]).sum(), include_groups=False).rename("den").reset_index()
    series_summary = series_summary.merge(den, on=["uplift_cells", "comb_id"]); series_summary["uplift"] = series_summary["upl_w"] / series_summary["den"].clip(lower=1e-9)
    s = r.groupby(["uplift_cells", "comb_id"])["uplift_lookup"].std().rename("s").reset_index()
    series_summary = series_summary.merge(s, on=["uplift_cells", "comb_id"]).fillna({"s": 0})
    series_summary["se"] = series_summary["s"] / np.sqrt(series_summary["meses"].clip(lower=1))
    print(f"[f2.1] {len(series_summary)} celdas de uplift · rango [{series_summary['uplift'].min():.2f}, {series_summary['uplift'].max():.2f}]")
    return series_summary, r

def f2_diagnose(series_summary, r, cfg):
    """GOAL: diagnose the value branch — which axes separate the uplift and where
    internal heterogeneity lives (high s with decent n = a missing axis or a mix).

    INPUT:  uplift_cells + renewer_rows (2.1) · cfg (extra_revalorizacion).
    OUTPUT: eta2 dict per axis (weights = renewed $). Verdict printed.
    STEPS:
      [1] Base per cell×extras with mean uplift and $ weight.
      [2] Weighted η² per extra_revalorizacion axis."""
    from fase1 import _eta2_w
    base = r.groupby(["uplift_cells", "comb_id"] + cfg.extra_revalorizacion, as_index=False).agg(
        u=("uplift_lookup", "mean"), w=(cfg.renewed_usd_col, "sum"))
    eta2_by_dim = {d: _eta2_w(base, d, "u", "w") for d in cfg.extra_revalorizacion}
    print(f"[f2.2] η²-uplift: { {k: round(x,3) for k,x in eta2_by_dim.items()} } · cells with high s and decent n = internal heterogeneity")
    return eta2_by_dim

def f2_improve(series_summary, eta2_by_dim, cfg):
    """GOAL: repair value-side support with the adapted improvements — and stamp the
    final uplift per cell with its gain chain.

    INPUT:  uplift_cells + eta2 per axis (2.2) · cfg (k_uplift, write).
    OUTPUT: uplift_cells + `uplift_final` (always >0) and table `uplift_chain`
            (stages 0_fino / 1_padre / 2_shrink — stage VALUES stay as persisted data).
    STEPS:
      [1] Mute axes (η² < threshold): candidates for annulment — listed.
      [2] Parent with the SAME starting point: newcust is kept, the rest '*'.
      [3] Credibility z = n/(n+k) with n = renewers/month.
      [4] Three-stage chain stamped per cell; guardrail uplift>0."""
    # [1] mute axes
    anular = [d for d in cfg.extra_revalorizacion if eta2_by_dim.get(d, 0) < 0.05]
    # [2] parent with the same starting point
    padre_ejes = [d for d in cfg.extra_revalorizacion if d == "newcust"]
    def padre(comb):
        p = dict(zip(cfg.extra_revalorizacion, comb.split("|")))
        return "|".join(p[d] if d in padre_ejes else "*" for d in cfg.extra_revalorizacion)
    series_summary = series_summary.copy(); series_summary["padre"] = series_summary["comb_id"].map(padre)
    pg = series_summary.groupby(["uplift_cells"]).apply(lambda x: np.average(x["uplift"], weights=x["n_ren"]), include_groups=False)
    pp = series_summary.groupby(["uplift_cells", "padre"]).apply(lambda x: np.average(x["uplift"], weights=x["n_ren"]), include_groups=False)
    collected_rows = []
    for _, row in series_summary.iterrows():
        # [3] credibility
        n = row["n_ren"] / max(row["meses"], 1); z = n / (n + cfg.k_uplift)
        up = pp.get((row["uplift_cells"], row["padre"]), pg.get(row["uplift_cells"], row["uplift"]))
        uf = z * row["uplift"] + (1 - z) * up
        # [4] stage chain
        for et, u, se in [("0_fino", row["uplift"], row["se"]),
                          ("1_padre", up, row["se"]), ("2_shrink", uf, row["se"] * z)]:
            collected_rows.append(dict(gu=row["uplift_cells"], comb_id=row["comb_id"],
                              uplift_cell_key=hash_key(row["uplift_cells"] + "||" + row["comb_id"]), etapa=et,
                              uplift=round(float(u), 3), se=round(float(se), 4), n_ren=row["n_ren"]))
        series_summary.loc[row.name, "uplift_final"] = max(uf, 0.01)
    support_chain_rows = pd.DataFrame(collected_rows); cfg.write(support_chain_rows, "uplift_chain")
    print(f"[f2.3] mute axes annulled: {anular or 'none'} · credibility applied (k={cfg.k_uplift})")
    return series_summary, support_chain_rows
