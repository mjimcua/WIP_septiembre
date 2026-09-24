# GUION v3 — objetivos, criterios, algoritmo y funciones

*12-sep-2026. Esquema de alto nivel del framework antes de escribir código: qué se hace, por qué, con qué funciones, qué entra, qué sale, qué se valida y cómo se mide la mejora en dinero. Sustituye el enfoque de "refactorizar el legacy" por "construir v3 sobre objetivos explícitos". Incorpora las precisiones del usuario: técnica por serie mejorada con trazabilidad a la raw; muchas técnicas, con preferencia por series temporales; mejora cuantificada en dinero; bandas asimétricas acotadas al 100 %; resultado final con intervalo, construido desde las partes.*

---

## 1 · Objetivos (la historia completa, en orden)

1. **Tengo una pipeline**: contratos que vencen en meses futuros, con unidades y dinero conocidos. Es dato, no predicción.
2. **La mido antes de tocarla** por unos criterios (§2) y obtengo una valoración: cuánto dinero futuro está bien soportado y cuánto está en riesgo menos controlado.
3. **Uso la fórmula del valor esperado y la divido en dos ramas**, cada una a su grano, más ligado a la variable que predice (y a la incompletitud de ciertos datos):
   - `revenue = pipeline$ × tasa de renovación × revalorización`
   - rama tasa: grano de la serie de renovación (mandatory + timevarying + extras de renovación); binomial.
   - rama uplift: grano de la celda de revalorización (mandatory + extras de precio); continua.
4. **Mejoro la capacidad predictiva de cada rama** con técnicas propias de cada una: en la tasa, prestando soporte del pariente más cercano; en el uplift, agrupando renovadores.
5. **Resultado: una pipeline con forecast series distintas de las raw pero totalmente trazables**: cada serie raw sabe con quién se ha estimado y por qué.
6. **Sobre cada serie mejorada pruebo muchas técnicas**, con preferencia por series temporales cuando la historia lo permite (requisito de negocio), y elijo la que menor error medido tiene. La elección se guarda como decisión y la ejecución mensual la aplica hasta el siguiente análisis.
7. **La tasa no puede pasar del 100 %**, y hay estacionalidad, recurrencia y crecimiento: las bandas son asimétricas y acotadas, por lo que dicte la estadística de una proporción.
8. **Doy un resultado final con intervalo**, que proviene de las partes: fila a fila, agregado a cualquier grano, con el intervalo agregado correctamente.
9. **Cada análisis produce una decisión; cada decisión mejora atributos medibles de las series; la mejora se cuantifica en dinero.**
10. **Primero la maquinaria, luego la información que cualifica.** Las dimensiones de hoy son las disponibles; después entrarán (a) **propiedades estables del cliente** (puramente nuevo vs readquisición; propensión a buscar descuentos) como dimensiones de renovación, y (b) **cohortes de riesgo de un modelo predictivo** como timevarying. El framework no cambia: cambia la config.

---

## 2 · Criterios de medida y niveles de riesgo (en dinero)

> **PRINCIPIO RECTOR — la referencia binomial y φ.** La tasa de renovación es una proporción: k renovaciones de n vencimientos. Eso da una referencia exacta que no depende de ningún umbral externo: **el error por tamaño de muestra**, `√(p(1−p)/n)`. Con p = 0,8 y n = 100 al mes, la tasa mensual oscila ±4 pp *aunque nada cambie*. Ese error se calcula a dos niveles: por **forecast unit** (cada mes con su propio n, a p = 0,5 como peor caso antes de estimar nada: `fu_summary`) y por **forecast series** (con su tasa y su n mensual típico: `error_binomial_pp` en la ficha).
>
> **φ (phi)** es, por serie, la variación observada de la tasa mes a mes dividida por la que *tendría que haber* solo por muestreo si la tasa fuera constante. **φ ≈ 1**: la serie oscila lo que la moneda predice; no hay nada que modelar y el promedio es la mejor técnica. **φ > 1**: hay un motor (estación, tendencia, régimen, mezcla interna) que mueve la tasa más de lo que el muestreo explica; ahí una serie temporal tiene algo que capturar. Es una referencia propia de cada serie, no un umbral externo. Todo lo demás del framework se mide contra ella: el suelo de soporte, la normalización de bandas, los tests de estacionalidad y tendencia, y la decisión de dónde merece la pena una técnica compleja.

