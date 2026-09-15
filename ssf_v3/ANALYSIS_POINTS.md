# PUNTOS DE ANÁLISIS — qué capturar y compartir conmigo

Cada punto dice: la tabla (nombre lógico → físico con prefijo `sff_`), qué mirar, y qué
copiar en el chat para que lo analicemos juntos. El orden es el del pipeline. Los
puntos marcados **★** son los que más información dan por línea de texto: si solo puedes
compartir tres, que sean esos.

Todos salen de `run_analysis(configuration)`; la consola de esa ejecución ya imprime
un resumen de cada uno (cópiala entera si puedes: son ~150 líneas).

---

## FASE 0 · el raw

**P0.1 · La foto del raw** — consola `[0.1]` y `[0.2]`.
Filas, meses, roles después de la doctrina del mes en curso, dinero de pipeline por rol,
filas que traían resultados en proyección (deberían ser solo las del mes en curso).
Compartir: las líneas `[0.1]`/`[0.2]`/`[0.3]`.

**P0.2 · Rutas y universos** — `fu_summary` (`forecast_units_raw_summary`).
```sql
SELECT ruta, universo, COUNT(*) series, SUM(usd_proyectado) usd FROM sff_fu_summary GROUP BY 1,2
```
Qué mirar: cuánto dinero va por `heuristic` (series solo en proyección) y por
`time_series` (universo reservado). Si es > 5 % del total, hay que hablar de ellos.

**P0.3 · Perfil del raw (nivel 0)** — `raw_profile` y `dim_domains`.
```sql
SELECT seccion, concepto, valor, detalle FROM sff_raw_profile
SELECT dimension, valor, filas, usd, primer_mes, ultimo_mes FROM sff_dim_domains WHERE aparece_dentro = 1 OR desaparece_dentro = 1 ORDER BY usd DESC
```
Qué mirar: calendario contiguo por rol; filas con renovados > pipeline o uplift de fila fuera de [0,3, 3]; valores de dimensión que aparecen o desaparecen a mitad de historia (movimientos de cartera, cambios de catálogo); plazos sin mapear.

**P0.4 · Perfil de las unidades (nivel 1)** — `fu_profile` y `dial_buckets`.
```sql
SELECT tramo_dial, series, usd, pct_usd FROM sff_dial_buckets ORDER BY 1
SELECT fs_id, primer_mes, ultimo_mes, meses, huecos, nace_dentro, muere_dentro, n_mediana, combinaciones_max, meses_0pct, meses_100pct
FROM sff_fu_profile WHERE nace_dentro = 1 OR muere_dentro = 1 OR huecos > 3 ORDER BY usd_proyectado DESC
```
Qué mirar: cuánto dinero está en unidades por debajo de 30 antes de prestar (la foto cruda), series que nacen o mueren dentro de la historia, series con muchas combinaciones de revalorización por unidad (nunca tendrán uplift propio).

---

## FASE 1 · series, dimensiones, escalera

**P1.1 ★ Dinero por nivel de riesgo** — `risk_levels` (`risk_levels_report`).
La tabla más importante del framework: cuánto dinero se predice con qué calidad.
```sql
SELECT nivel_riesgo, series, usd, pct_usd, error_medio_pp FROM sff_risk_levels ORDER BY 1
```
Niveles: A propio · B prestado (peldaño ≤ 2) · C lejano (peldaño ≥ 3 o neutra bajo suelo) ·
D sin historia · S con signo bajo suelo · M signo mixto · N sin impacto · T universo ts.
Compartir: la tabla entera (8 filas).

**P1.2 · Separación de dimensiones** — `decision_eta2` y `decision_eta2_pairs`.
```sql
SELECT dimension, grupo, eta2_individual, contribucion_unica, omega2, anulable FROM sff_decision_eta2
SELECT par, eta2_par, interaccion FROM sff_decision_eta2_pairs ORDER BY interaccion DESC
```
Qué mirar: una dimensión con η² individual alto pero contribución única baja está
confundida con otra (no separa por sí misma). La extra con menor contribución única es la
que se anula en el peldaño 2. Un par con interacción alta es una combinación que separa
más que sus partes (candidata a celda mandatory).
Compartir: las dos tablas.

