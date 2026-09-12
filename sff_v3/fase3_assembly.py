"""fase3_assembly.py — PHASE 3 · Forecast assembly.

The fine future row carries both keys at once: its series (→ rate through the chain
own→L1→L2→credibility) and its extras combination (→ uplift through its hierarchy).
Row-by-row multiplication; aggregate to any reporting grain (DISENO_V2 §8).
"""
import numpy as np
import pandas as pd

from config import join_columns


def f3_ensamblaje(fine_grain_table, v2, series_estimates, uplift_cells, cfg):
    """INPUT:  fine table (projection rows), series estimates, uplift cells, config.
    OUTPUT: persisted table `forecast_detail` (fu_key, tasa, uplift, esperado_usd, etiqueta).
    RULES:  (1) expected = pipeline_usd × rate × uplift, row by row; (2) rate saturated
    at the cap (rate_cap); (3) a series without an estimate inherits its mandatory-cell
    mean; (4) a combination without uplift uses neutral 1.0; (5) semantic labels from config.
    EDGES:  empty projection → empty table, no error.
    LOGGING: process_date + execution_id via config.write.
    STEPS:
      [1] Future-row identities (fs_id, gu).
      [2] Rate lookup per series, saturated at the cap (rate_cap).
      [3] Fallback: no estimate → mandatory-cell mean.
      [4] Uplift lookup per combination (no match → neutral 1.0).
      [5] expected = pipeline_usd × rate × uplift, row by row.
      [6] Semantic labels and persistence."""
    future_rows = fine_grain_table[fine_grain_table[cfg.dataset_role_col] == "projection"].copy()
    # [1] future-row identities
    future_rows["fs_id"] = join_columns(future_rows, cfg.grano_tasa)
    # [2] rate lookup (saturated at the cap)
    tasa = series_estimates.set_index("fs_id")["tasa_final"].clip(upper=cfg.rate_cap)
    future_rows["tasa"] = future_rows["fs_id"].map(tasa)
    # [3] FALLBACK CASCADE, with traceability: own estimate → mandatory-cell mean →
    #     global mean. The cell key must join EXACTLY the mandatory dims (fs_id starts
    #     with them, in order): taking only the first field silently matches nothing
    #     whenever there is more than one mandatory dim.
    future_rows["tasa_origen"] = np.where(future_rows["tasa"].notna(), "serie", "")
    mandatory_count = len(cfg.business_mandatory_dims)
    cell_of_series = (series_estimates["fs_id"].str.split("|").str[:mandatory_count]
                      .str.join("|"))
    cell_rate = (series_estimates.assign(celda=cell_of_series)
                 .groupby("celda")["tasa_final"].mean())
    cell_key_of_row = join_columns(future_rows, cfg.business_mandatory_dims)
    from_cell = cell_key_of_row.map(cell_rate)
    future_rows["tasa_origen"] = np.where(future_rows["tasa"].isna() & from_cell.notna(),
                                          "celda", future_rows["tasa_origen"])
    future_rows["tasa"] = future_rows["tasa"].fillna(from_cell)
    global_rate = float(series_estimates["tasa_final"].mean())
    future_rows["tasa_origen"] = np.where(future_rows["tasa"].isna(), "global",
                                          future_rows["tasa_origen"])
    future_rows["tasa"] = future_rows["tasa"].fillna(global_rate).clip(upper=cfg.rate_cap)
    origen_census = future_rows["tasa_origen"].value_counts().to_dict()
    money_by_origin = (future_rows.groupby("tasa_origen")[cfg.pipeline_usd_col].sum()
                       / max(future_rows[cfg.pipeline_usd_col].sum(), 1) * 100)
    print(f"[f3] rate lookup coverage: {origen_census} · "
          f"$ share by origin: { {k: f'{v:.1f}%' for k, v in money_by_origin.items()} }")
    if "global" in origen_census:
        print(f"[f3] ⚠ {origen_census['global']} rows fell back to the GLOBAL mean: "
              f"neither their series nor their mandatory cell had an estimate — "
              f"check phase 1 coverage before trusting their forecast")
    future_rows["uplift_cells"] = join_columns(future_rows, cfg.grano_uplift)
    uplift_lookup = uplift_cells.set_index(["uplift_cells", "comb_id"])["uplift_final"]
    # [4] uplift lookup per combination
    future_rows["uplift"] = [uplift_lookup.get((a, b), 1.0) for a, b in zip(future_rows["uplift_cells"], future_rows["comb_id"])]
    # [5] the row-by-row multiplication
    future_rows["esperado_usd"] = future_rows[cfg.pipeline_usd_col] * future_rows["tasa"] * future_rows["uplift"]
    # [6] semantic labels from config
    future_rows["etiqueta"] = ""
    for col, val, lab in cfg.semantic_labels:
        future_rows.loc[future_rows[col] == val, "etiqueta"] = lab
    # GUARDRAILS with a diagnosis, never a mute assert: if something is NaN, say WHICH
    # lookup failed, how many rows and how much money, and show an offending example
    if future_rows["esperado_usd"].isna().any():
        broken = future_rows[future_rows["esperado_usd"].isna()]
        culprit = ("tasa" if broken["tasa"].isna().any() else
                   "uplift" if broken["uplift"].isna().any() else "pipeline_usd")
        example = broken.iloc[0]
        raise AssertionError(
            f"esperado_usd has NaN in {len(broken):,} rows (${broken[cfg.pipeline_usd_col].sum():,.0f} "
            f"of pipeline) — the broken lookup is '{culprit}'. Example: fs_id={example['fs_id']!r}, "
            f"comb_id={example['comb_id']!r}, tasa={example['tasa']}, uplift={example['uplift']}")
    if (future_rows["tasa"] > cfg.rate_cap + 1e-9).any():
        over = future_rows[future_rows["tasa"] > cfg.rate_cap + 1e-9]
        raise AssertionError(f"rate above the cap in {len(over):,} rows "
                             f"(max {over['tasa'].max():.4f} vs cap {cfg.rate_cap})")
    if (future_rows["uplift"] <= 0).any():
        raise AssertionError(f"uplift <= 0 in {int((future_rows['uplift'] <= 0).sum()):,} rows")
    cfg.write(future_rows[["fu_key", "comb_key", "fs_id", cfg.period_col, cfg.pipeline_usd_col, "tasa", "uplift",
                   "esperado_usd", "etiqueta", "tasa_origen"]].assign(**{cfg.period_col: future_rows[cfg.period_col].astype(str)}), "forecast_detail")
    res = future_rows.groupby("etiqueta")["esperado_usd"].sum()
    print(f"[f3] total forecast ${future_rows['esperado_usd'].sum():,.0f} · by label: { {k or 'genuine': f'${x:,.0f}' for k,x in res.items()} }")
    return future_rows



