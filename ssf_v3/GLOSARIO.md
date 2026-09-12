# GLOSARIO — términos del framework y su equivalente en español

*SFF v2 · vivo desde el 12-sep-2026. Se amplía con cada término que el usuario pregunta. Complementa a DISENO_V2.md (doctrina) y POR_QUE_ESTE_FORECAST.md (motivación). Cada entrada: qué es, cómo pensarlo en español, dónde vive en las tablas o en el código, ejemplo con la configuración de pruebas (`mandatory=[region]`, `timevarying=[dormant, softcancel, no_instalado, autorenew]`, `extra_renovacion=[product, channel]`, `extra_revalorizacion=[discount, newcust]`).*

*Convención: los nombres de columnas y valores persistidos siguen en español (`celda`, `gu`, `tasa`, `etapa`…); los identificadores de código en inglés. Cuando un término tiene dos nombres, se dan ambos.*

---

## 1 · La cadena de identidad (rama tasa)

Tres niveles de agrupación, de fino a grueso. Un nivel está contenido en el siguiente: **una FU pertenece a exactamente una serie, y una serie a exactamente una celda.**

```
celda mandatory        EU
  └── forecast series  EU|0|0|0|0|A|web           (una por combinación del grano tasa)
        └── forecast unit  EU|0|0|0|0|A|web|2026-01   (una por serie × mes)
```

### Forecast unit (FU)
- **Qué es**: una observación. En un mes concreto, en una combinación concreta de dimensiones, vencían n unidades y renovaron k. Es la fila atómica de la rama tasa.
- **En español**: *unidad de forecast*; la casilla serie × mes.
- **Columnas del id**: `rate_series_columns` + mes. Separador `|`.
- **Dónde vive**: `fu_id`, `fu_key`; una fila de `fact_fu`; la referencia inmutable `fu_summary` (soporte y error binomial peor-caso por FU).
- **Ejemplo**: `EU|0|0|0|0|A|web|2026-01`.

### Forecast series (FS)
- **Qué es**: la serie temporal de FUs de una combinación. Es lo que recibe una tasa estimada, un pool y una técnica de forecast.
- **En español**: *serie de forecast*; la secuencia mensual de una combinación.
- **Columnas del id**: `rate_series_columns` (sin mes).
- **Dónde vive**: `fs_id`, `fs_key`; `fs_summary`, `support_chain`, `parent_ladder`, backtest, `forecast_seleccion`.
- **Ejemplo**: `EU|0|0|0|0|A|web` → 30 FUs, una por mes desde 2024-01.

### Celda mandatory (mandatory cell)
- **Qué es**: el grupo de series que comparten los valores de las dimensiones `business_mandatory_dims` (las que nunca se colapsan en pools). Es el padre natural de toda serie.
- **En español**: *celda*; el segmento de negocio irreducible.
- **Columnas del id**: solo `business_mandatory_dims`.
- **Dónde vive**: `celda` (contrafactual Simpson, cascada de fallback), `celda_id` (`key_bridge`). En código: `mandatory_cell`. En producción son 10 columnas (`tr_regional_level_1..3`, `tr_product_level_1..2`, `tr_origin_type_SKU_based`, `tr_term_level_1..2`, `tr_band_level_1..2`).
- **Ejemplo**: `EU` → todas las series de Europa.

### Celda de uplift (uplift cell)
- **Qué es**: la unidad de estimación del uplift. NO es una serie: el uplift se estima con todos los renovadores de todos los meses juntos, no tiene eje temporal ni backtest por horizonte.
- **En español**: *celda de revalorización*; grupo estático mandatory × extras de precio.
- **Columnas del id**: `uplift_cell_columns` = `business_mandatory_dims` + `extra_revalorizacion`.
- **Dónde vive**: `gu` y `uplift_cell_key` en `uplift_chain`. En código: `uplift_cell`.
- **Ejemplo**: `EU|d40|1`.
- **Aviso de vocabulario**: en el legacy «celda» está sobrecargado (celda mandatory en fase 1/3, celda de uplift en fase 2). En código se usa siempre el nombre completo: `mandatory_cell` o `uplift_cell`, nunca «cell» a secas.

