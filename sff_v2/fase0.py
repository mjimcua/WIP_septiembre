"""fase0.py — PHASE 0 · Contract, load, conditioning and reference (DISENO_V2 §5).

"Load, review, condition, and establish a reference to compare against." Not a single
datum is modified: the raw is immutable — label, never amputate (P4). Blocks:
  0.1 f0_load_and_validate    column contract + blocking validations
  0.2 f0_split_and_key        the two tables + hash keys + lookups + conservation
  0.3 f0_universe_routes      universe · coverage pattern · route (labels)
  0.4 f0_fu_summary           the immutable reference (binomial error at p=0.5)
"""
import numpy as np
import pandas as pd

from config import hash_key, join_columns


def f0_load_and_validate(raw: pd.DataFrame, cfg) -> pd.DataFrame:
    """GOAL: guarantee the raw is usable before computing anything; if any blocking
    check fails, stop with the full list of problems in hand.

    INPUT:  raw (every column of the SQL extract) · cfg (uses: validar_columnas,
            period_col, medidas, grano_tasa, extra_revalorizacion,
            renewed_*_col, dataset_role_col, current_month_col).
    OUTPUT: the same raw with `period` normalized to monthly Period. No new columns.
    STEPS:
      [1] Exhaustive contract: every column declared in a role, or exception (P3).
      [2] Normalize the period to monthly; one unparseable value = stop.
      [3] Money must be non-negative; a renewal with USD<=0 (zero uplift) is forbidden.
      [4] Nulls in dimensions = stop (an empty dimension breaks the ids).
      [5] Role census with an empty-role alarm (train/test/projection).
      [6] Detect the current month (truthy values).
      [7] CURRENT-MONTH DOCTRINE (change 2026-08-16, user-sealed): the running month
          belongs to PROJECTION — it is the FIRST month to project, never test.
          Projection cleansing: any renewal/reacquisition already booked in the
          current month OR in any projection month is wiped to NaN, so the future
          looks like it has not started yet. A summary of what was removed is
          printed. From this point on, THIS is the raw.
    """
    # [1] exhaustive column contract
    cfg.validar_columnas(raw)
    declared_count = len(raw.columns)
    # [2] period to monthly
    df = raw.copy()
    df[cfg.period_col] = pd.PeriodIndex(df[cfg.period_col].astype(str), freq="M")
    blocking_problems: list[str] = []
    # [3] money and uplift
    for money_column in (cfg.pipeline_units_col, cfg.pipeline_usd_col):
        if (df[money_column] < 0).any():
            blocking_problems.append(f"{money_column} has negative values")
    renewer_mask = df[cfg.renewed_units_col].fillna(0) > 0
    if (df.loc[renewer_mask, cfg.renewed_usd_col].fillna(0) <= 0).any():
        blocking_problems.append("renewal with USD<=0 (zero uplift forbidden: renewing for free does not exist)")
    # [4] nulls in dimensions
    dimension_columns = cfg.grano_tasa + cfg.extra_revalorizacion
    null_dimension_counts = {c: int(df[c].isna().sum())
                             for c in dimension_columns if df[c].isna().any()}
    if null_dimension_counts:
        blocking_problems.append(f"nulls in dimensions {null_dimension_counts} — "
                                 "an empty dimension breaks the ids")
    if blocking_problems:
        raise ValueError("f0_load_and_validate: " + "; ".join(blocking_problems))
    # [5] role census
    role_census = df[cfg.dataset_role_col].value_counts().to_dict()
    for expected_role in ("train", "test", "projection"):
        if role_census.get(expected_role, 0) == 0:
            print(f"[f0.1] ⚠ role '{expected_role}' is EMPTY in the raw: check the SQL labeling")
    # [6] current month (truthy) and its doctrine
    current_month_mask = (df[cfg.current_month_col].isin([1, True, "1", "true", "yes", "si"])
                          | (df[cfg.current_month_col] == 1))
    current_periods = sorted(df.loc[current_month_mask, cfg.period_col].astype(str).unique())
    # [7] current month → projection, and projection cleansing (wipe early results)
    reassigned_rows = int((current_month_mask
                           & (df[cfg.dataset_role_col] != "projection")).sum())
    df.loc[current_month_mask, cfg.dataset_role_col] = "projection"
    projection_mask = df[cfg.dataset_role_col] == "projection"
    wipe_columns = [c for c in (cfg.renewed_units_col, cfg.renewed_usd_col,
                                cfg.reacq_units_col, cfg.reacq_usd_col)
                    if c in df.columns]
    early_results = df.loc[projection_mask, wipe_columns].fillna(0)
    rows_with_early_results = int((early_results != 0).any(axis=1).sum())
    wiped_renewed_units = float(df.loc[projection_mask, cfg.renewed_units_col].fillna(0).sum())
    wiped_renewed_usd = float(df.loc[projection_mask, cfg.renewed_usd_col].fillna(0).sum())
    df.loc[projection_mask, wipe_columns] = np.nan
    final_role_census = df[cfg.dataset_role_col].value_counts().to_dict()
    print(f"[f0.1] contract ✓ {declared_count} columns declared · {len(df):,} rows")
    print(f"[f0.1] current month {current_periods} → PROJECTION ({reassigned_rows} rows "
          f"reassigned): it is the FIRST month to project, never test")
    print(f"[f0.1] projection cleansing: {rows_with_early_results} rows carried early "
          f"results — wiped {wiped_renewed_units:,.0f} renewed units / "
          f"${wiped_renewed_usd:,.0f} (reacquisitions included in the wipe)")
    print(f"[f0.1] roles after conditioning {final_role_census} · from here on, THIS is the raw")
    return df


