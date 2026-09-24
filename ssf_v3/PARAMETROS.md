# PARÁMETROS CONFIGURABLES — versión candidata

Generado del bloque TUNABLE PARAMETERS de `config.py` (la fuente de verdad es el código). Cada parámetro: para qué vale, por qué ese valor por defecto y qué mirar antes de cambiarlo. Al final, las constantes de algoritmo que viven en los módulos y NO son configuración.

## the binomial reference (every phase)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `z` | `1.645` | Confidence multiplier for every interval and bound. 1.645 = 90 % two-sided: the level the business reads ("nine times out of ten"). 1.96 would give 95 % and bands ~20 % wider; the hold-out calibration (P3.2) tells whether 90 % is honoured. |
| `rate_cap` | `0.95` | Renewal rates above this are saturated. A 95 % ceiling keeps a small series with a lucky 100 % month from forecasting 100 %; no real cohort renews above it. Raise it only if the calibration table (tv_calibration) shows real cohorts above 95 %. |

## phase 0 · the calendar of roles (from the current month, not from the raw)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `pending_close_months` | `1` | The raw's dataset_role is OVERWRITTEN from the current month (`is_current_month`): current month and later      → projection (results wiped: the future has not started) the month(s) just before     → pending_close: not closed yet (people renew after expiry); NOT used to evaluate, NOT used to learn; forecast like a projection month, reported apart the `test_months` before     → test: the exam (evaluation only) everything earlier           → train Forecasting learns from train AND test (every closed month); only the choice of technique and its bands are decided without the test months. |
| `test_months` | `6` |  |

## phase 1.1 · rate series

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|

## phase 1.2 · dimension separation and mix-shift (ANALYSIS)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `counterfactual_window_months` | `12` | Months with truth judged by the walk-forward valuation of the mandatory-only view (one rate per cell vs the segmented series, each month against what happened). 12 = one full year of verdicts, so a seasonal cell is judged in every season. More months = more evidence, older past. |
| `counterfactual_min_history_months` | `6` | A cell needs this many past months before its first verdict; below it the "flat" rate is itself noise and the comparison says nothing. 6 = half a year. |
| `eta2_max_pairs` | `15` | Pairs of dimensions kept in decision_eta2_pairs (pairs explode combinatorially with many dims); the top by interaction. 15 is what fits on one screen. |

## phase 1.3 · support ladder and credibility (RUN)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `support_floor` | `30.0` | The support floor: median monthly pipeline units a relative needs to be "enough". 30 is the dial at ±15 pp (90 %, p=.5): below it a month's rate says almost nothing. It is the one parameter that moves the whole ladder: raise it and more series borrow (and level B/C grow); lower it and more series keep noisy own rates. The money by risk level (risk_levels) is the table to look at before touching it. |
| `own_rate_floor` | `271.0` | The precision floor: a series with n_propio ≥ this predicts ALONE (z = 1); below it, even with support of its own, it climbs to its first relative with support and blends with z = n/(n+k). 271 is the dial at ±5 pp: the promise to the business. Between 30 and 271 there is evidence but not precision: it is used, weighted, and completed with the pool. 30 says who may speak; 271 says who may speak alone. |
| `k_cred` | `60.0` | Default credibility k (Bühlmann-Straub) when a relative has fewer than 3 siblings with history, so no between/within variance can be estimated. z = n/(n+k): with k=60 a series with n=30 keeps 33 % of its own rate; with n=12, 17 %. 60 ≈ two floors: "you need twice the floor to be believed half". Estimated k's (decision_support.k) override it wherever there are siblings. |
| `close_relative_max_rung` | `2` | Risk level "B_prestado" vs "C_lejano": a relative at rung ≤ 2 (same sign / extra annulled) is close; from rung 3 (the mandatory cell or above) it is far. The distinction is the money report's, not the estimate's. |
| `own_level_min_history_months` | `12` | Months of history a series needs to be level "A_propio" even when it has support: one full year, so a seasonal series has seen every season. |
| `signed_ladder_max_loss` | `0.05` | How far a series WITH SIGN may climb beyond its mandatory cell × sign, keeping the sign: it may collapse mandatory dims in the sequential order while the CUMULATIVE R² lost (decision_eta2.perdida_secuencial) stays ≤ this. 0.0 = the strict rule (the ladder of a signed series ends at the cell × sign). 0.05 (default) lets it collapse the dims that separate almost nothing (in Kamelot: band_2, band_1, product_2, product_1), i.e. cohorts nearly identical — pooled signal, not mixed cohorts. With 10 mandatory dims the strict rule left 4,237 signed series ($8.3M) without a pool. |

