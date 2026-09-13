# LA COTA BINOMIAL — se_pp_max, moe y el dial de 30 / 271 / 752

Un documento corto para una idea que sostiene todo el framework: **una tasa de renovación
medida sobre n clientes no puede ser más precisa que lo que n permite**, aunque la
probabilidad real no cambie nada. Ese límite se puede calcular antes de predecir, y por
eso es la primera medida que se persiste (`fu_summary`, por unidad) y la que fija el suelo
de soporte (30) y los tramos del dial (`dial_buckets`).

## 1 · La idea en una frase

Si 100 clientes vencen y cada uno renueva con probabilidad 0,8, no renovarán exactamente
80: unos meses 76, otros 84. Esa oscilación no es un error del modelo ni un cambio de
comportamiento: es muestreo. Cuanto menor es n, mayor es la oscilación. Predecir bien no
puede significar acertar dentro de esa oscilación; significa acertar *hasta* ella.

## 2 · Las tres medidas

**Qué es el MOE.** MOE = *margin of error*, margen de error: la mitad del ancho de un
intervalo de confianza. Si decimos "80 % ± 8 puntos al 90 %", el MOE es 8 puntos y
significa: en 9 de cada 10 meses, la tasa que observaremos estará entre el 72 % y el 88 %
aunque la probabilidad real de renovar sea exactamente el 80 % y nada haya cambiado. El
MOE no es cuánto nos equivocamos: es cuánto puede moverse el resultado por puro azar. Un
error menor que el MOE no es un error; uno mayor, sí.

Con n = unidades de pipeline de la unidad (los clientes que vencen ese mes) y p la
probabilidad de renovar:

| Medida | Fórmula | Qué es |
|---|---|---|
| **se** (error estándar) | √(p·(1−p) / n) | la desviación típica de la tasa observada en un mes con n clientes: la "unidad de azar" |
| **se_pp_max** | 100 · √(0,25 / n) | ese se en puntos porcentuales en el **peor caso**, p = 0,5 (donde p·(1−p) es máximo, 0,25). Es una cota: vale para cualquier p y no necesita conocer la tasa |
| **moe_pp_max** | z · se_pp_max, con z = 1,645 (90 %) | el MOE de la unidad: el margen dentro del cual caerá la tasa observada 9 de cada 10 meses. z traduce "una unidad de azar" a "un nivel de confianza": 1,645 → 90 %, 1,96 → 95 % |
| **moe_usd_max** | moe_pp_max / 100 · pipeline$ de la unidad | el MOE en dinero: cuántos dólares de esa unidad pueden moverse ese mes por azar |

Por qué p = 0,5: porque no hay tasa todavía cuando se calcula (fase 0) y porque es el caso
más desfavorable; a p = 0,8 el error real es un 20 % menor. Cuando ya hay tasa estimada,
el framework usa la propia p (Wilson en `error_binomial_pp` de `fs_summary`, y las bandas
de la fase 5).

## 3 · Ejemplos con números

| n (unidades que vencen en el mes) | se_pp_max | moe_pp_max (90 %) | lectura |
|---|---|---|---|
| 5 | 22,4 pp | ±36,8 pp | de 5 clientes al 80 % renovarán entre 2 y 5; el mes no dice casi nada |
| 10 | 15,8 pp | ±26,0 pp | ±26 puntos: el forecast de esa unidad es una moneda |
| **30** | 9,1 pp | **±15,0 pp** | el **suelo de soporte**: por debajo, se presta |
| 100 | 5,0 pp | ±8,2 pp | ya se distingue un 75 % de un 85 % |
| **271** | 3,0 pp | **±5,0 pp** | el corte del "5 %": una unidad con 271 vencimientos se predice a ±5 puntos |
| **752** | 1,8 pp | **±3,0 pp** | ±3 puntos |
| 1.000 | 1,6 pp | ±2,6 pp | |
| 5.000 | 0,7 pp | ±1,2 pp | |

Y en dinero: una unidad con 30 vencimientos de $30 (pipeline $900) tiene
`moe_usd_max` = 0,15 × 900 = **±$135**; una con 5.000 vencimientos ($150.000) tiene
±$1.800: mucho más dinero, mucho menos margen relativo (1,2 % frente a 15 %).

## 4 · El dial: de "cuánto error acepto" a "cuántos clientes necesito"

La misma fórmula al revés: `n = (z · 100 · √(p(1−p)) / margen)²`. Con p = 0,5 y 90 %:

| Margen que acepto | n necesario | Tramo en `dial_buckets` |
|---|---|---|
| ±15 pp | 30 | `0_menos_de_30` = por debajo del suelo |
| ±5 pp | 271 | `1_30_a_271` = con soporte, pero por encima de ±5 |
| ±3 pp | 752 | `2_271_a_752` = entre ±5 y ±3 |
| — | ≥ 752 | `3_desde_752` = mejor que ±3 |

Los 271 son el "corte del 5 %" que recordabas: con 271 vencimientos al mes, el margen de
muestreo baja de ±5 puntos. Si la tasa real está lejos de 0,5, hacen falta menos: a
p = 0,8 bastan 173 para ±5 pp y 481 para ±3 pp. Por eso `support_floor` y los tramos se
calculan con p = 0,5 (cota) pero `error_binomial_pp` de cada serie se calcula con su
tasa real (estimación).

Los tramos son configurables a través de `z` (cambiar a 1,96 para 95 % sube los cortes a
43 / 384 / 1.067) y de las amplitudes en `analysis_data_profile.DIAL_HALF_WIDTHS_PP`.

## 5 · Dónde se usa

- **`fu_summary`** (fase 0): las tres columnas por unidad. Sumables por lo que se quiera:
  "cuánto margen de puro muestreo tiene el dinero de septiembre" es `SUM(moe_usd_max)` de
  esas unidades (suma lineal: cota conservadora; en cuadratura sería menor).
- **`dial_buckets`** (fase 1, nivel 1): dinero proyectado por tramo de soporte de la serie,
  **antes de prestar**: la foto cruda de qué parte de la cartera puede predecirse a ±3,
  ±5, ±15 o peor.
- **`support_floor = 30`**: el suelo de la evidencia: qué grupo puede prestar una tasa.
- **`own_rate_floor = 271`**: el suelo de la precisión: qué serie puede ir sola (±5 pp).
  Entre los dos, la serie usa su tasa y la completa con su primer pariente con soporte,
  en proporción a n (credibilidad). 30 dice quién puede hablar; 271, quién puede hablar solo.
- **`fs_summary.error_binomial_pp`**: la mitad del intervalo de Wilson con la tasa propia y
  n_propio (mediana mensual): la versión "con tasa" de la misma cota.
- **Bandas de la fase 5**: la banda de cada fila combina en cuadratura el error del pool y
  el muestreo de la propia fila (`z · se` con su n): una serie de 12 unidades tiene ±20 pp
  aunque su pool tenga ±3, porque el mes sigue muestreando con 12.
- **Error normalizado del backtest**: cada error se divide por el se binomial del mes
  objetivo; 1,0 = un error de muestreo, el suelo teórico que ninguna técnica baja.

## 6 · Por qué importa

Sin esta cota, un forecast de una unidad de 10 clientes y otro de una de 5.000 se leen igual
("la tasa será 80 %") y se juzgan igual ("falló por 8 puntos"). Con ella, el primero tiene
±26 puntos de margen y el segundo ±1,2: el primero no falló, y el segundo sí. Es lo que
convierte "reportar" en "predecir": cada número lleva cuánto puede moverse por azar, y
cada error se mide en unidades de ese azar.