La unidad de medida es la **forecast series** y su dinero futuro (`usd_proyectado`). Cada serie se clasifica en un nivel de calidad predictiva; el informe de cada fase es **cuánto dinero hay en cada nivel, antes y después**.

### 2.1 Atributos que se miden (por serie)
| Atributo | Qué mide | Fase que lo fija |
|---|---|---|
| `n_propio` | unidades que vencen al mes (mediana) | 0 |
| `meses_historia`, `huecos` | cuánta historia y cuán continua | 0 |
| `error_binomial_pp` | **el error por tamaño de muestra**: z·100·√(p(1−p)/n_propio) (Wilson, 90 %). Por forecast unit está en `fu_summary` (p = 0,5, su n del mes) | 0 |
| `n_efectivo`, `id_estimacion`, `peldano` | con quién se estima y cuánto soporte aporta | 1 |
| `se_estimacion_pp`, `se_prediccion_pp` | cuánto conocemos la tasa · cuánto oscilará el mes que viene | 1 |
| `phi` | ¿hay señal más allá del muestreo? (§7) | 2 |
| `estacional`, `tendencia`, `ciclos_completos` | qué dinámica tiene, con cuánta evidencia | 2 |
| `tecnica`, `err_medido_pp`, `n_predicciones` | qué método, con qué error y con cuánta evidencia se eligió | 3 |
| `banda_sup_pp(h)`, `banda_inf_pp(h)`, `calibracion` | la banda asimétrica por horizonte y si es honesta | 3 |
| `riesgo_mix_pp` | cuánto se movería su celda solo por composición | 1b |
| `uplift`, `n_renovadores`, `banda_uplift` | la rama de valor | 4 |

### 2.2 Niveles de riesgo (la valoración)
| Nivel | Criterio | Lectura de negocio |
|---|---|---|
| **A · propio** | `n_propio ≥ suelo` y `meses_historia ≥ 12` | la serie se predice sola; riesgo controlado |
| **B · prestado** | `n_propio < suelo`, pariente en peldaño ≤ 2 con `n_efectivo ≥ suelo` | se predice con un pariente cercano; riesgo controlado con supuesto declarado |
| **C · lejano** | pariente en peldaño ≥ 3 (celda o más arriba; solo neutras suben más allá de la celda) | se predice con un grupo grueso; riesgo medio |
| **S · con signo bajo suelo** | serie con flags (neg o pos) cuya celda × signo no alcanza el suelo | se predice con lo mejor de su signo, sin padre; ruidosa pero cualificada; riesgo declarado |
| **M · signo mixto** | flags de ambos signos activos | no se agrupa con nadie; debería ser ≈ 0 |
| **D · sin historia** | ruta heuristic (futuro sin pasado) | se predice por herencia de celda; riesgo alto |
| **E · sin banda medida** | cualquier nivel cuya banda es teórica (sin backtest a ese h) | el intervalo es una cota, no una medida |

**El informe cabecera de cada fase:** tabla nivel × ($ futuro, % del total, nº series, cota media ponderada por $). La mejora de una fase = dinero que sube de nivel. Ejemplo del formato:

```
                 RAW                 tras fase 1          tras fase 3
A propio      $120,3M  69%          $120,3M  69%         $120,3M  69%
B prestado         —                $ 38,1M  22%         $ 38,1M  22%
C lejano           —                $ 12,7M   7%         $ 12,7M   7%
D sin historia $  2,2M   1%         $  2,2M   1%         $  2,2M   1%
bajo suelo    $ 53,0M  31%  → 0
sin banda     $173,3M 100%          $173,3M 100%   →     $  9,1M   5%
```

Esto responde a "dentro de qué predecir es un riesgo, cuánto dinero hay en un riesgo menos controlado".

---

## 3 · Modelo de datos y trazabilidad