## phase 4 · the contract path of the uplift

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `discount_value_column` | `None` | Where the customer's CURRENT discount is known, the renewal price is not estimated: the contract fixes it. `discount_value_column` names the raw column with the exact discount in tanto por 1 (0.30 = 30 %); 0 = list price, null = unknown (never read as 0). It is a formula input, not a cell dimension: it rides along every raw row (nulls allowed), it is not part of any id, and it does not cut the support. The row's uplift = price_increase(period) / (1 − discount) × realization ratio of its cell; rows with an unknown discount (or one above `discount_cap`, near-free licences) take the statistical uplift of their cell as before. None = every row is statistical. |
| `price_increase_by_period` | `{}` | Multiplicative list-price increases by period ({"2027-01": 1.05}); the factor of a month is the product of every increase dated at or before it. Empty = no increase. |
| `discount_cap` | `0.9` | Discounts above this are treated as unknown (1/(1−d) explodes for near-free licences). |
| `contract_apply_realization_ratio` | `True` | The realization ratio (observed uplift / rule uplift, dollar-weighted, per uplift cell) corrects the rule where renewal offers make customers renew below list. Applied only where the cell has ≥ uplift_floor renewers with a known discount; else 1.0. |
| `statistical_uplift_from_unknown_only` | `False` | Estimate the statistical uplift only with rows whose discount is unknown (pending confirmation: if the missing discount is not random, mixing both populations biases it). |

## phase 1.5 · discount and churn (ANALYSIS)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `discount_column` | `None` | The column with the discount bucket (None = the first extra de revalorización whose name contains "disc") and the value that means "no discount" (None = the first bucket in sorted order). The analysis compares every bucket to that reference. |
| `no_discount_value` | `None` |  |

## phase 2 · the seasonality benchmark (ANALYSIS)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `technique_history_months` | `None` | Months of history the TECHNIQUES see (backtest, forecast): None = all. The ladder and the pools always use the whole history (support is support); this only cuts what the techniques learn from. Try 24 and compare the hold-out of the total. |
| `benchmark_group_dims` | `[]` | One decision for the whole portfolio, taken where the test has power: the biggest NEUTRAL series (no flag), fully segmented, with support ≥ benchmark_min_support in EVERY closed month (±5 pp floor or better), top N by money inside each group of benchmark_group_dims (None = the first two mandatory dims). Seasonal if amplitude ≥ benchmark_amplitude_pp AND both extreme months keep their sign in ≥ benchmark_consistency of the years AND the seasonal shape improves the recent level by ≥ benchmark_improvement_pct at h=6 without worsening it at h=1. If the seasonal series carry less than benchmark_material_share_pct of the sample's money, the rate has NO material seasonality and the rate branch keeps level techniques only. |
| `benchmark_top_n` | `5` |  |
| `benchmark_min_support` | `271.0` |  |
| `benchmark_min_months` | `36` |  |
| `benchmark_short_months` | `24` |  |
| `benchmark_min_years` | `2` |  |
| `benchmark_amplitude_pp` | `2.0` |  |
| `benchmark_consistency` | `0.67` |  |
| `benchmark_improvement_pct` | `10.0` |  |
| `benchmark_material_share_pct` | `10.0` |  |
| `benchmark_min_extreme_z` | `1.0` | The extreme months must ALSO stand out of the noise: their mean standardized residual \|z\| (rate − trend, in binomial errors) ≥ this. Without it, on 40 simulated pure-noise series the criteria declared 4 seasonal (10 %); with it, 0, and the power on an 8 pp planted season stayed at 34/40. Measured, not assumed (test_statistics S5). |

