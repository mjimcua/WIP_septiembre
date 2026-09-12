"""main.py — SFF v2 end-to-end on the synthetic dataset. python main.py [seed] | --golden"""
import sys
from config import Config
from synthetic import build_raw
import fase0 as f0
import fase1 as f1
import fase2 as f2
import fase3_assembly as f3
import fase4_backtest as f4
import validation

from sqlalchemy import create_engine
ENGINE = create_engine("sqlite:///salida/sff_v2.db")   # demo: for real SQL, inject your mssql engine
cfg = Config(sql_engine=ENGINE, sql_schema=None, business_mandatory_dims=["region"],
             structural_timevarying_dims={"dormant": "negative", "softcancel": "negative",
                          "no_instalado": "negative", "autorenew": "positive"},
             extra_renovacion=["product", "channel"],  # semantic_labels: empty by default
             extra_revalorizacion=["discount", "newcust"])
if "--golden" in sys.argv:
    import pandas as pd
    raw = pd.read_csv("raw_golden.csv", keep_default_na=False, na_values=[""])  # "NA" is North America, not NaN
else:
    raw = build_raw(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
print("═" * 70, "\nPHASE 0 — contract, load, reference")
df = f0.f0_load_and_validate(raw, cfg)
fu_view, fine_grain_table, fu_lookup, comb_lookup = f0.f0_split_and_key(df, cfg)
cfg.write(fu_view, "fact_fu"); cfg.write(fine_grain_table, "fact_fine")
cfg.write(fu_lookup, "lookup_fu"); cfg.write(comb_lookup, "lookup_comb")
v = f0.f0_universe_routes(fu_view, cfg)
fu_summary = f0.f0_fu_summary(v, cfg)   # la referencia inmutable: se persiste, no la consume ninguna fase
print("═" * 70, "\nPHASE 1 — renewal branch")
v, series_summary = f1.f1_series_and_gaps(v, cfg)
# gap-filler rows (sintetica=1) persisted so BI can see WHICH months were imputed
gap_rows = v[v["sintetica"] == 1][["fu_key", "fu_id", "fs_id", cfg.period_col,
    cfg.dataset_role_col] + cfg.medidas + ["sintetica"]].copy()
gap_rows[cfg.period_col] = gap_rows[cfg.period_col].astype(str)
cfg.write(gap_rows, "fact_fu_gaps")
eta2_by_dim, eta2_pairs, counterfactual_table = f1.f1_diagnose_round1(v, series_summary, cfg)
v2, series_estimates, support_chain_rows = f1.f1_improve_support(v, series_summary, eta2_by_dim, cfg)
f1.f1_support_chain(support_chain_rows, cfg)
dynamics_diagnosis = f1.f1_diagnose_round2(v2, series_estimates, cfg)
print("═" * 70, "\nPHASE 2 — revaluation branch")
uplift_cells, r = f2.f2_uplift_fine(fine_grain_table, cfg)
uplift_eta2_by_axis = f2.f2_diagnose(uplift_cells, r, cfg)
uplift_cells, uplift_chain_rows = f2.f2_improve(uplift_cells, uplift_eta2_by_axis, cfg)
print("═" * 70, "\nPHASE 3 — assembly")
key_bridge = f3.f3_build_key_bridge(fine_grain_table, v2, series_estimates, cfg)
future_rows = f3.f3_ensamblaje(fine_grain_table, v2, series_estimates, uplift_cells, cfg)
print("═" * 70, "\nPHASE 4 — backtest by horizon")
backtest_long, technique_selection, rate_series_by_pool = f4.f4_backtest(v2, series_estimates, cfg)
rolling_table, rolling_summary = f4.f4_rolling_next_month(v2, cfg)
forecast_bands = f4.f4_forecast_bands(future_rows, rolling_table, technique_selection,
                                     series_estimates, rate_series_by_pool, cfg)
technique_dim, backtest_per_fu, forecast_per_fu = f4.f4_tablas_fu(v2, fine_grain_table, series_estimates, uplift_cells, backtest_long, rate_series_by_pool, cfg)
horizon_series, horizon_total = f4.f4_horizon_report(rolling_table, technique_selection,
                                                    forecast_bands, future_rows, cfg)
validation.run_validation(dict(fine_grain_table=fine_grain_table, fu_view=v,
    key_bridge=key_bridge, future_rows=future_rows, support_chain_rows=support_chain_rows,
    rolling_table=rolling_table, technique_selection=technique_selection,
    forecast_bands=forecast_bands, dynamics_diagnosis=dynamics_diagnosis,
    uplift_cells=uplift_cells), cfg)
print("═" * 70, "\n✓ full run complete · tables in", cfg.outdir)
