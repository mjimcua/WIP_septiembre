"""fase4_backtest.py — PHASE 4 · Backtest by horizon and technique selection.

Walk-forward with the current month EXCLUDED (incomplete test: out of method
selection). Long format (adding a technique = adding rows). Permanent challengers
T0/T2: a technique only wins where it beats them by more than the margin (CATALOG §3).
"""
import numpy as np
import pandas as pd

# ─── METHOD CONSTANTS ───
EWMA_HALFLIFE_MONTHS = 3.0
CHALLENGER_MARGIN_PP = 0.1
RECENT_WINDOW_MONTHS = 6
DAMPING_PHI = 0.90              # Holt damping: the trend must fade, never extrapolate forever
CROSTON_ZERO_SHARE = 0.30       # from this share of zero months on, the series is intermittent
BACKTEST_ORIGINS = 3            # walk-forward origins per horizon (1 origin = one lucky month)       # from this share of zero months on, the series is intermittent
ROLLING_MIN_HISTORY_MONTHS = 8   # minimum history required to have an opinion
ROLLING_HORIZONS = (1, 2, 3)     # next month, second and third


# ── técnicas (catálogo v1) ──────────────────────────────────────────
def _tecnicas(s, h, cfg):
    """GOAL: apply the catalog of eligible techniques to a rate series.
    INPUT:  s (Series period→rate, history ≤ origin) · h (horizon) · cfg (rate_cap).
    OUTPUT: dict tecnica_id → predicted rate (only techniques meeting eligibility).
    STEPS: [1] T0/T2/T4 always · [2] T1 if a same-month exists · [3] T7 with ≥13 months ·
           [4] T8 with ≥12, SATURATED at the cap · [5] T14 temporal credibility."""
    out = {}
    x = s.dropna()
    if not len(x): return out
    out["T0_naive"] = x.iloc[-1]
    out["T2_promedio"] = x.mean()
    w = np.exp(-np.arange(len(x))[::-1] / EWMA_HALFLIFE_MONTHS); out["T4_ewma"] = float(np.average(x, weights=w))
    tgt = x.index[-1] + h
    mm = x[x.index.month == tgt.month]
    if len(mm): out["T1_naive_estacional"] = mm.iloc[-1]
    if len(x) >= 13:
        idx = x.groupby(x.index.month).mean(); nivel = x.iloc[-6:].mean()
        out["T7_indice_estacional"] = nivel * idx.get(tgt.month, idx.mean()) / idx.mean()
    if len(x) >= 12:
        t = np.arange(len(x)); b, a = np.polyfit(t, x.values, 1)
        out["T8_tendencia_sat"] = min(cfg.rate_cap, max(0.01, a + b * (len(x) - 1 + h)))
    rec = x.iloc[-RECENT_WINDOW_MONTHS:].mean()
    recent_months_count = RECENT_WINDOW_MONTHS
    z = recent_months_count / (recent_months_count + RECENT_WINDOW_MONTHS)
    out["T14_credibilidad_t"] = z * rec + (1 - z) * x.mean()
    # [6] T3 moving averages: the cheapest way to buy sample size from the past
    if len(x) >= 3: out["T3_media_movil_3"] = x.iloc[-3:].mean()
    if len(x) >= 6: out["T3_media_movil_6"] = x.iloc[-6:].mean()
    # [7] T5 drift: last value plus the average step (needs saturation like T8)
    if len(x) >= 6:
        drift_per_month = (x.iloc[-1] - x.iloc[0]) / max(len(x) - 1, 1)
        out["T5_drift"] = min(cfg.rate_cap, max(0.01, x.iloc[-1] + drift_per_month * h))
    # [8] T6 same-month mean across years: stable seasonality, hungry for history
    if len(x) >= 24:
        same_month = x[x.index.month == (x.index[-1] + h).month]
        if len(same_month) >= 2: out["T6_promedio_mismo_mes"] = same_month.mean()
    # [9] T9 SES: adaptive level, alpha chosen by in-sample error
    if len(x) >= 6:
        best_alpha, best_error = None, np.inf
        for alpha in (0.1, 0.2, 0.3, 0.5, 0.7):
            level, errors = x.iloc[0], []
            for value in x.iloc[1:]:
                errors.append(abs(value - level)); level = alpha * value + (1 - alpha) * level
            mean_error = float(np.mean(errors)) if errors else np.inf
            if mean_error < best_error: best_alpha, best_error, best_level = alpha, mean_error, level
        out["T9_ses"] = best_level
    # [10] T10 damped Holt: level + trend that fades with the horizon
    if len(x) >= 18:
        alpha, beta, phi = 0.3, 0.1, DAMPING_PHI
        level, trend = x.iloc[0], x.iloc[1] - x.iloc[0]
        for value in x.iloc[1:]:
            previous_level = level
            level = alpha * value + (1 - alpha) * (level + phi * trend)
            trend = beta * (level - previous_level) + (1 - beta) * phi * trend
        damped_sum = sum(phi ** i for i in range(1, h + 1))
        out["T10_holt_damped"] = min(cfg.rate_cap, max(0.01, level + damped_sum * trend))
    # [11] T11 Holt-Winters (additive seasonality): the priority technique when
    #      history allows it — it REPORTS level, trend and season (free flags)
    if len(x) >= 24:
        season_index = x.groupby(x.index.month).mean() - x.mean()
        deseasonalized = x - x.index.month.map(season_index).values
        alpha, beta, phi = 0.3, 0.1, DAMPING_PHI
        level, trend = deseasonalized.iloc[0], 0.0
        for value in deseasonalized.iloc[1:]:
            previous_level = level
            level = alpha * value + (1 - alpha) * (level + phi * trend)
            trend = beta * (level - previous_level) + (1 - beta) * phi * trend
        target_month = (x.index[-1] + h).month
        damped_sum = sum(phi ** i for i in range(1, h + 1))
        out["T11_holt_winters"] = min(cfg.rate_cap, max(0.01,
            level + damped_sum * trend + float(season_index.get(target_month, 0.0))))
    # [12] T13 Croston-style for intermittent series: separate "is there anything"
    #      from "how much" — a niche that survives the support repair
    zero_share = float((x == 0).mean())
    if zero_share >= CROSTON_ZERO_SHARE and (x > 0).any():
        out["T13_croston"] = float(x[x > 0].mean() * (1 - zero_share))
    return out

