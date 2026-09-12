"""fase1.py — PHASE 1 · Renewal branch: the binomial path (DISENO_V2 §6).

  1.1 f1_series_and_gaps      fs_id/fs_key · gaps→synthetic rows (legitimate 0) · summary
  1.2 f1_diagnose_round1      binomial photo · Simpson (counterfactual $) · ANOVA · pairs
  1.3 f1_improve_support      L1 by SIGN · L2 asterisk · credibility z=n/(n+k)
  1.4 f1_support_chain        waterfall of money below the floor, stage by stage
  1.5 f1_diagnose_round2      history, dynamics and overdispersion phi ON the consolidated base (P9)
"""
import numpy as np
import pandas as pd

# ─── METHOD CONSTANTS ───
COUNTERFACTUAL_WINDOW_MONTHS = 6      # months with truth used by the walk-forward
MIN_HISTORY_FOR_COUNTERFACTUAL = 6    # a cell needs this much past to be judged
MIN_MONTHS_FOR_SEASONALITY = 13       # one full yearly cycle before talking about seasons

from config import hash_key, join_columns

def _build_collapse_order(mandatory_dims: list, eta2_by_dim: dict) -> list:
    """GOAL: the order in which mandatory dims collapse when climbing the parent ladder.
    RULES: (1) inside a family (`x_level_1/2/3`), the FINEST level falls first — the
    hierarchy already answers this and asking ANOVA would be redundant; (2) between
    families, the EVIDENCE decides: whichever droppable dim separates least (lowest η²)
    goes first; (3) a dim is droppable only once every deeper level of its family is gone."""
    def family_and_level(dim_name):
        if "_level_" in dim_name:
            head, _, tail = dim_name.rpartition("_level_")
            if tail.isdigit():
                return head, int(tail)
        return dim_name, 1
    pending = list(mandatory_dims)
    order = []
    while pending:
        droppable = []
        for dim in pending:
            family, level = family_and_level(dim)
            deeper_left = any(family_and_level(other) == (family, level + 1) for other in pending)
            if not deeper_left:
                droppable.append(dim)
        next_dim = min(droppable, key=lambda d: (eta2_by_dim.get(d, 0.0), d))
        order.append(next_dim); pending.remove(next_dim)
    return order


def _act(v, cfg): return v.isin(cfg.timevarying_positive_values)