### Grano (grain) → `rate_series_columns`, `uplift_cell_columns`
- **Qué es**: término de modelado dimensional (Kimball): la lista de columnas que identifica una fila de una tabla; el nivel de detalle al que se agrega.
- **En español**: *nivel de detalle*; «qué columnas definen una fila».
- **En código**: se sustituyó por nombres que dicen qué definen: `rate_series_columns` (las columnas que definen una serie de tasa) y `uplift_cell_columns` (las que definen una celda de uplift). Ambas son propiedades derivadas de la taxonomía, nunca escritas a mano:
  - `rate_series_columns` = `mandatory + timevarying + extra_renovacion`
  - `uplift_cell_columns` = `mandatory + extra_revalorizacion`

---

## 2 · Soporte y su reparación

### Soporte (support) y suelo de soporte (support floor)
- **Qué es**: n = unidades del pipeline de una serie (mediana mensual de los meses con vencimientos). Es el denominador del error binomial √(p(1−p)/n). El suelo (`support_floor` = 30) es el n mínimo para que una serie estime su tasa sola: con n=30 y p=0,5 la banda al 90% es ±15 pp.
- **En español**: *soporte* = cuánta evidencia tiene la serie; *suelo* = umbral de admisión, no promesa de calidad.
- **Dónde vive**: `n_avg`, `soporte`, columnas `n_efectivo` en `support_chain`.

### Pool
- **Qué es**: el conjunto de series con el que se **calcula** una tasa cuando una serie sola no llega al suelo. Regla P5/P6: el cálculo se hace con la suma de todas las series del pool (mes a mes, sumando unidades), y el **resultado se estampa en cada miembro**; cada serie conserva su propio pipeline y su propia identidad. El pool es de dónde sale el número, no a qué se aplica.
- **En español**: *grupo de estimación*, *agrupación*, *conjunto de préstamo*. Si una serie tiene 10 unidades y su hermana 20, la tasa se calcula con 30 y se escribe dos veces, una en cada serie.
- **Regla fija**: un pool nunca mezcla celdas mandatory distintas en L1 ni en L2.
- **Dónde vive**: `fs_id_L1`, `fs_id_L2` (el id del pool al que pertenece la serie en cada nivel), `id_efectivo` en `support_chain`.
- **Ejemplo**: las series `EU|1|0|0|0|A|web` (dormant, n=15), `EU|0|1|0|0|A|web` (softcancel, n=12) y `EU|0|0|1|0|A|web` (no_instalado, n=10) forman el pool L1 `EU|SIG=neg|A|web` con n=37, que supera el suelo.

### Las tres estrategias de reparación (L1, L2, L3)
Por orden de coste de información. Se aplican solo a series por debajo del suelo (L1, L2); la credibilidad (L3) se aplica a todas.
- **L1 · agrupar por signo**: las series con timevarying activas del mismo signo (neg/pos) se juntan en un pool `SIG=neg` / `SIG=pos`. Los motivos se pierden, el signo se conserva.
- **L2 · asterisco**: para lo que sigue pequeño sin señal timevarying, se anula la dimensión extra con menor η² (se sustituye su valor por `*`), juntando a las hermanas que solo difieren en ella.
- **L3 · credibilidad**: ver siguiente entrada.

### Credibilidad (credibility shrinkage)
- **Qué es**: la tasa final de una serie es una media ponderada entre su propia tasa (tras L1/L2) y la tasa de su padre: `tasa_final = z·tasa_propia + (1−z)·tasa_padre`, con `z = n/(n+k)` y `k_cred` = 60. Con n=60, z=0,5 (mitad y mitad); con n=600, z=0,91 (casi toda propia); con n=6, z=0,09 (casi toda del padre). El error se combina en cuadratura.
- **En español**: *encoger hacia el padre*, *cuánto te fías de la serie frente a su grupo*. Es la fórmula clásica de Bühlmann en actuarial.
- **Dónde vive**: etapa `3_shrink` en `support_chain` (`id_efectivo = "z=0.43→EU|*"`); `tasa_final`, `se_final`.