def f4_backtest(v2, series_estimates, cfg, horizontes=(1, 2, 3, 4)):
    """GOAL: the judge — walk-forward by horizon with the current month OUT, in long
    format (adding a technique = adding rows), and a champion per series.
    INPUT:  fu_view with L2 · series_estimates · cfg.
    OUTPUT: backtest_long (`backtest_predictions`), technique_selection
            (`forecast_final_seleccion`), rate_series_by_pool (for reuse).
    STEPS:
      [1] Exclude the current month (incomplete test) from the judge's history.
      [2] Monthly series per L2 pool with minimum eligibility.
      [3] SEVERAL origins per horizon (BACKTEST_ORIGINS): each technique's prediction
          vs what happened — one origin alone is one lucky month, not evidence.
      [4] Champion per series: best mean that ALSO beats T0/T2 by the margin;
          otherwise the average wins (the cheap challenger)."""
    current_month_periods = set(v2.loc[v2[cfg.current_month_col].isin([1, True, "1"]), cfg.period_col].astype(str))
    history_rows = v2[(v2["universo"] == "normal") & v2["tasa"].notna()
              & ~v2[cfg.period_col].astype(str).isin(current_month_periods)]   # mes en curso FUERA del backtest
    if current_month_periods: print(f"[f4] current month excluded from the backtest: {sorted(current_month_periods)}")
    rate_series_by_pool = {}
    # [2] per-pool series with eligibility
    for l2, sub in history_rows.groupby("fs_id_L2"):
        agg = sub.groupby(cfg.period_col).apply(lambda x: (x[cfg.renewed_units_col].sum(), x[cfg.pipeline_units_col].sum()), include_groups=False)
        s = pd.Series({m: r / max(p, 1) for m, (r, p) in agg.items()}).sort_index()
        n = sub.groupby(cfg.period_col)[cfg.pipeline_units_col].sum().median()
        if len(s) >= 10 and n >= cfg.support_floor / 2: rate_series_by_pool[l2] = s
    collected_rows = []
    # [3] one origin per horizon
    for l2, s in rate_series_by_pool.items():
        for h in horizontes:
            # several origins per horizon: one origin is one lucky (or unlucky) month
            for origin_offset in range(BACKTEST_ORIGINS):
                target_position = len(s) - 1 - origin_offset
                origin_position = target_position - h
                if origin_position < 8 or target_position < 0:
                    continue
                base = s.iloc[:origin_position + 1]
                real = s.iloc[target_position]
                if not np.isfinite(real):
                    continue
                for tec, pred in _tecnicas(base, h, cfg).items():
                    collected_rows.append(dict(fs_id_L2=l2, tecnica=tec, h=h,
                        origen=str(s.index[origin_position]), mes_objetivo=str(s.index[target_position]),
                        pred=round(float(pred), 4), real=round(float(real), 4),
                        abs_err_pp=100 * abs(pred - real)))
    backtest_long = pd.DataFrame(collected_rows); cfg.write(backtest_long, "backtest_predictions")
    lb = backtest_long.groupby("tecnica")["abs_err_pp"].mean().sort_values()
    print("[f4] leaderboard (mean |err| pp):")
    for technique_name, mean_abs_error in lb.items():
        print(f"   {technique_name:22s} {mean_abs_error:5.2f}")
    # campeón por serie: mejor media, debe batir a T2 y T0 por >0.1pp
    # [4] champion with challengers
    champion_by_series = {}
    for l2, sub in backtest_long.groupby("fs_id_L2"):
        m = sub.groupby("tecnica")["abs_err_pp"].mean()
        ret = min(m.get("T2_promedio", 99), m.get("T0_naive", 99))
        best = m.idxmin()
        champion_by_series[l2] = best if m[best] < ret - CHALLENGER_MARGIN_PP else "T2_promedio"
    technique_selection = pd.DataFrame({"fs_id_L2": list(champion_by_series), "tecnica_elegida": list(champion_by_series.values())})
    technique_selection = technique_selection.merge(backtest_long.groupby(["fs_id_L2", "tecnica"])["abs_err_pp"].mean().rename("err_bt").reset_index(),
                    left_on=["fs_id_L2", "tecnica_elegida"], right_on=["fs_id_L2", "tecnica"], how="left")
    cfg.write(technique_selection[["fs_id_L2", "tecnica_elegida", "err_bt"]], "forecast_final_seleccion")
    print(f"[f4] champions: {technique_selection['tecnica_elegida'].value_counts().to_dict()}")
    return backtest_long, technique_selection, rate_series_by_pool

