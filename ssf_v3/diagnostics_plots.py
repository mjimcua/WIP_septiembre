"""diagnostics_plots.py — SFF v3 · look at the series the numbers are built on.

    from diagnostics_plots import run_series_diagnostics
    paths = run_series_diagnostics(configuration, top=10, by="usd")            # reads the sff_* tables
    paths = run_series_diagnostics(results=results, top=10, by="history")     # from run_analysis' dict

Picks the top series (by projected money or by history length, with a minimum history),
prints a table with their dynamics (φ, seasonal, trend, technique, hold-out error) and
saves FOUR compact figures under <outdir>/diagnostics/:

  1_rates.png      the monthly renewal rate of every top series on ONE axis (one colour
                   per series, legend with n · φ · season · slope), hold-out months shaded
  2_pipeline.png   the monthly pipeline units of the same series (log scale): portfolio
                   moves, spikes and holes show here, not in the rates
  3_season.png     the seasonal profile by calendar month (index = month / overall) of the
                   series declared seasonal, with the 2× binomial bound
  4_holdout.png    real vs predicted (h=1, chosen technique) on the hold-out months

Style: palette GREEN #2E7D7D / BLUE #3B8BC8 / YELLOW #E8B84F first, then tab10; vertical
single-letter month labels; big fonts. Everything from code, nothing by hand.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                        # noqa: E402
import numpy as np                                    # noqa: E402
import pandas as pd                                   # noqa: E402

PROJECT_FOLDER = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
if PROJECT_FOLDER not in sys.path:
    sys.path.insert(0, PROJECT_FOLDER)

from audit_series import read_table                   # noqa: E402
from config import Config                             # noqa: E402

# ─── named constants ─────────────────────────────────────────────────────────────
PALETTE = ["#2E7D7D", "#3B8BC8", "#E8B84F"] + [matplotlib.colormaps["tab10"](i) for i in range(10)]
MONTH_LETTERS = "JFMAMJJASOND"
FIGURE_WIDTH = 16
PERIOD_COLUMN_CANDIDATES = ("period", "periodo")


def top_series(series_card: pd.DataFrame, top: int, by: str, min_history_months: int) -> pd.DataFrame:
    """The top series by projected money ('usd') or by history length ('history'),
    among trainable series with at least `min_history_months` of history."""
    eligible = series_card[(series_card["ruta"] == "trainable") & (series_card["meses_historia"] >= min_history_months)]
    key = "usd_proyectado" if by == "usd" else "meses_historia"
    return eligible.sort_values([key, "usd_proyectado"], ascending=False).head(top)


def monthly_of(units: pd.DataFrame, series_id: str, configuration: Config) -> pd.DataFrame:
    """The real history months of one series: rate and pipeline units, indexed by period."""
    period = configuration.period_col
    rows = units[(units["fs_id"] == series_id) & (units["sintetica"] == 0) & (units[configuration.dataset_role_col] != "projection")]
    monthly = rows.groupby(period).agg(pipe=(configuration.pipeline_units_col, "sum"), ren=(configuration.renewed_units_col, "sum")).sort_index()
    monthly["rate"] = np.where(monthly["pipe"] > 0, monthly["ren"] / monthly["pipe"].replace(0, np.nan), np.nan)
    monthly.index = pd.PeriodIndex(monthly.index, freq="M")
    return monthly


def month_ticks(axis, periods: pd.PeriodIndex) -> None:
    """Vertical single-letter month labels, the year under every January."""
    positions = np.arange(len(periods))
    axis.set_xticks(positions)
    axis.set_xticklabels([MONTH_LETTERS[p.month - 1] + (f"\n{p.year}" if p.month == 1 else "") for p in periods],
                         fontsize=9, rotation=0)
    axis.grid(axis="x", alpha=0.15)


def label_of(row: pd.Series, dynamics: pd.Series, technique: pd.Series) -> str:
    """One legend line: id · n · φ · season · slope · technique."""
    season = {0: "no season", 1: "season?", 2: "SEASON"}.get(int(dynamics.get("estacional", 0)), "")
    return (f"{row['fs_id'][:52]} · n={row['n_propio']:.0f} · φ={dynamics.get('phi', float('nan'))} · {season} "
            f"(amp {dynamics.get('amp_estacional_pp', 0)}pp) · slope {dynamics.get('pendiente_pp_ano', 0)}pp/yr · "
            f"{technique.get('tecnica', '-')} {technique.get('tecnica_origen', '')}")


def plot_rates_and_pipeline(monthlies: dict, labels: dict, holdout_start, output_folder: str) -> list:
    """Figures 1 and 2: rates on one axis; pipeline units on one axis (log)."""
    all_periods = sorted(set().union(*[set(m.index) for m in monthlies.values()]))
    all_periods = pd.PeriodIndex(all_periods, freq="M")
    position = {p: i for i, p in enumerate(all_periods)}
    paths = []
    for name, column, ylabel, log in (("1_rates", "rate", "renewal rate", False), ("2_pipeline", "pipe", "pipeline units (log)", True)):
        figure, axis = plt.subplots(figsize=(FIGURE_WIDTH, 7))
        for index, (series_id, monthly) in enumerate(monthlies.items()):
            x = [position[p] for p in monthly.index]
            axis.plot(x, monthly[column], color=PALETTE[index % len(PALETTE)], linewidth=2.2, marker="o", markersize=3.5,
                      label=labels[series_id] if column == "rate" else series_id[:52])
        if holdout_start is not None and holdout_start in position:
            axis.axvspan(position[holdout_start] - 0.5, len(all_periods) - 0.5, color="#E8B84F", alpha=0.12, label="hold-out")
        if log:
            axis.set_yscale("log")
        else:
            axis.set_ylim(0, 1.0)
        month_ticks(axis, all_periods)
        axis.set_ylabel(ylabel, fontsize=12)
        axis.set_title(f"top series · {ylabel}", fontsize=14, loc="left")
        axis.legend(fontsize=8, loc="lower left" if column == "rate" else "best", ncol=1, framealpha=0.9)
        figure.tight_layout()
        path = os.path.join(output_folder, f"{name}.png")
        figure.savefig(path, dpi=110)
        plt.close(figure)
        paths.append(path)
    return paths


def plot_seasonal_profiles(top: pd.DataFrame, dynamics_by_id: dict, output_folder: str) -> str:
    """Figure 3: the seasonal index by calendar month of the series with a profile."""
    figure, axis = plt.subplots(figsize=(FIGURE_WIDTH, 5.5))
    drawn = 0
    for index, (_, row) in enumerate(top.iterrows()):
        dynamics = dynamics_by_id.get(row["id_estimacion"], {})
        profile_text = dynamics.get("perfil_estacional", "") or ""
        if not profile_text:
            continue
        profile = {int(k): float(v) for k, v in (item.split(":") for item in profile_text.split("|"))}
        months = sorted(profile)
        style = "-" if int(dynamics.get("estacional", 0)) == 2 else ("--" if int(dynamics.get("estacional", 0)) == 1 else ":")
        axis.plot(months, [100 * (profile[m] - 1) for m in months], style, color=PALETTE[index % len(PALETTE)], linewidth=2.2, marker="o",
                  label=f"{row['fs_id'][:40]} · φ={dynamics.get('phi')} · bound ±{dynamics.get('cota_pp')}pp · cycles {dynamics.get('ciclos_completos')}")
        drawn += 1
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set_xticks(range(1, 13))
    axis.set_xticklabels(list(MONTH_LETTERS), fontsize=11)
    axis.set_ylabel("% above / below the series' mean rate", fontsize=12)
    axis.set_title("seasonal profile by calendar month (detrended) · solid = firm (≥2 cycles), dashed = 1 cycle, dotted = not seasonal", fontsize=12, loc="left")
    if drawn:
        axis.legend(fontsize=8, framealpha=0.9)
    figure.tight_layout()
    path = os.path.join(output_folder, "3_season.png")
    figure.savefig(path, dpi=110)
    plt.close(figure)
    return path


def plot_holdout(top: pd.DataFrame, holdout: pd.DataFrame, output_folder: str) -> str:
    """Figure 4: real vs predicted (h=1) on the hold-out months for the top series' estimation ids."""
    figure, axis = plt.subplots(figsize=(FIGURE_WIDTH, 6))
    drawn = 0
    if len(holdout):
        at_h1 = holdout[holdout["h"] == 1]
        for index, (_, row) in enumerate(top.iterrows()):
            block = at_h1[at_h1["id_estimacion"] == row["id_estimacion"]].sort_values("mes_objetivo")
            if block.empty:
                continue
            x = np.arange(len(block))
            colour = PALETTE[index % len(PALETTE)]
            axis.plot(x, block["tasa_real"], "-o", color=colour, linewidth=2, markersize=4, label=f"{row['fs_id'][:40]} real")
            axis.plot(x, block["tasa_pred"], "--", color=colour, linewidth=1.6, label=f"   predicted h=1 ({block['tecnica'].iloc[0]}), "
                      f"|err| {block['err_pp'].abs().mean():.1f}pp, {block['dentro_banda'].mean():.0%} in band")
            axis.fill_between(x, block["tasa_pred"] + block["banda_low_pp"] / 100, block["tasa_pred"] + block["banda_high_pp"] / 100,
                              color=colour, alpha=0.08)
            axis.set_xticks(x)
            axis.set_xticklabels(block["mes_objetivo"], rotation=45, fontsize=9)
            drawn += 1
    axis.set_ylim(0, 1.0)
    axis.set_ylabel("renewal rate", fontsize=12)
    axis.set_title("hold-out · real (solid) vs predicted at h=1 (dashed) with its band", fontsize=14, loc="left")
    if drawn:
        axis.legend(fontsize=8, ncol=2, framealpha=0.9)
    figure.tight_layout()
    path = os.path.join(output_folder, "4_holdout.png")
    figure.savefig(path, dpi=110)
    plt.close(figure)
    return path


