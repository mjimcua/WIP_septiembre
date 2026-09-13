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

**Problema.** El forecast total es una suma de muchas piezas, cada una con su banda. ¿Cuál
es la banda de la suma? No es la suma de las bandas.

**Regla.** Si dos errores son **independientes**, sus varianzas se suman y el error de la
suma es la raíz de la suma de cuadrados: `e = √(e₁² + e₂²)`. Eso es "en cuadratura". Si
los errores son el **mismo** error (dos filas que usan la misma tasa se equivocan a la
vez y en el mismo sentido), se suman linealmente: `e = e₁ + e₂`.

**Ejemplo.** Dos series con bandas ±$3.000 y ±$4.000:
- independientes → √(9 + 16) = **±$5.000** (no ±7.000);
- misma tasa (comparten `id_estimacion` y mes) → **±$7.000**.
Con 1.646 series de nivel A de ±3,9 pp cada una, el error relativo del total baja hacia
3,9 / √1.646 ≈ 0,1 pp si fueran iguales e independientes. Por eso el agregado de muchas
series bien soportadas es más preciso que cualquiera de ellas — y por eso los agregados
suman errores *solo* cuando comparten la causa.

**Cómo se aplica.** `aggregate_with_bands`: primero suma LINEAL dentro de cada
(`id_estimacion`, mes) — las filas que comparten tasa —, después CUADRATURA entre grupos.
El mismo criterio en la banda de cada fila: el error del pool y el muestreo de la fila son
independientes → `√((q·se_pool)² + (z·se_fila)²)`. Y en la estimación por credibilidad:
`se_est = √((z·se_propio)² + ((1−z)·se_pariente)²)`.

**Dónde.** `run_forecast_assembly.py` (`aggregate_with_bands`, `forecast_bands`),
`run_support_ladder.py` (`estimate_rates`).

---

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

**Ejemplo (sintético).** Negativos `EU|SIG=neg|A|web`: hermanas con tasas 0,31-0,44 →
k = 111; la serie de n = 12 tiene z = 12/(12+111) = 0,10: 10 % suya, 90 % del pool. Con
menos de 3 hermanas no hay varianza entre que estimar: k = `k_cred` = 60.

**Dos errores.** `se_estimacion_pp` = error de la mezcla (cuadratura de las dos partes
ponderadas); `se_prediccion_pp` = √(se_estimación² + se_binomial(p, n_propio)²): el mes que
vamos a predecir sigue muestreando con el n de la serie. Prestar soporte mejora lo que
*sabemos* de la tasa, no lo que *va a pasar* con 12 clientes.

**Dónde.** `run_support_ladder.py` (`estimate_credibility_k`, `estimate_rates`).

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

## 5 · Mix-shift: Kitagawa y el contrafactual

**Problema.** La tasa de una celda puede bajar sin que ninguna de sus series baje, solo
porque cambian los pesos (Simpson). ¿Cuánto del movimiento es eso?

**Descomposición de Kitagawa.** Para una celda entre dos meses, con series i de tasa p_i y
peso w_i (su parte del pipeline):
`Δ tasa = Σ w̄_i·Δp_i  (comportamiento)  +  Σ p̄_i·Δw_i  (composición)`
con w̄ y p̄ los puntos medios. Ejemplo: A al 90 % baja su peso de 60 % a 40 %, B al 50 %
sube de 40 % a 60 %; ninguna cambia su tasa → comportamiento 0, composición −8 pp: el
agregado baja del 74 % al 66 % "sin que pase nada". `mix_shift.delta_composicion_pp` es
ese término; `riesgo_mix_pp` de una celda es su valor absoluto medio.

**Contrafactual walk-forward.** Para cada celda y cada mes t de los últimos 12: solo con
datos ≤ t−1, dos predicciones de la tasa de t: **plana** (Σren/Σpipe de la celda) y
**segmentada** (tasa pasada de cada serie, ponderada por el pipeline *real* de t). Se
comparan con lo que pasó; `ahorro_usd = (|err_plano| − |err_seg|) × pipeline$ de t`. No
busca casos: mide en dinero, celda a celda, qué habría costado no segmentar.