```
raw row  ──fu_comb_key──►  fine_table  ──fu_id──►  forecast_unit (serie × mes)
                                                         │ fs_id
                                                         ▼
                                              forecast_series (raw)  ── series_card ──► nivel de riesgo
                                                         │ id_estimacion (decision_support)
                                                         ▼
                                              serie de estimación (ella misma o un pariente)
                                                         │ tecnica (decision_technique), bandas (decision_error_bands)
                                                         ▼
                                              forecast por fila futura  ──►  forecast_detail + forecast_bands
```

Tablas de decisión (escribe ANALYSIS, lee RUN; todas con `decision_date`, `execution_id`):
`decision_eta2` · `decision_support` · `decision_dynamics` · `decision_technique` · `decision_error_bands` · `decision_uplift`.

Tablas de trazabilidad (escribe RUN): `key_bridge` (fila raw → serie → id_estimacion → celda uplift), `parent_ladder` (serie × peldaño), `series_card`.

---

## 3b · Las timevarying como cohortes de riesgo (generalización de la taxonomía)

**Lo previsto en la doctrina (DISENO_V2 §3, sellado):** las timevarying son «el puerto de inyección de los predictivos en el forecast»: la predicción cliente a cliente se convierte en dimensión y targetea un conjunto de clientes en situación homogénea; para acciones sirven las predicciones individuales, para el forecast hace falta volumen. Reglas: **as-of** (el histórico es lo que el modelo predijo entonces, nunca re-puntuado), **versión del modelo como bandera** (al reentrenar, las tasas por flag pueden saltar: se anota), y **la tasa realizada del pool por signo es la calibración empírica del modelo**. Lo que propones hoy es exactamente eso, llevado a su forma general.

**Por qué funciona la intuición de las cohortes extremas.** Un score individual tiene mucho error por cliente; pero al agrupar los clientes de score extremo, el promedio de la cohorte se separa mucho del promedio general, y la binomial de la cohorte (con su n) mide esa separación con su propia referencia. El forecast no usa el score: usa la tasa realizada de la cohorte. Si la cohorte "riesgo muy alto" renueva al 35 % y el resto al 82 %, la cohorte tiene capacidad predictiva propia aunque cada cliente dentro sea incierto. Y ese 35 % realizado es la auditoría del modelo, gratis.

**La config no cambia: una columna binaria por motivo, con su signo.** Un cliente puede ser softcancel y dormant a la vez, y en el futuro puede tener alta probabilidad de abandono *por decir que no* y *por no usar el producto*: son señales distintas que coexisten. Por eso las timevarying **no** son una categórica (una categórica obliga a un solo valor por cliente); son binarias independientes, cada una con su significado (el motivo, para actuar) y su signo (la dirección, para predecir):

```python
structural_timevarying_dims = {
    "softcancel":                  "negative",   # observadas hoy
    "dormant":                     "negative",
    "no_instalado":                "negative",
    "autorenew":                   "positive",
    "alta_prob_abandono_no_uso":   "negative",   # producidas por un modelo, una por motivo
    "alta_prob_abandono_no_renov": "negative",
    "alta_prob_renovacion":        "positive",
}
timevarying_model_version = {"alta_prob_abandono_no_uso": "churn_uso_v3", ...}   # bandera as-of por columna
```

Esto es exactamente la doctrina (§3): «cada motivo conserva su identidad en el id fino; el forecast los junta por signo cuando el soporte manda». Y es general: si un modelo distingue intensidades (alto / muy alto), son dos binarias con el mismo signo, no una categórica. El id fino conserva qué flags tenía cada serie; la escalera agrupa por signo cuando el soporte no alcanza.

**Positivos y negativos nunca se juntan.** No hay grupo `neg+pos` ni dominancia: mezclar signos no tiene sentido. Una serie con flags activos de ambos signos **no se agrupa con nadie**: se queda con su tasa propia y se etiqueta `mixed_sign`; un check de DOCTRINE cuenta cuántas series y cuánto dinero hay así. Con modelos que clasifican solo los casos extremos debería ser ≈ 0; si no lo es, el problema está en los modelos, no en la escalera.