def run_series_diagnostics(configuration: Config = None, results: dict = None, top: int = 10, by: str = "usd",
                           min_history_months: int = 24, output_folder: str = None) -> list:
    """Pick the top series, print their diagnostics, save the four figures. Returns the paths."""
    card = read_table("series_card", configuration, results)
    dynamics = read_table("decision_dynamics", configuration, results)
    technique = read_table("decision_technique", configuration, results)
    holdout = read_table("backtest_holdout", configuration, results)
    units = results["units"] if results is not None and "units" in results else None
    if units is None:
        fact = read_table("fact_fu", configuration, results)
        if fact.empty:
            raise RuntimeError("series history not available: pass results=run_analysis(...) or an engine with sff_fact_fu")
        fact["fs_id"] = fact["fu_id"].str.rsplit("|", n=1).str[0]
        fact["sintetica"] = 0
        fact[configuration.period_col] = pd.PeriodIndex(fact[configuration.period_col].astype(str), freq="M")
        units = fact
    chosen = top_series(card, top, by, min_history_months)
    dynamics_by_id = {row["id_estimacion"]: row for _, row in dynamics.iterrows()} if len(dynamics) else {}
    technique_by_id = {row["id_estimacion"]: row for _, row in technique.iterrows()} if len(technique) else {}
    folder = output_folder or os.path.join(configuration.outdir if configuration else ".", "diagnostics")
    os.makedirs(folder, exist_ok=True)
    print(f"[diag] top {len(chosen)} series by {by} (≥ {min_history_months} history months)")
    print("   series · $ projected · months · n · id_estimacion · φ · gate · season(amp) · slope · technique · hold-out |err| h=1")
    monthlies, labels = {}, {}
    for _, row in chosen.iterrows():
        d, t = dynamics_by_id.get(row["id_estimacion"], {}), technique_by_id.get(row["id_estimacion"], {})
        block = holdout[(holdout["id_estimacion"] == row["id_estimacion"]) & (holdout["h"] == 1)] if len(holdout) else pd.DataFrame()
        err = f"{block['err_pp'].abs().mean():.1f}pp" if len(block) else "-"
        print(f"   {row['fs_id'][:58]:<58} ${row['usd_proyectado']:>11,.0f} {int(row['meses_historia']):>3}m n={row['n_propio']:>6.0f} "
              f"→ {str(row['id_estimacion'])[:36]:<36} φ={d.get('phi', '-')} {d.get('gate', '-')} est={d.get('estacional', '-')}"
              f"({d.get('amp_estacional_pp', '-')}pp) slope={d.get('pendiente_pp_ano', '-')} {t.get('tecnica', '-')}/{t.get('tecnica_origen', '')} {err}")
        monthlies[row["fs_id"]] = monthly_of(units, row["fs_id"], configuration)
        labels[row["fs_id"]] = label_of(row, d, t)
    holdout_start = pd.Period(holdout["mes_objetivo"].min(), freq="M") if len(holdout) else None
    paths = plot_rates_and_pipeline(monthlies, labels, holdout_start, folder)
    paths.append(plot_seasonal_profiles(chosen, dynamics_by_id, folder))
    paths.append(plot_holdout(chosen, holdout, folder))
    print(f"[diag] figures in {folder}: " + ", ".join(os.path.basename(p) for p in paths))
    return paths