**P1.3 ★ La ficha de cada serie** — `series_card`.
```sql
SELECT fs_id, signo, ruta, n_propio, meses_historia, huecos, tasa_propia, error_binomial_pp,
       id_estimacion, peldano, n_efectivo, k, z, tasa_estimada, se_estimacion_pp, se_prediccion_pp,
       nivel_riesgo, usd_proyectado
FROM sff_series_card ORDER BY usd_proyectado DESC
```
Qué mirar: las 20-30 series con más dinero; para cada una, de quién toma la tasa
(`id_estimacion`), a qué peldaño, con qué peso (`z`), y la diferencia entre
`se_estimacion_pp` (lo que sabemos de la tasa) y `se_prediccion_pp` (lo que va a pasar
en un mes con ese n). Compartir: las 30 primeras filas.

**P1.4 · La escalera de cada serie** — `parent_ladder`.
```sql
SELECT fs_id, peldano, descripcion, padre_id, n_padre, tasa_padre, elegido FROM sff_parent_ladder
WHERE fs_id IN ('...')   -- las series que llamen la atención en P1.3
ORDER BY fs_id, peldano
```
Qué mirar: si el peldaño elegido tiene sentido, si el salto de tasa entre peldaños es
grande (una serie cuyo padre tiene una tasa muy distinta de la propia está heredando
comportamiento ajeno), y las series con `elegido` en el último peldaño (bajo suelo).

**P1.5 · Composición: la cuenta** — `mandatory_only_cost`, `mix_shift`.
```sql
SELECT celda, SUM(ahorro_usd) ahorro, AVG(gana_segmentado) pct_gana, COUNT(*) meses
FROM sff_mandatory_only_cost GROUP BY 1 ORDER BY ahorro DESC
SELECT celda, AVG(ABS(delta_composicion_pp)) riesgo_mix_pp, AVG(ABS(delta_comportamiento_pp)) mov_comportamiento_pp
FROM sff_mix_shift GROUP BY 1 ORDER BY 2 DESC
```
Qué mirar: cuánto sobre o infraestimaría la vista solo-mandatory (una tasa por celda) y en
qué celdas; y en qué celdas el agregado se mueve por composición. Es la cuenta de la
composición, no una búsqueda de casos. Compartir: ambas.

**P1.6 · Calibración de los flags timevarying** — `tv_calibration`.
```sql
SELECT tipo, nombre, signo, COUNT(*) meses, SUM(n) n, SUM(n*tasa_realizada)/SUM(n) tasa
FROM sff_tv_calibration GROUP BY 1,2,3
```
Qué mirar: la tasa realizada de cada flag y de cada signo. Un flag `negative` cuya tasa
realizada no es claramente menor que la de los neutros no está funcionando como señal.
Compartir: la tabla (pocas filas) y, si hay un flag dudoso, su serie mensual.

---

## FASE 2 · dinámica

**P2.1 ★★ El benchmark de estacionalidad** — `decision_estacionalidad` (consola `[2] SEASONALITY BENCHMARK`).
```sql
SELECT fs_id, grupo, usd_proyectado, n_mediana, meses, phi, amplitud_pp, mes_alto, mes_bajo, consistencia_alto, consistencia_bajo,
       mejora_h1_pct, mejora_h6_pct, usd_impacto, veredicto_estacional, pendiente_pp_anio, veredicto_tendencia, motivo
FROM sff_decision_estacionalidad ORDER BY usd_proyectado DESC
```
Qué mirar: la DECISIÓN de la consola (sin estación material / estación en estas series), y por serie: φ (cuánto se mueve más que el muestreo), amplitud en pp y meses extremos, si esos meses son altos/bajos todos los años, y si la forma mejora al nivel reciente a 1 y 6 meses vista. `bench_panel` (serie × mes × año → z) es la figura para Power BI; `bench_flags`, la estación de las señales. Compartir: la tabla entera y la línea DECISION.