def f1_series_and_gaps(v, cfg):
    """GOAL: create the forecast-series concept and make the FIRST improvement of the
    data — filling gaps with legitimate zeros — leaving the per-series summary.

    INPUT:  labeled fu_view (0.3) · cfg (grain, measures, roles, z, write).
    OUTPUT: fu_view + fs_key + synthetic rows + `tasa` column (null≠zero) and table
            `forecast_series_raw_summary` (support, history, gaps, moe in $).
    STEPS:
      [1] fs_key = hash of fs_id; `sintetica` flag = 0 on everything real.
      [2] Gaps: only trainable series, only INSIDE their history; the synthetic row
          carries measures at 0 (an empty month is a legitimate zero) and the role
          inherited from the previous real month; its fu_id/fu_key are born here.
      [3] Per-row rate with null≠zero discipline: NaN on projection and on real
          pipeline 0; 0.0 on synthetic rows.
      [4] Per-series summary: support = monthly median of REAL units; gaps counted;
          historical rate with its se and its moe translated into projection $.
      [5] Persist the summary."""
    # [1] series identity and imputation flag
    v = v.copy()
    v["fs_key"] = v["fs_id"].map(hash_key)
    v["sintetica"] = 0
    collected_rows = []
    # [2] gap filling inside the trainable history
    for fs, sub in v[v["universo"] == "normal"].groupby("fs_id"):
        if sub["ruta"].iat[0] != "trainable": continue
        history_rows = sub[sub[cfg.dataset_role_col] != "projection"]
        rango = pd.period_range(history_rows[cfg.period_col].min(), history_rows[cfg.period_col].max(), freq="M")
        falta = rango.difference(pd.PeriodIndex(history_rows[cfg.period_col]))
        for m in falta:
            f = sub.iloc[0].copy(); f[cfg.period_col] = m
            prev = history_rows[history_rows[cfg.period_col] < m]
            f[cfg.dataset_role_col] = prev[cfg.dataset_role_col].iloc[-1] if len(prev) else "train"
            for c in cfg.medidas: f[c] = 0.0
            f[cfg.current_month_col] = 0; f["sintetica"] = 1
            f["fu_id"] = fs + "|" + str(m); f["fu_key"] = hash_key(f["fu_id"])
            collected_rows.append(f)
    if collected_rows: v = pd.concat([v, pd.DataFrame(collected_rows)], ignore_index=True)
    # [3] rate with null≠zero discipline
    gap_rate_value = 0.0 if cfg.gap_rate_policy == "zero_rate" else np.nan
    v["tasa"] = np.where(v["sintetica"] == 1, gap_rate_value,
                np.where(v[cfg.pipeline_units_col] > 0, v[cfg.renewed_units_col] / v[cfg.pipeline_units_col], np.nan))
    v.loc[v[cfg.dataset_role_col] == "projection", "tasa"] = np.nan
    # summary por serie
    # [4] per-series summary over train∪test
    history_rows = v[(v["universo"] == "normal") & (v[cfg.dataset_role_col] != "projection")]
    series_summary = history_rows.groupby(["fs_id", "fs_key"], as_index=False).agg(
        n_avg=(cfg.pipeline_units_col, lambda s: s[s > 0].median() if (s > 0).any() else 0),
        meses=("sintetica", "size"), huecos=("sintetica", "sum"),
        ren=(cfg.renewed_units_col, "sum"), pipe=(cfg.pipeline_units_col, "sum"))
    series_summary["tasa_hist"] = series_summary["ren"] / series_summary["pipe"].clip(lower=1)
    series_summary["se_pp"] = 100 * np.sqrt((series_summary["tasa_hist"] * (1 - series_summary["tasa_hist"])).clip(lower=.0025) / series_summary["n_avg"].clip(lower=1))
    proj = v[v[cfg.dataset_role_col] == "projection"].groupby("fs_key")[cfg.pipeline_usd_col].sum().rename("usd_proj")
    series_summary = series_summary.merge(proj, on="fs_key", how="left").fillna({"usd_proj": 0})
    series_summary["moe_usd"] = cfg.z * series_summary["se_pp"] / 100 * series_summary["usd_proj"]
    # [5] persist
    cfg.write(series_summary.assign(), "forecast_series_raw_summary")
    print(f"[f1.1] {len(series_summary)} series · synthetic rows added {int(v['sintetica'].sum())} "
          f"(gap policy '{cfg.gap_rate_policy}': " + ("rate 0%" if cfg.gap_rate_policy == "zero_rate" else "rate undefined — a month with no expirations is not a 0% month") + ")")
    return v, series_summary

def _eta2_w(df, technique_dim, val, w):
    m = np.average(df[val], weights=df[w]); sst = np.sum(df[w] * (df[val] - m) ** 2)
    if sst <= 0: return 0.0
    ssb = sum(np.sum(sub[w]) * (np.average(sub[val], weights=sub[w]) - m) ** 2
              for _, sub in df.groupby(technique_dim, observed=True))
    return float(ssb / sst)