# ═══════════════════════════════════════════════════════════════════════════════════
# THE SHEET OF ONE SERIES · the showcase trio · the guess game
# ═══════════════════════════════════════════════════════════════════════════════════

def binomial_band(rates: np.ndarray, units: np.ndarray, z: float = 1.645) -> tuple:
    """The z·binomial band of each month around its own rate (pure sampling)."""
    se = np.sqrt(np.maximum(rates * (1 - rates), 0.0475) / np.maximum(units, 1.0))
    return np.clip(rates - z * se, 0, 1), np.clip(rates + z * se, 0, 1)


def series_sheet(series_id: str, configuration: Config = None, results: dict = None, output_folder: str = None) -> str:
    """ONE figure with everything the numbers say about one series, next to the series itself.

    Panels: (1) monthly rate with its binomial band, the pooled mean, the last-12-month
    trend line, the level change (vertical line), hold-out shaded; (2) pipeline units by
    month; (3) seasonal profile of the RATE vs of the UNITS (where the season lives);
    (4) hold-out real vs predicted with band. A text box carries the diagnostics in words.
    Returns the PNG path. Prints the summary too.
    """
    card = read_table("series_card", configuration, results)
    row = card[card["fs_id"] == series_id]
    if row.empty:
        raise KeyError(f"series '{series_id}' not in series_card")
    row = row.iloc[0]
    dynamics = read_table("decision_dynamics", configuration, results)
    dynamics = dynamics[dynamics["id_estimacion"] == row["id_estimacion"]]
    d = dynamics.iloc[0] if len(dynamics) else pd.Series(dtype=object)
    technique = read_table("decision_technique", configuration, results)
    technique = technique[technique["id_estimacion"] == row["id_estimacion"]]
    if len(technique) and "tramo_h" in technique.columns:
        technique = technique.sort_values("h_min")
    t = technique.iloc[0] if len(technique) else pd.Series(dtype=object)
    holdout = read_table("backtest_holdout", configuration, results)
    holdout = holdout[(holdout["id_estimacion"] == row["id_estimacion"]) & (holdout["h"] == 1)].sort_values("mes_objetivo") if len(holdout) else holdout
    units = _units_frame(configuration, results)
    monthly = monthly_of(units, series_id, configuration)
    valid = monthly[monthly["rate"].notna()]
    periods = pd.PeriodIndex(valid.index, freq="M")
    x = np.arange(len(valid))
    rates, pipe = valid["rate"].to_numpy(dtype=float), valid["pipe"].to_numpy(dtype=float)

    figure, axes = plt.subplots(2, 2, figsize=(FIGURE_WIDTH, 10), gridspec_kw=dict(height_ratios=[1.3, 1]))
    ax_rate, ax_units, ax_season, ax_holdout = axes[0, 0], axes[1, 0], axes[0, 1], axes[1, 1]
    # (1) rate with binomial band, mean, recent trend, level change
    low, high = binomial_band(rates, pipe, configuration.z if configuration else 1.645)
    ax_rate.fill_between(x, low, high, color="#3B8BC8", alpha=0.12, label="binomial band of each month (sampling only)")
    ax_rate.plot(x, rates, "-o", color="#2E7D7D", linewidth=2.4, markersize=4, label="monthly rate")
    pooled = valid["ren"].sum() / max(valid["pipe"].sum(), 1)
    ax_rate.axhline(pooled, color="#E8B84F", linewidth=1.8, linestyle="--", label=f"pooled mean {pooled:.3f}")
    if len(valid) >= 12:
        recent_x = x[-12:]
        coefficients = np.polyfit(recent_x, rates[-12:], 1)
        ax_rate.plot(recent_x, np.polyval(coefficients, recent_x), color="#C0392B", linewidth=2,
                     label=f"last 12 months trend {100 * 12 * coefficients[0]:+.1f} pp/yr")
    change_month = d.get("cambio_nivel_mes", "") if len(d) else ""
    if change_month:
        try:
            cut = list(periods.astype(str)).index(change_month)
            ax_rate.axvline(cut - 0.5, color="black", linestyle=":", linewidth=1.5,
                            label=f"level change {change_month}: {d['cambio_nivel_pp']:+.1f} pp ({d['cambio_nivel_fuerza']:.1f} binomial units)")
        except ValueError:
            pass
    if len(holdout):
        first = pd.Period(holdout["mes_objetivo"].min(), freq="M")
        if first in set(periods):
            ax_rate.axvspan(list(periods).index(first) - 0.5, len(x) - 0.5, color="#E8B84F", alpha=0.12, label="hold-out")
    month_ticks(ax_rate, periods)
    ax_rate.set_ylim(0, 1.0)
    ax_rate.set_title(f"{series_id[:70]}  ·  n≈{row['n_propio']:.0f}/month  ·  level {row['nivel_riesgo']}", fontsize=13, loc="left")
    ax_rate.legend(fontsize=8, loc="lower left", framealpha=0.9)
    # (2) units
    ax_units.bar(x, pipe, color="#3B8BC8", alpha=0.8)
    month_ticks(ax_units, periods)
    ax_units.set_ylabel("pipeline units", fontsize=11)
    ax_units.set_title(f"pipeline units by month · volume seasonality {d.get('amp_volumen_pct', float('nan'))} % of mean · "
                       f"corr(units, rate) {d.get('corr_unidades_tasa', float('nan'))}", fontsize=11, loc="left")
    # (3) seasonal profile: rate vs units
    if len(valid) >= 13:
        by_month_rate = pd.Series(rates, index=periods.month).groupby(level=0).mean()
        by_month_units = pd.Series(pipe, index=periods.month).groupby(level=0).mean()
        ax_season.plot(by_month_rate.index, 100 * (by_month_rate / rates.mean() - 1), "-o", color="#2E7D7D", linewidth=2.4,
                       label=f"RATE by calendar month (amp {d.get('amp_estacional_pp', '-')} pp, seasonal={d.get('estacional', '-')}, φ={d.get('phi', '-')})")
        ax_season.plot(by_month_units.index, 100 * (by_month_units / pipe.mean() - 1), "-s", color="#3B8BC8", linewidth=2.4,
                       label=f"UNITS by calendar month (amp {d.get('amp_volumen_pct', '-')} %)")
        bound = float(d.get("cota_pp", 0) or 0)
        ax_season.axhspan(-2 * bound / max(pooled, 0.01), 2 * bound / max(pooled, 0.01), color="grey", alpha=0.12, label="2× binomial bound of the rate")
    ax_season.axhline(0, color="black", linewidth=0.8)
    ax_season.set_xticks(range(1, 13)); ax_season.set_xticklabels(list(MONTH_LETTERS), fontsize=11)
    ax_season.set_ylabel("% above / below own mean", fontsize=11)
    ax_season.set_title("where the season lives: in the rate or in the volume?", fontsize=12, loc="left")
    ax_season.legend(fontsize=8, framealpha=0.9)
    # (4) hold-out
    if len(holdout):
        hx = np.arange(len(holdout))
        ax_holdout.plot(hx, holdout["tasa_real"], "-o", color="#2E7D7D", linewidth=2.4, label="real")
        ax_holdout.plot(hx, holdout["tasa_pred"], "--o", color="#C0392B", linewidth=2, label=f"predicted h=1 · {holdout['tecnica'].iloc[0]}")
        ax_holdout.fill_between(hx, holdout["tasa_pred"] + holdout["banda_low_pp"] / 100, holdout["tasa_pred"] + holdout["banda_high_pp"] / 100,
                                color="#C0392B", alpha=0.10, label=f"band · {holdout['dentro_banda'].mean():.0%} inside")
        ax_holdout.set_xticks(hx); ax_holdout.set_xticklabels(holdout["mes_objetivo"], rotation=45, fontsize=9)
        ax_holdout.set_ylim(0, 1.0)
        ax_holdout.set_title(f"hold-out at h=1 · |error| {holdout['err_pp'].abs().mean():.1f} pp · bias {holdout['err_pp'].mean():+.1f} pp", fontsize=12, loc="left")
        ax_holdout.legend(fontsize=8, framealpha=0.9)
    else:
        ax_holdout.text(0.5, 0.5, "no hold-out (no backtest for this id: under the floor or not run)", ha="center", fontsize=11)
        ax_holdout.set_axis_off()
    summary = sheet_summary(row, d, t, holdout)
    figure.text(0.01, 0.005, summary, fontsize=9, family="monospace", va="bottom")
    figure.tight_layout(rect=(0, 0.09, 1, 1))
    folder = output_folder or os.path.join(configuration.outdir if configuration else ".", "diagnostics")
    os.makedirs(folder, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in series_id)[:80]
    path = os.path.join(folder, f"sheet_{safe}.png")
    figure.savefig(path, dpi=110)
    plt.close(figure)
    print(summary)
    return path


