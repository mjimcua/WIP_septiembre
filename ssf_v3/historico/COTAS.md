# COTAS — se_pp_max, moe_pp_max, moe_usd_max: qué son, cómo se miden, por qué importan

Tres columnas de `fu_summary` (una por unidad de forecast = serie × mes), calculadas en la
fase 0 antes de estimar ninguna tasa. Son la **cota** de lo que puede oscilar una unidad
por puro azar, sin saber nada de su comportamiento. Todo lo demás del framework se
mide contra esta cota.

## 1 · La idea en una frase

La tasa de renovación de un mes es una proporción: k renovados de n vencimientos. Aunque
la probabilidad real de renovar fuera exactamente la misma todos los meses, k cambiaría de
un mes a otro por muestreo. La cota dice **cuánto**, y depende solo de n.

## 2 · Las tres columnas

| Columna | Fórmula | Unidad | Qué es |
|---|---|---|---|
| `se_pp_max` | 100 · √(0,25 / n) | puntos porcentuales | el error estándar de una proporción en el **peor caso** (p = 0,5, donde p(1−p) es máximo = 0,25), con n = las unidades de pipeline de esa unidad (mínimo 1) |
| `moe_pp_max` | z · `se_pp_max` (z = 1,645 → 90 %) | puntos porcentuales | el **margen**: la mitad del intervalo en el que caerá la tasa del mes 9 de cada 10 veces por muestreo |
| `moe_usd_max` | `moe_pp_max` / 100 · pipeline $ de la unidad | dólares | el mismo margen en dinero, sobre el pipeline de esa unidad |

"max" porque es el peor caso: con la tasa real (p = 0,8, digamos) el error es menor
(√(0,16/n) en vez de √(0,25/n): un 20 % menos). Se usa el peor caso porque en la fase 0
todavía no hay tasa, y una cota que no depende de ella es la única honesta.

## 3 · Ejemplos con números

| Unidad | n (vencen) | pipeline $ | se_pp_max | moe_pp_max (90 %) | moe_usd_max |
|---|---|---|---|---|---|
| DACH · KIS MD · 2 year · 1 device · 2026-10 | 4.000 | $120.000 | 0,79 pp | ±1,3 pp | ±$1.560 |
| APAC · Kaspersky Plus · 1 year · 2026-10 | 40 | $1.200 | 7,9 pp | ±13,0 pp | ±$156 |
| Rusia · KTS · 2 device · 2026-10 | 12 | $360 | 14,4 pp | ±23,7 pp | ±$85 |

Lectura: en la primera unidad, si la tasa real es 80 %, el mes puede salir entre 78,7 y
81,3 aunque nada cambie; en la tercera, entre 56 y 100. **Nadie puede predecir la
tercera con ±3 pp**: ni una persona, ni una técnica, ni un modelo. Ese es el suelo.

El dial (los mismos números al revés): para tener ±15 pp hacen falta 30 unidades; ±5,
271; ±3, 752. De ahí sale el suelo de soporte (30).

## 4 · Cómo se suman: en cuadratura

Las cotas de unidades distintas son errores **independientes** (cada mes muestrea por su
cuenta), así que se suman en cuadratura: la cota de una suma es la raíz de la suma de
cuadrados, no la suma.

Ejemplo: 1.646 series de nivel A con ±3,9 pp de error de fila cada una. La suma lineal
sería ±3,9 % del total; en cuadratura, si tuvieran igual peso, ±3,9 / √1.646 ≈ ±0,1 %.
Por eso el agregado de muchas unidades bien soportadas es mucho más preciso que
cualquiera de ellas, y por eso `moe_usd_max` **no se suma** con SUM en Power BI: se suma
`moe_usd_max²` y se hace la raíz (`SQRT(SUMX(tabla, moe_usd_max^2))`).

Excepción: unidades que comparten la misma tasa estimada (mismo `id_estimacion` y mismo
mes) se equivocan juntas: entre ellas la suma es lineal. Eso ya lo hace
`aggregate_with_bands` en la fase 5; para `fu_summary`, donde todavía no hay tasa,
cuadratura simple.

## 5 · Sus parientes en las fases siguientes

| Dónde | Columna | Diferencia con la cota |
|---|---|---|
| `fs_summary` / `series_card` | `error_binomial_pp` | por **serie**, con su tasa propia y su n típico (mediana mensual), intervalo de **Wilson** (asimétrico cerca de 0 y 100 %); ya no es peor caso |
| `series_card` | `se_estimacion_pp` | error de la **estimación** de la tasa tras la credibilidad: combina en cuadratura z·(propio) y (1−z)·(pariente); baja cuando se presta soporte |
| `series_card` | `se_prediccion_pp` | error de la **predicción** de un mes: √(se_estimación² + binomial(p, n_propio)²); nunca baja de la cota de la propia serie, por mucho que se preste |
| `support_chain` | `se_pp`, `moe_usd` | la cota en cada peldaño de la escalera, sobre el dinero de la serie: cuánto margen se gana al subir |
| `decision_dynamics` | `cota_pp` | z · binomial del mes típico del **pool**: contra ella se declara la estacionalidad (amplitud > 2 × cota) y la tendencia |
| `backtest_pred` | `se_binom_pp`, `err_norm` | la cota del mes objetivo; `err_norm` = error / cota: 1,0 = un error de muestreo, el suelo teórico de cualquier técnica |
| `forecast_bands` | `banda_low_pp` / `_high_pp` | cuantiles del error medido × cota del pool ⊕ cota de la fila |

## 6 · Por qué importa

1. **Separa lo predecible de lo ruidoso antes de predecir.** `dial_buckets` reparte el
   dinero por tramo de cota; es la primera tabla que dice cuánto del negocio puede
   tener un forecast fino y cuánto solo puede tener un margen ancho, sin haber estimado nada.
2. **Da la escala de todo lo demás.** Un error de backtest de 6 pp es malo en una unidad
   con cota 1 pp y excelente en una con cota 14 pp. Por eso el juez mide en `err_norm`.
3. **Fija el suelo de la promesa a negocio.** Un mes con n = 40 no puede prometerse con
   ±3 pp; con n = 4.000 sí. Explicar esto (slide 3 y 4 de la presentación) es explicar
   por qué el forecast lleva banda y por qué la banda no es la misma para todos.
4. **Decide dónde invertir.** Bajar la cota solo se consigue con más n: agrupando
   (escalera) o esperando meses. Donde la cota es grande y el dinero también, la
   pregunta no es "qué técnica" sino "con quién agrupamos".
