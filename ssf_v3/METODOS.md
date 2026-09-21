# MÉTODOS — cada técnica del framework, explicada con números

Este documento existe para que ninguna técnica sea una caja negra. Cada sección dice qué
problema resuelve, cómo se calcula, un ejemplo con números y dónde vive en el código.
Los nombres persistidos están en español; el código en inglés.

---

## 1 · La referencia binomial

**Problema.** La tasa de renovación es una proporción: k renovaciones de n vencimientos.
Aunque la probabilidad real no cambie, el resultado de cada mes oscila. ¿Cuánto?

**Cálculo.** Error estándar de una proporción: `se = √(p(1−p)/n)`. En puntos porcentuales
(pp), ×100. Con p = 0,8 y n = 100: se = √(0,16/100) = 0,04 → **±4 pp** cada mes por puro
muestreo. Con n = 12: ±11,5 pp. Con n = 600: ±1,6 pp.

**El intervalo (Wilson).** El intervalo "p ± z·se" (Wald) falla cerca de 0 % y 100 % y con n
pequeño (puede salir 104 %). El de Wilson corrige el centro y es asimétrico cerca de los
bordes: con p̂ = 0,95, n = 20 y z = 1,645 da [0,85; 0,98], no [0,87; 1,03]. Es lo que
persiste `error_binomial_pp` (mitad del ancho de Wilson).

**El dial.** Cuántos clientes hacen falta para un margen dado (90 %, p = 0,5):
`n = (z·100·√(p(1−p)) / τ)²` → ±15 pp ↔ 30 · ±5 pp ↔ 271 · ±3 pp ↔ 752. De aquí sale el
suelo de soporte: 30.

**Dónde.** `binomial_reference.py` (`binomial_se`, `wilson_interval`, `support_for_half_width`).

---

## 2 · Cuadratura: cómo se suman los errores

**Primero, lo que sí hacemos.** Cada pool tiene su intervalo de confianza de la tasa (los
cuantiles de su error medido en el backtest) y ese intervalo se convierte en dinero
fila a fila: tasa ± banda × dólares que vencen × uplift. Hasta ahí, exactamente lo que
propones. La pregunta es la siguiente: tengo 2.000 piezas, cada una con su intervalo en
dólares; ¿cuál es el intervalo de la suma?

**La intuición, con dos piezas.** Dos pools, cada uno puede fallar ±$10.000. Si sumo los
intervalos, la suma puede fallar ±$20.000. Pero eso solo ocurre si los dos fallan a la
vez, en la misma dirección y por el máximo. Si cada uno falla por su cuenta (uno se
pasa, el otro se queda corto), lo normal es que se compensen en parte: el fallo típico
de la suma es √(10.000² + 10.000²) = $14.100, no $20.000. Eso es "en cuadratura": los
errores independientes se suman por sus cuadrados, como los catetos de un triángulo.

**Con muchas piezas se nota mucho más.** 100 pools de ±$10.000 cada uno: sumando
intervalos, ±$1.000.000; en cuadratura, √100 × 10.000 = ±$100.000. Diez veces menos.
Con 2.000 pools, 45 veces menos. Por eso la banda del total salía de ±0,25 %: es
matemáticamente correcta **si** los 2.000 pools fallan cada uno por su cuenta.

**Y ahí está la trampa.** No fallan del todo por su cuenta. Una subida de precios, una
campaña, un cambio de mercado mueven muchos pools a la vez y en el mismo sentido. El
sesgo del hold-out (todos los pools quedándose cortos a horizontes largos) lo demuestra.
Ese error común no se compensa: se suma linealmente, como en el primer caso.

**Lo que hace el framework, en tres pasos.**
1. Dentro de un mismo pool y mes, las filas comparten tasa: si el pool falla, fallan
   todas juntas → sus bandas se suman en línea.
2. Entre pools y meses distintos, la parte **idiosincrática** (lo que cada uno falla por
   su cuenta) se suma en cuadratura.
3. La parte **común** se mide aparte: se suma toda la cartera por mes y horizonte, se
   compara con el total real en los meses de decisión, y sus cuantiles por horizonte
   son la banda común, que se aplica al dinero de cada mes y se suma en línea entre
   meses. La banda que se promete es la combinación de la idiosincrática y la común.