def sheet_summary(row: pd.Series, d: pd.Series, t: pd.Series, holdout: pd.DataFrame) -> str:
    """The diagnostics of one series in plain words (the text box of the sheet)."""
    if not len(d):
        return f"{row['fs_id']}: no dynamics (under the floor or no history). Level {row['nivel_riesgo']}."
    season = {0: "not seasonal", 1: "seasonal? (1 cycle only)", 2: f"SEASONAL (firm, {int(d['ciclos_completos'])} cycles; high {d['meses_alto'] or '-'}, low {d['meses_bajo'] or '-'})"}[int(d["estacional"])]
    trend = {-1: "declining", 0: "no trend", 1: "rising"}[int(d["tendencia"])]
    engine = "φ≈1: the rate only samples" if d["phi"] < 1.5 else f"φ={d['phi']}: an engine moves it beyond sampling"
    regime = (f"level change in {d['cambio_nivel_mes']}: {d['cambio_nivel_pp']:+.1f} pp ({d['cambio_nivel_fuerza']:.1f} binomial units"
              f"{', a REGIME' if d['cambio_nivel_fuerza'] >= 3 else ', noise'})") if d["cambio_nivel_mes"] else "no level change found"
    volume = (f"volume season {d['amp_volumen_pct']} % of mean units, corr(units, rate) {d['corr_unidades_tasa']:+.2f}"
              if pd.notna(d.get("amp_volumen_pct")) else "volume season n/a")
    lines = [
        f"SERIES {row['fs_id']} · estimated with {row['id_estimacion']} (rung {int(row['peldano'])}, n_efectivo {row['n_efectivo']:.0f}) · level {row['nivel_riesgo']}",
        f"RATE   {row['tasa_estimada']:.3f} · se_estimacion {row['se_estimacion_pp']:.1f} pp · se_prediccion {row['se_prediccion_pp']:.1f} pp · {engine}",
        f"SHAPE  {season} (amp {d['amp_estacional_pp']} pp vs bound {d['cota_pp']} pp) · {trend} ({d['pendiente_pp_ano']} pp/yr whole history, "
        f"{d['pendiente_12m_pp_ano']} pp/yr last 12 months) · {regime}",
        f"VOLUME {volume}",
    ]
    if len(t):
        lines.append(f"TECHN. {t['tecnica']} ({t['tecnica_origen']}, band {t.get('tramo_h', '-')}) · mean |error| {t['err_pp_medio']} pp = {t['err_norm_medio']} binomial units · challenger at {t['retador_err_norm']}"
                     + (f" · hold-out h=1 |error| {holdout['err_pp'].abs().mean():.1f} pp, bias {holdout['err_pp'].mean():+.1f} pp, {holdout['dentro_banda'].mean():.0%} in band" if len(holdout) else ""))
    return "\n".join(lines)