### Escalera de padres (parent ladder) y peldaño (rung)
- **Qué es**: la secuencia de padres cada vez más gruesos hacia los que puede encoger una serie. Cada peldaño se construye colapsando una dimensión mandatory más (su valor pasa a `*`). El orden de colapso lo fija `_build_collapse_order`: dentro de una familia `x_level_1/2/3` cae primero el nivel más fino; entre familias, cae primero la que menos separa (menor η²).
- **Primer peldaño que alcanza el suelo**: la serie sube peldaño a peldaño y se queda con el **primer padre cuyo n ≥ suelo**. Es el padre más parecido a la serie que ya tiene evidencia suficiente. Si ninguno llega, se toma el último (el total). Hacia ese padre encoge la credibilidad.
- **En español**: *escalera de padres* = jerarquía de agrupaciones; *peldaño* = un nivel de esa jerarquía; *el primer peldaño que alcanza el suelo* = el padre más cercano con evidencia suficiente.
- **Dónde vive**: tabla `parent_ladder` (serie × peldaño: `peldano`, `dims_colapsadas`, `padre_id`, `n_padre`, `tasa_padre`, `elegido`); `peldanos_padre` en `support_chain`.
- **Ejemplo Kamelot (sep-2026)**: orden de colapso empieza por `tr_band_level_2`; con 1 peldaño (`…|*` en band_level_2) el 100% de las series encontró padre con soporte.
- **Nota**: los peldaños están **por encima** de la celda mandatory (empiezan colapsando una mandatory). La celda mandatory completa no es un peldaño; es el punto de partida.

---

## 3 · Diagnóstico y ensamblaje

### Contrafactual Simpson (Simpson counterfactual)
- **Qué es**: la medida en dólares de cuánto cuesta NO segmentar. Para cada celda mandatory y cada uno de los últimos 6 meses con verdad (t), se calculan dos predicciones usando solo datos ≤ t−1:
  - **plano**: una tasa agregada de toda la celda.
  - **segmentado**: la tasa de cada serie de la celda, recombinada con los **pesos reales** del mes t (legítimo: el pipeline del mes t es dato conocido).
  Ambas se comparan con la tasa real de t. `ahorro = (|err_plano| − |err_seg|) × pipeline$`. Se suma con signo (los meses donde el plano acierta más restan) y se reporta además el % de celdas-mes donde gana el segmentado.
- **En español**: *cuánto dinero se equivoca el método plano de más que el segmentado*; el precio de la mezcla. Es «contrafactual» porque responde a «¿qué error habríamos tenido si no hubiéramos segmentado?».
- **Dónde vive**: tabla `simpson_contrafactual` (`celda`, `mes`, `err_plano_pp`, `err_seg_pp`, `ahorro_usd`).
- **Cifras**: $738.611 (12-ago, con el mes en curso contaminando) → $166.370 (sep, con la doctrina del mes en curso). El segundo es el honesto.
- **Distinto de**: la *búsqueda de casos* (`fase_pre.py`, tablas `simpson_showcase*`), que intentaba encontrar una paradoja visual limpia y no la encontró. Esa pieza es candidata a eliminarse; Simpson se explicará a nivel teórico.

### Cascada de fallback (fallback cascade)
- **Qué es**: en el ensamblaje (fase 3), cada fila futura del pipeline necesita una tasa. Se busca en orden y se anota de dónde salió:
  1. la tasa de **su propia serie** (`tasa_final`) → `tasa_origen = "serie"`;
  2. si la serie no tiene estimación (ruta heuristic: futuro sin historia), la **media de su celda mandatory** → `"celda"`;
  3. si la celda tampoco existe en el histórico, la **media global** → `"global"`.
- **En español**: *cadena de respaldo*, *a qué recurre una fila cuando no tiene tasa propia*. Nunca silenciosa: `tasa_origen` queda en `forecast_detail` y la validación cuenta cuántas filas y cuánto dinero van por cada vía.
- **Dónde vive**: `tasa_origen` en `forecast_detail`; check en `validation_report`; `smoke_multidim.py` exige que ninguna fila caiga a `global`.
- **Distinto de**: la escalera de padres (fase 1, mejora la *estimación* de series con historia) y de los pools (fase 1, de dónde sale el número). La cascada es de fase 3 y trata filas *sin* estimación.

---

## 4 · Herramientas de obra

