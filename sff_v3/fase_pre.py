"""fase_pre.py — PHASE P (intro) · Simpson showcase finder.

Runs BEFORE the framework on a small, time-anchored raw (e.g., the full 2025
pipeline with softcancel frozen as of Jan 1st) and answers ONE question:
WHERE can the mix-rotation story be SEEN — no statistics, just eyes.

Doctrine (Anexo E, act 1): the aggregate rate can fall while nobody changes,
because the low-rate group grows inside the mix. This phase hunts cells where
that movie is visually obvious, so the analyst can paint it (Power BI / charts).
Deliberately NO binomial yardstick here — plain pp windows and ranges, by design
and by user request: this is the intuition builder, not the judge.
"""
import sys

import numpy as np
import pandas as pd

# ─── VISUAL-DETECTION CONSTANTS (plain pp / units — not statistical tests) ───
EDGE_WINDOW_MONTHS = 3          # "start" and "end" = mean of first/last 3 months
FLATNESS_MAX_RANGE_PP = 10.0    # a subgroup counts as visually flat if max-min ≤ this
MIN_MONTHLY_UNITS = 20          # below this the lines look jagged, not tellable
MIN_MONTHS = 8                  # a story needs a timeline
TOP_N_DEFAULT = 10


def fp_find_simpson_showcases(raw: pd.DataFrame, cfg, split_dim: str = "softcancel",
                              showcase_grain: list = None, top_n: int = TOP_N_DEFAULT):
    """GOAL: rank the cells where a mix rotation visibly moves the aggregate rate
    while both subgroup rates stay flat — the paintable Simpson showcases.

    INPUT:  raw (small, time-anchored extract) · cfg (contract, grains, write) ·
            split_dim (the rotating dimension; default softcancel) ·
            showcase_grain (cell definition; default the mandatory dims) · top_n.
    OUTPUT: persisted `simpson_showcase` (one row per cell: mix swing, subgroup
            flatness, aggregate drop, drop explained by mix, purity, score) and
            `simpson_showcase_series` (tidy month-by-month lines of the top cells,
            ready to paint: share, rate_active, rate_rest, rate_aggregate, units).
    STEPS:
      [1] Contract & conditioning through fase 0 (same language, same guarantees).
      [2] Split each cell's months into ACTIVE (split_dim on) vs REST, and build
          the three monthly lines: share of active, rate of each group, aggregate.
      [3] Edge windows (first/last months): mix swing, aggregate drop, and the
          visual flatness of each subgroup (plain max-min range in pp).
      [4] The primary-school attribution: drop_explained_by_mix = swing × gap.
          purity = explained / observed drop (capped 0..1) — 1.0 means the whole
          fall is the mix rotating: pure Simpson, nobody changed.
      [5] Score = |explained drop| × purity × flatness bonus; rank, persist both
          tables, and narrate the top cells on the console.
    """
    from fase0 import f0_load_and_validate
    # [1] same contract as the framework: an intro phase speaks the same language
    df = f0_load_and_validate(raw, cfg)
    grain = showcase_grain if showcase_grain is not None else cfg.business_mandatory_dims
    if split_dim in cfg.structural_timevarying_dims:
        active_mask = df[split_dim].isin(cfg.timevarying_positive_values)
    else:
        heaviest = df.groupby(split_dim)[cfg.pipeline_units_col].sum().nlargest(2).index
        active_mask = df[split_dim] == heaviest[-1]     # challenger vs leader
    df = df.assign(_active=active_mask)
    truth = df[df[cfg.renewed_units_col].notna()]

    showcase_rows, series_rows = [], []
    for cell_values, cell_rows in truth.groupby(grain, observed=True):
        # [2] the three monthly lines of this cell
        monthly = cell_rows.groupby([cfg.period_col, "_active"]).agg(
            units=(cfg.pipeline_units_col, "sum"),
            renewed=(cfg.renewed_units_col, "sum")).reset_index()
        pivot_units = monthly.pivot(index=cfg.period_col, columns="_active", values="units").fillna(0)
        pivot_renew = monthly.pivot(index=cfg.period_col, columns="_active", values="renewed").fillna(0)
        if True not in pivot_units.columns or False not in pivot_units.columns:
            continue                                    # no rotation possible with one group
        total_units = pivot_units.sum(axis=1)
        if len(total_units) < MIN_MONTHS or total_units.median() < MIN_MONTHLY_UNITS:
            continue
        share_active = pivot_units[True] / total_units.clip(lower=1)
        rate_active = pivot_renew[True] / pivot_units[True].clip(lower=1)
        rate_rest = pivot_renew[False] / pivot_units[False].clip(lower=1)
        rate_aggregate = pivot_renew.sum(axis=1) / total_units.clip(lower=1)
        # [3] edge windows and visual flatness — eyes, not statistics
        w = EDGE_WINDOW_MONTHS
        mix_swing = share_active.iloc[-w:].mean() - share_active.iloc[:w].mean()
        aggregate_drop_pp = 100 * (rate_aggregate.iloc[-w:].mean() - rate_aggregate.iloc[:w].mean())
        range_active_pp = 100 * (rate_active.max() - rate_active.min())
        range_rest_pp = 100 * (rate_rest.max() - rate_rest.min())
        gap_pp = 100 * (rate_rest.mean() - rate_active.mean())
        # [4] primary-school attribution: what the rotation ALONE would move
        explained_pp = -mix_swing * gap_pp
        purity = float(np.clip(explained_pp / aggregate_drop_pp, 0, 1)) if abs(aggregate_drop_pp) > 0.5 else 0.0
        # [5] visual-drama score: big explained move, high purity, flat subgroups
        flat_bonus = 1.0 if (range_active_pp <= FLATNESS_MAX_RANGE_PP
                             and range_rest_pp <= FLATNESS_MAX_RANGE_PP) else 0.4
        score = abs(explained_pp) * purity * flat_bonus
        cell_id = "|".join(str(v) for v in (cell_values if isinstance(cell_values, tuple) else (cell_values,)))
        showcase_rows.append(dict(cell=cell_id, meses=len(total_units),
            units_mes_mediana=float(total_units.median()),
            share_ini=round(float(share_active.iloc[:w].mean()), 3),
            share_fin=round(float(share_active.iloc[-w:].mean()), 3),
            gap_pp=round(gap_pp, 1), rango_activa_pp=round(range_active_pp, 1),
            rango_resto_pp=round(range_rest_pp, 1),
            caida_agregado_pp=round(aggregate_drop_pp, 1),
            caida_explicada_mix_pp=round(explained_pp, 1),
            pureza=round(purity, 2), score=round(score, 2)))
        for month in total_units.index:
            series_rows.append(dict(cell=cell_id, mes=str(month),
                share_activa=round(float(share_active[month]), 3),
                tasa_activa=round(float(rate_active[month]), 4),
                tasa_resto=round(float(rate_rest[month]), 4),
                tasa_agregado=round(float(rate_aggregate[month]), 4),
                units=float(total_units[month])))
    showcase = pd.DataFrame(showcase_rows).sort_values("score", ascending=False)
    top_cells = set(showcase.head(top_n)["cell"])
    series = pd.DataFrame([r for r in series_rows if r["cell"] in top_cells])
    cfg.write(showcase, "simpson_showcase")
    cfg.write(series, "simpson_showcase_series")
    print(f"[fP] {len(showcase)} cells examined · top stories by visual drama:")
    for _, r in showcase.head(min(top_n, 5)).iterrows():
        print(f"   {r['cell']:30s} share {r['share_ini']:.0%}→{r['share_fin']:.0%} · "
              f"aggregate {r['caida_agregado_pp']:+.1f}pp, mix alone explains {r['caida_explicada_mix_pp']:+.1f}pp "
              f"(purity {r['pureza']:.0%}) · groups flat within {max(r['rango_activa_pp'], r['rango_resto_pp']):.0f}pp")
    return showcase, series


if __name__ == "__main__":
    # standalone runner: python fase_pre.py <raw.csv> [split_dim]
    from config import Config, join_columns
    raw_path = sys.argv[1]
    chosen_split = sys.argv[2] if len(sys.argv) > 2 else "softcancel"
    production_config = Config()                     # your defaults; edit here if needed
    raw_extract = pd.read_csv(raw_path, keep_default_na=False, na_values=[""])
    fp_find_simpson_showcases(raw_extract, production_config, split_dim=chosen_split)