**Con números (sintético).** Idiosincrática ±1,9 %; común −2,5 / +5,0 %; total
−3,1 / +5,3 %. El peor mes realizado del examen: 2,8 pp. Sin la parte común, la banda
habría sido ±1,2 % y ese mes se habría salido.

**Cómo se aplica.** `aggregate_with_bands` (pasos 1 y 2), `aggregate_error_bands` y
`common_band_per_row` (paso 3), `pipeline_summary` y `business_summary` (la suma).

## 3 · Credibilidad (Bühlmann-Straub)

**Problema.** Una serie con 12 clientes al mes tiene tasa propia (ruidosa) y un pariente
con 600 (preciso pero no es exactamente ella). ¿Cuánto creerse a cada uno?

**Cálculo.** `tasa = z·propia + (1−z)·pariente`, con `z = n/(n+k)`. El k se estima por
pariente: `k = varianza dentro / varianza entre` de las series hermanas del pool:
- *dentro* = media de p_i(1−p_i) (cuánto oscila cada una por muestreo);
- *entre* = varianza ponderada de las tasas de las hermanas menos la parte que ya explica
  el muestreo.
Grupo homogéneo (las hermanas tienen la misma tasa) → *entre* ≈ 0 → k grande → z ≈ 0 → la
serie toma la del pool. Grupo heterogéneo → k pequeño → conserva la suya.

**Dos suelos.** `support_floor = 30` dice qué grupo tiene evidencia suficiente para
prestar (por debajo, una tasa es una moneda: ±15 pp). `own_rate_floor = 271` dice qué
serie tiene precisión suficiente para ir sola (±5 pp, la promesa a negocio). Entre 30 y
271 hay evidencia sin precisión: la serie sube hasta su primer pariente con soporte y
mezcla con z = n/(n+k). Con un solo suelo en 30, una cohorte de 120 iría sola con ±7,5
pp teniendo al lado un pool de 2.400 con ±1,7; con un solo suelo en 271, ignoraría sus
120 clientes y las señales de churn (que casi nunca reúnen 271) se quedarían sin pool.

**Ejemplo (sintético).** Negativos `EU|SIG=negativo|A|web`: hermanas con tasas 0,31-0,44 →
k = 111; la serie de n = 12 tiene z = 12/(12+111) = 0,10: 10 % suya, 90 % del pool. Con
menos de 3 hermanas no hay varianza entre que estimar: k = `k_cred` = 60.

**Dos errores.** `se_estimacion_pp` = error de la mezcla (cuadratura de las dos partes
ponderadas); `se_prediccion_pp` = √(se_estimación² + se_binomial(p, n_propio)²): el mes que
vamos a predecir sigue muestreando con el n de la serie. Prestar soporte mejora lo que
*sabemos* de la tasa, no lo que *va a pasar* con 12 clientes.

**Dónde.** `run_support_ladder.py` (`estimate_credibility_k`, `estimate_rates`).

---

## 3b · Forma del pool, nivel de la serie

**Problema.** Una serie que presta toma su técnica (estación, tendencia) del pool: ella
sola no tiene con qué medirlas. Pero su nivel puede ser distinto del pool (renueva 5
puntos peor que su familia) y la credibilidad ya nos dijo cuánto creernos esa
diferencia (z).

**Cálculo.** En logit: `tasa(h) = pool(h) + z · (nivel propio − nivel del pool)`. El pool
pone la forma mes a mes; la serie pone su desviación, ponderada.

**Ejemplo.** Pool DACH·Front Line: 2.400 clientes, nivel 78 %, estacional: abril 84 %,
noviembre 72 %. Serie X dentro del pool: 120 clientes, nivel propio 73 %, z = 0,67.
Desviación aplicada: 0,67 × (73 − 78) = −3,4 puntos. Abril: 84 − 3,4 ≈ 80,6 %; noviembre:
72 − 3,4 ≈ 68,6 %. Con z → 0 (serie minúscula o hermanas iguales) X recibiría 84/72; con
z → 1, 79/67. Sin este paso, X recibía el 84/72 del pool aunque supiéramos que renueva
peor. `forecast_detail.tasa_pool_h` y `desviacion_propia_pp` guardan las dos partes.