def f0_split_and_key(df: pd.DataFrame, cfg):
    """GOAL: split the raw into the TWO tables of the design — the view at the rate
    grain (fewer rows, ratios coherent by construction) and the fine-grain table with
    the revaluation extras — with hash keys and exact money conservation.

    INPUT:  validated df (0.1) · cfg (uses: grano_tasa, extra_revalorizacion,
            period_col, dataset_role_col, current_month_col, flag_time_series_col,
            medidas).
    OUTPUT: (fu_view, fine_grain_table, fu_lookup, comb_lookup). New columns:
            fu_id/fu_key in both; comb_id/comb_key in the fine table.
    STEPS:
      [1] Fine table = raw copy + fu_id (rate_grain|month) + comb_id (extras) + hash keys.
      [2] View = aggregate by rate_grain×month: measures are SUMMED; ratios will be
          recomputed from the aggregate (never averages of averages).
      [3] Exact conservation: Σ$ of the fine table == Σ$ of the view, or stop.
      [4] fu_id must be unique in the view (a duplicate means the grain is misdeclared).
      [5] id↔key lookups so the keys can be used outside the framework.
    """
    rate_grain_columns = cfg.grano_tasa
    # [1] fine table with identities
    fine_grain_table = df.copy()
    fine_grain_table["fu_id"] = (join_columns(fine_grain_table, rate_grain_columns)
                                 + "|" + fine_grain_table[cfg.period_col].astype(str))
    fine_grain_table["comb_id"] = (join_columns(fine_grain_table, cfg.extra_revalorizacion)
                                   if cfg.extra_revalorizacion else "na")
    fine_grain_table["fu_key"] = fine_grain_table["fu_id"].map(hash_key)
    fine_grain_table["comb_key"] = fine_grain_table["comb_id"].map(hash_key)
    # single-column key so BI can join the raw anchor to the key bridge (1 relationship)
    fine_grain_table["fu_comb_key"] = (fine_grain_table["fu_id"] + "||"
                                       + fine_grain_table["comb_id"]).map(hash_key)
    # [2] view at the rate grain
    grouping_keys = rate_grain_columns + [cfg.period_col, cfg.dataset_role_col,
                                          cfg.current_month_col, cfg.flag_time_series_col]
    fu_view = (fine_grain_table.groupby(grouping_keys, as_index=False, observed=True)
               [cfg.medidas].sum(min_count=1))
    fu_view["fu_id"] = (join_columns(fu_view, rate_grain_columns)
                        + "|" + fu_view[cfg.period_col].astype(str))
    fu_view["fu_key"] = fu_view["fu_id"].map(hash_key)
    # [3] exact money conservation
    fine_total_usd = fine_grain_table[cfg.pipeline_usd_col].sum()
    view_total_usd = fu_view[cfg.pipeline_usd_col].sum()
    assert abs(view_total_usd - fine_total_usd) < 1e-6, (
        f"conservation BROKEN: fine ${fine_total_usd:,.2f} vs view ${view_total_usd:,.2f}")
    # [4] fu_id uniqueness in the view
    assert fu_view["fu_id"].is_unique, "duplicated fu_id in the view: grain misdeclared"
    # [5] lookups
    fu_lookup = fu_view[["fu_id", "fu_key"]].drop_duplicates()
    comb_lookup = fine_grain_table[["comb_id", "comb_key"]].drop_duplicates()
    print(f"[f0.2] fine {len(fine_grain_table):,} rows → view {len(fu_view):,} · "
          f"pipeline conserved ✓ (${view_total_usd:,.0f}) · "
          f"lookups: {len(fu_lookup)} fu · {len(comb_lookup)} combinations")
    return fu_view, fine_grain_table, fu_lookup, comb_lookup