### EDGE CASES (sección del docstring)
- Equivale a **BORDES** del contrato de cinco secciones (ENTRADA · SALIDA · REGLAS · BORDES · REGISTRO ↔ INPUT · OUTPUT · RULES · EDGE CASES · CONSOLE). Lista los casos límite y qué hace la función en cada uno: entrada vacía, nulo, índice duplicado, columna ausente, qué excepción lanza y con qué diagnóstico.

### Test de caracterización (vs TDD)
- **TDD**: test primero, código después; el test dirige el diseño.
- **Caracterización / regresión** (lo que hace `tests/test_config.py`): el código ya existe; el test fija su comportamiento para que un cambio futuro que lo rompa falle con una frase que diga qué se rompió. Es lo adecuado para un refactor. La comparación con la referencia (`tests/test_pipeline.py`) es lo mismo a nivel de sistema. Orden de uso: test de unidad primero, pipeline después. Falla el test → contrato roto; pasa el test y falla el pipeline → fase rota. La referencia es temporal: desaparece al cerrar la primera versión definitiva.

---

## 5 · Fase 0 y la separación RUN / ANALYSIS

### RUN y ANALYSIS
- **RUN** (`run/`): lo imprescindible para producir cada mes el forecast **sin tomar ninguna decisión**: lee el raw, aplica reglas ya decididas, escribe tablas. Es lo que se delega a un equipo técnico.
- **ANALYSIS** (`analysis/`): lo que decide *cómo* se hace el forecast y mide *si* lo hace bien: referencias, diagnósticos, η², contrafactual, backtest, elección de técnica. Es lo que se retiene para mantener el control.
- Fase 0: `run/raw_data_validation.py` (0.1–0.3, operacional) y `analysis/support_reference.py` (0.4, la referencia inmutable: nadie la consume, sirve para auditar).

### Doctrina del mes en curso (current-month doctrine)
- **Qué es**: el mes en curso tiene el pipeline completo (se sabe qué vence) pero el resultado incompleto (aún no han renovado todos). Regla sellada (16-ago-2026): se le asigna el rol `projection` sea cual sea su etiqueta, es el **primer mes a proyectar**, nunca test ni train, y se borran (NaN) las renovaciones y readquisiciones ya contabilizadas en él y en cualquier mes de proyección, para que el futuro parezca no empezado.
- **Por qué**: si entra como test, contamina el backtest con un mes a medias; si entra como train, sesga la tasa a la baja.
- **Dónde vive**: `apply_current_month_doctrine`; consola `[0.1] current month [...] → PROJECTION`.

### Universo (`universo`)
- `normal` o `time_series`, según `flag_time_series`. El universo `time_series` está reservado a un tratamiento propio (por eso `ts_revenue_col` sigue declarado en Config); hoy solo se etiqueta.

### Cobertura (`cobertura`) y ruta (`ruta`)
- **Cobertura**: qué roles tiene una serie, ordenados y unidos con `_` (`projection_test_train`, `projection`, `train`…).
- **Ruta**: qué se hace con la serie, deducido de la cobertura: `trainable` (historia + futuro: se estima su tasa), `heuristic` (futuro sin historia: la cascada de fallback le da la tasa de su celda), `no_impact` (sin futuro: nada que predecir; se etiqueta, no se borra — P4).
- Test solo no es historia: `projection_test` es `heuristic`.

### Tabla fina y tabla de forecast units
- **Tabla fina** (`fact_fine`): cada fila del raw con sus identidades (`fu_id`, `comb_id`, `fu_key`, `comb_key`, `fu_comb_key`). Conserva las extras de revalorización.
- **Tabla de forecast units** (`fact_fu`): una fila por FU, medidas **sumadas** (`min_count=1`: un grupo todo NaN sigue NaN, no se convierte en 0). Sin extras. Los ratios se recalculan de las sumas, nunca se promedian.
- Entre ambas: el dinero se conserva al céntimo o el programa para.

---

## 6 · Referencia binomial, φ y timevarying (sellado 12-sep)

