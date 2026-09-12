# PLAN v3 — la ficha de cada forecast series y el ciclo análisis → decisión → mejora

*12-sep-2026. Ordena y concreta la idea del usuario: cada forecast series tiene una capacidad predictiva medible; cada fase hace un análisis, del análisis sale una decisión, la decisión se guarda en configuración/tablas de decisión, y mes a mes la ejecución la aplica sin pensar hasta el siguiente análisis. Lo que mejora en cada paso se mide contra el raw con los mismos atributos. Complementa a REVISION.md.*

---

## 1 · La idea central, en tres frases

1. **Cada forecast series tiene una ficha**: un conjunto de atributos que dicen cuánto se puede fiar uno de su predicción y por qué (soporte, historia, ruido, señal, estacionalidad, tendencia, riesgo de mezcla, técnica, banda).
2. **Cada fase de análisis rellena o mejora atributos de la ficha y deja una decisión** persistida (tabla `decision_*`). La ejecución mensual solo lee decisiones; no decide nada.
3. **El progreso se mide en la ficha**: "en raw esta serie tenía soporte 12 y cota ±36 pp; tras el paso 2 tiene soporte efectivo 612 y cota ±3,3 pp; tras el paso 4 su banda medida a h=1 es +2,1/−1,4 pp". Si un paso no mejora ningún atributo, sobra.

---

## 2 · La ficha de una forecast series (atributos de capacidad predictiva)

Una fila por `fs_id` en una tabla `series_card` (persistida por ANALYSIS, leída por RUN y por el BI). Agrupados por lo que responden. Los que dependen de decisión llevan el nombre de la tabla de decisión que los fija.

### 2.1 Identidad y contexto (fase 0)
| Atributo | Qué responde | Tipo |
|---|---|---|
| `fs_id`, `fs_key`, `celda_id` | quién es y a qué celda pertenece | id |
| `universo` | normal / time_series | etiqueta |
| `ruta` | trainable / heuristic / no_impact | etiqueta |
| `meses_historia` | cuántos meses con verdad | entero |
| `huecos` | cuántos meses sin vencimientos dentro de la historia | entero |
| `usd_proyectado` | cuánto dinero futuro depende de esta serie | $ |

### 2.2 Soporte y ruido (lo binomial: fases 0 y 1)
| Atributo | Qué responde | Fórmula |
|---|---|---|
| `n_propio` | cuántas unidades vencen al mes (mediana) | mediana mensual de pipeline_units |
| `tasa_propia` | la tasa histórica sola | Σren / Σpipe |
| `cota_propia_pp` | el ruido de muestreo de UN mes con su propio n | z·100·√(p(1−p)/n_propio) (Wilson) |
| `id_estimacion` | con quién se calcula su tasa (ella misma, o un pariente) | decisión `decision_support` |
| `n_efectivo` | el soporte del pariente elegido | del pariente |
| `tasa_estimada` | la tasa que usa la ejecución | credibilidad hacia el pariente |
| `se_estimacion_pp` | cuánto conocemos la tasa (error de la estimación) | se de la mezcla |
| `se_prediccion_pp` | cuánto oscilará la tasa realizada el mes que viene con `n_propio` | √(se_estimación² + p(1−p)/n_propio) |
| `phi` | ¿hay un motor que mueve la tasa más allá del muestreo? | var observada / var binomial |

### 2.3 Dinámica (fase de dinámica, solo si `n_efectivo ≥ suelo` y φ > 1)
| Atributo | Qué responde | Decisión |
|---|---|---|
| `estacional` (0/1) | ¿el mes del año importa? | `decision_dynamics` |
| `perfil_estacional` | índice por mes de calendario (12 valores, 1 = media) | `decision_dynamics` |
| `meses_alto`, `meses_bajo` | los meses cuyo índice sale de la cota | etiqueta derivada |
| `tendencia` (−1/0/+1) | ¿sube, baja o nada, más allá del ruido? | `decision_dynamics` |
| `pendiente_pp_ano` | cuánto | número |
| `horizonte_max_tendencia` | hasta cuántos meses se extrapola antes de amortiguar del todo | `decision_dynamics` (tope de inferencia) |
| `ciclos_completos` | cuántos años enteros de historia respaldan la estacionalidad | entero (1 = tentativa) |