DIM_TECNICA = [
    ("T0_naive", "naive", "último mes observado", "1 mes"),
    ("T1_naive_estacional", "estacional", "mismo mes del año anterior", "13 meses"),
    ("T2_promedio", "promedio", "media de toda la historia", "3 meses"),
    ("T4_ewma", "recencia", "media con pesos decrecientes (hl=3)", "3 meses"),
    ("T7_indice_estacional", "estacional", "nivel reciente × índice mensual", "13 meses"),
    ("T8_tendencia_sat", "tendencia", "regresión temporal saturada al techo", "12 meses"),
    ("T14_credibilidad_t", "credibilidad", "z·reciente + (1−z)·histórico", "6 meses"),
    ("T3_media_movil_3", "promedio", "media de los últimos 3 meses", "3 meses"),
    ("T3_media_movil_6", "promedio", "media de los últimos 6 meses", "6 meses"),
    ("T5_drift", "tendencia", "último valor + paso medio, saturado", "6 meses"),
    ("T6_promedio_mismo_mes", "estacional", "media del mismo mes en varios años", "24 meses"),
    ("T9_ses", "recencia", "suavizado exponencial simple, alpha ajustada", "6 meses"),
    ("T10_holt_damped", "tendencia", "nivel + tendencia amortiguada", "18 meses"),
    ("T11_holt_winters", "estacional", "nivel + tendencia + estación (reporta los tres)", "24 meses"),
    ("T13_croston", "intermitente", "separa ocurrencia de magnitud", "series con ceros"),
]