## phase 3 · backtest, technique, bands (ANALYSIS)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `backtest_test_start` | `None` | First month of the hold-out: the months ≥ this are NEVER used to choose techniques or to measure bands; they are the exam. None = the first month with role 'test' in the extract (the extract's own split), else the last `holdout_default_months`. Training always uses the whole history before each origin. |
| `holdout_default_months` | `6` |  |
| `backtest_min_history_months` | `8` | Months of history before the first origin. 8 = enough for every non-seasonal technique to be eligible (ma6, ses, drift); seasonal ones wait for 13 anyway. |
| `backtest_max_targets` | `6` | The judge uses only the most recent target months: the business changes, so the evidence must be as recent as possible. 6 = the last half year of verdicts. |
| `backtest_horizons` | `[1, 6]` | Horizons judged. Sparse on purpose (bands are monotone in h, so the nearest lower judged horizon is a safe band for the ones in between); the forecast horizon H is added automatically. [1,2,3,4] for the operational months, 6/9/12 for the year. TWO test batteries, two views: the SHORT one (predict next month with data up to the previous month: h=1) and the MEDIUM-LONG one (predict a month with data up to six months before: h=6). Months further than six ahead use the six-month evidence and are re-forecast every month. |
| `backtest_screen_horizons` | `[1, 6]` | Two-stage judge: every eligible technique is screened at these horizons to choose the champion; then only champion + challenger are judged at every horizon. {1,3,6} covers the operational month, the quarter and the half-year with ~3× less cost. |
| `backtest_horizon_bands` | `{"corto": [1, 1], "medio_largo": [2, 999]}` | Horizon bands: ONE champion per band, not one per pool. A 3-month average wins the near months and knows nothing about January twelve months out; a seasonal or mixed technique may lose at h=1 and win at h=12. Each band is judged with the screen horizons that fall inside it (so every band needs at least one screen horizon). h=1 is a band of its own: the current month is the forecast the business trusts first, so its technique is chosen on its own evidence. Beyond `backtest_horizon_cap` nothing is judged: a month 16 ahead is predicted as if 12 ahead (same technique, same band). The error there is large and declared, not measured. |
| `backtest_horizon_cap` | `6` |  |
| `backtest_persist` | `"chosen"` | What to persist of the long backtest table (`backtest_pred`): "chosen" = only the rows of each band's champion and the challenger (~25 % of the rows: enough to audit the decision and the hold-out); "all" = every technique (the full error-by-horizon figure from SQL; in Kamelot 2M rows, ~3 minutes of writing); "none". The full table stays in memory (results["backtest"]["backtest_long"]) during the session either way. |
| `backtest_workers` | `1` | Parallel workers for the backtest (1 = sequential; identical result). Useful with thousands of estimation ids on a multi-core machine; harmless otherwise. |
| `backtest_min_predictions` | `6` | Minimum predictions a technique needs to dethrone the challenger: 6 = at least half a year of verdicts at the screen horizons. |
| `challenger_technique` | `"T3_ma3"` | The challenger: the technique a champion must beat. The 3-month average ("what happened last quarter"): in Kamelot it beat the whole-history mean in every horizon band (2.1 vs 3.6 binomial units near, 4.5 vs 4.7 far) because the rate moves by level changes, not by season. A champion has to beat THAT to be a champion. |
| `challenger_margin_normalized` | `0.10` | Margin, in units of the binomial error, by which a champion must beat the challenger (and within which techniques tie → the richer family wins). 0.10 = a tenth of a sampling error: enough to ignore luck, small enough to let real signal through. The leaderboard (P3.1) shows how far apart techniques really are. |
| `challenger_margin_by_band` | `{"corto": 0.10, "medio_largo": 0.0}` | Margin per horizon band, overriding the one above where set. Far from now the challenger (a short window) carries no information about the shape of the future, so a technique that merely TIES it there should be allowed to win when it uses more history: the margin to dethrone the challenger shrinks with the horizon, and within the margin the technique with the longest MEMORY wins (see techniques.MEMORY_MONTHS). Never below zero: a technique still has to be at least as good as the challenger. |
| `richer_family_min_history_months` | `24` | Among techniques within the margin of the best, the technique with more memory (and then the richer family: time series > smoothing > average) wins — but only when the id has at least this many months of history: a month-effect technique chosen on 14 months is a story, not a model. 24 = two full cycles. Below it, the simplest wins. |
| `band_min_predictions` | `20` | Predictions an (id, h) needs for its OWN error quantiles; below it the band comes from the family (same technique, every id). 20 predictions make a p5/p95 that is not just the extremes. |
| `band_low_quantile` | `0.05` | The band quantiles of the signed normalized error: p5 / p95 → a 90 % band, matching z. Widen to .025/.975 for 95 %. The hold-out "% inside band" is the check. |
| `band_high_quantile` | `0.95` |  |
| `intermittent_zero_share` | `0.30` | Share of near-zero months (rate < 2 %) above which a series is "intermittent" and the SBA technique competes. 30 %: below it, the zeros are just bad months. |