**La mayoría será neutra.** Solo se clasifican los extremos: la mayor parte de las series tendrán todos los flags a 0. "Neutro" es un signo más a efectos de agrupación: los neutros solo se agrupan con neutros. Los positivos sirven para encontrar oportunidades; los negativos, para cuantificar efectos adversos antes de tiempo.

**Propiedades estables del cliente** (nuevo puro vs readquisición, buscador de descuentos): no varían mes a mes, así que **no son timevarying**: entran como `extra_renovacion` (pasan por η² y pueden anularse si no separan) o como `mandatory` si el negocio exige que nunca se colapsen. Se declaran en config, sin código nuevo.

**Función nueva en ANALYSIS:** `analysis_timevarying_calibration(forecast_units, config) → tabla flag × mes × (n, tasa realizada, error binomial)` y la misma por signo: la tasa realizada de cada motivo y su evolución. Es la calibración de cada modelo (por motivo) y el argumento para reentrenarlo o no; y por signo, la referencia que usa la escalera. Y un check de DOCTRINE: si `timevarying_model_version` cambia dentro de la historia, se marca el corte (nunca se descubre por sorpresa).

## 4 · El algoritmo, fase a fase, con sus funciones

Convención de cada función: **propósito · entrada · salida · validaciones (bloqueantes) · decisión que produce o lee · métrica de mejora**. Prefijo `run_` = ejecución mensual; `analysis_` = periodo de análisis.

### FASE 0 · Validación del raw — hecha (`raw_data_validation.py`, `support_reference.py`)
`validate_raw` · `apply_current_month_doctrine` · `build_fine_table` · `aggregate_to_forecast_units` · `build_key_lookups` · `label_universe_and_routes` · `build_support_reference`. Sin cambios salvo dos añadidos: asertar `fu_comb_key` único y `fu_key` único (colisión de hash) en `build_fine_table`; comprobar columnas declaradas ausentes en `validate_raw`.

### FASE 1 · Soporte de la rama tasa

**`run_build_rate_series(forecast_units, config) → forecast_units, series_summary`**
- Propósito: crear la serie mensual de cada forecast series con disciplina null≠zero y su resumen.
- Entrada: unidades etiquetadas (fase 0). Salida: unidades + `fs_key`, `tasa` por fila (NaN en proyección y en pipeline 0), huecos como filas sintéticas con tasa NaN; `series_summary` (n_propio, meses, huecos, tasa_propia, error_binomial_pp, usd_proyectado).
- Validaciones: una fila por (serie, mes); huecos solo dentro de la historia de series trainable.
- Métrica: la foto del raw (nivel A vs bajo suelo, en $).

**`analysis_dimension_separation(series_summary, forecast_units, config) → decision_eta2`**
- Propósito: medir qué dimensiones separan comportamiento y fijar el orden de colapso. **Sin las timevarying** (doctrina: «seguro que van a tener una gran diferencia»; se gestionan por signo, no por η²).
- Qué se calcula (tres cifras por dimensión, no una):
  1. **η² individual**, ponderado por soporte: cuánto explica la dimensión sola. Es lo de hoy: útil como pantalla, pero **confundido** cuando las dimensiones están correlacionadas (si producto y región van juntos, cada uno "explica" lo del otro).
  2. **Contribución única** (tipo II): η²(todas las dimensiones) − η²(todas menos ésta). Es la pregunta que hace la escalera: *¿qué pierdo si la anulo, dado que conservo el resto?* Una dimensión con η² individual alto pero contribución única ≈ 0 es redundante y **debe colapsar primero**.
  3. **η² ajustado** (ω²), que descuenta el número de grupos: con muchas categorías y pocas series por celda, η² sube por azar.
  Más los **pares** (η² de la clave conjunta vs sus individuales) para detectar interacciones que justifiquen conservar dos dimensiones juntas.
