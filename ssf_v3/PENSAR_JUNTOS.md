# PARA PENSAR JUNTOS — lo que los ejemplos ya dicen y lo que hay que decidir

No es documentación: son las observaciones que salen de mirar las salidas del sintético y
de la escala de Kamelot, con la pregunta que abre cada una y qué evidencia la cierra.
Cuando corras `run_analysis` sobre los datos reales, las primeras cuatro se responden solas.

## 1 · Lo que ya sabemos de tu cartera (por la captura)

10.877 series · 34.315 huecos · 7.107 series trainable bajo el suelo con $23,8M de los
$189,2M proyectados (12,6 % del dinero) · resto ($165M, 87 %) en 3.770 series con soporte.

Lectura: la escalera tiene trabajo (dos de cada tres series prestan), pero el dinero está
mayoritariamente en series que se predicen solas. La pregunta relevante no es "cuántas
series prestan" sino **cuántos ids de estimación distintos quedan** después de prestar:
ese número (`decision_dynamics` filas) es lo que gobierna el coste del backtest y la
calidad del pool. Si son ~1.000, todo va rápido y los pools son gordos; si son ~5.000,
muchas series se quedaron solas bajo el suelo (niveles S/C) y hay que mirar por qué.

**Primer dato a compartir**: `SELECT gate, COUNT(*), SUM(n_pool) FROM sff_decision_dynamics GROUP BY 1`.

## 2 · Lo que el ejemplo de auditoría enseña (AUDITORIA_EJEMPLO_SINTETICO.txt)

**a) La banda de una fila pequeña la domina su propio muestreo.** `EU|A|tele` (n=12)
toma la tasa de un pool de 612 con ±3 pp, pero su banda de fila es ±20 pp. Es correcto:
predecir 12 clientes es predecir 12 monedas. Pero al agregar, esas bandas anchas de
filas pequeñas entran en cuadratura y pesan poco. **Pregunta**: ¿queremos que el nivel B
en `forecast_by_level` muestre la banda de fila (lo que va a pasar) o la del pool (lo que
sabemos de la tasa)? Hoy muestra la de fila. Para negocio creo que es la honesta; para
decidir dónde invertir en datos, la del pool dice más.

**b) Sesgo persistente en el hold-out de un pool.** `EU|SIG=neg|A|web` (los negativos)
tiene sesgo −3,5 a −5,5 pp en los 8 meses de 2026: la media histórica (T2_mean) predice
por debajo de lo que pasó. La banda con signo lo absorbe ([−1,70; +1,58] × se) y el 100 %
cae dentro, pero el punto no se corrige. **Pregunta**: ¿debería el retador ser la media
reciente con credibilidad temporal (T14) en vez de la media de toda la historia? En el
sintético T14 no ganó por el margen 0,10. La evidencia que lo decide: en Kamelot, la
columna `sesgo_pp` por id en P3.2. Si la mayoría de ids tienen sesgo del mismo signo, el
retador está desfasado y hay que cambiarlo (es un parámetro: `challenger_technique`).

**c) La escalera de los negativos se para donde debe.** Los tres peldaños con signo
tienen el mismo n (42): en el sintético no hay más negativos en la celda. En Kamelot
veremos peldaños que sí crecen; lo que hay que vigilar es el salto de tasa entre el
peldaño 1 y el 3 (`parent_ladder.tasa_padre`): si el "celda × signo" tiene una tasa muy
distinta del "mismas dims × signo", estamos prestando comportamiento ajeno y el nivel C
merece su nombre.

## 3 · Parámetros que yo cambiaría primero, y con qué evidencia

| Parámetro | Defecto | Cambiaría a | Si la evidencia dice… |
|---|---|---|---|
| `challenger_margin_normalized` | 0.10 | 0.05 | en P3.1 muchos ids tienen un campeón a menos de 0,10 del retador con `n_predicciones` ≥ 24 (evidencia sobrada, margen demasiado conservador) |
| `challenger_technique` | T2_mean | T14_temporal_cred | sesgo sistemático del mismo signo en P3.2 (la historia lejana ya no describe el presente) |
| `support_floor` | 30 | 50 | `risk_levels`: el nivel A tiene error medio > 5 pp porque hay muchas series "propias" entre 30 y 50 |
| `support_floor` | 30 | 20 | el nivel B/C acumula > 20 % del dinero con parientes cuya tasa dista > 10 pp de la propia (`support_chain` etapa 0 vs final) |
| `band_low/high_quantile` | .05/.95 | .10/.90 | P3.2 muestra > 96 % dentro de banda en todos los h (banda demasiado ancha: el negocio deja de leerla) |
| `backtest_max_targets` | 24 | 12 | la cartera cambió de régimen (una campaña, un cambio de producto) y los 24 meses mezclan dos mundos |
| `trend_horizon_months` | 6 | 3 | series con `tendencia ≠ 0` cuyo hold-out empeora con h más rápido que las demás |
| `uplift_cap` | 3.0 | 2.0 | en `decision_uplift` hay celdas recortadas con `n_renovadores` grande (no es ruido: es un bundle o una moneda, y hay que tratarlo aparte) |

## 4 · Tres cosas que el sintético NO puede enseñar y Kamelot sí

1. **Cuántas dimensiones separan de verdad.** Con una mandatory el η² es trivial. Con
   tus 5-8 dims, `decision_eta2` va a decir qué extras se pueden anular sin perder nada
   (contribución única ≈ 0) y `decision_eta2_pairs` si alguna pareja (región × producto)
   separa más que sus partes. Eso puede cambiar qué es mandatory.
2. **Si el uplift necesita η² propio.** Hoy el uplift repara soporte por padre/celda con
   `uplift_parent_keep_columns`. Si en `decision_uplift` las celdas con el mismo
   `newcust` y distinto `discount` tienen uplifts muy distintos, el padre correcto no es
   "newcust" sino "newcust × discount" y hay que decidirlo con datos, no a mano.
3. **El factor de adquisición.** En el sintético sale 1,43 porque la pipeline es
   constante y la tasa ~0,8 (1/0,8 + captación). En Kamelot, `fu_extended.factor_adquisicion`
   por serie dirá si la captación es estable (mediana ≈ media) o si hay series con
   factores absurdos (> 3: captación masiva o un dato mal) que conviene fijar con
   `acquisition_factor` global.

## 5 · Lo que no me convence del todo (para que lo discutamos)

- **La banda de familia con pocas series.** Cuando un id tiene < 20 predicciones a un h,
  toma los cuantiles de "la misma técnica en todos los ids". Si en Kamelot casi todos los
  ids usan T2_mean, la familia es enorme y muy heterogénea; puede ser demasiado ancha para
  un pool grande y demasiado estrecha para uno pequeño. Alternativa: familia por técnica
  **y tramo de n_pool** (tres tramos). Es un cambio pequeño; la evidencia es `banda_origen`
  = familia con `pct_dentro` lejos del 90 %.
- **El mes en curso.** Se predice como h=1 desde el último mes con verdad, y sus
  resultados parciales se borran. Con datos reales el mes en curso a día 13 ya tiene
  ~40 % de las renovaciones cerradas; usarlas (un "nowcast" = parcial observado +
  predicción del resto) reduciría el error de h=1 a la mitad. No está hecho; es la
  primera mejora que propondría después de estabilizar lo demás.
- **Series mixtas.** Si en Kamelot hay muchas (`M_signo_mixto` con dinero), el problema
  no es del forecast: dos modelos están marcando al mismo cliente en sentidos opuestos.
  La calibración `tv_calibration` por flag dice cuál de los dos tiene razón.