**Lectura de tus números.** 32 % del movimiento mes a mes es composición; segmentar
ahorra $536k en 12 meses ganando en el 49 % de los celda-meses: gana donde hay dinero y
pierde poco en muchas celdas pequeñas. La consola ahora lo lista por celda.

**Dónde.** `analysis_dimensions.py` (`counterfactual_and_decomposition`).

---

## 6 · φ: ¿se mueve la serie o solo muestrea?

**Cálculo.** φ = varianza observada de la tasa mensual / varianza que predice la binomial
(p̄(1−p̄)·media(1/n_t), con el n de cada mes). φ ≈ 1: la tasa no se mueve, muestrea; la
media es la mejor técnica. φ ≫ 1: hay un motor (estación, tendencia, régimen, mezcla
interna) y una técnica de series temporales tiene algo que capturar.

**Ejemplo.** Una serie plana con n = 300: sd observada 2,4 pp, sd binomial 2,3 → φ ≈ 1,1.
La estacional `EU|A` (±5 pp de amplitud): φ = 5,2. Y la que gana en el backtest con T7 es
justo esa.

**Estacionalidad y tendencia** se miden sobre la serie *sin tendencia* (una serie que baja
dos años parece "estacional": sus eneros son más altos que sus diciembres) y se declaran
solo si superan 2× la cota binomial del mes típico del pool.

**Dónde.** `binomial_reference.py` (`overdispersion_phi`), `analysis_dynamics.py`.

---

## 7 · Logit y amortiguación en las técnicas

**Por qué logit.** Las técnicas predicen `log(p/(1−p))` y se transforma de vuelta. Así
ninguna predice más del 100 % ni menos del 0 %, los intervalos se estrechan al acercarse
al techo, y una tendencia se frena sola al acercarse a 1.

**Amortiguación.** Una tendencia no se extrapola lineal: a h meses se aplica
Σφ^i (φ = 0,9): a h = 1 el 90 % de la pendiente, a h = 12 el 64 %, a h = 24 el 82 % del
tope 9. Una serie que baja 1 pp/mes no llega a 0 en 2027: se estabiliza.

**Elegibilidad.** Cada técnica declara meses mínimos y etiqueta necesaria (`dim_tecnica`):
una serie sin estacionalidad nunca compite con T7; una con 14 meses nunca con
Holt-Winters (24). Así se usan series temporales *cuando se puede*, sin que ganen por
suerte cuando no.

**Dónde.** `techniques.py`.

---

## 8 · Backtest rolling-origin y error normalizado

**Cálculo.** Para cada id de estimación y cada mes objetivo t (los 24 más recientes con
verdad), y cada horizonte h juzgado: origen = t − h; solo historia ≤ origen; cada técnica
elegible predice t. Error con signo: `err_pp = pred − real`. **Normalizado**:
`err_norm = err_pp / se_binomial(real, n_t)`. Un pool de 1.000 y otro de 35 se juzgan en
la misma escala: 1,0 = un error de muestreo, el suelo teórico.

**Dos etapas.** Cribado de todas las técnicas en h = {1, 3, 6} → campeón; luego solo
campeón y retador en todos los horizontes → bandas. Cuesta un tercio que juzgarlo todo.

**Retador.** T2_mean (media de toda la historia). Un campeón necesita ≥ 6 predicciones y
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

**Calibración.** Si la banda es del 90 %, el 90 % de los meses del hold-out deben caer
dentro (`backtest_holdout.dentro_banda`). Por encima del 96 %: demasiado ancha; por debajo
del 80 %: demasiado estrecha.

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
R1  mismas dims, flags resumidos en el signo    EU|SIG=neg|A|web         n = 42  (15+12+10+5)
R2  la extra anulada, mismo signo               EU|SIG=neg|A|*           n = 42
R3  celda mandatory × signo  ← TOPE             EU|SIG=neg|*|*           n = 42
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