- Cómo: no hace falta ANCOVA. ANCOVA es para covariables continuas; aquí todas las dimensiones son categóricas (el descuento continuo ya se discretiza en intervalos por doctrina), así que lo correcto es un **ANOVA factorial ponderado** (varias dimensiones a la vez) del que se extraen las contribuciones únicas. Implementación práctica: mínimos cuadrados ponderados (pesos = soporte) de la tasa por serie sobre las dimensiones como categóricas; contribución única = caída de R² al quitar cada una. Sin librerías nuevas más allá de numpy.
- Salida: `decision_eta2` (rama, dimensión, η²_individual, contribución_única, ω², orden_colapso) + `decision_eta2_pairs`.
- Validaciones: toda dimensión del grano tiene las tres cifras; el orden de colapso usa la **contribución única** y respeta las familias `_level_N` (fino antes que grueso); si dos dimensiones tienen contribución única ≈ 0 pero par alto, se anulan juntas o ninguna (declarado).
- Decisión: orden de colapso de la escalera y extra anulable.

**`analysis_mix_shift(forecast_units, config) → simpson_contrafactual, riesgo_mix por celda`**
- Propósito: cuantificar en $ lo que cuesta no segmentar (contrafactual walk-forward) y descomponer el cambio de la tasa agregada por celda en comportamiento + composición (Kitagawa).
- Salida: tabla por celda × mes (err_plano, err_seg, ahorro_usd, delta_comportamiento_pp, delta_composicion_pp); `riesgo_mix_pp` por celda en la ficha.
- Métrica: ahorro total; % de celdas-mes donde gana segmentar.

**`build_relatives(series_id, config, decision_eta2) → lista ordenada de parientes`** (pura, sin datos)
- Propósito: la lista de parientes de una serie, del más cercano al más lejano. **Las timevarying no se colapsan como las demás dimensiones: se resumen en su SIGNO, y el signo nunca se pierde.** Un cliente con `softcancel = 1` o `dormant = 1` tiene una expectativa de renovación muy distinta de otro idéntico en región, producto, precio y descuento sin marca; agruparlo con quien no ha avisado le daría la tasa equivocada y crearía el mix-shift que queremos evitar. La escalera es distinta según el signo:

  ```
  Serie CON signo (neg o pos)                         Serie NEUTRA (ningún flag activo)
  R0  ella misma                                      R0  ella misma
  R1  mismas dims, flags resumidos en el signo        —   (ya es neutra)
      EU|SIG=neg|A|tele
  R2  extra de menor η² anulada, mismo signo          R2  extra de menor η² anulada, neutros
      EU|SIG=neg|A|*                                      EU|SIG=0|A|*
  R3  celda mandatory × signo  ← TOPE                 R3  celda mandatory, neutros
      EU|SIG=neg|*|*                                      EU|SIG=0|*|*
                                                      R4  una mandatory colapsada, neutros
                                                      …
                                                      Rk  total de neutros
  ```
  **Para las series con signo la escalera termina en la celda mandatory × signo.** Más arriba se estarían juntando cohortes muy distintas (otras regiones, otros productos, con un aviso de churn encima): mezclar eso es fabricar Simpson. Si R3 sigue bajo el suelo, la serie **se queda con la mejor tasa alcanzada dentro de su signo**, sin credibilidad hacia ningún padre, con su banda binomial ancha y la etiqueta `signed_under_floor`: la predicción es ruidosa, pero está más cualificada que la de una serie neutra grande. Es una decisión consciente y queda en la tabla de niveles.
  Las series neutras son la mayoría y sí suben por las mandatory (siempre entre neutras).
- Validaciones: las mandatory nunca se anulan antes que las no-mandatory; el signo nunca se pierde; una serie con signo nunca tiene pariente por encima de su celda; ids con `*` y `SIG=` reconstruibles.
- **Diferencia con el legacy (defecto a corregir):** el legacy aplicaba la escalera de mandatory y la credibilidad a **todas** las series, incluidas las `SIG=`, hacia un padre que mezclaba signos. Es justo lo que no se puede hacer.

**`run_pool_support(forecast_units, relative_pattern, config) → n, tasa, se`**
- Propósito: soporte y tasa de un pariente, calculado con **todas** las series que casan con el patrón (grandes incluidas), sumando por mes antes de tomar la mediana.