def f4_tablas_fu(v2, fine_grain_table, series_estimates, uplift_cells, backtest_long, rate_series_by_pool, cfg):
    """GOAL: dim_tecnica (master) + per-FU stamping: backtest_predictions_fu (with error, reserved months)
    and forecast_predictions_fu (projection × technique: band, no error).
    STEPS: [1] dim_tecnica (master) · [2] backtest stamped per member FU with its own
    actual and its error in $ (P5) · [3] forecast per future FU: technique × its own
    horizon, with its combination's uplift — no error column, because no truth exists there yet."""
    import pandas as pd, numpy as np
    technique_dim = pd.DataFrame(DIM_TECNICA, columns=["tecnica_id", "familia", "descripcion", "elegibilidad_min"])
    cfg.write(technique_dim, "dim_tecnica")
    # backtest por FU: la pred del pool estampada en cada FU miembro del mes target_period, error vs SU real
    collected_rows = []
    history_rows = v2[(v2["universo"] == "normal") & v2["tasa"].notna()]
    for l2, s in rate_series_by_pool.items():
        target_period = s.index[-1]
        member_rows = history_rows[(history_rows["fs_id_L2"] == l2) & (history_rows[cfg.period_col] == target_period)]
        for _, r in backtest_long[backtest_long["fs_id_L2"] == l2].iterrows():
            for _, m in member_rows.iterrows():
                collected_rows.append(dict(fu_key=m["fu_key"], fs_id=m["fs_id"], fs_id_L2=l2,
                    period=str(target_period), h=r["h"], tecnica_id=r["tecnica"],
                    tasa_pred=r["pred"], tasa_real_fu=round(float(m["tasa"]), 4),
                    abs_err_pp=round(100 * abs(r["pred"] - m["tasa"]), 2),
                    err_usd=round(abs(r["pred"] - m["tasa"]) * m[cfg.pipeline_usd_col], 2)))
    backtest_per_fu = pd.DataFrame(collected_rows); cfg.write(backtest_per_fu, "backtest_predictions_fu")
    # per-FU forecast on projection: every technique at its own horizon + its combination uplift → $
    uplift_lookup = uplift_cells.set_index(["uplift_cells", "comb_id"])["uplift_final"]
    future_rows = fine_grain_table[fine_grain_table[cfg.dataset_role_col] == "projection"].copy()
    future_rows["fs_id"] = future_rows[cfg.grano_tasa].astype(str).agg("|".join, axis=1)
    future_rows["uplift_cells"] = future_rows[cfg.grano_uplift].astype(str).agg("|".join, axis=1)
    l2map = series_estimates.set_index("fs_id")["fs_id_L2"]
    collected_rows = []
    for _, r in future_rows.iterrows():
        l2 = l2map.get(r["fs_id"]);  s = rate_series_by_pool.get(l2)
        if s is None: continue
        h = (r[cfg.period_col] - s.index[-1]).n
        u = float(uplift_lookup.get((r["uplift_cells"], r["comb_id"]), 1.0))
        for tec, pred in _tecnicas(s, h, cfg).items():
            pred = min(pred, cfg.rate_cap)
            collected_rows.append(dict(fu_key=r["fu_key"], fs_id=r["fs_id"], fs_id_L2=l2,
                period=str(r[cfg.period_col]), h=h, tecnica_id=tec,
                tasa_pred=round(float(pred), 4), uplift_pred=round(u, 3),
                forecast_usd=round(float(r[cfg.pipeline_usd_col] * pred * u), 2)))
    forecast_per_fu = pd.DataFrame(collected_rows); cfg.write(forecast_per_fu, "forecast_predictions_fu")
    print(f"[f4+] dim_tecnica {len(technique_dim)} · backtest_fu {len(backtest_per_fu)} collected_rows · forecast_fu {len(forecast_per_fu)} collected_rows ({forecast_per_fu['fu_key'].nunique()} FUs × técnicas × h)")
    return technique_dim, backtest_per_fu, forecast_per_fu