def f1_diagnose_round1(v, series_summary, cfg):
    """GOAL: round-1 diagnosis — what can be measured HONESTLY on the raw data:
    support, Simpson in dollars, and evidence of what separates behavior.

    INPUT:  fu_view with rate (1.1) + series_summary · cfg (mandatory, extras,
            timevarying, support_floor, write).
    OUTPUT: eta2_by_dim, eta2_pairs, persisted table `simpson_contrafactual`.
    STEPS:
      [1] Binomial photo: how much money lives in series below the floor.
      [2] Simpson counterfactual in $: walk-forward over the last months with
          truth — flat method vs segmented (rates ≤t−1 × real weights of t),
          both against what happened; the saving is the headline figure.
      [3] Weighted ANOVA (η², weights=support) per dimension, WITHOUT timevarying.
      [4] Combinations: η² of pairs vs individuals — the interaction."""
    # [1] binomial photo
    bajo = series_summary[series_summary["n_avg"] < cfg.support_floor]
    print(f"[f1.2] binomial photo: {len(bajo)}/{len(series_summary)} series below the floor · ${bajo['usd_proj'].sum():,.0f} of ${series_summary['usd_proj'].sum():,.0f} with no right to speak alone")
    history_rows = v[(v["universo"] == "normal") & v["tasa"].notna() & (v["sintetica"] == 0)].copy()
    history_rows["mandatory_cell"] = join_columns(history_rows, cfg.business_mandatory_dims)
    # walk-forward counterfactual (last months with truth)
    # [2] walk-forward counterfactual
    meses = sorted(history_rows[cfg.period_col].unique())[-COUNTERFACTUAL_WINDOW_MONTHS:]
    collected_rows = []
    for mandatory_cell, sub in history_rows.groupby("mandatory_cell"):
        for t in meses:
            pas, act = sub[sub[cfg.period_col] < t], sub[sub[cfg.period_col] == t]
            if len(pas) < MIN_HISTORY_FOR_COUNTERFACTUAL or not len(act): continue
            real = act[cfg.renewed_units_col].sum() / act[cfg.pipeline_units_col].sum()
            plano = pas[cfg.renewed_units_col].sum() / pas[cfg.pipeline_units_col].sum()
            th = pas.groupby("fs_id").apply(lambda s: s[cfg.renewed_units_col].sum() / max(s[cfg.pipeline_units_col].sum(), 1), include_groups=False)
            w = act.groupby("fs_id")[cfg.pipeline_units_col].sum()
            seg = float(np.average(th.reindex(w.index).fillna(plano), weights=w))
            pipe_d = act[cfg.pipeline_usd_col].sum()
            collected_rows.append(dict(celda=mandatory_cell, mes=str(t), err_plano_pp=100*(plano-real), err_seg_pp=100*(seg-real),
                              ahorro_usd=(abs(plano-real)-abs(seg-real))*pipe_d))
    counterfactual_table = pd.DataFrame(collected_rows); cfg.write(counterfactual_table, "simpson_contrafactual")
    print(f"[f1.2] Simpson counterfactual: segmented-method saving = ${counterfactual_table['ahorro_usd'].sum():,.0f} over {len(meses)} walk-forward months")
    # ANOVA (sin timevarying) + combinaciones
    base = series_summary.merge(v.drop_duplicates("fs_id")[["fs_id"] + cfg.business_mandatory_dims + cfg.extra_renovacion +
                   list(cfg.structural_timevarying_dims)], on="fs_id")
    # [3] ANOVA without timevarying
    sin_tv = base[~base[list(cfg.structural_timevarying_dims)].apply(lambda r: _act(r, cfg).any(), axis=1)] if cfg.structural_timevarying_dims else base
    ejes = cfg.business_mandatory_dims + cfg.extra_renovacion
    eta2_by_dim = {d: _eta2_w(sin_tv, d, "tasa_hist", "n_avg") for d in ejes}
    # [4] pairwise interaction
    eta2_pairs = {f"{a}×{b}": _eta2_w(sin_tv.assign(_p=sin_tv[a].astype(str)+"|"+sin_tv[b].astype(str)), "_p", "tasa_hist", "n_avg")
             for a, b in [(x, y) for i, x in enumerate(ejes) for y in ejes[i+1:]]}
    print(f"[f1.2] η² (without tv): { {k: round(x,3) for k,x in eta2_by_dim.items()} } · eta2_pairs: { {k: round(x,3) for k,x in eta2_pairs.items()} }")
    return eta2_by_dim, eta2_pairs, counterfactual_table