**`run_climb_ladder(series_summary, forecast_units, decision_eta2, config) → decision_support, parent_ladder`**
- Propósito: para cada serie, subir por su lista de parientes hasta el primero con `n ≥ suelo`; registrar cada peldaño.
- Salida: `decision_support` (fs_id → id_estimacion, peldaño, n_efectivo, tasa_pariente, k); `parent_ladder` (fs_id × peldaño: patrón, n, tasa, elegido).
- Validaciones: toda serie trainable tiene un pariente elegido; ninguna mandatory anulada antes del peldaño "celda"; `n_efectivo ≥ suelo` o pariente = total.
- Métrica: $ bajo suelo raw → después (objetivo 0); distribución de $ por peldaño (A/B/C).

**`analysis_credibility_k(parent_groups, config) → k por pariente`**
- Propósito: estimar k = varianza dentro / varianza entre hermanas (Bühlmann-Straub) por pariente; `k_cred` de config como valor por defecto si no hay hermanas suficientes.
- Decisión: columna `k` en `decision_support`.

**`run_estimate_rates(series_summary, decision_support, config) → series_estimates`**
- Propósito: tasa estimada por serie: `z·tasa_propia + (1−z)·tasa_pariente`, `z = n_propio/(n_propio+k)`, **solo cuando la escalera encontró un pariente con soporte**; una serie `signed_under_floor` o `mixed_sign` usa la mejor tasa de su signo sin mezcla. Dos errores: `se_estimacion_pp` (de la mezcla) y `se_prediccion_pp` (añade p(1−p)/n_propio).
- Validaciones: 0 ≤ tasa ≤ rate_cap; `se_prediccion ≥ se_estimacion` siempre.
- Métrica: cota media ponderada por $ raw → después, **por separado** para estimación y predicción.

**`analysis_support_report(series_card) → tabla nivel × $`** — el informe cabecera (§2.2).

### FASE 2 · Dinámica de cada serie de estimación

**`analysis_signal_detection(pool_monthly_series, config) → phi, gate`**
- Propósito: ¿la tasa se mueve más de lo que el muestreo explica? φ (§7); gate soporte / temporal / estacional / tendencia / promedio.

**`analysis_seasonality(pool_monthly_series, config) → estacional, perfil_12, meses_alto, meses_bajo, ciclos_completos`**
- Propósito: índice por mes de calendario contra su cota binomial; firme con ≥ 2 ciclos, tentativo con 1.
- Validaciones: no se declara estacionalidad con < 13 meses.

**`analysis_trend(pool_monthly_series, config) → tendencia, pendiente_pp_ano, horizonte_max`**
- Propósito: pendiente contra su cota; tope de extrapolación (la tendencia se amortigua a 0 en `horizonte_max`).

**Salida de la fase:** `decision_dynamics` (id_estimacion → phi, gate, estacional, perfil, tendencia, pendiente, horizonte_max, ciclos). Se estampa en cada serie miembro.
**Métrica:** se mide en fase 3: el $ cuya técnica estacional/tendencia bate al promedio en su backtest.

### FASE 3 · Técnica y banda por serie de estimación

**`techniques.py`** — el catálogo, cada técnica con: id, familia, `historia_minima`, `requiere` (estacional/tendencia/nada), `predict(serie_logit, h) → pred`. Amplio (§5): promedios, suavizados, ETS/Holt-Winters amortiguado, Theta, SARIMA, STL+ETS, Croston/SBA para intermitentes, credibilidad temporal. Trabajan sobre la **tasa en escala logit** (§6).

**`analysis_backtest(pool_monthly_series, decision_dynamics, config) → backtest_long`**
- Propósito: rolling-origin con **todos** los orígenes disponibles (no un número fijo), horizontes 1..H (H = horizonte máximo proyectado), solo técnicas elegibles para esa serie (por historia y por etiquetas de dinámica). Error **con signo**, en pp y normalizado por la cota del pool-mes.
- Validaciones: el mes en curso fuera; cada predicción usa solo historia < origen.

