# DIEZ PREGUNTAS DE NEGOCIO QUE ESTE FORECAST RESPONDE

Cada pregunta con la tabla que la responde, las columnas, y cómo leerla. Todas salen de
`run_analysis`; las tablas van con prefijo `sff_`.

## 1 · ¿Cómo va a acabar este año?

`business_summary`, fila del año en curso: `renovado_real_usd` (lo ya contabilizado en
los meses cerrados) + `forecast_usd` (el mes pendiente de cierre y los meses de
proyección) = `total_esperado_usd`, con `banda_low_usd` / `banda_high_usd`.
Lectura: "si nada cambia, cerraremos en X, y nueve de cada diez veces entre X−a y X+b".
La parte del mes pendiente se ve aparte (`forecast_mes_pendiente_usd` frente a
`renovado_parcial_mes_pendiente_usd`, lo ya contabilizado): cuando cierre, comprobación
gratis.

## 2 · ¿Cuál es la pipeline del año que viene y cuánto de ella es real?

`business_summary`, fila del año siguiente: `pipeline_real_usd` (contratos que existen
hoy), `pipeline_proyectada_usd` (renovaciones que estamos prediciendo y que reentran un
plazo después) y `pipeline_simulada_usd` (la adquisición de los meses de proyección al
ritmo histórico). Lectura: cuanto mayor la parte real, más firme la respuesta a la
pregunta 3. Por mes, en `horizon_report_total` (`pipeline_real_usd`, `pipeline_proyectada_usd`,
`pipeline_simulada_usd`).

## 3 · ¿Cómo acabará el año que viene?

`business_summary`, fila del año siguiente: `forecast_usd` con su banda, y desglosado por
origen de pipeline (`forecast_sobre_real_usd`, `forecast_sobre_proyectada_usd`,
`forecast_sobre_simulada_usd`). Lectura: el forecast sobre pipeline real es un forecast;
el forecast sobre pipeline proyectada o simulada es un forecast sobre un forecast, y se
presenta como tal.

## 4 · ¿Cuánto podemos fiarnos del número? ¿Cuál es el peor caso?

`pipeline_summary`, por bloque (resto del año, año siguiente, total): `banda_total_*`
(lo que se promete: idiosincrática ⊕ común), `cota_min_usd` (el suelo de muestreo que
nadie baja), `cota_max_usd` (el peor caso absoluto), y lo que pasó de verdad en el examen:
`error_realizado_pct`, `error_total_realizado_pct`, `error_total_peor_mes_pct`.
Lectura: la banda es honesta si el error realizado del total cae dentro de ella.

## 5 · ¿Dónde está el dinero que no sabemos predecir bien?

`risk_levels` (por nivel: series, dinero, % y error) y `forecast_by_level` (forecast y
banda por nivel). Lectura: el nivel A (precisión propia) debería concentrar la mayor
parte del dinero; B/C (prestado) y S (señal sin pool) son donde invertir en datos o en
agrupación; D (sin historia) es lo que se predice por cascada.

## 6 · ¿En qué regiones (o productos) está el riesgo, y de qué tipo?

`forecast_by_region`: por región, `esperado_usd`, `pct_del_total`, `pct_banda`,
`pct_nivel_A`, `pct_senal`, `pct_nivel_S`, `uplift_medio`, `composicion_pct`. Lectura y
estrategia en `ESTRATEGIA_POR_REGION.md`: cada región cae en un cuadrante (peso × certeza)
y cada columna señala una acción distinta.

## 7 · ¿Cuánto vale un punto de tasa de renovación? ¿Y un 1 % de revalorización?

`forecast_detail`: Σ `total_tr_usd × uplift` / 100 es lo que mueve un punto de tasa en toda
la cartera; Σ `total_tr_usd × tasa` / 100, un 1 % de uplift. Por región, la misma suma
filtrada. Lectura: es la sensibilidad que convierte una campaña o una subida de precio en
dólares, y lo que hace comparables una mejora de retención y una de precio.

## 8 · ¿Qué clientes están en riesgo, cuánto dinero llevan, y qué renuevan de verdad?

`tv_calibration` (tasa realizada por flag y por signo, mes a mes) y `series_card` filtrada
por `signo`. Lectura: los negativos (dormidos, cancelación anunciada, no instalados)
renuevan al X % frente al Y % de los neutros; ese hueco, multiplicado por su pipeline, es
el dinero que una acción de recuperación puede disputar. Y la calibración dice si cada
señal funciona como señal.

## 9 · ¿La estacionalidad que vemos es real o es la cartera?

`decision_estacionalidad` (el benchmark sobre las series grandes) y `mix_shift` /
`mandatory_only_cost` (la cuenta de la composición). Lectura: si el benchmark no encuentra
estación material en la tasa y la composición explica una parte grande del movimiento,
lo que sube y baja cada año es *cuántos* vencen, no *cuántos* renuevan; y se predice
desde los vencimientos programados, no desde una onda.

## 10 · ¿Cuánto mejor es esto que la hoja de cálculo?

`baseline_summary`: por grano (global, corte grueso, mandatory) y ventana (1, 3, 12
meses), el forecast de la hoja frente al del framework, y el error walk-forward de la
hoja a 1 y 4 meses; el del framework, en `backtest_holdout_agg`. Lectura: si la hoja
acierta igual, el framework aporta la banda y la trazabilidad, no el número; si acierta
peor, aporta también el número. Y explica de dónde sale la diferencia con la cifra de
negocio cuando la hay.

## Y una que responde por el camino

**¿De dónde sale cada número?** `sheet(clave)`: la ficha de cualquier serie, unidad, fila,
pool o celda: de quién toma la tasa y con qué peso, qué técnica y por qué, qué banda y
por qué, y su forecast mes a mes con la pipeline por origen.