**Dónde.** `run_forecast_assembly.py` (`assemble_forecast`).

---

## 4 · η², contribución única y el orden de colapso

**Problema.** ¿Qué dimensiones separan la tasa? ¿En qué orden puede una serie pequeña
prescindir de ellas para encontrar un pariente sin mezclar cohortes distintas?

**Tres medidas por dimensión** (series neutras, ponderadas por soporte):
- **η² individual**: cuánto explica la dimensión *sola* (varianza entre grupos / total).
  Engaña cuando dos dimensiones van juntas: las dos parecen explicar lo mismo.
- **contribución única** (tipo II): R²(todas) − R²(todas menos esta). Lo que se pierde si
  se anula esta *manteniendo las demás*. Es cero para una dimensión redundante con otra
  — y por construcción para todo nivel grueso de una jerarquía mientras esté el fino.
- **ω²**: η² descontando el número de grupos (muchas categorías con pocas series parecen
  señal por azar).

**El orden de colapso no usa la única: usa la pérdida secuencial.** La pregunta de la
escalera es "si ya he anulado las extras y estoy en la celda, ¿qué mandatory puedo
colapsar perdiendo menos?". Se responde paso a paso (greedy): con el modelo *solo de
mandatory*, en cada paso se puede dejar caer una dimensión si no queda un nivel más fino
de su familia (`_level_3` antes que `_level_2`), y cae la que menos R² pierde *dado lo que
queda*. Se repite hasta vaciar. En un caso con tu estructura:
`regional_3 (pierde 0,04) → regional_2 (0,00) → regional_1 (0,31) → purchase_type (0,62)`.
La que más separa colapsa la última. Se persiste en `decision_eta2.orden_colapso` y
`perdida_secuencial`; la suma acumulada de pérdidas dice hasta dónde es seguro subir.

**Por qué salió mal en la primera ejecución real.** Se usó la contribución única:
`purchase_type` daba 0,000 porque `net_new` (extra) llevaba la misma información, pero
`net_new` se anula en el peldaño 2 y `purchase_type` colapsaba primero. Corregido.

**Dónde.** `analysis_dimensions.py` (`weighted_eta2`, `weighted_r2_factorial`,
`sequential_collapse_order`).

---

## 5 · Composición: Kitagawa y el coste de la vista solo-mandatory

**Problema.** La tasa de una celda puede bajar sin que ninguna de sus series baje, solo
porque cambian los pesos (Simpson). ¿Cuánto del movimiento es eso?

**Descomposición de Kitagawa.** Para una celda entre dos meses, con series i de tasa p_i y
peso w_i (su parte del pipeline):
`Δ tasa = Σ w̄_i·Δp_i  (comportamiento)  +  Σ p̄_i·Δw_i  (composición)`
con w̄ y p̄ los puntos medios. Ejemplo: A al 90 % baja su peso de 60 % a 40 %, B al 50 %
sube de 40 % a 60 %; ninguna cambia su tasa → comportamiento 0, composición −8 pp: el
agregado baja del 74 % al 66 % "sin que pase nada". `mix_shift.delta_composicion_pp` es
ese término; `riesgo_mix_pp` de una celda es su valor absoluto medio.

**El coste de la vista solo-mandatory (walk-forward).** Para cada celda y cada mes t de los últimos 12: solo con
datos ≤ t−1, dos predicciones de la tasa de t: **plana** (Σren/Σpipe de la celda) y
**segmentada** (tasa pasada de cada serie, ponderada por el pipeline *real* de t). Se
comparan con lo que pasó; `ahorro_usd = (|err_plano| − |err_seg|) × pipeline$ de t`. No
busca casos: mide en dinero, celda a celda, qué habría costado predecir con las mandatory solas.

**Lectura de tus números.** 32 % del movimiento mes a mes es composición; segmentar
ahorra $536k en 12 meses ganando en el 49 % de los celda-meses: gana donde hay dinero y
pierde poco en muchas celdas pequeñas. La consola ahora lo lista por celda.