## phase 4 · uplift (RUN)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `uplift_mandatory_dims` | `None` | The mandatory dims that open an uplift cell. None = every mandatory dim (cell = mandatory + extra_revalorizacion). With 10 mandatory dims that made 25,710 cells in Kamelot, 70 % below the floor: a subset (e.g. regional_level_1, product_level_1, purchase_type, term_level_2) keeps the revaluation drivers and gives cells with enough renewers. Every dim listed must be a mandatory dim. |
| `uplift_floor` | `30.0` | Renewers a cell needs to use its own ratio; below it the parent's (starting-point extras kept) or the mandatory cell's. 30, like the rate floor: an uplift is a ratio of the money of ~30 renewers before it stops jumping. |
| `uplift_cap` | `3.0` | Ratios above this are clipped and flagged `recortado`. 3.0: a renewer paying three times the pipeline AUV is a data problem (a bundle, a currency), not a revaluation. |
| `uplift_parent_keep_columns` | `[]` | extra_revalorizacion columns KEPT in the parent cell: the "starting point" (e.g. newcust) that a small cell must not lose when it borrows. Empty = the parent is the mandatory cell. |
| `uplift_window_months` | `None` | Months of history the uplift is estimated on: None = all. The uplift tracks the discount mix, recovery campaigns (lower it) and price rises (raise it): a price rise is a step, and the whole-history ratio averages before and after. 12 keeps the current price regime. The parent/cell fallbacks use the same window. |
| `uplift_bootstrap_samples` | `200` | Bootstrap resamples for the uplift band. 200 gives a stable p5/p95 in milliseconds (numpy resampling); 1000 changes the third decimal. |