**`analysis_select_technique(backtest_long, config) → decision_technique`**
- Propósito: por serie de estimación, la técnica con menor error medio que bate al retador (promedio) por un margen expresado en cotas, con `n_predicciones ≥ mínimo`; si no, promedio con `tecnica_origen = "retador"`.
- Salida: id_estimacion → tecnica, err_medido_pp, n_predicciones. Se estampa en cada serie.

**`analysis_error_bands(backtest_long, decision_technique, config) → decision_error_bands`**
- Propósito: por (id_estimacion, h): p5 y p95 del error con signo **normalizado** (banda asimétrica); si el pool tiene pocas predicciones, cuantiles de la familia (misma técnica, todos los pools) escalados por la cota propia.
- Validaciones: banda no decrece con h (se fuerza monótona); calibración en backtest ≈ nivel nominal.
- Métrica: **calibración** (% de reales dentro de banda, objetivo 90 %); % de $ con banda medida hasta H.

### FASE 4 · Uplift (versión simple)

**`run_uplift_cells(fine_table, config) → uplift_cells`** — ratio de sumas por celda de uplift, n = renovadores, meses.
**`run_uplift_parents(uplift_cells, config) → decision_uplift`** — si n < `suelo_uplift`, padre = misma celda mandatory con las extras "punto de partida" (config `uplift_parent_keep_columns`) conservadas y el resto a `*`.
**`analysis_uplift_bands(fine_table, config) → banda por celda`** — bootstrap de renovadores (p5/p95), sin fórmula.
- Validaciones: uplift > 0; `uplift ≤ uplift_cap` (config; investigación del 466× pendiente).
- Métrica: celdas y $ bajo `suelo_uplift` antes/después.

### FASE 5 · Ensamblaje y resultado final (RUN)

**`run_assemble_forecast(fine_table, series_estimates, decision_technique, decision_dynamics, decision_uplift, config) → forecast_detail`**
- Propósito: por fila futura: tasa(h) = técnica de su serie de estimación aplicada a horizonte h, saturada en rate_cap; uplift de su celda; `esperado_usd = pipeline$ × tasa × uplift`; `tasa_origen`, `tecnica_origen`, `uplift_origen`.
- Validaciones: sin NaN; 0 ≤ tasa ≤ cap; uplift > 0; toda fila tiene origen.

**`run_forecast_bands(forecast_detail, decision_error_bands, config) → forecast_bands`**
- Propósito: banda asimétrica por fila (inf, sup) en pp y $, a su h.

**`run_aggregate_with_bands(forecast_bands, grouping) → tabla agregada`**
- Propósito: agregar a cualquier grano con el intervalo correcto: **suma** dentro de (id_estimacion, mes) — misma tasa, error correlado — y **cuadratura** entre. El resultado final "proviene de las partes" con su intervalo.
- Validaciones: la banda relativa del total no decrece con h.

**`run_validation_panel`** — INTEGRITY y DOCTRINE bloquean; QUALITY informa.

---

## 5 · Política de técnicas

- **Catálogo amplio**, como pides: promedio y naive (retadores), medias móviles, EWMA, SES, Holt amortiguado, Holt-Winters aditivo/multiplicativo, Theta, ETS automático, SARIMA, STL+ETS, Croston y SBA (intermitentes), índice estacional simple, credibilidad temporal.
- **Elegibilidad por serie, no por catálogo**: cada técnica declara `historia_minima` y qué etiqueta requiere. Una serie con 14 meses no compite con SARIMA estacional (necesita ≥ 2-3 ciclos); una sin `estacional` no compite con Holt-Winters. Así se usan series temporales **cuando se puede** y no se elige por suerte cuando no.
- **Preferencia por series temporales**: en empate dentro del margen, gana la técnica de la familia más rica (series temporal > suavizado > promedio). El margen se expresa en cotas, no en pp fijos.
- **Selección con evidencia**: todos los orígenes disponibles; `n_predicciones` mínimo para destronar al retador; la decisión queda registrada con su evidencia.
- **Corrección a lo dicho antes**: la sugerencia de reducir a 5 técnicas venía de que el legacy elige con solo 3 orígenes por horizonte (constante `BACKTEST_ORIGINS = 3` en el código): con tan poca evidencia, más técnicas = más falsos campeones. Con todos los orígenes y elegibilidad por etiquetas, el catálogo amplio es correcto. Se retira la sugerencia.

