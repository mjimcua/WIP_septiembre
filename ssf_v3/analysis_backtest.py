"""analysis_backtest.py — SFF v3 · ANALYSIS · phase 3: the judge, one judge.

For every estimation id, a ROLLING-ORIGIN backtest (Tashman 2000): every month with
truth that has at least `backtest_min_history_months` before it is a target; for every
horizon h in 1..H, the origin is h months before the target and only history ≤ origin
is used. All eligible techniques predict; the error is stored WITH SIGN in pp and
NORMALIZED by the binomial error of the pool-month (so a pool of n=1000 and a pool of
n=35 are judged on the same scale).

From the same table:
  · `decision_technique`  the champion per estimation id: the technique with the lowest
                          mean |normalized error| that beats the challenger (T2_mean) by
                          the margin, with at least `backtest_min_predictions` predictions;
                          ties inside the margin go to the richer family (time series
                          preferred). Otherwise the challenger, with `tecnica_origen`.
  · `decision_error_bands` the asymmetric band per (estimation id, h): the p5 and p95
                          of the signed normalized error (family quantiles — same
                          technique, every pool — when the id has too few predictions),
                          made monotone in h. Multiplied by the pool's own binomial
                          error at prediction time, the band respects each pool's size.
  · `backtest_holdout`    the report the business asked for: the months ≥
                          `backtest_test_start` (the 2026 months already happened),
                          predicted from origins with all the history before them.
  · calibration           % of hold-out realizations inside the band (target ≈ 90 %).
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from binomial_reference import binomial_se_pp, inverse_logit, logit, weighted_quantile
from config import Config
from techniques import CATALOGUE, eligible_techniques, family_rank, month_numbers_of, technique_dimension

# ─── named constants ─────────────────────────────────────────────────────────────
CHALLENGER_ORIGIN = "retador"
CHAMPION_ORIGIN = "campeon"
# (intermittent_zero_share is a Config parameter: see config.py, phase 3)


def dynamics_labels(decision_dynamics: pd.DataFrame, requires_firm: bool = True) -> dict:
    """id_estimacion → dict(estacional, tendencia, intermitente, requiere_firme)."""
    labels = {}
    for _, row in decision_dynamics.iterrows():
        labels[row["id_estimacion"]] = dict(estacional=int(row["estacional"]), tendencia=int(row["tendencia"]),
                                            intermitente=0, requiere_firme=requires_firm)
    return labels


def backtest_parameters(configuration: Config) -> dict:
    """The few numbers the backtest loop needs, picklable for the worker processes."""
    return dict(min_history=configuration.backtest_min_history_months, max_targets=configuration.backtest_max_targets,
                intermittent_zero_share=configuration.intermittent_zero_share)


def _backtest_chunk(arguments: tuple) -> list:
    """Worker: the raw prediction rows of a chunk of estimation ids (module-level so it pickles)."""
    chunk, labels, gate_by_id, horizons, parameters, techniques_by_id = arguments
    rows = []
    for estimation_id, monthly in chunk:
        if gate_by_id.get(estimation_id) == "soporte":
            continue
        valid = monthly[monthly["rate"].notna() & (monthly["pipe"] > 0)]
        if len(valid) <= parameters["min_history"]:
            continue
        rates, months = valid["rate"].to_numpy(dtype=float), pd.PeriodIndex(valid.index)
        supports = valid["pipe"].to_numpy(dtype=float)
        logit_rates, month_numbers = logit(rates), month_numbers_of(months)
        dynamics = dict(labels.get(estimation_id, {}))
        dynamics["intermitente"] = int(np.mean(rates < 0.02) >= parameters["intermittent_zero_share"])
        first_target = max(parameters["min_history"], len(valid) - parameters["max_targets"])
        eligible_by_length = {}
        for target_position in range(first_target, len(valid)):
            real, n_real = rates[target_position], supports[target_position]
            se_pp = binomial_se_pp(real, n_real)
            target_month = str(months[target_position])
            for h in horizons:
                origin_position = target_position - h
                if origin_position < parameters["min_history"] - 1:
                    continue
                history_logit, history_months = logit_rates[:origin_position + 1], month_numbers[:origin_position + 1]
                origin_month = str(months[origin_position])
                length = len(history_logit)
                if length not in eligible_by_length:
                    eligible = eligible_techniques(length, dynamics)
                    if techniques_by_id is not None:
                        eligible = [t for t in eligible if t in techniques_by_id.get(estimation_id, ())]
                    eligible_by_length[length] = eligible
                for technique_id in eligible_by_length[length]:
                    try:
                        value = CATALOGUE[technique_id][4](history_logit, history_months, h, dynamics)
                    except Exception:
                        continue
                    if not np.isfinite(value):
                        continue
                    predicted = float(inverse_logit(value))
                    error_pp = 100 * (predicted - real)
                    rows.append((estimation_id, target_month, origin_month, h, technique_id, round(predicted, 4),
                                 round(real, 4), n_real, round(error_pp, 3), round(se_pp, 3), round(error_pp / se_pp, 4)))
    return rows


def rolling_origin_backtest(monthly_series: dict, decision_dynamics: pd.DataFrame, horizons: list,
                            configuration: Config, techniques_by_id: dict = None) -> pd.DataFrame:
    """The long table of predictions: one row per (id, target, h, technique).

    OUTPUT:  backtest_long: id_estimacion, mes_objetivo, origen, h, tecnica_id, tasa_pred,
             tasa_real, n_real, err_pp (signed: pred − real), se_binom_pp (of the target
             month with its own n), err_norm (err_pp / se_binom_pp).
    RULES:   history ≤ origin only; the target must have a defined rate and n > 0.
             Only estimation ids WITH SUPPORT are judged (gate ≠ 'soporte'): a series under
             the floor gets the challenger and a binomial band by doctrine (P9), and
             judging it would cost the same as judging a real pool for nothing. Targets =
             the most recent `backtest_max_targets` months; the history before each
             origin is the whole history.
             `techniques_by_id` (id → list) restricts the techniques judged per id (the
             second stage: champion + challenger only); None = every eligible technique.
    COST:    ≈ targets × horizons × techniques per id. The logit is computed once per id.
    """
    labels = dynamics_labels(decision_dynamics, configuration.seasonal_requires_firm)
    gate_by_id = dict(zip(decision_dynamics["id_estimacion"], decision_dynamics["gate"]))
    items = list(monthly_series.items())
    parameters = backtest_parameters(configuration)
    workers = max(1, int(configuration.backtest_workers))
    if workers == 1 or len(items) < 2 * workers:
        rows = _backtest_chunk((items, labels, gate_by_id, horizons, parameters, techniques_by_id))
    else:
        chunks = [items[index::workers] for index in range(workers)]
        arguments = [(chunk, labels, gate_by_id, horizons, parameters, techniques_by_id) for chunk in chunks]
        try:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                rows = [row for chunk_rows in pool.map(_backtest_chunk, arguments) for row in chunk_rows]
        except Exception as error:                       # a spawn problem must not kill the analysis
            print(f"[3] ⚠ parallel backtest failed ({type(error).__name__}: {error}); running sequentially")
            rows = _backtest_chunk((items, labels, gate_by_id, horizons, parameters, techniques_by_id))
    return pd.DataFrame(rows, columns=["id_estimacion", "mes_objetivo", "origen", "h", "tecnica_id", "tasa_pred",
                                       "tasa_real", "n_real", "err_pp", "se_binom_pp", "err_norm"])


def select_technique(backtest_long: pd.DataFrame, configuration: Config, history_months: dict = None) -> pd.DataFrame:
    """One champion per estimation id, with its evidence.

    OUTPUT:  decision_technique: id_estimacion, tecnica, tecnica_origen (campeon/retador),
             err_norm_medio, err_pp_medio, n_predicciones, retador_err_norm.
    RULES:   score = mean |err_norm| over every horizon and origin. Champion = lowest
             score with n_predicciones ≥ minimum AND score < challenger score − margin;
             among candidates within the margin of the best, the richest family wins when
             the id has ≥ richer_family_min_history_months of history; else the simplest.
    """
    rows = []
    challenger = configuration.challenger_technique
    for estimation_id, block in backtest_long.groupby("id_estimacion"):
        absolute = block.assign(abs_norm=block["err_norm"].abs(), abs_pp=block["err_pp"].abs())
        scores = absolute.groupby("tecnica_id").agg(err_norm_medio=("abs_norm", "mean"), err_pp_medio=("abs_pp", "mean"),
                                                    n_predicciones=("err_norm", "size"))
        challenger_score = float(scores.loc[challenger, "err_norm_medio"]) if challenger in scores.index else np.inf
        candidates = scores[scores["n_predicciones"] >= configuration.backtest_min_predictions]
        best_score = candidates["err_norm_medio"].min() if len(candidates) else np.inf
        within_margin = candidates[candidates["err_norm_medio"] <= best_score + configuration.challenger_margin_normalized]
        chosen, origin = challenger, CHALLENGER_ORIGIN
        if len(within_margin) and best_score < challenger_score - configuration.challenger_margin_normalized:
            enough_history = (history_months or {}).get(estimation_id, 0) >= configuration.richer_family_min_history_months
            rank_sign = 1 if enough_history else -1
            chosen = max(within_margin.index, key=lambda t: (rank_sign * family_rank(t), -within_margin.loc[t, "err_norm_medio"]))
            origin = CHAMPION_ORIGIN
        row = scores.loc[chosen] if chosen in scores.index else pd.Series(dict(err_norm_medio=np.nan, err_pp_medio=np.nan, n_predicciones=0))
        rows.append(dict(id_estimacion=estimation_id, tecnica=chosen, tecnica_origen=origin,
                         err_norm_medio=round(float(row["err_norm_medio"]), 4), err_pp_medio=round(float(row["err_pp_medio"]), 3),
                         n_predicciones=int(row["n_predicciones"]), retador_err_norm=round(challenger_score, 4)))
    return pd.DataFrame(rows, columns=["id_estimacion", "tecnica", "tecnica_origen", "err_norm_medio", "err_pp_medio",
                                       "n_predicciones", "retador_err_norm"])


def error_bands(backtest_long: pd.DataFrame, decision_technique: pd.DataFrame, horizons: list,
                configuration: Config) -> pd.DataFrame:
    """The asymmetric band per (estimation id, h) of its chosen technique.

    OUTPUT:  decision_error_bands: id_estimacion, tecnica, h, q_low_norm, q_high_norm,
             n_predicciones, banda_origen ("propia" / "familia" / "binomial"), and the
             widths made MONOTONE in h (a band never narrows as the horizon grows).
    RULES:   own quantiles when the id has ≥ band_min_predictions at that h; otherwise
             the family's (same technique, every id, that h). Quantiles are of err_norm
             (signed), so a trending series gets a shifted band by itself.
    NOTE:    the long table is grouped ONCE by (id, technique, h) and once by (technique,
             h); filtering it per id would scan millions of rows thousands of times.
    """
    own_groups = {key: group.to_numpy() for key, group in backtest_long.groupby(["id_estimacion", "tecnica_id", "h"])["err_norm"]}
    family_groups = {key: group.to_numpy() for key, group in backtest_long.groupby(["tecnica_id", "h"])["err_norm"]}
    rows = []
    for _, choice in decision_technique.iterrows():
        low_so_far, high_so_far = 0.0, 0.0
        for h in horizons:
            at_h = own_groups.get((choice["id_estimacion"], choice["tecnica"], h), np.array([]))
            if len(at_h) >= configuration.band_min_predictions:
                origin, source = "propia", at_h
            else:
                origin, source = "familia", family_groups.get((choice["tecnica"], h), np.array([]))
            low = weighted_quantile(source, configuration.band_low_quantile)
            high = weighted_quantile(source, configuration.band_high_quantile)
            if not np.isfinite(low) or not np.isfinite(high):
                low, high, origin = -configuration.z, configuration.z, "binomial"
            low_so_far, high_so_far = min(low_so_far, low), max(high_so_far, high)
            rows.append(dict(id_estimacion=choice["id_estimacion"], tecnica=choice["tecnica"], h=h,
                             q_low_norm=round(low_so_far, 4), q_high_norm=round(high_so_far, 4),
                             n_predicciones=int(len(source)), banda_origen=origin))
    return pd.DataFrame(rows)


def holdout_report(backtest_long: pd.DataFrame, decision_technique: pd.DataFrame, decision_error_bands: pd.DataFrame,
                   configuration: Config) -> pd.DataFrame:
    """The hold-out: months ≥ backtest_test_start predicted with the chosen technique.

    OUTPUT:  backtest_holdout: id_estimacion, mes_objetivo, h, tecnica, tasa_pred,
             tasa_real, err_pp, err_norm, banda_low_pp, banda_high_pp, dentro_banda.
    RULES:   the band of a prediction = q_norm × se_binom of the target month (the real n).
    """
    if backtest_long.empty:
        return pd.DataFrame()
    start = configuration.backtest_test_start
    if start is None:
        months = sorted(backtest_long["mes_objetivo"].unique())
        start = months[-12] if len(months) >= 12 else months[0]
    chosen = decision_technique[["id_estimacion", "tecnica"]].rename(columns={"tecnica": "tecnica_id"})
    holdout = backtest_long[backtest_long["mes_objetivo"] >= start].merge(chosen, on=["id_estimacion", "tecnica_id"])
    bands = decision_error_bands[["id_estimacion", "h", "q_low_norm", "q_high_norm"]]
    holdout = holdout.merge(bands, on=["id_estimacion", "h"], how="left")
    holdout["banda_low_pp"] = (holdout["q_low_norm"] * holdout["se_binom_pp"]).round(2)
    holdout["banda_high_pp"] = (holdout["q_high_norm"] * holdout["se_binom_pp"]).round(2)
    holdout["dentro_banda"] = ((holdout["err_pp"] >= holdout["banda_low_pp"]) & (holdout["err_pp"] <= holdout["banda_high_pp"])).astype(int)
    return holdout.rename(columns={"tecnica_id": "tecnica"})[["id_estimacion", "mes_objetivo", "origen", "h", "tecnica", "tasa_pred",
                                                             "tasa_real", "n_real", "err_pp", "err_norm", "banda_low_pp",
                                                             "banda_high_pp", "dentro_banda"]]


def run_backtest_analysis(monthly_series: dict, decision_dynamics: pd.DataFrame, configuration: Config,
                          horizons: list) -> dict:
    """Phase 3 end to end, in two stages. Persists dim_tecnica, backtest_predictions,
    decision_technique, decision_error_bands, backtest_holdout.

    STAGE 1 · screen: every eligible technique at `backtest_screen_horizons` → the champion
             per id (select_technique on the screen table).
    STAGE 2 · judge: champion + challenger at EVERY judged horizon → bands, hold-out. The
             persisted `backtest_predictions` is the union of both stages.
    Two stages cost ~3× less than judging every technique at every horizon, and the
    champion is chosen where it matters most (the near horizons).
    """
    configuration.write(technique_dimension(), "dim_tecnica")
    screen_horizons = sorted({h for h in configuration.backtest_screen_horizons if h in horizons} | {horizons[0]})
    screen = rolling_origin_backtest(monthly_series, decision_dynamics, screen_horizons, configuration)
    history_months = dict(zip(decision_dynamics["id_estimacion"], decision_dynamics["meses"]))
    decision_technique = select_technique(screen, configuration, history_months)
    remaining = [h for h in horizons if h not in screen_horizons]
    chosen_and_challenger = {row["id_estimacion"]: {row["tecnica"], configuration.challenger_technique}
                             for _, row in decision_technique.iterrows()}
    judged = rolling_origin_backtest(monthly_series, decision_dynamics, remaining, configuration, chosen_and_challenger) if remaining else screen.head(0)
    backtest_long = pd.concat([screen, judged], ignore_index=True).sort_values(["id_estimacion", "mes_objetivo", "h", "tecnica_id"])
    bands = error_bands(backtest_long, decision_technique, horizons, configuration)
    holdout = holdout_report(backtest_long, decision_technique, bands, configuration)
    configuration.write(backtest_long, "backtest_predictions")
    configuration.write(decision_technique, "decision_technique")
    configuration.write(bands, "decision_error_bands")
    configuration.write(holdout, "backtest_holdout")
    if len(screen):
        leaderboard = screen.groupby("tecnica_id")["err_norm"].apply(lambda e: float(np.mean(np.abs(e)))).sort_values()
        print(f"[3] backtest: {len(backtest_long):,} predictions · {backtest_long['id_estimacion'].nunique()} estimation ids with support · "
              f"{backtest_long['mes_objetivo'].nunique()} target months · screened at h={screen_horizons}, judged at h={horizons}")
        print("[3] leaderboard on the screen (mean |error| in binomial units; 1.0 = one sampling error):")
        for technique_id, score in leaderboard.items():
            print(f"   {technique_id:<20} {score:5.2f}   {CATALOGUE[technique_id][1]}")
        print(f"[3] champions: {decision_technique['tecnica'].value_counts().to_dict()} · "
              f"{(decision_technique['tecnica_origen'] == CHAMPION_ORIGIN).mean():.0%} beat the challenger")
    if len(holdout):
        weighted = holdout.assign(abs_pp=holdout["err_pp"].abs(), w=holdout["n_real"])
        by_h = weighted.groupby("h").apply(lambda g: pd.Series(dict(
            err_pp=g["abs_pp"].mean(), err_pp_w=np.average(g["abs_pp"], weights=g["w"]), bias_w=np.average(g["err_pp"], weights=g["w"]),
            dentro=g["dentro_banda"].mean(), n=len(g))), include_groups=False)
        print(f"[3] HOLD-OUT (months ≥ {holdout['mes_objetivo'].min()}): chosen technique per id · "
              f"|error| plain and weighted by units (≈ money) · signed bias (− = under-forecast)")
        for h, row in by_h.iterrows():
            print(f"   h={int(h):>2}: |error| {row['err_pp']:.2f} pp · weighted {row['err_pp_w']:.2f} pp · bias {row['bias_w']:+.2f} pp · "
                  f"{row['dentro']:.0%} inside band · {int(row['n'])} predictions")
    return dict(backtest_long=backtest_long, decision_technique=decision_technique, decision_error_bands=bands,
                backtest_holdout=holdout)