## phase 5 · assembly and extended horizon (RUN)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `max_forecast_horizon` | `None` | None = derived: months from the last month with truth to the end of the forecast (known projection or extended horizon). Set it only to cut the forecast short. |
| `extended_horizon_end` | `None` | Simulate the pipeline beyond the known projection up to this month ("2027-12"). None = no extension. Everything built on simulated rows is flagged (simulada = 1) and reported (horizon_report_total.pct_simulado). |
| `renewal_term_months` | `12` | A renewed contract re-enters the pipeline after its term. `renewal_term_months` is the default (12 = yearly). A mixed-term portfolio declares the column that carries the term and the months of each value: e.g. term_column = "term_level_2", term_months_by_value = {"1 year": 12, "2 year": 24, "3 year": 36}; values not in the map fall back to the default. Used by the extended horizon and the acquisition factor. |
| `term_column` | `None` |  |
| `term_months_by_value` | `{}` |  |
| `acquisition_factor` | `None` | pipeline(m) = renewed(m − term) × factor. None = estimated from history per series (median of pipeline(t) / renewed(t − term) = 1 + acquisitions / renewals; global fallback). Set a number to impose a business assumption on acquisition. |
| `extension_row_filter` | `{}` | Only rows matching this filter re-enter the simulated pipeline: column → allowed values, e.g. {"term_level_2": ["1 year"]}. Multi-year contracts renewed now fall due beyond the horizon and their known expirations are already in the pipeline; only the 12-month ones (renewals AND acquisitions) shape next year. {} = every row. |
| `acquisition_min_pairs` | `3` | The simulated pipeline is valued at the RENEWED price: a contract renewed in 2026 at pipeline AUV × uplift is worth that when it falls due in 2027 (observed renewed AUV where there is truth, pipeline AUV × the cell's uplift where there is not). The 2027 forecast then applies rate × uplift again on that revalued pipeline. Pairs (t, t − term) a series needs for its own acquisition factor; below it the global one. 3 = a median that is not a single point. |
| `band_narrowing_tolerance_pct` | `1.0` | The total's relative band may narrow from one month to the next when the mix leans toward well-supported series; a narrowing beyond this many percentage points of the total is flagged in horizon_report_total.banda_monotona. Per id the band never narrows (by construction); this is a mix signal, not a calibration one. |

## phase 5.9 · maturation of the signals (RUN)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `signal_final_window_months` | `12` | The final composition of a cell (neutral / softcancel / dormant…) is measured over the last N closed months; the pending maturation of a future month is that final share minus today's share. 12 = a full year of expiries. |

## sheets drawn at the end of every analysis

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `sheets_top_series` | `5` | After the forecast, the sheet (six-panel figure + story) of the N series with the most projected money is drawn into <outdir>/diagnostics/. 5 by default; 0 disables. |

## console

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `console_top_rows` | `15` | Rows printed per listing (cells, champions, candidates...). The tables hold everything; the console shows the top by support or money. 15 fits a screen. |
| `console_explanations` | `True` | Print, after every block of numbers, two or three lines that say how to read them (what a binomial unit is, what a band promises, why the mean is not the forecast). Off for the delegated monthly run once the reader knows the framework. |

## baseline (ANALYSIS)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `baseline_grains` | `["global", "mandatory"]` | Grains of the spreadsheet baseline: "global" (one dollar rate for the portfolio), "mandatory" (every mandatory dim), or a '+'-joined list of columns (a coarse cut, e.g. "regional_level_1+product_level_1+purchase_type"). Each grain × window (1, 3, 12 months) gives a forecast and its own walk-forward error, next to the framework's. |

## governance

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `timevarying_model_version` | `{}` | Version (as-of) of the model that produces each timevarying flag, stamped on the calibration table so a flag's realized rate can be compared across versions. |
| `decision_max_age_months` | `6` | The monthly run warns when the decision tables are older than this. 6 months: two seasons; the ladder and the champions should be re-judged at least twice a year. |
| `random_seed` | `7` | Seed of every random draw (uplift bootstrap): the same run gives the same band. |

## Constantes de algoritmo (en los módulos, no en Config)

No son decisiones de negocio: son parte de la definición de cada técnica o de la referencia. Se documentan aquí para que se sepa que existen y dónde están.

| Módulo | Constante | Valor | Qué es |
|---|---|---|---|
| `binomial_reference.py` | `MIN_PROPORTION_VARIANCE` | 0.0475 | suelo de p(1−p) (= varianza de una tasa del 5 %) para que una muestra con 0 % o 100 % no reclame error cero |
| `binomial_reference.py` | `LOGIT_CLIP` | 1e-4 | las tasas se recortan a (1e-4, 1−1e-4) antes del logit |
| `techniques.py` | `EWMA_HALFLIFE_MONTHS` | 3 | vida media de la media exponencial (T4) |
| `techniques.py` | `SES_ALPHA` | 0.3 | suavizado exponencial simple (T9, T12) |
| `techniques.py` | `HOLT_ALPHA / HOLT_BETA / HOLT_DAMPING` | 0.3 / 0.1 / 0.9 | Holt amortiguado (T10); el damping 0.9 también amortigua T5 y T8 |
| `techniques.py` | `HW_ALPHA / HW_BETA / HW_GAMMA` | 0.3 / 0.05 / 0.2 | Holt-Winters aditivo en logit (T11) |
| `techniques.py` | `THETA_WEIGHT` | 0.5 | peso de la tendencia amortiguada frente a SES en Theta (T12) |
| `techniques.py` | `TEMPORAL_CREDIBILITY_K / RECENT_WINDOW_MONTHS` | 6 / 6 | credibilidad temporal (T14): ventana reciente y su k |
| `techniques.py` | `CATALOGUE[...].historia_minima / requiere` | por técnica | elegibilidad: meses mínimos y etiqueta necesaria (`dim_tecnica`) |
| `techniques.py` | `MONTHS_PER_CYCLE` | 12 | el ciclo del efecto de mes (T15) |
| `run_uplift.py` | `MIN_UPLIFT` | 0.01 | suelo del uplift recortado |
| `run_forecast_assembly.py` | `DEFAULT_ACQUISITION_FACTOR` | 1.0 | factor global cuando no hay ningún par (t, t−plazo) en la historia |
| `raw_data_validation.py` | `CURRENT_MONTH_TRUTHY_VALUES` | 1, True, "1", "true", "yes", "si" | valores que marcan el mes en curso |
| `raw_data_validation.py` | `MONEY_CONSERVATION_TOLERANCE_USD` | 1e-6 | tolerancia de la conservación de dinero fina ↔ unidades |

Estas constantes de suavizado (alphas, damping) son candidatas a optimizarse por serie en el backtest (grid pequeño) en una versión futura; hoy son fijas para que dos ejecuciones den la misma técnica con los mismos números.