**Dónde.** `analysis_dimensions.py` (`counterfactual_and_decomposition`).

---

## 6 · La estacionalidad de la tasa se decide una vez: el benchmark

**Problema.** Una técnica de series temporales siempre devuelve una componente estacional,
haya o no; y con miles de clientes cualquier test de significación sale significativo.
¿Cómo decidir de forma defendible si la tasa tiene forma anual?

**Dónde se decide.** Donde la prueba tiene potencia y la composición está controlada: las
series grandes neutras (sin señal), segmentadas con todas las dimensiones, con ≥ 271
clientes en todos los meses cerrados (±5 pp de suelo), top 5 por dinero en cada región ×
producto. Lo que se mueve ahí es comportamiento, no mezcla de cartera. Si ahí no hay
estación material, no se busca en el resto (donde además no habría soporte para medirla).

**Cómo se decide, por serie.** (1) φ tras quitar la tendencia lineal: cuánto se mueve más
que el muestreo. (2) Regresión logit(tasa) ~ tendencia + dummies de mes, ponderada por n:
la amplitud (mes alto − mes bajo, en pp) y la pendiente ± su error; el LRT se reporta y
nunca decide. (3) Panel mes × año de residuos estandarizados: un mes es alto de verdad si
es alto casi todos los años. (4) La prueba que decide: en los últimos 6 meses cerrados,
"nivel reciente + efecto de mes" (T15) contra "nivel reciente" (ma3), a 1 y a 6 meses
vista. **Estacional** si amplitud ≥ 2 pp, meses extremos consistentes ≥ 2 de 3 años, y la
forma mejora al nivel ≥ 10 % a h=6 sin empeorarlo a h=1. **Tendencia** si |pendiente| ≥ 2
errores estándar y ≥ 1 pp/año. Materialidad = amplitud × pipeline de los meses extremos.

**La decisión para la cartera.** Si las series estacionales llevan menos del 10 % del
dinero de la muestra: la tasa no tiene estación material; el catálogo se queda en
técnicas de nivel. Si no: efectos de mes solo en esas series, nivel en el resto. Y una
comprobación aparte: la proporción de clientes con cada señal por mes del año, por si la
estación se ha mudado de la tasa a las señales.

**Ejemplo (sintético).** `EU|A`: φ 5,3, amplitud 11,8 pp (abril/noviembre), consistencia
1,0/1,0, la forma mejora al nivel +77 % a h=1 y +61 % a h=6 → estacional. `NA|A`:
amplitud 4,7 pp con p-valor 0,05, pero la forma empeora al nivel a h=1 (−24 %) → no
material. `EU|B`: tendencia −6,3 ± 0,5 pp/año, sin estación.

**Dónde.** `analysis_seasonality_benchmark.py`; `pool_reference` traslada el veredicto a cada pool.

## 7 · Logit y amortiguación en las técnicas

**Por qué logit.** Las técnicas predicen `log(p/(1−p))` y se transforma de vuelta. Así
ninguna predice más del 100 % ni menos del 0 %, los intervalos se estrechan al acercarse
al techo, y una tendencia se frena sola al acercarse a 1.

**Amortiguación.** Una tendencia no se extrapola lineal: a h meses se aplica
Σφ^i (φ = 0,9): a h = 1 el 90 % de la pendiente, a h = 12 el 64 %, a h = 24 el 82 % del
tope 9. Una serie que baja 1 pp/mes no llega a 0 en 2027: se estabiliza.

**El catálogo.** Técnicas de nivel (media, media de 3 y de 6 meses, EWMA, suavizado
exponencial, credibilidad temporal), dos series temporales clásicas que nunca inventan
estación (Holt amortiguado y Theta: nivel y tendencia), y dos con forma anual (T15 nivel
reciente + efecto de mes; Holt-Winters) que solo compiten en las series que el benchmark
declaró estacionales. Ninguna técnica decide por su cuenta que hay estación.

**Dónde.** `techniques.py`.

---

## 8 · Backtest rolling-origin y error normalizado