---

## 6 · Bandas: lo que dicta la estadística para una proporción

- La tasa vive en [0, 1]. Trabajar en **escala logit** (`log(p/(1−p))`) resuelve tres cosas a la vez: las técnicas de series temporales no pueden predecir por encima de 1 ni por debajo de 0; al deshacer la transformación los intervalos son **asimétricos** de forma natural (más estrechos cerca del 100 %); y una tendencia se amortigua sola al acercarse al techo. Es el tratamiento estándar de datos acotados (Hyndman & Athanasopoulos, *FPP3* §3.1).
- La banda de cada serie combina dos fuentes: **error de estimación/técnica** (medido en backtest, con signo, p5/p95 normalizados por la cota) y **ruido de muestreo del mes** (p(1−p)/n de la fila, que no desaparece nunca). En logit ambas se suman en varianza; se vuelve a escala natural y sale acotada y asimétrica.
- Para n pequeño y p extremo, intervalos de proporción de **Wilson** (no Wald): honestos, asimétricos, dentro de [0, 1].
- `rate_cap` se mantiene como techo de negocio además del techo estadístico.
- Agregación: suma dentro del grupo que comparte tasa, cuadratura entre grupos; en logit no se agrega (se agrega en dinero).

---

## 7 · φ, explicado, y de dónde salen mis cifras

**φ (phi)** compara dos números por serie: la variación **observada** de la tasa mes a mes, y la variación que **tendría que haber** solo por muestreo si la tasa real fuera constante. La segunda se calcula exactamente de la binomial: con p = 0,8 y n = 100 al mes, la tasa mensual oscila ±4 pp aunque nada cambie. φ = varianza observada / varianza binomial.
- φ ≈ 1: la serie oscila lo que la moneda predice; **no hay nada que modelar**; el promedio es la mejor técnica y cualquier "tendencia" es ruido.
- φ > 1: hay un motor (estación, tendencia, régimen, mezcla interna) que mueve la tasa más de lo que el muestreo explica; ahí las técnicas de series temporales tienen algo que capturar.
Es la referencia propia (P1): no es un umbral externo, sale de los datos de cada serie. Y es la que dice **dónde** merece la pena una técnica compleja.

**De dónde salen las cifras que cité.** Todas las evidencias numéricas de la revisión (uplift no-op, L2 sin hermana, peldaño global, bandas +16-23 %, "3 pools con motor") salen de **la salida de referencia del dataset sintético de este chat**, no de Kamelot ni de otros chats. Los defectos de lógica son del código y se reproducen con cualquier dato; las magnitudes (cuánto infravalora la banda, cuántos pools tienen φ > 1) son del sintético y **en Kamelot serán otras**. El "3 orígenes" no es un dato: es la constante `BACKTEST_ORIGINS = 3` del código legacy. No tengo cifras de φ de Kamelot; HANDOVER no las recoge.

---

## 8 · Cómo seguir

1. Validar este guion: objetivos (§1), niveles de riesgo (§2.2), lista de funciones (§4), política de técnicas (§5), escala logit (§6). Lo que no convenza se cambia aquí, no en código.
2. Paso 1 de construcción: `run_build_rate_series` + `analysis_support_report` → la **foto del raw en dinero por nivel** (con el error binomial de cada serie y de cada unidad). Pequeño, útil para la presentación, y fija el vocabulario de la ficha.
3. Después, en orden: escalera unificada (`build_relatives`, `run_climb_ladder`, `run_estimate_rates`) con test de 6 series a ojo; η² y Kitagawa; dinámica; catálogo + backtest + bandas; uplift simple; ensamblaje y agregación; limpieza.
4. Cada paso cierra con: test de mano en verde, `test_pipeline.py` en verde, informe nivel × $ antes/después.
