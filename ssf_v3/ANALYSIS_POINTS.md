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

**P1.5 · Contrafactual Simpson y mix-shift** — `simpson_contrafactual`, `mix_shift`.
```sql
SELECT celda, SUM(ahorro_usd) ahorro, AVG(gana_segmentado) pct_gana, COUNT(*) meses
FROM sff_simpson_contrafactual GROUP BY 1 ORDER BY ahorro DESC
SELECT celda, AVG(ABS(delta_composicion_pp)) riesgo_mix_pp, AVG(ABS(delta_comportamiento_pp)) mov_comportamiento_pp
FROM sff_mix_shift GROUP BY 1 ORDER BY 2 DESC
```
Qué mirar: en qué celdas segmentar ahorra dinero (contra el método plano, con los pesos
reales del mes) y en qué celdas el agregado se mueve por composición (el Simpson
silencioso). Compartir: ambas.

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

**P2.1 ★ Diagnóstico de dinámica por id de estimación** — `decision_dynamics`.
```sql
SELECT id_estimacion, meses, n_pool, tasa_pool, cota_pp, phi, sd_obs_pp, sd_binom_pp, gate,
       estacional, amp_estacional_pp, ciclos_completos, meses_alto, meses_bajo, tendencia, pendiente_pp_ano
FROM sff_decision_dynamics ORDER BY n_pool DESC
```
Qué mirar: `phi` es la clave. φ ≈ 1: la tasa no se mueve, muestrea; la media es la mejor
técnica y no hay que buscar más. φ ≫ 1: hay motor. `gate` dice cuál cree el sistema que es
(estacional / tendencia) y `meses_alto` / `meses_bajo` los meses del perfil.
Compartir: la tabla entera ordenada por n_pool (suelen ser < 50 filas).

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

**P5.1 ★ Horizonte** — `horizon_report_total`.
```sql
SELECT period, esperado_usd, banda_low_usd, banda_high_usd, pct_low, pct_high, pct_simulado, pct_tasa_serie
FROM sff_horizon_report_total ORDER BY period
```
Qué mirar: el total mensual con su banda asimétrica; desde qué mes el pipeline es simulado
(`pct_simulado`) y con qué factor de adquisición (consola `[5]`). Compartir: la tabla entera.

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