def f1_improve_support(v, series_summary, eta2_by_dim, cfg):
    """GOAL: the THREE support-repair strategies, in order of information cost — and
    the final estimate stamped per series (P5: the calculation is done with the
    pool; the result is written onto every member).

    INPUT:  fu_view (1.1), series_summary, eta2_by_dim (1.2) · cfg (signed
            timevarying, support_floor, k_cred, business_mandatory_dims).
    OUTPUT: fu_view + fs_id_L1/L2 · series_estimates with tasa_final/se_final ·
            support_chain_rows (one row per series×stage).
    STEPS:
      [1] Sign per series: neg/pos/neg+pos label from the ACTIVE signals.
      [2] L1 by SIGN across columns: candidate = active signal and support below
          the floor → id = stable dims + SIG=sign. Mandatory dims untouched.
      [3] L2 asterisk: for what remains small WITHOUT a signal, annul the extra
          dim with the lowest η² (SIG= series are excluded: their regime IS
          their signal).
      [4] Pools per level: sum by month BEFORE taking medians (the pool's n is
          the monthly sum of its members).
      [5] L3 credibility z=n/(n+k) toward the mandatory cell; blend se in
          quadrature; implicit n to read the whole chain in support units.
      [6] Stamp the four stages per member into support_chain_rows."""
    tv = list(cfg.structural_timevarying_dims); info = v.drop_duplicates("fs_id").set_index("fs_id")
    series_estimates = series_summary.set_index("fs_id").copy()
    act = info[tv].apply(lambda col: _act(col, cfg)) if tv else pd.DataFrame(index=info.index)
    # [1] sign per series
    def signo(fs):
        s = {cfg.structural_timevarying_dims[c] for c in tv if act.loc[fs, c]}
        return "" if not s else ("neg+pos" if len(s) == 2 else ("neg" if "negative" in s else "pos"))
    series_estimates["signo"] = [signo(fs) for fs in series_estimates.index]
    estable = [d for d in cfg.grano_tasa if d not in tv]
    # [2] L1 by sign
    def id_l1(fs):
        if series_estimates.loc[fs, "signo"] and series_estimates.loc[fs, "n_avg"] < cfg.support_floor:
            return "|".join(str(info.loc[fs, d]) for d in estable) + "|SIG=" + series_estimates.loc[fs, "signo"]
        return fs
    series_estimates["fs_id_L1"] = [id_l1(fs) for fs in series_estimates.index]
    # L2: on L1 pools still below the floor and WITHOUT a signal; annuls the extra dim with the lowest η²
    n1 = series_estimates.groupby("fs_id_L1")["n_avg"].sum()
    anulable = min([d for d in cfg.extra_renovacion], key=lambda d: eta2_by_dim.get(d, 1), default=None)
    pos = {d: i for i, d in enumerate(cfg.grano_tasa)}
    # [3] L2 asterisk
    def id_l2(fs):
        l1 = series_estimates.loc[fs, "fs_id_L1"]
        if "SIG=" in l1 or n1[l1] >= cfg.support_floor or anulable is None: return l1
        p = l1.split("|"); p[pos[anulable]] = "*"; return "|".join(p)
    series_estimates["fs_id_L2"] = [id_l2(fs) for fs in series_estimates.index]
    # per-stage estimation (P5: computed with the pool, stamped on every member)
    v2 = v.merge(series_estimates[["fs_id_L1", "fs_id_L2"]], on="fs_id", how="left")
    history_rows = v2[(v2["universo"] == "normal") & v2["tasa"].notna()]
    # [4] pools: sum by month before taking medians
    def pool(idcol):
        pm = history_rows.groupby([idcol, cfg.period_col]).agg(ren=(cfg.renewed_units_col, "sum"),
                                                       pipe=(cfg.pipeline_units_col, "sum")).reset_index()
        p = pm.groupby(idcol).agg(ren=("ren", "sum"), pipe=("pipe", "sum"),
                                  n=("pipe", lambda s: s[s > 0].median() if (s > 0).any() else 0))
        p["tasa"] = p["ren"] / p["pipe"].clip(lower=1); return p
    p1, p2 = pool("fs_id_L1"), pool("fs_id_L2")
    # [5] PARENT LADDER (multi-level): inside a family the hierarchy gives the rung
    #     (the finest level falls first — annulling level_1 while keeping level_3
    #     would build meaningless cells); BETWEEN families the evidence decides
    #     (the family whose finest level separates least, by η², collapses first).
    collapse_order = _build_collapse_order(cfg.business_mandatory_dims, eta2_by_dim)

    def pool_by_columns(columns):
        """Support and rate of a pool defined by a set of dims: sum by month FIRST,
        then take the median monthly support (the pool's n is its members' sum)."""
        if not columns:
            monthly = history_rows.groupby(cfg.period_col).agg(
                ren=(cfg.renewed_units_col, "sum"), pipe=(cfg.pipeline_units_col, "sum"))
            return pd.DataFrame({"ren": [monthly["ren"].sum()], "pipe": [monthly["pipe"].sum()],
                                 "n": [monthly["pipe"][monthly["pipe"] > 0].median()],
                                 "tasa": [monthly["ren"].sum() / max(monthly["pipe"].sum(), 1)]},
                                index=["*ALL*"])
        monthly = history_rows.groupby(columns + [cfg.period_col]).agg(
            ren=(cfg.renewed_units_col, "sum"), pipe=(cfg.pipeline_units_col, "sum")).reset_index()
        pooled = monthly.groupby(columns).agg(ren=("ren", "sum"), pipe=("pipe", "sum"),
            n=("pipe", lambda s: s[s > 0].median() if (s > 0).any() else 0))
        pooled["tasa"] = pooled["ren"] / pooled["pipe"].clip(lower=1)
        pooled.index = (pooled.index.to_frame().astype(str).agg("|".join, axis=1)
                        if len(columns) > 1 else pooled.index.astype(str))
        return pooled

    ladder_steps = []                       # [(dims_dropped, remaining_dims, pooled)]
    for step_number in range(1, len(collapse_order) + 1):
        dropped = collapse_order[:step_number]
        remaining = [d for d in cfg.business_mandatory_dims if d not in dropped]
        ladder_steps.append((dropped, remaining, pool_by_columns(remaining)))

    def parent_id_of(fs, dropped):
        """Readable parent id: the mandatory tuple with '*' on the collapsed dims."""
        return "|".join("*" if d in dropped else str(info.loc[fs, d])
                        for d in cfg.business_mandatory_dims)

    def climb_ladder(fs):
        """Climb rung by rung until the parent reaches the support floor.
        Returns (parent_id, n, rate, rungs_climbed, trace rows)."""
        trace = []
        for rung, (dropped, remaining, pooled) in enumerate(ladder_steps, start=1):
            lookup_key = ("|".join(str(info.loc[fs, d]) for d in remaining)
                          if remaining else "*ALL*")
            if lookup_key not in pooled.index:
                continue
            parent_n = float(pooled.loc[lookup_key, "n"])
            parent_rate = float(pooled.loc[lookup_key, "tasa"])
            readable = parent_id_of(fs, dropped)
            reached = parent_n >= cfg.support_floor
            trace.append(dict(fs_id=fs, peldano=rung, dims_colapsadas="|".join(dropped),
                              padre_id=readable, n_padre=round(parent_n, 1),
                              tasa_padre=round(parent_rate, 4), elegido=int(reached)))
            if reached:
                return readable, parent_n, parent_rate, rung, trace
        if trace:                                   # nobody reached the floor: take the top
            trace[-1]["elegido"] = 1
            last = trace[-1]
            return last["padre_id"], last["n_padre"], last["tasa_padre"], last["peldano"], trace
        return None, 0.0, np.nan, 0, trace

    def se(t, n):
        pq = max(t * (1 - t), .0025)
        return 100 * np.sqrt(pq / max(n, 1))
    collected_rows, ladder_rows = [], []
    for fs in series_estimates.index:
        r = series_estimates.loc[fs]; n0 = r["n_avg"]; t0 = r["tasa_hist"]
        etapas = [("0_raw", fs, n0, t0)]
        l1 = r["fs_id_L1"]; etapas.append(("1_L1", l1, p1.loc[l1, "n"] if l1 in p1.index else n0,
                                          p1.loc[l1, "tasa"] if l1 in p1.index else t0))
        l2 = r["fs_id_L2"]; etapas.append(("2_L2", l2, p2.loc[l2, "n"] if l2 in p2.index else n0,
                                          p2.loc[l2, "tasa"] if l2 in p2.index else t0))
        nz = etapas[-1][2]; tz = etapas[-1][3]
        parent_readable, parent_n, parent_rate, rungs, trace = climb_ladder(fs)
        ladder_rows.extend(trace)
        if parent_readable is None or not np.isfinite(parent_rate):
            parent_readable, parent_n, parent_rate = "(sin padre)", nz, tz
        # [6] credibility toward the chosen parent: z = n/(n+k), se blended in quadrature
        z = nz / (nz + cfg.k_cred)
        t3 = z * tz + (1 - z) * parent_rate
        se3 = np.sqrt(z**2 * se(tz, nz)**2 + (1 - z)**2 * se(parent_rate, parent_n)**2)
        n_impl = (t3 * (1 - t3)) / (se3 / 100) ** 2 if se3 > 0 else nz
        etapas.append(("3_shrink", f"z={z:.2f}→{parent_readable}", n_impl, t3))
        # [7] stamped per member
        for et, ide, n, t in etapas:
            collected_rows.append(dict(fs_id=fs, fs_key=r["fs_key"], etapa=et, id_efectivo=ide,
                              n_efectivo=round(float(n), 1), tasa=round(float(t), 4),
                              se_pp=round(float(se(t, n)) if et != "3_shrink" else float(se3), 2),
                              usd_proj=r["usd_proj"], peldanos_padre=rungs))
        series_estimates.loc[fs, "tasa_final"] = t3; series_estimates.loc[fs, "se_final"] = se3
    parent_ladder = pd.DataFrame(ladder_rows)
    cfg.write(parent_ladder, "parent_ladder")
    if len(parent_ladder):
        chosen = parent_ladder[parent_ladder["elegido"] == 1]
        print(f"[f1.3] parent ladder: order {collapse_order[:4]}... · "
              f"median rungs climbed {chosen['peldano'].median():.0f} · "
              f"{(chosen['n_padre'] >= cfg.support_floor).mean():.0%} of parents reach the floor")
    support_chain_rows = pd.DataFrame(collected_rows)
    support_chain_rows["moe_usd"] = cfg.z * support_chain_rows["se_pp"] / 100 * support_chain_rows["usd_proj"]
    support_chain_rows["actuo"] = support_chain_rows.groupby("fs_id")["id_efectivo"].transform(lambda s: s != s.iloc[0])
    return v2, series_estimates.reset_index(), support_chain_rows