### Error binomial por tamaño de muestra (`error_binomial_pp`)
- **Qué es**: la tasa es una proporción (k de n). Su error de muestreo es exacto: `√(p(1−p)/n)`; al 90 %, `1,645·√(p(1−p)/n)`. Con p = 0,8 y n = 100, ±4 pp al mes *sin que nada cambie*. Con n = 5, ±36 pp.
- **Dos niveles**: por **forecast unit** (`fu_summary`: cada mes con su n, a p = 0,5 como peor caso antes de estimar nada) y por **forecast series** (ficha: con su tasa y su n mensual típico).
- **Para qué sirve**: es la referencia propia contra la que se mide todo: el suelo de soporte (n = 30 ⇔ ±15 pp), la normalización de las bandas, los tests de estacionalidad y tendencia, y φ.
- **En español**: *el ruido de la moneda*; lo que oscila una tasa por puro azar de muestra.

### φ (phi, factor de sobredispersión) — PRINCIPIO RECTOR
- **Qué es**: por serie, la variación **observada** de la tasa mes a mes dividida por la que **tendría que haber** solo por muestreo si la tasa fuera constante (que la binomial da exacta).
- **Lectura**: **φ ≈ 1** → la serie oscila lo que la moneda predice; no hay nada que modelar; el promedio es la mejor técnica y cualquier "tendencia" que se vea es ruido. **φ > 1** → hay un motor (estación, tendencia, cambio de régimen, mezcla interna) que mueve la tasa más de lo que el muestreo explica; ahí una técnica de series temporales tiene algo que capturar.
- **Por qué importa**: es una referencia propia de cada serie, no un umbral externo (P1). Dice **dónde** merece la pena una técnica compleja y dónde no. Frase de negocio: «de los ±7 pp que ves cada mes, ±5 son moneda (nadie los reduce) y el resto es la tasa moviéndose de verdad».
- **Dónde vive**: `diagnostico_dinamica` (`sd_obs_pp`, `sd_binom_pp`, `phi`); ficha de la serie.

### Timevarying (dimensiones que varían en el tiempo) y su signo
- **Qué son**: columnas dicotómicas que un mismo cliente puede tener a 0 hoy y a 1 el mes que viene: `softcancel` (ha pedido no renovar), `dormant` (no usa el producto), `no_instalado`, `autorenew` (renovación automática activada). Dos clientes idénticos en región, producto, precio y descuento tienen expectativas de renovación muy distintas si uno ha marcado softcancel y el otro no.
- **Signo**: cada timevarying declara si empuja hacia churn (`negative`: softcancel, dormant, no_instalado) o hacia renovar (`positive`: autorenew). Una serie con alguna negativa activa es de signo `neg`; con positiva, `pos`; con ambas, `neg+pos`; sin ninguna, neutra.
- **Cómo se tratan**: no se colapsan como una dimensión más. Se resumen en su signo y **el signo nunca se pierde**: el primer pariente de una serie pequeña son las series de su mismo signo (antes "L1"); el siguiente anula la extra de menor η²; el último es la celda mandatory × signo, y ahí termina la escalera para las series con signo. Agrupar un softcancel con la celda entera, o con otras regiones, le daría la tasa de los que no han avisado y fabricaría mix-shift.
- **Histórico as-of**: la marca se toma como estaba en el momento del vencimiento, nunca re-puntuada con lo que se supo después.

### Timevarying producidas por modelos predictivos (una binaria por motivo)
- **Qué son**: flags binarios que un modelo cliente a cliente enciende: `alta_prob_abandono_no_uso`, `alta_prob_abandono_no_renov`, `alta_prob_renovacion`. Doctrina DISENO_V2 §3: «el puerto de inyección de los predictivos en el forecast». Cada flag conserva su **motivo** (para actuar sobre él) y declara su **signo** (para agruparlo al predecir).
- **Por qué binarias y no una categórica**: un cliente puede tener varios motivos a la vez (softcancel y dormant; no quiere renovar y además no usa el producto). Una categórica obligaría a elegir uno. Intensidades (alto / muy alto) = dos binarias con el mismo signo.
- **Por qué cohortes y no scores**: el score individual es ruidoso; el promedio del grupo de flags extremos se separa mucho del general y su binomial (con su n) mide esa separación. El forecast usa la tasa realizada del grupo, no el score.
- **Reglas**: as-of (lo que el modelo predijo entonces); versión del modelo como bandera por columna; la tasa realizada por flag es la calibración de ese modelo y la tasa por signo es la referencia de la escalera.
- **Positivos y negativos nunca se juntan.** Una serie con flags de ambos signos no se agrupa con nadie (`mixed_sign`); se cuenta y debería ser ≈ 0. La mayoría de series será neutra (solo se clasifican los extremos); los neutros solo se agrupan con neutros.
- **Tope de la escalera para series con signo**: la celda mandatory × signo. Más arriba se mezclarían cohortes muy distintas (Simpson). Si sigue bajo el suelo, se queda con lo mejor de su signo: ruidosa pero cualificada (`signed_under_floor`).
- **Diferencia con propiedad estable**: una propiedad del cliente que no cambia mes a mes (nuevo puro vs readquisición, buscador de descuentos) no es timevarying; entra como `extra_renovacion` (pasa por η²) o `mandatory`.

