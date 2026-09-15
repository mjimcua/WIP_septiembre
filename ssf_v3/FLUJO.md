# FLUJO — todos los métodos de `run_analysis`, en orden de llamada

Numeración jerárquica: el entero es el paso que llama `pipeline.run_analysis`; los
decimales, los métodos que ese paso llama a su vez, en el orden en que los llama. Cada
fila: método (módulo), propósito, salida esperada (tabla persistida en **negrita**).
`run_pipeline` (el run mensual) ejecuta los pasos 0, 1, 2, 4, 5, 6.9, 9, 11 y 12 leyendo
las decisiones (`read_decisions`) en vez de calcularlas: no ejecuta 3, 6.2, 7, 8 ni 10.

| # | Método (módulo) | Propósito | Salida esperada |
|---|---|---|---|
| **0** | `check_configuration_version` (pipeline) | Comprobar que `config.py` tiene los campos v3 antes de tocar datos | Nada, o `AttributeError` diciendo que `config.py` está desactualizado |
| **1** | `phase_0` (pipeline) | Fase 0: del raw a las unidades de forecast etiquetadas | dict(fine_table, labeled_units) |
| 1.1 | `Config.read_raw` (config, sobreescrito) | Traer el extracto | DataFrame con todas las columnas declaradas |
| 1.2 | `validate_raw` (raw_data_validation) | Contrato de columnas (ninguna sin rol, ninguna requerida ausente), periodos parseados, roles conocidos | El raw validado, `period` como Period[M]; consola `[0.1] contract OK` |
| 1.3 | `apply_current_month_doctrine` (raw_data_validation) | El calendario de roles se decide desde el mes en curso, ignorando el del raw: mes en curso y posteriores → `projection` (resultados borrados); el mes anterior → `pending_close` (no cerrado: ni verdad ni entrenamiento, pero sí se predice); los `test_months` anteriores → `test` (el examen); el resto → `train`. El forecast aprende de train y test | Raw condicionado; consola `[0.1] calendar from the current month` |
| 1.4 | `build_fine_table` (raw_data_validation) | Una fila por (unidad, combinación de extras de revalorización): `fu_id`, `comb_id` y sus tres claves; falla si hay duplicados | Tabla fina; asserts de grano y colisión |
| 1.5 | `aggregate_to_forecast_units` (raw_data_validation) | Sumar las combinaciones dentro de cada unidad (serie × mes); comprobar que el dinero se conserva | Forecast units; consola `[0.2] fine ... -> forecast units ... pipeline conserved` |
| 1.6 | `build_key_lookups` (raw_data_validation) | Diccionarios id ↔ clave de unidades y combinaciones | **lookup_fu**, **lookup_comb** |
| 1.7 | `label_universe_and_routes` (raw_data_validation) | Universo (`normal` / `time_series`), `fs_id`, cobertura y ruta (`trainable` / `no_impact` / `heuristic`) por serie según sus roles | Unidades etiquetadas; consola `[0.3] routes per series` |
| 1.8 | `Config.write` ×4 (config) | Persistir (fact_fu con las etiquetas; fact_fine con `fs_id`; cada `write` estampa claves derivadas, `process_date`, `execution_id`) | **fact_fu**, **fact_fine**, **lookup_fu**, **lookup_comb** |
| 1.9 | `build_support_reference` (support_reference) | La foto del soporte por serie (ANALYSIS) | **fu_summary** |
| 1.10 | `run_raw_profile` (analysis_data_profile) → `calendar_by_role`, `dimension_domains`, `measure_coherence`, `term_mapping_coverage` | Nivel 0: calendario por rol y contigüidad; dominios de cada dimensión y su estabilidad temporal (valores que aparecen o desaparecen); coherencia de medidas por fila (renovados > pipeline, negativos, AUV y uplift de fila fuera de rango); cobertura del mapeo de plazo; readquisiciones y universo ts | **raw_profile**, **dim_domains**; consola `[0.4]` |
| **2** | `build_rate_series` (run_rate_series) | Fase 1.1: series, huecos, tasas, resumen | (units, series_summary) |
| 2.1 | `hash_key` sobre `fs_id` | Clave de serie | columna `fs_key` |
| 2.2 | `fill_history_gaps` | Un mes ausente dentro de la historia de una serie trainable se rellena con una fila sintética (`sintetica=1`, medidas 0, rol heredado) | Units con las filas sintéticas |
| 2.3 | `compute_row_rates` | `tasa = renovados / pipeline` cuando pipeline > 0 y la fila es real e histórica; NaN en proyección y sintéticas | columna `tasa` |
| 2.4 | `build_series_summary` → `series_sign_table` → `sign_of_series` | Por serie: n_propio (mediana mensual de unidades), meses, huecos, tasa propia, error binomial (Wilson), $ proyectados, celda, signo (neutral / neg / pos / mixed) | series_summary |
| 2.5 | `Config.write` ×2 | Persistir | **fact_fu_gaps**, **fs_summary**; consola `[1.1]` |
| 2.6 | `run_fu_profile` (analysis_data_profile) → `series_completeness`, `dial_buckets` | Nivel 1: por serie primer/último mes, huecos, nace/muere dentro de la historia, soporte y tramo del dial (< 30 / 30-271 / 271-752 / ≥ 752), combinaciones por unidad y peso de la mayor, meses a 0 % o 100 % con pipeline pequeño, unidades descuadradas fina ↔ unidad; dinero por tramo del dial antes de prestar | **fu_profile**, **dial_buckets**; consola `[1.1b]` |
| **3** | `run_dimension_analysis` (analysis_dimensions) | Fase 1.2: qué separa, en qué orden colapsa, cuánto cuesta no segmentar | dict con las cinco tablas |
| 3.1 | `dimension_separation` → `weighted_eta2`, `weighted_omega2`, `weighted_r2_factorial` | Por dimensión (series neutras, peso = soporte): η² individual, contribución única (tipo II), ω²; pares con interacción | decision_eta2 (parcial), decision_eta2_pairs |
| 3.2 | `sequential_collapse_order` | Orden greedy de colapso de las mandatory (solo mandatory en el modelo; nivel fino antes que grueso; en cada paso la que menos R² pierde dado lo que queda) | columnas `orden_colapso`, `perdida_secuencial` en decision_eta2 |
| 3.3 | `Config.write` ×2 | Persistir | **decision_eta2**, **decision_eta2_pairs**; consola `[1.2]` |
| **4** | `run_support_ladder` (run_support_ladder) | Fase 1.3: la escalera, la credibilidad, la ficha, los niveles | (series_estimates, series_card, decision_support, parent_ladder) |
| 4.1 | lectura de `decision_eta2` (`orden_colapso`, `perdida_secuencial`, extra anulable) | El orden de colapso y la extra con menor contribución única | order, annullable, collapse_loss |
| 4.2 | `series_patterns_table` → `build_relatives` → `relative_pattern` | Por serie trainable normal: la lista ordenada de parientes (patrones) según su signo; con signo termina en celda × signo salvo `signed_ladder_max_loss` | patterns (fs_id × peldaño × patrón) |
| 4.3 | `pool_support` | Soporte y tasa de cada patrón con TODAS las series que casan (suma por mes, mediana de meses) | pools |
| 4.4 | `climb_ladder` | Peldaño 0 solo si n ≥ `own_rate_floor` (271: va sola); si no, el primer peldaño ≥ 1 con n ≥ `support_floor` (30: mezcla con él); si ninguno y la serie tiene n ≥ 30, ella misma sin refuerzo; si no, el último (alcanzo_suelo = 0) | decision_support (sin k), parent_ladder |
| 4.5 | `estimate_credibility_k` | k de Bühlmann-Straub por pariente elegido (varianza dentro / entre de las hermanas); `k_cred` si < 3 hermanas | k por id_estimacion |
| 4.6 | `estimate_rates` → `risk_level` | Tasa estimada `z·propia + (1−z)·pariente` solo con pariente con soporte; `se_estimacion_pp`, `se_prediccion_pp`; nivel de riesgo | series_estimates |
| 4.7 | `build_support_chain` | La cascada en dinero por serie: cada peldaño subido y el final, con su error y su margen en $ | support_chain |
| 4.8 | `build_series_card` | summary + estimates | series_card |
| 4.9 | `risk_levels_report` | Dinero, series y error medio por nivel | risk_levels |
| 4.10 | `Config.write` ×5 + `print_risk_levels` + `print_level_definitions` | Persistir e imprimir | **decision_support**, **parent_ladder**, **support_chain**, **series_card**, **risk_levels**; consola `[1.3]` con la leyenda y la ruta de colapso |
| **5** | `build_key_bridge` (pipeline) | El puente fila del raw → serie → id de estimación → celda de uplift → celda mandatory | **key_bridge** |
| **5b** | `run_composition_analysis` (analysis_dimensions) | Fase 1.4, tras la escalera: la composición se CUENTA, no se busca | dict |
| 5b.1 | `counterfactual_and_decomposition` | Por celda y mes de la ventana (walk-forward): cuánto sobre/infraestima la vista solo-mandatory (una tasa por celda) frente a las series segmentadas, en $; y Kitagawa (comportamiento vs composición) | **mandatory_only_cost**, **mix_shift** |
| 5b.2 | `timevarying_calibration` | Tasa realizada mes a mes por flag y por signo, con error (la auditoría de cada señal) | **tv_calibration** |
| 5b.3 | `print_mix_shift_by_cell` | Consola: las celdas donde segmentar paga y su riesgo de composición | consola `[1.4]` |
| **6** | `run_seasonality_benchmark` (analysis_seasonality_benchmark) | Fase 2: la decisión de estacionalidad, tomada UNA vez para toda la cartera donde hay potencia: las series grandes neutras | dict(decision_estacionalidad, bench_panel, bench_flags, selected, summary) |
| 6.1 | `select_benchmark_series` | Top N por dinero dentro de cada grupo (región × producto), neutras, soporte ≥ 271 en todos los meses cerrados, ≥ 24 meses (marca `historia_corta` < 36); % del pipeline cubierto | selected |
| 6.2 | `floor_and_phi` | Suelo binomial del mes típico y φ (varianza alrededor de la tendencia lineal / varianza binomial) | dict |
| 6.3 | `month_effect_regression` | logit(tasa) ~ tendencia + dummies de mes ponderada por n: amplitud (mes alto − bajo, en pp), LRT (se reporta, no decide), pendiente pp/año ± error estándar | dict |
| 6.4 | `month_year_panel` | z = (tasa − tendencia) / se binomial, por mes × año; consistencia = fracción de años con el mismo signo | (panel, consistencia) |
| 6.5 | `predictive_backtest` | T15 (nivel reciente + efecto de mes) contra T3_ma3 en los últimos 6 meses cerrados, a h=1 y h=6, ponderado por n: la prueba que DECIDE | dict(mejora_h1_pct, mejora_h6_pct…) |
| 6.6 | `materiality_and_verdict` | Todo en una fila con el veredicto: estacional si amplitud ≥ 2 pp y meses extremos consistentes ≥ 2/3 y la forma mejora ≥ 10 % a h=6 sin empeorar a h=1; tendencia si \|pendiente\| ≥ 2 se y ≥ 1 pp/año; impacto en $ = amplitud × pipeline de los meses extremos | fila de **decision_estacionalidad** |
| 6.7 | `flag_composition_check` | En las mismas celdas, la proporción mensual de unidades con cada flag por mes del año y su consistencia (la estación que puede haberse mudado a los flags; precondición: flag as-of el vencimiento) | **bench_flags** |
| 6.8 | `benchmark_summary` | La página: % del pipeline cubierto, % estacional, % con tendencia, flags, DECISIÓN (sin estación material → solo técnicas de nivel; con estación → efectos de mes solo en esas series) | **decision_estacionalidad**, **bench_panel**; consola `[2]` |
| 6.9 | `monthly_series_by_estimation_id` + `build_pool_reference` (analysis_backtest) | La serie mensual de cada pool (todas las series que casan el patrón) y su referencia: meses, n_pool, tasa_pool, gate (soporte / nivel), estacional (solo si el benchmark lo declaró para esa serie), tendencia. Sin diagnósticos individuales | **pool_reference** |
| **7** | `forecast_horizons` (pipeline) | H = meses desde el último mes con verdad hasta el fin del forecast (proyección conocida o horizonte extendido) | lista 1..H; horizontes juzgados = `backtest_horizons` ∩ [1, H] ∪ {H} |
| **8** | `run_backtest_analysis` (analysis_backtest) | Fase 3: el juez | dict(backtest_long, decision_technique, decision_error_bands, backtest_holdout) |
| 8.1 | `technique_dimension` (techniques) + `Config.write` | Catálogo de técnicas | **dim_tecnica** |
| 8.2 | `rolling_origin_backtest` (cribado) → `_backtest_chunk` → `eligible_techniques`, `CATALOGUE[...]` | Catálogo reducido a 8 técnicas de nivel (media 3/6, EWMA, suavizado, Holt amortiguado, credibilidad temporal, media) + T15 solo en las series con veredicto estacional. Solo ids con soporte; los últimos 6 meses ANTES del corte del examen más los del examen; dos horizontes (1 = mes siguiente con datos hasta el anterior; 6 = con datos hasta seis meses antes); todas las técnicas elegibles; error con signo y normalizado | screen (tabla larga) |
| 8.2b | `holdout_start_month` | El corte del hold-out: `backtest_test_start`, si no el primer mes con rol `test` del extracto, si no los últimos 6. Los meses ≥ corte NUNCA se usan para decidir | holdout_start |
| 8.3 | `select_technique` → `band_of_horizon` | Solo con los meses < corte: campeón por id **y tramo de horizonte** (corto 1-3, medio 4-6, largo 7+), juzgado con los horizontes de cribado de cada tramo: mejor `err_norm` medio que gane al retador por el margen con ≥ N predicciones; dentro del margen, familia más rica solo con historia suficiente; un tramo sin cribado hereda el anterior | decision_technique (una fila por id × tramo) |
| 8.3b | `print_candidates` | Consola: pools para mirar en detalle (la forma paga a largo; corto y largo eligen distinto; nada bate a lo simple) con la llamada `sheet("<id>")` | consola `[3] candidates` |
| 8.4 | `rolling_origin_backtest` (juicio) | Campeón + retador en los horizontes restantes | judged (tabla larga) |
| 8.5 | `error_bands` → `technique_for` | Solo con los meses < corte: por (id, h) p5/p95 del error normalizado de la técnica del tramo (propios o de familia), monótonos en h | decision_error_bands |
| 8.5b | `aggregate_error_bands` | El error COMÚN: el de toda la cartera sumada por mes y h (meses < corte, técnica elegida): sus p5/p95 por h son lo que cuesta que los pools se equivoquen juntos | **backtest_agg_error**, **decision_agg_bands** |
| 8.6 | `holdout_report` + `holdout_aggregate` | Meses ≥ `backtest_test_start` predichos con la técnica elegida, banda y dentro/fuera; y el hold-out del TOTAL (todos los pools sumados por mes y h: el error del agregado, que las bandas por pool no pueden dar) | backtest_holdout, **backtest_holdout_agg** |
| 8.7 | `Config.write` ×4 | Persistir | **backtest_pred**, **decision_technique**, **decision_error_bands**, **backtest_holdout**; consola `[3]` leaderboard, campeones, hold-out por h (plano, ponderado, sesgo, % en banda) |
| **9** | `run_uplift` (run_uplift) | Fase 4: la revalorización | decision_uplift |
| 9.1 | `renewer_rows` | Filas con renovadores, AUV de pipeline, uplift de fila, ids de celda de uplift, de padre y de celda mandatory | renewers |
| 9.2 | `estimate_uplift_cells` → `ratio_of_sums`, `bootstrap_band` | Por celda: ratio propio, del padre (extras de punto de partida conservadas), de la celda; decisión por suelo; banda por bootstrap; recorte al tope | decision_uplift |
| 9.3 | `build_uplift_chain` | La traza por celda (propio / padre / celda / final) | uplift_chain |
| 9.4 | `Config.write` ×2 | Persistir | **decision_uplift**, **uplift_chain**; consola `[4]` |
| **10** | (pipeline) | Reunir las seis decisiones en un dict | decisions |
| **11** | `run_forecast_assembly` (run_forecast_assembly) | Fase 5: el forecast, su banda, el total | dict(forecast_detail, forecast_bands, horizon_report, forecast_by_level, forecast_units_extended) |
| 11.1 | `extend_forecast_units` → `term_months_of`, `acquisition_factor_by_series` | Filas simuladas: reentradas de las renovaciones de los meses de PROYECCIÓN (el contrato aún no existe, su vencimiento no está en la pipeline aunque el extracto llegue hasta allí) y de las de meses con verdad más allá de la pipeline conocida: `unidades(m) = renovados(m − plazo) × factor`, plazo por fila, solo filas del filtro, valoradas al precio renovado (AUV observado o AUV × uplift) | **fu_extended** (si hay horizonte extendido); consola `[5] extended horizon` |
| 11.2 | `assemble_forecast` → `rate_forecast_by_estimation_id` → `predict` | Por fila futura: predicción de la técnica del pool a h, más la desviación propia de la serie ponderada por z (forma del pool, nivel de la serie); cascada tasa estimada → celda → global; tope; uplift de su celda; $ esperados; orígenes; `tasa_pool_h` y `desviacion_propia_pp` | detail |
| 11.3 | `forecast_bands` | Banda asimétrica por fila: cuantiles del id al h juzgado más cercano × se del pool ⊕ se de la fila; en pp y $ | bands |
| 11.4 | `Config.write` ×2 | Persistir | **forecast_detail**, **forecast_bands** |
| 11.5 | `horizon_report` → `aggregate_with_bands` | Total por mes con banda (suma lineal dentro de (id, mes), cuadratura entre), % simulado, % desde tasa de serie, monotonía | **horizon_report_total** |
| 11.6 | `aggregate_with_bands` por nivel + `Config.write` | Dinero y banda por nivel de riesgo | **forecast_by_level**; consola `[5]` mes a mes |
| 11.8b | `regional_summary` + `print_regional_summary` | Una fila por región: dinero, forecast, banda, % con precisión propia, % con señal, % señal sin pool, uplift, composición: la tabla de `ESTRATEGIA_POR_REGION.md` | **forecast_by_region**; consola `[5] BY REGION` |
| 11.8 | `business_summary` + `print_business_summary` | Las tres preguntas de negocio por año: cómo acaba este año (renovado real + forecast del resto), cuál es la pipeline del año que viene (real + proyectada + simulada, con la etiqueta `origen_pipeline` de cada fila) y cómo acaba el año que viene (forecast sobre cada origen, con banda) | **business_summary**; consola `[5] BUSINESS ANSWERS` |
| 11.7 | `pipeline_summary` → `common_band_per_row` + `print_pipeline_summary` | Por bloque: banda idiosincrática (pools independientes, cuadratura), banda común (error agregado por h × dinero, lineal entre meses) y **banda total** = ⊕ de las dos: la que se promete; El resumen de la pipeline por bloque (resto del año, año siguiente, total): $ a predecir, esperado, banda calibrada (lo que prometemos), cota mínima binomial en cuadratura (el suelo que nadie baja), cota máxima lineal (el peor caso absoluto), % simulado, % nivel A, error realizado en el hold-out (h ≤ 4, ponderado) | **pipeline_summary**; consola `[5] PIPELINE SUMMARY` |
| 11.9 | `run_baseline` (analysis_baseline) → `baseline_forecast`, `baseline_holdout` | La previsión "de Excel": tasa en dólares (renovado $ / vencido $) de los últimos 1 / 3 / 12 meses por grano agregado (global, corte grueso, mandatory) × pipeline futura; por año frente al framework; y su propio walk-forward (lag 1 y 4) para saber cuál acierta más | **baseline_forecast**, **baseline_summary**; consola `[5] BASELINE` |
| **11b** | `draw_top_sheets` (pipeline) → `sheet` | Al final de todo análisis, la ficha (seis paneles + resumen) de las `sheets_top_series` series con más dinero proyectado, en `<outdir>/diagnostics/` | PNG; consola `SHEETS` |
| **12** | `validate` → `run_validation` (run_validation) | Panel INTEGRITY / DOCTRINE / QUALITY; detiene si falla INTEGRITY o DOCTRINE | **validation_report**; consola `VALIDATION PANEL` |