def f4_rolling_next_month(v2: "pd.DataFrame", cfg) -> "pd.DataFrame":
    """FASE 4b · Fiabilidad a MES SIGUIENTE (origen móvil, h=1) — 'the other tool'. Horizons 1, 2 and 3; the current month is excluded twice over (neither target nor history).

    INPUT:  view with L2 pools and rates; config.
    OUTPUT: tables `rolling_next_month` (target month × pool × technique: pred, actual,
            errors) and `rolling_next_month_resumen` (per technique: unit WAPE,
            pipeline-weighted pp error, and COVERAGE = % of predictions whose error
            falls inside their own binomial bound).
    RULES:  (1) for every month t with truth, history is EVERYTHING before t;
            (2) the current month is out both as target and as history;
            (3) at least ROLLING_MIN_HISTORY_MONTHS of history to predict;
            (4) each pool-month bound is z·√(p(1−p)/n_pool_month)·100.
    EDGES:  pools without enough months stay silent; no targets → empty tables.
    LOGGING: process_date + execution_id via config.write."""
    # [1] current month out
    current_periods = set(v2.loc[v2[cfg.current_month_col].isin([1, True, "1"]),
                                 cfg.period_col].astype(str))
    history_rows = v2[(v2["universo"] == "normal") & v2["tasa"].notna()
                      & ~v2[cfg.period_col].astype(str).isin(current_periods)]
    collected_rows = []
    for pool_id, pool_rows in history_rows.groupby("fs_id_L2"):
        monthly = pool_rows.groupby(cfg.period_col).agg(
            renewed=(cfg.renewed_units_col, "sum"),
            pipeline=(cfg.pipeline_units_col, "sum"))
        monthly["rate"] = monthly["renewed"] / monthly["pipeline"].clip(lower=1)
        rate_series = monthly["rate"].sort_index()
        for horizon in ROLLING_HORIZONS:
          for position in range(ROLLING_MIN_HISTORY_MONTHS + horizon - 1, len(rate_series)):
            target_period = rate_series.index[position]
            # the origin recedes h months: to predict t at h=3, history ends at t−3
            history_slice = rate_series.iloc[:position - horizon + 1]
            actual_rate = rate_series.iloc[position]
            pipeline_units = monthly.loc[target_period, "pipeline"]
            binomial_bound_pp = cfg.z * 100 * (max(actual_rate * (1 - actual_rate), .0025)
                                               / max(pipeline_units, 1)) ** 0.5
            for technique_id, predicted_rate in _tecnicas(history_slice, horizon, cfg).items():
                error_pp = 100 * abs(predicted_rate - actual_rate)
                collected_rows.append(dict(
                    fs_id_L2=pool_id, mes_objetivo=str(target_period), h=horizon,
                    tecnica_id=technique_id,
                    tasa_pred=round(float(predicted_rate), 4),
                    tasa_real=round(float(actual_rate), 4),
                    abs_err_pp=round(error_pp, 2),
                    err_units=round(abs(predicted_rate - actual_rate) * pipeline_units, 1),
                    pipeline_units=pipeline_units,
                    dentro_de_cota=int(error_pp <= binomial_bound_pp)))
    rolling_table = pd.DataFrame(collected_rows)
    cfg.write(rolling_table, "rolling_next_month")
    summary = rolling_table.groupby(["tecnica_id", "h"]).apply(lambda block: pd.Series({
        "wape_units_pct": 100 * block["err_units"].sum()
                          / max((block["tasa_real"] * block["pipeline_units"]).sum(), 1),
        "err_pp_ponderado": np.average(block["abs_err_pp"], weights=block["pipeline_units"]),
        "cobertura_cota_pct": 100 * block["dentro_de_cota"].mean(),
        "n_predicciones": len(block)}), include_groups=False).reset_index()
    cfg.write(summary, "rolling_next_month_resumen")
    for horizon in ROLLING_HORIZONS:
        best = summary[summary["h"] == horizon].sort_values("err_pp_ponderado").iloc[0]
        print(f"[f4b] h={horizon} — best: {best['tecnica_id']:20s} · "
              f"error {best['err_pp_ponderado']:.2f}pp · WAPE {best['wape_units_pct']:.1f}% · "
              f"{best['cobertura_cota_pct']:.0f}% inside their bound ({int(best['n_predicciones'])} pred.)")
    return rolling_table, summary