def _units_frame(configuration, results):
    units = results["units"] if results is not None and "units" in results else None
    if units is None:
        fact = read_table("fact_fu", configuration, results)
        if fact.empty:
            raise RuntimeError("series history not available: pass results=run_analysis(...) or an engine with sff_fact_fu")
        fact["fs_id"] = fact["fu_id"].str.rsplit("|", n=1).str[0]
        fact["sintetica"] = 0
        fact[configuration.period_col] = pd.PeriodIndex(fact[configuration.period_col].astype(str), freq="M")
        units = fact
    return units


def pick_showcase_series(configuration: Config = None, results: dict = None, min_history_months: int = 24) -> dict:
    """Three series to explain the three complexities: the most seasonal, the most trending
    (last 12 months), the biggest regime change — each the one with most money among the
    candidates with support. Plus the biggest mix-shift cell's biggest series."""
    card = read_table("series_card", configuration, results)
    dynamics = read_table("decision_dynamics", configuration, results)
    joined = card.merge(dynamics, on="id_estimacion", how="inner")
    joined = joined[(joined["ruta"] == "trainable") & (joined["meses_historia"] >= min_history_months) & (joined["gate"] != "soporte")]
    picks = {}

    def first_unused(frame):
        for _, candidate in frame.iterrows():
            if candidate["fs_id"] not in picks.values():
                return candidate["fs_id"]
        return None
    seasonal = joined[joined["estacional"] == 2].sort_values(["amp_estacional_pp", "usd_proyectado"], ascending=False)
    if len(seasonal):
        picks["estacional"] = first_unused(seasonal)
    trending = (joined[(joined["phi"] > 1.5) & (joined["estacional"] != 2)].assign(a=lambda f: f["pendiente_12m_pp_ano"].abs())
                .sort_values(["a", "usd_proyectado"], ascending=False))
    if len(trending):
        picks["tendencia"] = first_unused(trending)
    regime = joined[joined["cambio_nivel_fuerza"] >= 3].sort_values(["cambio_nivel_fuerza", "usd_proyectado"], ascending=False)
    if len(regime):
        picks["cambio_de_nivel"] = first_unused(regime)
    mix = read_table("mix_shift_decomposition", configuration, results)
    if len(mix):
        worst_cell = mix.groupby("celda_id")["delta_composicion_pp"].apply(lambda s: s.abs().mean()).idxmax()
        in_cell = card[(card["celda_id"] == worst_cell) & (card["ruta"] == "trainable")].sort_values("usd_proyectado", ascending=False)
        if len(in_cell):
            picks["mix_shift"] = in_cell.iloc[0]["fs_id"]
    return picks