def f1_support_chain(support_chain_rows, cfg):
    """GOAL: the per-round indicator — how much money sat below the floor at each
    stage and how much each strategy rescued; includes the honest figure of the %
    that never needed repair ("what has support does not need the machinery").
    INPUT:  support_chain_rows (1.3) · cfg (support_floor, write).
    OUTPUT: persisted table `support_chain` + console waterfall.
    STEPS: [1] persist · [2] waterfall of $ below floor per stage · [3] healthy % at 0_raw."""
    cfg.write(support_chain_rows, "support_chain")
    print("[f1.4] WATERFALL — $ to predict sitting in series below the floor, per stage:")
    for et, sub in support_chain_rows.groupby("etapa"):
        bajo = sub[sub["n_efectivo"] < cfg.support_floor]
        print(f"   {et:9s} ${bajo['usd_proj'].sum():>12,.0f}  ({len(bajo)} series)")
    raw_stage_rows = support_chain_rows[support_chain_rows["etapa"] == "0_raw"]
    healthy_money_at_raw = raw_stage_rows[raw_stage_rows["n_efectivo"] >= cfg.support_floor]["usd_proj"].sum()
    print(f"   money that never needed repair: {100*healthy_money_at_raw/max(raw_stage_rows['usd_proj'].sum(),1):.0f}%")