### 2.4 Técnica y banda (fase de backtest)
| Atributo | Qué responde | Decisión |
|---|---|---|
| `tecnica` | qué método predice mejor esta serie (calculado en `id_estimacion`, estampado aquí) | `decision_technique` |
| `err_medido_pp` | error medio del método en el backtest de esta serie | número |
| `n_predicciones` | con cuánta evidencia se eligió | entero |
| `banda_sup_pp(h)`, `banda_inf_pp(h)` | banda **asimétrica** por horizonte: p95 y p5 del error **con signo** | `decision_error_bands` |
| `banda_medida` (0/1) | si la banda viene de errores medidos o de la cota | flag |
| `tope_tasa` | el techo aplicado (rate_cap) y si actuó | flag |

### 2.5 Riesgo de mezcla (fase de diagnóstico de celda)
| Atributo | Qué responde | Fórmula |
|---|---|---|
| `riesgo_mix_celda_pp` | cuánto se movería la tasa de la celda si la composición cambiara como en los últimos 6 meses sin que nadie cambie de comportamiento | término de composición de Kitagawa: Σ p_s·Δw_s |
| `ahorro_segmentar_usd` | lo que costó no segmentar en su celda (contrafactual) | de `simpson_contrafactual` |

---

## 3 · El ciclo por fase: hago → para qué → obtengo → mejora medida

Formato uniforme. "Mejora" siempre se mide en atributos de la ficha, comparando **raw vs después del paso**, agregado en dinero (Σ usd_proyectado de las series afectadas).

### Fase 0 · Validación del raw (RUN) + referencia (ANALYSIS) — hecha
- **Hago**: contrato exhaustivo, doctrina del mes en curso, dos tablas con claves, etiquetas de universo y ruta, referencia inmutable.
- **Para qué**: que ningún dato entre sin rol, que el futuro no contenga resultados, que cada fila sea localizable, y tener el punto cero contra el que medir.
- **Obtengo**: `fact_fu`, `fact_fine`, lookups, `fu_summary`; ficha 2.1 y `n_propio`, `tasa_propia`, `cota_propia_pp`.
- **Mejora medida**: ninguna todavía (es el raw). Sale el **diagnóstico de partida**: "X series con n < 30 concentran $Y (Z %) del futuro; su cota media es ±W pp".
- **Decisión**: ninguna. Es contrato.

### Fase 1 · Soporte: con quién se calcula cada tasa (ANALYSIS decide, RUN aplica)
- **Hago**: para cada serie bajo el suelo, buscar el pariente más cercano con soporte (escalera unificada, §4); credibilidad hacia él con k estimado de las hermanas.
- **Para qué**: que ninguna tasa se estime con menos de 30 unidades/mes sin decirlo, sin mezclar lo que no se parece.
- **Obtengo**: `decision_support` (fs_id → id_estimacion, peldaño, n_efectivo, k); ficha 2.2 completa; `support_chain` como reporte.
- **Mejora medida**:
  - `$ bajo el suelo`: raw $A → después $B (objetivo: 0).
  - `cota_pp` media ponderada por $: raw ±X → después ±Y (`se_estimacion`).
  - **Honestidad**: `se_prediccion_pp` NO baja para la serie pequeña (su mes seguirá siendo ruidoso); se reporta aparte para que nadie confunda las dos.
- **Decisión persistida**: `decision_support`. Vigencia: hasta el siguiente análisis (config `decision_max_age_months`).

### Fase 1b · Qué dimensiones separan (ANALYSIS) → alimenta la escalera
- **Hago**: η² ponderado por dimensión (sin timevarying), pares, descomposición Kitagawa por celda y mes.
- **Para qué**: decidir el orden en que se colapsan dimensiones y medir el riesgo de mezcla.
- **Obtengo**: `decision_eta2` (dimensión → η², orden de colapso), ficha 2.5.
- **Mejora medida**: no mejora una serie; mejora la **decisión** de fase 1 (el orden). Métrica: dinero que la escalera recupera en el peldaño 1 vs peldaño 2+ (cuanto antes encuentra padre, mejor era el orden).

### Fase 2 · Dinámica: ¿esta serie se mueve, y cómo? (ANALYSIS decide)
- **Hago**: sobre la serie mensual de `id_estimacion` (pool), φ; si φ > 1 y hay ≥ 13 meses: índice estacional por mes de calendario contra su cota; pendiente anual contra su cota; tope de extrapolación.
- **Para qué**: etiquetar la serie con lo que un método puede aprovechar y con lo que no debe inventar. Sin motor (φ ≈ 1) no hay nada que modelar: el promedio es lo correcto.
- **Obtengo**: `decision_dynamics`; ficha 2.3.
- **Mejora medida**: se mide en fase 3 (la técnica que usa la estacionalidad debe batir al promedio en el backtest de esa serie; si no, la etiqueta era ruido y se retira).
- **Regla de honestidad**: con 1 ciclo, `estacional = tentativa`; solo con ≥ 2 ciclos es firme.