def f3_build_key_bridge(fine_grain_table, labeled_view, series_estimates, cfg):
    """GOAL: ONE thin spine so every star table snaps back to the raw — the analyst
    reports at raw grain and reaches any result through a single chain of joins.

    INPUT:  fine table (0.2, with fu_comb_key), labeled view (0.3), series
            estimates (1.3) · cfg (grains, write).
    OUTPUT: persisted `key_bridge`: one row per (FU, combination) pair with every
            lineage id/key — fu, comb, series, L1/L2 pool, uplift cell, mandatory
            cell — plus universe and route labels.
    STEPS:
      [1] Distinct (fu, comb) pairs from the fine table with their ids and keys.
      [2] Series id from the fu id (strip the month) and lineage L1/L2 from the
          estimates (heuristic/no-history series keep their own id as lineage).
      [3] Uplift-cell id (uplift grain) and mandatory-cell id, with hash keys.
      [4] Universe and route labels from the labeled view; persist.
    """
    from config import hash_key, join_columns
    # [1] distinct pairs
    # dict.fromkeys keeps order and DEDUPES: mandatory dims live both in grano_uplift
    # and in business_mandatory_dims, and a duplicated column would silently corrupt
    # every id built from this frame (the uplift cell key would stop matching phase 2)
    bridge_columns = list(dict.fromkeys(
        ["fu_comb_key", "fu_id", "fu_key", "comb_id", "comb_key"]
        + cfg.grano_uplift + cfg.business_mandatory_dims))
    bridge = fine_grain_table.drop_duplicates("fu_comb_key")[bridge_columns].copy()
    # [2] series and pool lineage
    bridge["fs_id"] = bridge["fu_id"].str.rsplit("|", n=1).str[0]
    lineage = series_estimates[["fs_id", "fs_key", "fs_id_L1", "fs_id_L2"]].drop_duplicates("fs_id")
    bridge = bridge.merge(lineage, on="fs_id", how="left")
    bridge["fs_key"] = bridge["fs_key"].fillna(bridge["fs_id"].map(hash_key))
    for lineage_column in ("fs_id_L1", "fs_id_L2"):
        bridge[lineage_column] = bridge[lineage_column].fillna(bridge["fs_id"])
    # [3] uplift cell and mandatory cell
    bridge["gu"] = join_columns(bridge, cfg.grano_uplift)
    bridge["uplift_cell_key"] = (bridge["gu"] + "||" + bridge["comb_id"]).map(hash_key)
    bridge["celda_id"] = join_columns(bridge, cfg.business_mandatory_dims)
    # [4] labels and persistence
    labels = labeled_view.drop_duplicates("fs_id")[["fs_id", "universo", "ruta"]]
    bridge = bridge.merge(labels, on="fs_id", how="left")
    keep = ["fu_comb_key", "fu_id", "fu_key", "comb_id", "comb_key", "fs_id", "fs_key",
            "fs_id_L1", "fs_id_L2", "gu", "uplift_cell_key", "celda_id", "universo", "ruta"]
    return cfg.write(bridge[keep], "key_bridge")