def f1_diagnose_round2(v2, series_estimates, cfg):
    """GOAL: round-2 diagnosis — time, measured ON the consolidated base (P9: a big
    trend with low support is probably not real) — and the DUAL OFFICE of the
    binomial bound: yardstick of trust AND signal detector (the phi factor).

    INPUT:  fu_view with L2 (1.3) · cfg (support_floor, z, write).
    OUTPUT: table `diagnostico_dinamica` with, per pool: the gate verdict plus the
            explainability trio sd_obs_pp / sd_binom_pp / phi.
    STEPS:
      [1] Monthly pool series (sum by month) and its own binomial bound.
      [2] Gate in order: soporte → temporal (≥13 months) → estacional
          (amplitude>2·bound) → tendencia (slope>2·bound) → apto_promedio.
          (Gate VALUES stay in Spanish: they are persisted data.)
      [3] Overdispersion phi = observed variance / coin variance — IS there an
          engine moving the rate beyond sampling noise? (added 2026-08-15).
      [4] Persist the verdict.

    CHANGE LOG (2026-08-15, sealed from conversation — see DISENO_V2 Anexo F):
    added sd_obs_pp, sd_binom_pp and phi. Motivation: the binomial bound has a
    second job beyond "how sure am I of the rate" — the pure coin predicts EXACTLY
    how much the rate MUST dance month to month if nothing is happening, which
    makes it the null hypothesis with numbers. phi compares reality against that
    boredom: ~1 means all the dance is sampling; >1 means a real engine exists
    (trend, season, regime, internal mix) — phi says THAT there is an engine,
    the gates say WHICH one. Measured here; applying it to widen bands
    (calibrated band = z·se·sqrt(phi), rung 3 of the band ladder) belongs to the
    bands monograph and is intentionally NOT done yet.
    """
    history_rows = v2[(v2["universo"] == "normal") & v2["tasa"].notna()]
    collected_rows = []
    for pool_id, pool_rows in history_rows.groupby("fs_id_L2"):
        # [1] monthly pool series and its own bound ------------------------------
        monthly = pool_rows.groupby(cfg.period_col).agg(
            renewed=(cfg.renewed_units_col, "sum"),
            pipeline=(cfg.pipeline_units_col, "sum"))
        pool_rate_series = (monthly["renewed"] / monthly["pipeline"].clip(lower=1)).sort_index()
        pool_support = monthly["pipeline"].median()
        binomial_bound_pp = 100 * np.sqrt(.25 / max(pool_support, 1)) * cfg.z
        # [2] the gate: each question interrogates the SAME excess deviation -----
        # direction? → tendencia · calendar? → estacional · not enough months? → temporal
        gate = "apto_promedio"
        seasonal_amplitude_pp = 0.0
        yearly_slope_pp = 0.0
        if pool_support < cfg.support_floor:
            gate = "soporte"
        elif len(pool_rate_series) < MIN_MONTHS_FOR_SEASONALITY:
            gate = "temporal"
        else:
            rate_by_calendar_month = pool_rate_series.groupby(pool_rate_series.index.month).mean()
            seasonal_amplitude_pp = 100 * (rate_by_calendar_month.max() - rate_by_calendar_month.min())
            month_index = np.arange(len(pool_rate_series))
            yearly_slope_pp = 100 * 12 * np.polyfit(month_index, pool_rate_series.values, 1)[0]
            if seasonal_amplitude_pp > 2 * binomial_bound_pp:
                gate = "estacional"
            elif abs(yearly_slope_pp) > 2 * binomial_bound_pp:
                gate = "tendencia"
        # [3] phi — the overdispersion factor (sealed doctrine, 2026-08-15) ------
        # Observed monthly variance decomposes into two additive sources:
        #     Var(observed rate) = Var(coin: sampling) + Var(process: the true rate moving)
        # The coin term is computable EXACTLY from n and p — that is the whole point:
        # it is a reference of our own (P1: "a magic number is debatable; a reference
        # of your own is not"). phi = observed / coin:
        #     phi ≈ 1 → the rate does not move; it samples. Nothing to model.
        #     phi > 1 → a real engine moves the rate beyond luck; the excess
        #               (sd_obs − sd_binom) is the signal the techniques feed on.
        # Business phrasing this enables: "of the ±7pp you see monthly, ±5 is pure
        # coin (nobody can reduce it) and the rest is the rate actually moving."
        observed_variance = float(pool_rate_series.var(ddof=1)) if len(pool_rate_series) >= 6 else float("nan")
        pooled_rate = monthly["renewed"].sum() / max(monthly["pipeline"].sum(), 1)
        # coin variance uses EACH month's own n (a month with 400 licenses is a
        # steadier witness than one with 40) — hence the mean of 1/n_t:
        coin_variance = pooled_rate * (1 - pooled_rate) * float((1.0 / monthly["pipeline"].clip(lower=1)).mean())
        phi = observed_variance / coin_variance if coin_variance > 0 else float("nan")
        collected_rows.append(dict(
            fs_id_L2=pool_id, meses=len(pool_rate_series),
            n_pool=round(float(pool_support), 1),
            cota_pp=round(binomial_bound_pp, 2),
            amp_estacional_pp=round(seasonal_amplitude_pp, 1),
            pendiente_pp_ano=round(yearly_slope_pp, 1),
            gate=gate,
            sd_obs_pp=round(100 * np.sqrt(observed_variance), 2) if observed_variance == observed_variance else None,
            sd_binom_pp=round(100 * np.sqrt(coin_variance), 2),
            phi=round(phi, 2) if phi == phi else None))
    # [4] persist the verdict ----------------------------------------------------
    d = pd.DataFrame(collected_rows)
    cfg.write(d, "diagnostico_dinamica")
    print(f"[f1.5] gate census: {d['gate'].value_counts().to_dict()}")
    with_engine = d[(d["phi"].notna()) & (d["phi"] > 1.5) & (d["gate"] != "soporte")]
    healthy = d[(d["phi"].notna()) & (d["gate"] != "soporte")]
    if len(healthy):
        print(f"[f1.5] phi — median {healthy['phi'].median():.2f} on pools with history · "
              f"{len(with_engine)} pools with a real engine (phi>1.5): their dance is not just the coin")
    return d