**Dos baterías, dos visiones.** Para cada pool, los 6 meses más recientes ANTES del
examen son los objetivos, y hay dos pruebas: la CORTA (predecir cada mes con datos hasta
el mes anterior: h = 1) y la MEDIA-LARGA (predecir cada mes con datos hasta seis meses
antes: h = 6). Los meses a más de seis de distancia usan la evidencia de seis y se
vuelven a predecir cada mes. La premisa: probar con los datos más recientes posibles,
entendiendo que hay que predecir con antelación.

**Cálculo.** Para cada id de estimación y cada mes objetivo t (los 6 más recientes antes
del examen, más los del examen), y cada horizonte h juzgado (1 y 6): origen = t − h; solo
historia ≤ origen; cada técnica elegible predice t. Error con signo: `err_pp = pred − real`. **Normalizado**:
`err_norm = err_pp / se_binomial(real, n_t)`. Un pool de 1.000 y otro de 35 se juzgan en
la misma escala: 1,0 = un error de muestreo, el suelo teórico.

**Un campeón por visión.** Uno para h = 1 (el mes en curso y el siguiente) y otro para
h ≥ 2 (juzgado a seis meses). Con solo 6 objetivos, las bandas propias de un pool son
raras (hacen falta 20 predicciones): casi todas vienen de la familia (misma técnica,
todos los pools, mismo h), escaladas al tamaño del pool.

**Un campeón por tramo de horizonte.** Una técnica que acierta el mes que viene no
tiene por qué saber nada de enero a doce meses vista: se elige un campeón para el tramo
corto (h 1-3), otro para el medio (4-6) y otro para el largo (7+), cada uno con los
horizontes de cribado que caen en su tramo. La figura `technique_error_by_horizon` lo
enseña: la media de 3 meses gana a la izquierda y pierde a la derecha frente a una
técnica con forma, o no, y entonces se sabe que la forma no existe.

**Preferencia justa por la memoria a largo plazo.** Cerca, el retador (el último
trimestre) sabe lo que hace falta; lejos, no sabe nada de la forma del futuro. Por eso
el margen para destronarlo baja con el horizonte (0,10 a un mes, 0,05 a medio, 0 a
largo): a 7-12 meses, una técnica que empate con el retador y use más historia gana
(`MEMORY_MONTHS`: media de 3 meses = 3, toda la historia = ∞). Nunca se elige una
técnica peor que el retador; solo se deja de exigir que sea mejor por un margen.

**Retador.** T3_ma3 (media de los últimos tres meses). Un campeón necesita ≥ 6 predicciones y
ganar por 0,10 errores binomiales; entre técnicas a menos de 0,10 de la mejor, gana la
familia más rica. Si no, `tecnica_origen = retador`.

**Hold-out.** Los meses ≥ `backtest_test_start` con verdad (2026-01..08), predichos con la
técnica elegida desde orígenes con toda la historia anterior. Es el examen corregido.

**Dónde.** `analysis_backtest.py`.

---

## 9 · Bandas asimétricas por cuantiles

**Cálculo.** Por (id, h): p5 y p95 del `err_norm` con signo de la técnica elegida
(propios si hay ≥ 20 predicciones; si no, de la familia = misma técnica, todos los ids).
Se hacen **monótonas en h** (una banda nunca se estrecha al alejarse). Con signo: una
serie que se sobreestima sistemáticamente tiene q_low = −1,7 y q_high = +1,2 → banda
desplazada, sin tocar el punto.

**Aplicación.** Banda de una fila = `q × se_binomial del mes típico del pool`, en
cuadratura con `z × se_binomial de la fila` (su propio muestreo), recortada a
[0, rate_cap]. En dinero: × pipeline$ × uplift. Por eso una serie de 12 clientes tiene
±20 pp aunque su pool tenga ±3.

**Calibración honesta.** Los meses del hold-out (≥ el corte: los de rol `examen` del
extracto) no se usan ni para elegir técnica ni para medir bandas; solo para examinar. Si
se usaran, el 90 % dentro de banda saldría por construcción. Si la banda es del 90 %, el
90 % de los meses del hold-out deben caer dentro; por encima del 96 %: demasiado ancha;
por debajo del 80 %: demasiado estrecha.