## Fuera del flujo (a demanda)

| # | Método (módulo) | Propósito | Salida |
|---|---|---|---|
| A | `sheet` (sheet) → `resolve_key`, `filter_for_series`, `tell`, `sheet_summary`, `series_sheet` | La ficha de lo que señale una clave (fs_key, estimacion_key, celda_key, uplift_cell_key, fu_key, fu_comb_key, o un fs_id) | dict(keys, summary, tables, figure) |
| B | `audit_series` (audit_series) | Solo las tablas filtradas y la historia por consola | dict de tablas |
| C | `run_series_diagnostics` (diagnostics_plots) | Top series por $ o historia: tabla + 4 PNG (tasas, pipeline, perfil estacional, hold-out) | rutas de las figuras |
| D | `showcase_sheets` → `pick_showcase_series`, `series_sheet` | Una estacional, una con tendencia, una con cambio de nivel, una de la celda con más mix-shift | {motivo: PNG} |
| E | `guess_game` | Pregunta (historia hasta el origen) y respuesta (verdad, retador, campeón) | 2 PNG |
| G | `technique_error_by_horizon(key)` (diagnostics_plots) | Error medio por horizonte, una línea por técnica, con el campeón de cada tramo marcado: donde "lo simple gana cerca y la forma gana lejos" se ve | 1 PNG |
| F | `read_decisions` + `run_pipeline` (pipeline) | El run mensual: lee `decision_*` y ejecuta 0, 1, 2, 4, 5, 6.1, 9, 11 y 12 sin decidir | las tablas de RUN |