def showcase_sheets(configuration: Config = None, results: dict = None, output_folder: str = None) -> dict:
    """The sheets of the showcase series. Returns {reason: path}."""
    picks = pick_showcase_series(configuration, results)
    paths = {}
    for reason, series_id in picks.items():
        print(f"\n[sheet] {reason}: {series_id}")
        paths[reason] = series_sheet(series_id, configuration, results, output_folder)
    return paths


def guess_game(series_id: str, months_hidden: int = 6, configuration: Config = None, results: dict = None,
               output_folder: str = None) -> tuple:
    """Two figures for the room: (question) the series up to the origin, the hidden months
    blank, "how would you predict them?"; (answer) the hidden truth, the challenger, the
    champion, and the band. The machine sees exactly what the room sees."""
    units = _units_frame(configuration, results)
    monthly = monthly_of(units, series_id, configuration)
    valid = monthly[monthly["rate"].notna()]
    periods = pd.PeriodIndex(valid.index, freq="M")
    rates, pipe = valid["rate"].to_numpy(dtype=float), valid["pipe"].to_numpy(dtype=float)
    origin = len(valid) - months_hidden
    x = np.arange(len(valid))
    from techniques import month_numbers_of, predict, CATALOGUE
    card = read_table("series_card", configuration, results)
    row = card[card["fs_id"] == series_id].iloc[0]
    technique = read_table("decision_technique", configuration, results)
    technique = technique[technique["id_estimacion"] == row["id_estimacion"]]
    champion = technique.iloc[0]["tecnica"] if len(technique) else "T3_ma3"
    challenger = configuration.challenger_technique if configuration else "T2_mean"
    dynamics = read_table("decision_dynamics", configuration, results)
    dynamics = dynamics[dynamics["id_estimacion"] == row["id_estimacion"]]
    labels = dict(estacional=int(dynamics.iloc[0]["estacional"]), tendencia=int(dynamics.iloc[0]["tendencia"])) if len(dynamics) else {}
    month_numbers = month_numbers_of(periods)
    folder = output_folder or os.path.join(configuration.outdir if configuration else ".", "diagnostics")
    os.makedirs(folder, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in series_id)[:60]
    paths = []
    for stage in ("question", "answer"):
        figure, axis = plt.subplots(figsize=(FIGURE_WIDTH, 6.5))
        low, high = binomial_band(rates[:origin], pipe[:origin])
        axis.fill_between(x[:origin], low, high, color="#3B8BC8", alpha=0.12)
        axis.plot(x[:origin], rates[:origin], "-o", color="#2E7D7D", linewidth=2.4, markersize=4, label="what you know")
        axis.axvspan(origin - 0.5, len(x) - 0.5, color="#E8B84F", alpha=0.15, label=f"the next {months_hidden} months")
        if stage == "answer":
            axis.plot(x[origin:], rates[origin:], "-o", color="black", linewidth=2.4, markersize=5, label="what happened")
            for technique_id, colour, style in ((challenger, "#7F8C8D", "--"), (champion, "#C0392B", "-")):
                if technique_id not in CATALOGUE:
                    continue
                predicted = [predict(technique_id, rates[:origin], month_numbers[:origin], h, labels) for h in range(1, months_hidden + 1)]
                error = 100 * np.mean(np.abs(np.array(predicted) - rates[origin:]))
                axis.plot(x[origin:], predicted, style, color=colour, linewidth=2.2, marker="s", markersize=4,
                          label=f"{technique_id} · {CATALOGUE[technique_id][1]} · |error| {error:.1f} pp")
        month_ticks(axis, periods)
        axis.set_ylim(0, 1.0)
        axis.set_ylabel("renewal rate", fontsize=12)
        title = (f"{series_id[:60]} · n≈{row['n_propio']:.0f}/month · how would YOU predict the shaded months?" if stage == "question"
                 else f"{series_id[:60]} · the answer: truth vs the challenger and the champion")
        axis.set_title(title, fontsize=13, loc="left")
        axis.legend(fontsize=9, loc="lower left", framealpha=0.9)
        figure.tight_layout()
        path = os.path.join(folder, f"game_{safe}_{stage}.png")
        figure.savefig(path, dpi=110)
        plt.close(figure)
        paths.append(path)
    print(f"[game] {series_id}: {paths[0]} / {paths[1]}")
    return tuple(paths)