**P2.2 · Referencia de pools** — `pool_reference`: por id de estimación, meses, soporte, tasa, gate y si lleva efectos de mes.

---

## FASE 3 · backtest

**P3.1 ★ Leaderboard y campeones** — consola `[3]` y `decision_technique`.
```sql
SELECT id_estimacion, tecnica, tecnica_origen, err_norm_medio, err_pp_medio, n_predicciones, retador_err_norm
FROM sff_decision_technique ORDER BY err_pp_medio DESC
```
Qué mirar: `err_norm_medio` en unidades del error binomial: 1.0 = un error de muestreo;
un id con 1.0 está en el suelo teórico y ninguna técnica lo va a mejorar; uno con 3.0 tiene
algo que capturar. `retador_err_norm` − `err_norm_medio` es cuánto gana el campeón sobre
la media. Compartir: la tabla y el leaderboard de consola.

**P3.2 ★ Hold-out 2026** — `backtest_holdout`.
```sql
SELECT h, AVG(ABS(err_pp)) err_pp, AVG(err_pp) sesgo_pp, AVG(dentro_banda) pct_dentro, COUNT(*) n
FROM sff_backtest_holdout GROUP BY h ORDER BY h
SELECT id_estimacion, AVG(ABS(err_pp)) err_pp, AVG(err_pp) sesgo_pp, AVG(dentro_banda) pct_dentro
FROM sff_backtest_holdout WHERE h <= 3 GROUP BY 1 ORDER BY 2 DESC
```
Qué mirar: el error medio por horizonte sobre los meses de 2026 ya ocurridos, el sesgo
(si el signo medio es negativo, se sobreestima), y el % dentro de banda (objetivo ≈ 90 %).
Los ids con sesgo grande son los que tienen una tendencia que la técnica no sigue.
Compartir: las dos consultas.

**P3.3 · Bandas por id y horizonte** — `decision_error_bands`.
```sql
SELECT id_estimacion, h, q_low_norm, q_high_norm, n_predicciones, banda_origen FROM sff_decision_error_bands
WHERE h IN (1, 3, 6, 12)
```
Qué mirar: la asimetría (q_low ≠ −q_high dice hacia dónde se equivoca), el crecimiento con
h, y `banda_origen`: `propia` (medida en el id) vs `familia` (prestada de la técnica).

---

## FASE 4 · uplift

**P4.1 · Uplift por celda** — `decision_uplift`.
```sql
SELECT uplift_cell_id, n_renovadores, uplift_propio, uplift_padre, uplift_celda, uplift, uplift_origen,
       banda_low, banda_high, recortado FROM sff_decision_uplift ORDER BY n_renovadores DESC
```
Qué mirar: uplifts fuera de [0.8, 1.6] (sospechosos), celdas `recortado = 1` (el tope actuó:
hay que entender por qué), y celdas que toman el padre (`uplift_origen != propia`) con
mucho dinero. Compartir: la tabla (suele ser < 50 filas).

---

## FASE 5 · forecast

**P5.00 ★★ Las tres preguntas de negocio** — `business_summary` (consola `[5] BUSINESS ANSWERS`).
```sql
SELECT anio, meses_reales, meses_forecast, renovado_real_usd, forecast_usd, total_esperado_usd, banda_low_usd, banda_high_usd,
       pipeline_real_usd, pipeline_proyectada_usd, pipeline_simulada_usd, forecast_sobre_real_usd, forecast_sobre_proyectada_usd, forecast_sobre_simulada_usd
FROM sff_business_summary
```
Qué mirar: ¿cómo acaba este año? (`renovado_real` + `forecast` = `total_esperado`); ¿cuál es la pipeline del año que viene? (real = contratos que existen hoy; proyectada = reentradas de renovaciones que estamos prediciendo; simulada = adquisición al ritmo histórico); ¿cómo acaba el año que viene? (forecast sobre cada origen). Cada fila de `forecast_detail` lleva `origen_pipeline` para tirar del hilo.