### ANOVA de evidencia (η²) — qué mide y qué no
- **η² individual**: cuánto de la variación de la tasa entre series explica una dimensión sola (ponderado por soporte). Confundido si las dimensiones van correlacionadas.
- **Contribución única** (tipo II): cuánto se pierde si se anula esa dimensión conservando el resto. Es la pregunta de la escalera; es la cifra que fija el orden de colapso.
- **ω²**: η² descontando el número de grupos, para que muchas categorías con pocas series no parezcan señal.
- **Por qué no ANCOVA**: ANCOVA es para covariables continuas; aquí todo es categórico (el descuento se discretiza). Lo correcto es ANOVA factorial ponderado con todas las dimensiones a la vez.
- **Sin timevarying**: se gestionan por signo, no por η².


---

## Añadidos v3 (código)

- **id_estimacion**: el patrón del pariente elegido por la escalera (`EU|SIG=neg|A|*`); una serie con soporte propio es su propio id. Es la clave por la que se diagnostica la dinámica, se hace el backtest, se elige la técnica y se calculan las bandas. Todas las series que casan el patrón calculan su serie mensual; solo las que lo eligieron lo reciben.
- **Niveles de riesgo** (`nivel_riesgo`): `A_propio` (peldaño 0, ≥ 12 meses) · `B_prestado` (peldaño 1-2) · `C_lejano` (peldaño ≥ 3, o neutra que no alcanza el suelo) · `D_sin_historia` · `S_signo_bajo_suelo` (con signo, celda × signo bajo suelo: ruidosa pero cualificada) · `M_signo_mixto` (ambos signos: sola) · `N_sin_impacto` (sin proyección) · `T_universo_ts`.
- **se_estimacion_pp / se_prediccion_pp**: error de la ESTIMACIÓN de la tasa (mezcla con credibilidad) y error de la PREDICCIÓN de un mes (añade p(1−p)/n_propio). El segundo nunca encoge por prestar soporte.
- **k (Bühlmann-Straub)**: varianza intra / varianza entre de las hermanas del pariente. Grupo homogéneo → k grande → la serie toma la tasa del pool; heterogéneo → k pequeño → conserva la suya. Por defecto `k_cred` cuando hay < 3 hermanas.
- **gate** (`decision_dynamics`): `soporte` → `temporal` → `estacional` → `tendencia` → `apto_promedio`; primera puerta que se cierra. `estacional` 2 = firme (≥ 2 ciclos), 1 = tentativa. El perfil estacional se mide sobre la serie SIN tendencia.
- **err_norm**: error de backtest / error binomial del mes objetivo. 1.0 = un error de muestreo: el suelo teórico.
- **retador**: T2_mean. Un campeón debe ganarle por `challenger_margin_normalized` con ≥ `backtest_min_predictions`; si no, `tecnica_origen = retador`.
- **banda_origen**: `propia` (cuantiles del id) · `familia` (misma técnica, todos los ids) · `binomial` (sin backtest: ±z·se) · sufijo `+extrapolada` cuando h supera el máximo del backtest.
- **simulada / factor_adquisicion**: fila de pipeline generada para el horizonte extendido: `unidades(m) = renovados(m − plazo) × factor`; el factor es la mediana histórica de pipeline(t)/renovados(t − plazo) = 1 + adquisiciones/renovaciones.
- **Agregación de bandas**: dentro de (id_estimacion, mes) los errores se suman (misma tasa); entre ids y meses, en cuadratura.