def technique_error_by_horizon(key, configuration: Config = None, results: dict = None, output_folder: str = None) -> str:
    """ONE figure: mean |error| (binomial units) by horizon, one line per technique, for
    the pool a key points at. The champion of each band is marked. This is where "simple
    wins near, shape wins far" (or not) becomes visible."""
    from sheet import resolve_key
    keys = resolve_key(key, configuration, results)
    estimation_id = keys["id_estimacion"]
    predictions = read_table("backtest_predictions", configuration, results)
    block = predictions[predictions["id_estimacion"] == estimation_id]
    if block.empty:
        raise KeyError(f"no backtest predictions for {estimation_id} (under the floor, or backtest not run)")
    decision = read_table("decision_technique", configuration, results)
    decision = decision[decision["id_estimacion"] == estimation_id]
    table = block.assign(abs_norm=block["err_norm"].abs()).groupby(["tecnica_id", "h"])["abs_norm"].mean().unstack("h")
    counts = block.groupby(["tecnica_id", "h"]).size().unstack("h")
    figure, axis = plt.subplots(figsize=(FIGURE_WIDTH, 6.5))
    order = table.mean(axis=1).sort_values().index
    for index, technique_id in enumerate(order):
        row = table.loc[technique_id].dropna()
        judged_everywhere = counts.loc[technique_id].reindex(row.index).fillna(0) > 0
        style = "-" if len(row) >= 3 else "--"
        axis.plot(row.index, row.values, style, marker="o", markersize=5, linewidth=2.2 if index < 4 else 1.4,
                  color=PALETTE[index % len(PALETTE)], alpha=1.0 if index < 6 else 0.6, label=technique_id)
    for _, band in decision.iterrows():
        h_lo, h_hi = int(band["h_min"]), int(min(band["h_max"], table.columns.max()))
        axis.axvspan(h_lo - 0.4, h_hi + 0.4, alpha=0.06, color="grey")
        axis.text((h_lo + h_hi) / 2, axis.get_ylim()[1] * 0.97 if axis.get_ylim()[1] > 0 else 1, f"{band['tramo_h']}: {band['tecnica']}\n({band['tecnica_origen']})",
                  ha="center", va="top", fontsize=9)
    axis.axhline(1.0, color="black", linewidth=0.8, linestyle=":", label="1.0 = one sampling error (the floor)")
    axis.set_xlabel("horizon h (months ahead)", fontsize=12)
    axis.set_ylabel("mean |error| in binomial units", fontsize=12)
    axis.set_xticks(sorted(table.columns))
    axis.set_title(f"{estimation_id[:70]} · backtest error by horizon and technique (n≈{block['n_real'].median():.0f}/month)", fontsize=13, loc="left")
    axis.legend(fontsize=8, ncol=2, framealpha=0.9)
    figure.tight_layout()
    folder = output_folder or os.path.join(configuration.outdir if configuration else ".", "diagnostics")
    os.makedirs(folder, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in estimation_id)[:70]
    path = os.path.join(folder, f"horizon_{safe}.png")
    figure.savefig(path, dpi=110)
    plt.close(figure)
    print(f"[diag] error by horizon of {estimation_id}: {path}")
    return path
