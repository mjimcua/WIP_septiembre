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
import numpy as np
import pandas as pd

from binomial_reference import binomial_se_pp, weighted_quantile
from config import Config
from techniques import CATALOGUE, eligible_techniques, family_rank, predict, technique_dimension

# ─── named constants ─────────────────────────────────────────────────────────────
CHALLENGER_ORIGIN = "retador"
CHAMPION_ORIGIN = "campeon"
DEFAULT_HORIZON_WHEN_UNKNOWN = 4
INTERMITTENT_ZERO_SHARE = 0.30


def dynamics_labels(decision_dynamics: pd.DataFrame) -> dict:
    """id_estimacion → dict(estacional, tendencia, intermitente)."""
    labels = {}
    for _, row in decision_dynamics.iterrows():
        labels[row["id_estimacion"]] = dict(estacional=int(row["estacional"]), tendencia=int(row["tendencia"]),
                                            intermitente=0)
    return labels


def rolling_origin_backtest(monthly_series: dict, decision_dynamics: pd.DataFrame, horizons: list,
                            configuration: Config) -> pd.DataFrame:
    """The long table of predictions: one row per (id, target, h, technique).

    OUTPUT:  backtest_long: id_estimacion, mes_objetivo, origen, h, tecnica_id, tasa_pred,
             tasa_real, n_real, err_pp (signed: pred − real), se_binom_pp (of the target
             month with its own n), err_norm (err_pp / se_binom_pp).
    RULES:   history ≤ origin only; the target must have a defined rate and n > 0.
    """
    labels = dynamics_labels(decision_dynamics)
    rows = []
    for estimation_id, monthly in monthly_series.items():
        valid = monthly[monthly["rate"].notna() & (monthly["pipe"] > 0)]
        if len(valid) <= configuration.backtest_min_history_months:
            continue
        rates, months = valid["rate"].to_numpy(dtype=float), pd.PeriodIndex(valid.index)
        dynamics = labels.get(estimation_id, {})
        dynamics["intermitente"] = int(np.mean(rates < 0.02) >= INTERMITTENT_ZERO_SHARE)
        for target_position in range(configuration.backtest_min_history_months, len(valid)):
            real, n_real = rates[target_position], float(valid["pipe"].iloc[target_position])
            se_pp = binomial_se_pp(real, n_real)
            for h in horizons:
                origin_position = target_position - h
                if origin_position < configuration.backtest_min_history_months - 1:
                    continue
                history_rates, history_months = rates[:origin_position + 1], months[:origin_position + 1]
                for technique_id in eligible_techniques(len(history_rates), dynamics):
                    predicted = predict(technique_id, history_rates, history_months, h, dynamics)
                    if not np.isfinite(predicted):
                        continue
                    error_pp = 100 * (predicted - real)
                    rows.append(dict(id_estimacion=estimation_id, mes_objetivo=str(months[target_position]),
                                     origen=str(months[origin_position]), h=h, tecnica_id=technique_id,
                                     tasa_pred=round(predicted, 4), tasa_real=round(real, 4), n_real=n_real,
                                     err_pp=round(error_pp, 3), se_binom_pp=round(se_pp, 3),
                                     err_norm=round(error_pp / se_pp, 4)))
    return pd.DataFrame(rows, columns=["id_estimacion", "mes_objetivo", "origen", "h", "tecnica_id", "tasa_pred",
                                       "tasa_real", "n_real", "err_pp", "se_binom_pp", "err_norm"])