def f0_universe_routes(fu_view: pd.DataFrame, cfg) -> pd.DataFrame:
    """GOAL: label every series with its universe, its temporal coverage pattern and
    its management ROUTE — deleting nothing (P4: label, never amputate).

    INPUT:  fu_view (0.2) · cfg (uses: flag_time_series_col, grano_tasa,
            dataset_role_col).
    OUTPUT: fu_view + columns `universo`, `fs_id`, `cobertura`, `ruta`.
    STEPS:
      [1] Universe: normal / time_series from the flag.
      [2] fs_id: the series = rate grain joined with '|'.
      [3] Coverage: which roles each series has (train_test_projection, train_only...).
      [4] Route: trainable (history+future) / heuristic (future without history) /
          no_impact (no projection: nothing to predict) — as a LABEL.
    """
    labeled_view = fu_view.copy()
    # [1] universe from the flag
    labeled_view["universo"] = np.where(labeled_view[cfg.flag_time_series_col] == 1,
                                        "time_series", "normal")
    # [2] series identity
    labeled_view["fs_id"] = join_columns(labeled_view, cfg.grano_tasa)
    # [3] coverage pattern per series
    coverage_by_series = (labeled_view.groupby("fs_id")[cfg.dataset_role_col]
                          .agg(lambda roles: "_".join(sorted(set(roles))))
                          .rename("cobertura"))
    labeled_view = labeled_view.merge(coverage_by_series, on="fs_id")
    # [4] management route
    def route_from_coverage(coverage_pattern: str) -> str:
        if "projection" not in coverage_pattern:
            return "no_impact"
        return "trainable" if "train" in coverage_pattern else "heuristic"
    labeled_view["ruta"] = labeled_view["cobertura"].map(route_from_coverage)
    route_census = labeled_view.drop_duplicates("fs_id")["ruta"].value_counts().to_dict()
    print(f"[f0.3] routes per series: {route_census} — no_impact is labeled, never dropped (P4)")
    return labeled_view


def f0_fu_summary(labeled_view: pd.DataFrame, cfg) -> pd.DataFrame:
    """GOAL: persist the IMMUTABLE REFERENCE — per forecast unit, how much support
    exists and what binomial error to expect in the worst case, before touching anything.

    INPUT:  labeled_view (0.3) · cfg (uses: pipeline_*_col, period_col,
            dataset_role_col, current_month_col, z, write).
    OUTPUT: persisted table `forecast_units_raw_summary` (fu_key, period, role,
            universe, route, support, se/moe in pp and $ at p=0.5).
    STEPS:
      [1] Select identity + context + support of each FU.
      [2] BOUND binomial error at p=0.5 (the honest worst case: no rate exists yet).
      [3] Translate it into dollars over the FU's own pipeline.
      [4] Persist (process_date + execution_id are automatic in write).
    """
    # [1] selection
    summary = labeled_view[["fu_key", "fu_id", cfg.period_col, cfg.dataset_role_col,
                            cfg.current_month_col, "universo", "ruta",
                            cfg.pipeline_units_col, cfg.pipeline_usd_col]].copy()
    # [2] binomial bound at p=0.5
    support_units = summary[cfg.pipeline_units_col].clip(lower=1)
    summary["se_pp_max"] = 100 * np.sqrt(.25 / support_units)
    summary["moe_pp_max"] = cfg.z * summary["se_pp_max"]
    # [3] the bound in dollars
    summary["moe_usd_max"] = summary["moe_pp_max"] / 100 * summary[cfg.pipeline_usd_col]
    summary[cfg.period_col] = summary[cfg.period_col].astype(str)
    # [4] persist
    return cfg.write(summary, "forecast_units_raw_summary")