def f4_forecast_bands(future_rows, rolling_table, technique_selection, series_estimates,
                      rate_series_by_pool, cfg):
    """PHASE 4c · Empirical bands on the final forecast (rung 4 of the band ladder).

    GOAL: put a band on every forecast row that comes from MEASURED error, not theory:
    the distribution of the chosen technique's own errors at that horizon.

    INPUT:  future_rows (3, with fs_id and expected $) · rolling_table (4b, walk-forward
            errors per technique and horizon) · technique_selection (4) · series
            estimates (for the L2 lineage) · rate_series_by_pool (last history month) · cfg.
    OUTPUT: persisted `forecast_bands` (fu_key, pool, technique, h, empirical band in pp
            and $, and the fallback flag) + portfolio band by quadrature on the console.
    STEPS:
      [1] Empirical band per (technique, h): the 90th percentile of |error| observed in
          the rolling walk-forward — the honest yardstick, no distributional assumption.
      [2] Each future row: its pool, its chosen technique, and its own horizon h
          (months from the pool's last month with truth).
      [3] Look up the band; if that pair was never measured, fall back to the binomial
          bound of the row (flagged, never silent).
      [4] Band in dollars = band_pp/100 × pipeline$ × uplift; portfolio band in
          QUADRATURE (independent errors add in variance, not in absolute value).
    """
    # [1] measured band per technique and horizon
    if len(rolling_table):
        empirical = (rolling_table.groupby(["tecnica_id", "h"])["abs_err_pp"]
                     .quantile(0.90).rename("banda_pp").reset_index())
        band_lookup = {(r["tecnica_id"], r["h"]): r["banda_pp"] for _, r in empirical.iterrows()}
    else:
        band_lookup = {}
    champion_by_pool = dict(zip(technique_selection["fs_id_L2"],
                                technique_selection["tecnica_elegida"]))
    pool_of_series = dict(zip(series_estimates["fs_id"], series_estimates["fs_id_L2"]))
    last_month_of_pool = {pool: series.index[-1] for pool, series in rate_series_by_pool.items()}
    # a series with no history of its own still lives on a calendar: use the newest month
    # with truth in the whole run as its reference, so its horizon is real, never 1 by default
    global_last_month = max(last_month_of_pool.values()) if last_month_of_pool else None
    collected_rows = []
    for _, row in future_rows.iterrows():
        # [2] pool, technique and this row's own horizon
        pool_id = pool_of_series.get(row["fs_id"], row["fs_id"])
        technique = champion_by_pool.get(pool_id, "T2_promedio")
        last_month = last_month_of_pool.get(pool_id, global_last_month)
        horizon = (int((row[cfg.period_col] - last_month).n)
                   if last_month is not None else 1)
        # [3] measured band, or the binomial bound as a flagged fallback
        band_pp = band_lookup.get((technique, horizon))
        fallback = 0
        if band_pp is None:
            support_units = max(float(row[cfg.pipeline_units_col]), 1.0)
            band_pp = cfg.z * 100 * (0.25 / support_units) ** 0.5
            fallback = 1
        # [4] into dollars
        band_usd = band_pp / 100 * float(row[cfg.pipeline_usd_col]) * float(row["uplift"])
        collected_rows.append(dict(fu_key=row["fu_key"], comb_key=row["comb_key"],
            fs_id_L2=pool_id, tecnica_id=technique, h=horizon,
            banda_pp=round(float(band_pp), 2), banda_usd=round(band_usd, 2),
            esperado_usd=round(float(row["esperado_usd"]), 2), banda_fallback=fallback))
    forecast_bands = pd.DataFrame(collected_rows)
    cfg.write(forecast_bands, "forecast_bands")
    if len(forecast_bands):
        total_expected = forecast_bands["esperado_usd"].sum()
        portfolio_band = float(np.sqrt((forecast_bands["banda_usd"] ** 2).sum()))
        measured_share = 1 - forecast_bands["banda_fallback"].mean()
        print(f"[f4c] forecast ${total_expected:,.0f} ± ${portfolio_band:,.0f} "
              f"({portfolio_band / max(total_expected, 1):.1%} at 90%, quadrature) · "
              f"{measured_share:.0%} of rows use a MEASURED band, the rest the binomial bound")
    return forecast_bands


