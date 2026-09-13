# PARÁMETROS CONFIGURABLES — versión candidata

Generado del bloque TUNABLE PARAMETERS de `config.py` (la fuente de verdad es el código). Cada parámetro: para qué vale, por qué ese valor por defecto y qué mirar antes de cambiarlo. Al final, las constantes de algoritmo que viven en los módulos y NO son configuración.

## the binomial reference (every phase)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `z` | `1.645` | Confidence multiplier for every interval and bound. 1.645 = 90 % two-sided: the level the business reads ("nine times out of ten"). 1.96 would give 95 % and bands ~20 % wider; the hold-out calibration (P3.2) tells whether 90 % is honoured. |
| `rate_cap` | `0.95` | Renewal rates above this are saturated. A 95 % ceiling keeps a small series with a lucky 100 % month from forecasting 100 %; no real cohort renews above it. Raise it only if the calibration table (tv_calibration) shows real cohorts above 95 %. |

## phase 1.1 · rate series

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `gap_rate_policy` | `"no_rate"` | A missing month means "no contracts were due": the rate is undefined (0/0), NOT 0 %. "no_rate" is the only implemented policy (the synthetic gap row keeps the series continuous but its rate is NaN, so no technique ever sees a false 0 % month). The field exists so the decision is visible, not so it can be flipped. |

## phase 1.2 · dimension separation and mix-shift (ANALYSIS)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `counterfactual_window_months` | `12` | Months with truth judged by the walk-forward Simpson counterfactual (flat vs segmented, each month against what happened). 12 = one full year of verdicts, so a seasonal cell is judged in every season. More months = more evidence, older past. |
| `counterfactual_min_history_months` | `6` | A cell needs this many past months before its first verdict; below it the "flat" rate is itself noise and the comparison says nothing. 6 = half a year. |
| `eta2_max_pairs` | `15` | Pairs of dimensions kept in decision_eta2_pairs (pairs explode combinatorially with many dims); the top by interaction. 15 is what fits on one screen. |

## phase 1.3 · support ladder and credibility (RUN)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `support_floor` | `30.0` | The support floor: median monthly pipeline units a relative needs to be "enough". 30 is the dial at ±15 pp (90 %, p=.5): below it a month's rate says almost nothing. It is the one parameter that moves the whole ladder: raise it and more series borrow (and level B/C grow); lower it and more series keep noisy own rates. The money by risk level (risk_levels) is the table to look at before touching it. |
| `k_cred` | `60.0` | Default credibility k (Bühlmann-Straub) when a relative has fewer than 3 siblings with history, so no between/within variance can be estimated. z = n/(n+k): with k=60 a series with n=30 keeps 33 % of its own rate; with n=12, 17 %. 60 ≈ two floors: "you need twice the floor to be believed half". Estimated k's (decision_support.k) override it wherever there are siblings. |
| `close_relative_max_rung` | `2` | Risk level "B_prestado" vs "C_lejano": a relative at rung ≤ 2 (same sign / extra annulled) is close; from rung 3 (the mandatory cell or above) it is far. The distinction is the money report's, not the estimate's. |
| `own_level_min_history_months` | `12` | Months of history a series needs to be level "A_propio" even when it has support: one full year, so a seasonal series has seen every season. |
| `signed_ladder_max_loss` | `0.0` | How far a series WITH SIGN may climb beyond its mandatory cell × sign, keeping the sign: it may collapse mandatory dims in the sequential order while the CUMULATIVE R² lost (decision_eta2.perdida_secuencial) stays ≤ this. 0.0 = the sealed doctrine (the ladder of a signed series ends at the cell × sign). 0.05 lets it collapse the dims that separate almost nothing (in Kamelot: band_2, band_1, product_2, product_1), i.e. cohorts nearly identical — pooled signal, not Simpson. Watch S_signo_bajo_suelo. |