def select_technique(backtest_long: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One champion per estimation id, with its evidence.

    OUTPUT:  decision_technique: id_estimacion, tecnica, tecnica_origen (campeon/retador),
             err_norm_medio, err_pp_medio, n_predicciones, retador_err_norm.
    RULES:   score = mean |err_norm| over every horizon and origin. Champion = lowest
             score with n_predicciones ≥ minimum AND score < challenger score − margin;
             among candidates within the margin of the best, the richest family wins.
    """
    rows = []
    challenger = configuration.challenger_technique
    for estimation_id, block in backtest_long.groupby("id_estimacion"):
        scores = block.groupby("tecnica_id").agg(err_norm_medio=("err_norm", lambda e: float(np.mean(np.abs(e)))),
                                                 err_pp_medio=("err_pp", lambda e: float(np.mean(np.abs(e)))),
                                                 n_predicciones=("err_norm", "size"))
        challenger_score = float(scores.loc[challenger, "err_norm_medio"]) if challenger in scores.index else np.inf
        candidates = scores[scores["n_predicciones"] >= configuration.backtest_min_predictions]
        best_score = candidates["err_norm_medio"].min() if len(candidates) else np.inf
        within_margin = candidates[candidates["err_norm_medio"] <= best_score + configuration.challenger_margin_normalized]
        chosen, origin = challenger, CHALLENGER_ORIGIN
        if len(within_margin) and best_score < challenger_score - configuration.challenger_margin_normalized:
            chosen = max(within_margin.index, key=lambda t: (family_rank(t), -within_margin.loc[t, "err_norm_medio"]))
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
             n_predicciones, banda_origen ("propia" / "familia"), and the widths made
             MONOTONE in h (a band never narrows as the horizon grows).
    RULES:   own quantiles when the id has ≥ band_min_predictions at that h; otherwise
             the family's (same technique, every id, that h). Quantiles are of err_norm
             (signed), so a trending series gets a shifted band by itself.
    """
    rows = []
    family = backtest_long.groupby(["tecnica_id", "h"])["err_norm"]
    for _, choice in decision_technique.iterrows():
        own = backtest_long[(backtest_long["id_estimacion"] == choice["id_estimacion"]) & (backtest_long["tecnica_id"] == choice["tecnica"])]
        low_so_far, high_so_far = 0.0, 0.0
        for h in horizons:
            at_h = own[own["h"] == h]["err_norm"].to_numpy()
            if len(at_h) >= configuration.band_min_predictions:
                origin, source = "propia", at_h
            else:
                key = (choice["tecnica"], h)
                source = family.get_group(key).to_numpy() if key in family.groups else np.array([])
                origin = "familia"
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
    """Phase 3 end to end. Persists dim_tecnica, backtest_predictions, decision_technique,
    decision_error_bands, backtest_holdout."""
    configuration.write(technique_dimension(), "dim_tecnica")
    backtest_long = rolling_origin_backtest(monthly_series, decision_dynamics, horizons, configuration)
    decision_technique = select_technique(backtest_long, configuration)
    bands = error_bands(backtest_long, decision_technique, horizons, configuration)
    holdout = holdout_report(backtest_long, decision_technique, bands, configuration)
    configuration.write(backtest_long, "backtest_predictions")
    configuration.write(decision_technique, "decision_technique")
    configuration.write(bands, "decision_error_bands")
    configuration.write(holdout, "backtest_holdout")
    if len(backtest_long):
        leaderboard = backtest_long.groupby("tecnica_id")["err_norm"].apply(lambda e: float(np.mean(np.abs(e)))).sort_values()
        print(f"[3] backtest: {len(backtest_long):,} predictions · {backtest_long['id_estimacion'].nunique()} estimation ids · "
              f"{backtest_long['mes_objetivo'].nunique()} target months · horizons {horizons}")
        print("[3] leaderboard (mean |error| in binomial units; 1.0 = one sampling error):")
        for technique_id, score in leaderboard.items():
            print(f"   {technique_id:<20} {score:5.2f}   {CATALOGUE[technique_id][1]}")
        print(f"[3] champions: {decision_technique['tecnica'].value_counts().to_dict()} · "
              f"{(decision_technique['tecnica_origen'] == CHAMPION_ORIGIN).mean():.0%} beat the challenger")
    if len(holdout):
        by_h = holdout.groupby("h").agg(err_pp=("err_pp", lambda e: float(np.mean(np.abs(e)))), dentro=("dentro_banda", "mean"), n=("err_pp", "size"))
        print(f"[3] HOLD-OUT (months ≥ {holdout['mes_objetivo'].min()}): chosen technique per id")
        for h, row in by_h.iterrows():
            print(f"   h={h}: mean |error| {row['err_pp']:.2f} pp · {row['dentro']:.0%} inside their band · {int(row['n'])} predictions")
    return dict(backtest_long=backtest_long, decision_technique=decision_technique, decision_error_bands=bands,
                backtest_holdout=holdout)