def f4_horizon_report(rolling_table, technique_selection, forecast_bands, future_rows, cfg):
    """PHASE 4d · How well do we predict month 1, month 2, month 3 — and how fast does
    it degrade? Per forecast series AND for the whole portfolio.

    GOAL: answer the business question "how sure am I about the FIRST projected month,
    and how much do I lose each month further out", using the error of the technique
    that was ACTUALLY chosen for each pool — not the average of all techniques.

    INPUT:  rolling_table (4b) · technique_selection (4) · forecast_bands (4c) ·
            future_rows (3) · cfg.
    OUTPUT: `horizon_report_series` (pool × h: chosen technique, mean error, p90 band,
            coverage, degradation vs h=1) and `horizon_report_total` (h and projected
            month: expected $, band $ in quadrature, $-weighted error, degradation).
    STEPS:
      [1] Keep, for every pool, only the rolling rows of ITS champion technique.
      [2] Per pool and horizon: mean |error|, p90 (the band), coverage of its own
          bound, and how many predictions back it.
      [3] Degradation per pool: error at h minus error at h=1 — the cost of distance.
      [4] Portfolio: attach the projected month to every forecast row, then per month
          sum the expected $, combine bands in QUADRATURE, and weight the pool error
          by money — plus the same degradation reading at portfolio level.
    """
    if not len(rolling_table) or not len(technique_selection):
        return pd.DataFrame(), pd.DataFrame()
    # [1] each pool judged by its own champion
    champions = technique_selection[["fs_id_L2", "tecnica_elegida"]]
    champion_rows = rolling_table.merge(champions, on="fs_id_L2")
    champion_rows = champion_rows[champion_rows["tecnica_id"] == champion_rows["tecnica_elegida"]]
    # [2] per pool and horizon
    per_series = champion_rows.groupby(["fs_id_L2", "tecnica_elegida", "h"]).agg(
        n_predicciones=("abs_err_pp", "size"),
        err_pp_medio=("abs_err_pp", "mean"),
        err_pp_p90=("abs_err_pp", lambda errors: errors.quantile(0.90)),
        cobertura_cota_pct=("dentro_de_cota", lambda flags: 100 * flags.mean())).reset_index()
    # [3] degradation against the first month
    first_horizon = (per_series[per_series["h"] == 1]
                     .set_index("fs_id_L2")["err_pp_medio"].to_dict())
    per_series["err_pp_h1"] = per_series["fs_id_L2"].map(first_horizon)
    per_series["degradacion_pp"] = (per_series["err_pp_medio"] - per_series["err_pp_h1"]).round(2)
    per_series["err_pp_medio"] = per_series["err_pp_medio"].round(2)
    per_series["err_pp_p90"] = per_series["err_pp_p90"].round(2)
    per_series["cobertura_cota_pct"] = per_series["cobertura_cota_pct"].round(0)
    cfg.write(per_series.drop(columns=["err_pp_h1"]), "horizon_report_series")
    # [4] portfolio: money by projected month, bands in quadrature
    months = future_rows[["fu_key", "comb_key", cfg.period_col]].copy()
    months[cfg.period_col] = months[cfg.period_col].astype(str)
    priced = forecast_bands.merge(months, on=["fu_key", "comb_key"], how="left")
    pool_error = per_series.set_index(["fs_id_L2", "h"])["err_pp_medio"].to_dict()
    priced["err_pp_pool"] = [pool_error.get((pool, horizon), np.nan)
                             for pool, horizon in zip(priced["fs_id_L2"], priced["h"])]
    total_rows = []
    for (horizon, month), block in priced.groupby(["h", cfg.period_col]):
        expected = float(block["esperado_usd"].sum())
        band_usd = float(np.sqrt((block["banda_usd"] ** 2).sum()))
        weighted_error = (np.average(block["err_pp_pool"].fillna(block["banda_pp"]),
                                     weights=block["esperado_usd"].clip(lower=0.01))
                          if len(block) else np.nan)
        total_rows.append(dict(h=horizon, mes_proyectado=month,
            esperado_usd=round(expected, 2), banda_usd=round(band_usd, 2),
            banda_pct=round(100 * band_usd / max(expected, 1), 2),
            err_pp_ponderado=round(float(weighted_error), 2),
            filas=len(block), pct_banda_medida=round(100 * (1 - block["banda_fallback"].mean()), 0)))
    horizon_total = pd.DataFrame(total_rows).sort_values(["h", "mes_proyectado"])
    if len(horizon_total):
        first_band_pct = horizon_total.iloc[0]["banda_pct"]
        horizon_total["degradacion_vs_h1_pct"] = (horizon_total["banda_pct"] - first_band_pct).round(2)
    cfg.write(horizon_total, "horizon_report_total")
    print("[f4d] HORIZON REPORT — how the forecast degrades month by month:")
    for _, row in horizon_total.iterrows():
        print(f"   h={int(row['h'])} ({row['mes_proyectado']}): ${row['esperado_usd']:>12,.0f} "
              f"± ${row['banda_usd']:>10,.0f} ({row['banda_pct']:>5.2f}%) · "
              f"error medio de la técnica elegida {row['err_pp_ponderado']:>5.2f}pp · "
              f"banda medida en {row['pct_banda_medida']:.0f}% de las filas")
    return per_series, horizon_total