## phase 2 · dynamics (ANALYSIS)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `seasonality_min_months` | `13` | Months of history before seasonality or trend are even measured (13 = one full cycle plus one month, the minimum for a calendar profile). Below it the gate is "temporal" and the mean is used. |
| `signal_multiple_of_bound` | `2.0` | Seasonal amplitude / yearly slope must exceed this many times the binomial bound of the pool's typical month to be declared. 2× = the movement is at least twice what sampling alone would produce. Lower to 1.5 to be more sensitive (more series compete with seasonal/trend techniques; the backtest still has the last word). |
| `phi_engine_threshold` | `1.5` | φ (observed variance / binomial variance) above which "there is an engine". A series is declared seasonal or trending ONLY above it: with φ ≈ 1 the rate only samples, and any amplitude or slope measured on it is noise (in Kamelot, hundreds of ids with φ < 1.3 showed 20-36 pp of "amplitude" on one cycle: pure sampling). |
| `seasonal_requires_firm` | `True` | Seasonal techniques (T6, T7, T11) compete only on FIRM seasonality (≥ 2 full cycles, estacional = 2). With one cycle the seasonal index is last year's noise: in Kamelot they scored 5.4 binomial units on the screen against 2.3 for a 3-month average. |
| `trend_horizon_months` | `6` | Horizon after which a detected trend is considered fully damped (the inference cap): 6 months. Beyond it the techniques' own damping (φ=0.9) has removed most of the trend anyway; the label is what the forecast_by_level reader sees. |

## phase 3 · backtest, technique, bands (ANALYSIS)

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `backtest_test_start` | `None` | First month of the hold-out report ("the 2026 months that already happened"): months ≥ this with truth are reported as the out-of-sample exam. None = the last 12 months with truth. Training always uses the WHOLE history before each origin. |
| `backtest_min_history_months` | `8` | Months of history before the first origin. 8 = enough for every non-seasonal technique to be eligible (ma6, ses, drift); seasonal ones wait for 13 anyway. |
| `backtest_max_targets` | `24` | The judge uses only the most recent targets (the hold-out is inside them). 24 = two years of verdicts, so both seasons and the recent regime count. Halve it if the backtest is slow; the champion changes little, the bands lose evidence. |
| `backtest_horizons` | `[1, 2, 3, 4, 6, 9, 12]` | Horizons judged. Sparse on purpose (bands are monotone in h, so the nearest lower judged horizon is a safe band for the ones in between); the forecast horizon H is added automatically. [1,2,3,4] for the operational months, 6/9/12 for the year. |
| `backtest_screen_horizons` | `[1, 3, 6]` | Two-stage judge: every eligible technique is screened at these horizons to choose the champion; then only champion + challenger are judged at every horizon. {1,3,6} covers the operational month, the quarter and the half-year with ~3× less cost. |
| `backtest_workers` | `1` | Parallel workers for the backtest (1 = sequential; identical result). Useful with thousands of estimation ids on a multi-core machine; harmless otherwise. |
| `backtest_min_predictions` | `6` | Minimum predictions a technique needs to dethrone the challenger: 6 = at least half a year of verdicts at the screen horizons. |
| `challenger_technique` | `"T2_mean"` | The challenger: the technique a champion must beat. The mean of the whole history is the natural one — it is the best forecast wherever φ ≈ 1. |
| `challenger_margin_normalized` | `0.10` | Margin, in units of the binomial error, by which a champion must beat the challenger (and within which techniques tie → the richer family wins). 0.10 = a tenth of a sampling error: enough to ignore luck, small enough to let real signal through. The leaderboard (P3.1) shows how far apart techniques really are. |
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

## console

| Parámetro | Defecto | Para qué vale · por qué ese valor · qué mirar |
|---|---|---|
| `console_top_rows` | `15` | Rows printed per listing (ids with an engine, cells, champions...). The tables hold everything; the console shows the top by support or money. 15 fits a screen. |

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
| `analysis_dynamics.py` | `MONTHS_PER_CYCLE` | 12 | el ciclo estacional |
| `run_uplift.py` | `MIN_UPLIFT` | 0.01 | suelo del uplift recortado |
| `run_forecast_assembly.py` | `DEFAULT_ACQUISITION_FACTOR` | 1.0 | factor global cuando no hay ningún par (t, t−plazo) en la historia |
| `raw_data_validation.py` | `CURRENT_MONTH_TRUTHY_VALUES` | 1, True, "1", "true", "yes", "si" | valores que marcan el mes en curso |
| `raw_data_validation.py` | `MONEY_CONSERVATION_TOLERANCE_USD` | 1e-6 | tolerancia de la conservación de dinero fina ↔ unidades |

Estas constantes de suavizado (alphas, damping) son candidatas a optimizarse por serie en el backtest (grid pequeño) en una versión futura; hoy son fijas para que dos ejecuciones den la misma técnica con los mismos números.