**P5.01 ★ La baseline de Excel** — `baseline_summary` (consola `[5] BASELINE`).
```sql
SELECT * FROM sff_baseline_summary
```
Qué mirar: por grano (global / corte grueso / mandatory) y ventana (1 / 3 / 12 meses), el forecast del resto del año y del siguiente frente al framework, y el error walk-forward de la propia baseline a 1 y 4 meses con su sesgo. Si la baseline reproduce la cifra de negocio, la diferencia con el framework está en las filas de `baseline_forecast` por mes; y el walk-forward dice cuál de las dos ha acertado más en los últimos 12 meses.

**P5.0 ★★ El resumen de la pipeline** — `pipeline_summary` (o consola `[5] PIPELINE SUMMARY`).
```sql
SELECT bloque, meses, pipeline_usd, esperado_usd, banda_low_usd, banda_high_usd, pct_banda_high,
       cota_min_usd, pct_cota_min, cota_max_usd, pct_cota_max, pct_simulado, pct_nivel_A, error_realizado_pct
FROM sff_pipeline_summary
```
Qué mirar: por bloque (resto del año, año siguiente, total): la **banda total** (idiosincrática ⊕ común: lo que prometemos), sus dos partes, la **cota mínima** (el muestreo de cada unidad en cuadratura: ningún método la baja), la **cota máxima** (todo el muestreo sumado en la misma dirección: el peor caso absoluto). La mejora de la pipeline se mide como la banda acercándose a la cota mínima. `error_realizado_pct` es lo que pasó de verdad en el hold-out a h ≤ 4. Compartir: la tabla entera (3-4 filas). Es la primera que hay que mirar.

**P5.1 ★ Horizonte** — `horizon_report_total`.
```sql
SELECT period, esperado_usd, banda_low_usd, banda_high_usd, pct_low, pct_high, pct_simulado, pct_tasa_serie
FROM sff_horizon_report_total ORDER BY period
```
Qué mirar: el total mensual con su banda asimétrica; desde qué mes el pipeline es simulado
(`pct_simulado`) y con qué factor de adquisición (consola `[5]`). Compartir: la tabla entera.

**P5.1b ★ Por región** — `forecast_by_region`.
```sql
SELECT region, esperado_usd, pct_del_total, pct_banda, pct_nivel_A, pct_senal, pct_nivel_S, uplift_medio, composicion_pct FROM sff_forecast_by_region ORDER BY esperado_usd DESC
```
Qué mirar: el cuadrante de cada región (peso × certeza) y sus palancas; ver `ESTRATEGIA_POR_REGION.md`.

**P5.2 · Forecast por nivel de riesgo** — `forecast_by_level`.
```sql
SELECT nivel_riesgo, esperado_usd, banda_low_usd, banda_high_usd, pct_low, pct_high FROM sff_forecast_by_level
```
Qué mirar: dónde está la incertidumbre en dinero. Un nivel C con banda ±20 % y $200k pesa
más que un nivel A con ±2 % y $1M.

**P5.3 · Detalle y origen de cada número** — `forecast_detail`.
```sql
SELECT tasa_origen, tecnica_origen, uplift_origen, simulada, COUNT(*) filas, SUM(esperado_usd) usd
FROM sff_forecast_detail GROUP BY 1,2,3,4
```
Qué mirar: qué parte del dinero viene de la técnica de su serie (`serie` + `campeon`),
cuánta cae al retador, cuánta a la celda o al global (debería ser ≈ 0).

**P5.4 · Panel de validación** — `validation_report` (o consola `VALIDATION PANEL`).
Compartir: el panel entero. Un FAIL en INTEGRITY/DOCTRINE detiene la ejecución; los WARN
de QUALITY son los puntos a discutir.

---

## Cómo compartirlo

1. La consola completa de `run_analysis` (es el resumen de todos los puntos).
2. P1.1, P1.3 (30 filas), P2.1, P3.1, P3.2, P5.1 — los seis ★.
3. Lo que te llame la atención de los demás.

Con eso puedo decirte dónde está el dinero mal predicho, si la escalera está eligiendo
bien, si las técnicas están capturando lo que hay, si las bandas están calibradas y dónde
merece la pena invertir la siguiente hora.