**La banda del total tiene dos partes.** La cuadratura de miles de pools supone que se
equivocan por causas independientes; el sesgo del hold-out (todos los pools en la misma
dirección a horizontes largos) demuestra que no del todo. Por eso el total lleva dos
bandas: la **idiosincrática** (cuadratura entre pools y meses) y la **común** (los
cuantiles del error de toda la cartera sumada, por horizonte, medidos en los meses de
decisión: `decision_agg_bands`), aplicada al dinero de cada mes y sumada linealmente entre
meses porque un shock común persiste. La banda que se promete es la combinación en
cuadratura de las dos. En el sintético: idiosincrática ±1,9 %, común −2,5/+5,0 %, total
−3,1/+5,3 %; el peor mes realizado del hold-out, 2,8 pp: dentro.

**Dónde.** `analysis_backtest.py` (`error_bands`), `run_forecast_assembly.py` (`forecast_bands`).

---

## 10 · Bootstrap del uplift

**Problema.** El uplift es un cociente de sumas (Σren$ / Σ(ren unidades × AUV pipeline));
su error no tiene fórmula limpia.

**Cálculo.** Se remuestrean las filas de renovadores de la celda con reemplazo 200 veces,
se recalcula el cociente, y p5/p95 de esos 200 valores es la banda. Intuitivo, sin teoría.
Con miles de renovadores la banda es de milésimas; con 30, de centésimas.

**Dónde.** `run_uplift.py` (`bootstrap_band`).

---

## 11 · Factor de adquisición (horizonte extendido)

**Cálculo.** Un contrato que renueva en m vuelve a vencer en m + plazo (12). Los que
vencerán en 2027 son los renovados en 2026 más los captados. Por serie,
`factor = mediana de pipeline(t) / renovados(t − 12)` en la historia = 1 + captación /
renovación. `pipeline simulada(m) = renovados(m − 12) × factor`, con renovados
observados si m − 12 tiene verdad, o esperados (pipeline × tasa) si es proyección. Las
filas van con `simulada = 1` y `factor_adquisicion`. Es la única hipótesis externa al dato.

**Dónde.** `run_forecast_assembly.py` (`acquisition_factor_by_series`, `extend_forecast_units`).

---

## 12 · La señal bajo suelo, explicada con tus números

Una serie *con señal* es una serie cuyos clientes tienen activo un flag de un modelo
(dormido, cancelación anunciada, no instalado → negativos; autorenovación → positivo).
Su tasa es muy distinta de la de los clientes sin señal (en el sintético: 38 % frente a
80 %). La doctrina dice: **una serie con señal nunca toma la tasa de series sin señal**,
ni de series con la señal contraria. Su escalera es:

```
R0  ella misma                                  EU|1|0|0|0|A|web         n = 15
R1  mismas dims, flags resumidos en el signo    EU|SIG=negativo|A|web         n = 42  (15+12+10+5)
R2  la extra anulada, mismo signo               EU|SIG=negativo|A|*           n = 42
R3  celda mandatory × signo  ← TOPE             EU|SIG=negativo|*|*           n = 42
```

Si en R3 sigue sin llegar a 30, **no hay más escalera**: se queda con la mejor tasa de su
signo (la de R3), sin credibilidad hacia nadie, con su banda binomial ancha, y el nivel
`S_signo_bajo_suelo` lo declara. Ruidosa, pero *cualificada*: prefiere ±26 pp de su
propio comportamiento a ±4 pp del comportamiento de otros.

En Kamelot son 4.287 series con $8,8M. La causa es que tu celda mandatory tiene 10
dimensiones: `regional_3 × product_2 × purchase_type × term_2 × band_2` es un punto, no
una celda, y "celda × signo" casi nunca reúne 30 clientes con señal. La decisión abierta
es permitir que las series con señal sigan subiendo por el orden de colapso *conservando
el signo* mientras la pérdida secuencial acumulada sea pequeña (las primeras mandatory
que colapsan son las que casi no separan: cohortes casi idénticas, no Simpson).