### Fase 3 · Técnica y banda por serie (ANALYSIS decide, RUN aplica)
- **Hago**: backtest rolling-origin, todos los orígenes, horizontes 1..H (H = horizonte máximo proyectado), catálogo reducido (§5.3); campeón por `id_estimacion` con margen vs promedio; errores con signo → banda asimétrica p5/p95 por (serie, h), normalizada por cota.
- **Para qué**: elegir con evidencia y dar una banda que respete tamaño, horizonte y dirección.
- **Obtengo**: `decision_technique`, `decision_error_bands`; ficha 2.4.
- **Mejora medida**:
  - `err_medido_pp` del campeón vs T2_promedio, ponderado por $ (si no bate por el margen, no hay campeón: promedio).
  - **Calibración**: % de meses de backtest cuyo real cae dentro de la banda (objetivo ≈ 90 %). Es la métrica que dice si la banda es honesta.
  - `banda_medida`: % de $ futuro con banda medida (objetivo 100 % hasta H).
- **Decisión persistida**: técnica y banda por serie. RUN las aplica cada mes.

### Fase 4 · Uplift (rama de valor) — versión simple primero
- **Hago**: uplift por celda de uplift = Σren$ / Σ(ren_units·auv_pipeline), con n = renovadores; si n < suelo_uplift, padre = misma celda mandatory con las extras declaradas como "punto de partida" (config, no `newcust` cableado). Error por **bootstrap** de renovadores (remuestrear 200 veces, tomar p5/p95): intuitivo, sin fórmula.
- **Para qué**: convertir tasa en dinero sin inventar precisión.
- **Obtengo**: `decision_uplift` (celda → uplift, n, banda); `uplift_chain`.
- **Mejora medida**: celdas bajo `suelo_uplift` antes/después; anchura de banda antes/después.
- **Aplazado**: credibilidad del uplift y η² de ejes. Primero que la versión simple sea correcta (hoy es un no-op).

### Fase 5 · Ensamblaje y agregación (RUN)
- **Hago**: fila a fila, pipeline$ × tasa(técnica, h) × uplift; banda por fila; agregación: suma dentro de (id_estimacion, mes), cuadratura entre.
- **Para qué**: el forecast y su banda a cualquier grano, coherentes con las decisiones.
- **Obtengo**: `forecast_detail`, `forecast_bands`, `horizon_report`.
- **Check**: la banda relativa del total no decrece con h; `tasa_origen` y `tecnica_origen` cuentan cuántas filas y $ van por defecto.

---

## 4 · La escalera, unificada: un solo mecanismo en vez de cuatro

Hoy son cuatro pasos con reglas distintas (L1 signo, L2 asterisco, escalera de mandatory, credibilidad). Es difícil de ver porque cada paso tiene su propia forma de construir el id y su propio pool. Propuesta: **una lista ordenada de parientes por serie** y un único bucle:

```
parientes(serie) = [
    ella misma,
    R1  mismas dims salvo las timevarying → agrupadas por SIGNO       (antes L1)
    R2  R1 con la extra de menor η² anulada                           (antes L2)
    R3  la celda mandatory (todo lo que no es mandatory, anulado)     (nuevo peldaño 0)
    R4  la celda con la mandatory de menor η² anulada                 (antes escalera 1)
    R5  … una mandatory más …
    Rk  el total
]
```

```
para cada serie:
    para cada pariente en orden:
        n = soporte mensual del pariente (calculado con TODAS las series que casan, grandes incluidas)
        si n >= suelo: elegido = pariente; parar
    tasa_estimada = z·tasa_propia + (1−z)·tasa_pariente,  z = n_propio/(n_propio + k)
```

Lo que cambia respecto a hoy: (1) un solo bucle, una sola forma de construir ids (`*` en las dims anuladas), una sola tabla de traza (`parent_ladder` con TODOS los peldaños, incluidos signo y asterisco); (2) el pool se calcula con todas las hermanas, no solo las pequeñas; (3) la celda mandatory es un peldaño; (4) k se estima por pariente. Y se explica en una frase: **"la serie toma prestado soporte del pariente más cercano que tiene suficiente, y se fía de él en proporción a lo poco que tiene ella".**

Test de mano: un raw de 6 series donde se ve a ojo qué pariente elige cada una y por qué.

---

## 5 · Valoración y simplificaciones que recomiendo

### 5.1 Lo que está bien y no se toca
Fase 0 entera; la disciplina null≠zero; el contrafactual; φ; el puente de claves; el panel de validación por familias; la doctrina del mes en curso.

### 5.2 Lo que hay que rehacer (no parchear)
Fase 1.3 (escalera unificada), fase 2.3 (uplift, hoy no-op), fase 4c (bandas). Son las tres piezas que la revisión encontró incorrectas. Rehacerlas con el esquema del §3 es más barato que corregirlas dentro del legacy.

### 5.3 Simplificar el catálogo de técnicas
15 técnicas para pools con φ ≈ 1 es ruido de selección: con 3 orígenes, el "campeón" es el que tuvo suerte. Propongo 5 y el resto se archivan:
- T2 promedio (retador permanente), T4 EWMA (reciente), T7 índice estacional (solo si `estacional = 1`), T8 tendencia amortiguada (solo si `tendencia ≠ 0`), T0 naive (retador).
Las etiquetas de la ficha (2.3) deciden **qué técnicas son elegibles** para cada serie: una serie sin estacionalidad no compite con T7. Menos comparaciones, menos falsos campeones.

### 5.4 Técnica por serie vs por pool
Tu idea (técnica por forecast series) y la realidad (una serie con n=12 no tiene serie mensual estable con la que hacer backtest) se reconcilian con P5: **la técnica se elige sobre la serie mensual de `id_estimacion`** (la serie misma si tiene soporte; su pariente si no) **y se estampa en cada serie**. La decisión sigue siendo por serie; el cálculo se hace donde hay evidencia. La ficha lo hace visible: `tecnica` + `id_estimacion`.

### 5.5 Bandas asimétricas y tope de inferencia
- Asimetría: guardar los errores **con signo** del backtest y tomar p5 y p95; una serie con tendencia tendrá banda desplazada. No hace falta ninguna teoría nueva.
- Tope: `rate_cap` (ya existe) + `horizonte_max_tendencia` (la tendencia se amortigua a 0 en ese horizonte: T8 ya tiene `DAMPING_PHI`; hacerlo configurable por serie).
- Escala: dividir el error por la cota del pool antes de tomar cuantiles y volver a multiplicar por la cota de cada serie: así la banda respeta el n de cada una.

### 5.6 Lo binomial es la columna vertebral; lo demás, lo mínimo
Estás cómodo con la binomial: úsala como referencia en todas partes (cota por serie, normalización de bandas, test de estacionalidad y tendencia contra la cota, φ). El uplift y las técnicas se mantienen en su versión más simple hasta que la binomial esté cerrada y validada con tests de mano. Nada de credibilidad en uplift ni η² de ejes en esta vuelta.

### 5.7 Riesgo principal del plan
La referencia actual codifica los defectos. Cada corrección la cambia. Hay que aceptar que la referencia es "salida del legacy", y que el criterio de aceptación pasa a ser: tests de mano en verde + diferencia con el legacy **explicada** + regenerar la referencia como salida de v3. Sin esa aceptación, no se puede corregir nada.

---

## 6 · Orden de trabajo (paso a paso, cada paso cierra solo)

| Paso | Entregable | Cierre |
|---|---|---|
| 1 | `series_card` con los atributos de 2.1 y 2.2-raw (n_propio, tasa_propia, cota Wilson) y el diagnóstico de partida en $ | test de mano; se ve la foto del raw |
| 2 | Escalera unificada (§4) → `decision_support`; ficha 2.2 completa con las dos `se` | test de 6 series a ojo; $ bajo suelo → 0 |
| 3 | η² + Kitagawa → `decision_eta2` y ficha 2.5 | orden de colapso testeado; riesgo mix por celda |
| 4 | Dinámica → `decision_dynamics`; ficha 2.3 | φ, estacionalidad y tendencia contra cota; test con serie sintética con estación conocida |
| 5 | Backtest con 5 técnicas, un juez, banda asimétrica normalizada → `decision_technique`, `decision_error_bands`; ficha 2.4 | calibración ≈ 90 % en backtest |
| 6 | Uplift simple + bootstrap → `decision_uplift` | celdas bajo suelo antes/después |
| 7 | Ensamblaje RUN leyendo las cinco tablas de decisión; agregación correcta | banda del total no decrece con h; `*_origen` cuentan defaults |
| 8 | Limpieza: `fase_pre`, alias, `sff_v2/`; referencia v3; prompts; ASUNCIONES/HANDOVER | tres tests en verde |

Cada paso: análisis → decisión persistida → mejora medida en la ficha → test de mano. Si un paso no mueve ningún atributo, se elimina.
