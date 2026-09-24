# MAPA DE SALIDA — qué produce una ejecución completa, cuánto, y quién lo lee

Simulación sobre el dataset sintético (843 filas de raw, 17 series, 30 meses de horizonte).
Los volúmenes de tablas escalan con Kamelot (660.000 filas, 10.877 series); el número de
bloques, figuras y páginas no. No se ha implementado nada: es la foto.

## 1 · Los cinco productos de una ejecución

| Producto | Qué es | Tamaño (sintético) | Tamaño (Kamelot, estimado) | Quién lo lee |
|---|---|---|---|---|
| **Consola** | el registro técnico de la ejecución | 384 líneas: 61 de escritura `[write]`, 47 de explicación `>`, 10 cabeceras de sección, 266 de resultados | ≈ 420 líneas (los listados están acotados a 15 filas) | el analista mientras corre; nadie después |
| **Tablas SQL** (`sff_`) | 59 tablas, 3 tipos | 8.600 filas en total | ≈ 3,5 M filas (fact_fine 660k, key_bridge 660k, backtest_pred ≈ 500k, forecast_detail/bands 185k×2, signal_composition ≈ 300k) | informe, ficha, run mensual, validación, Power BI |
| **Informe** | `informe/informe.md` + 10 PNG | 250 líneas: portada, 8 capítulos, anexo | igual | dirección, regiones, finanzas |
| **Fichas** | 6 paneles por serie, las 5 mayores (más las que se pidan con `sheet`) | 5 PNG | 5 PNG | quien pregunte "¿de dónde sale este número?" |
| **Validación** | el panel INTEGRITY / DOCTRINE / QUALITY | 23 comprobaciones | 23 | el analista; queda en `validation_report` |

## 2 · La consola, bloque a bloque (esqueleto real)

```
PHASE 0 — raw data validation
[0.1] contract OK · calendar from the current month: entrenamiento ≤ 2026-01 · examen 2026-02..07 · pendiente 2026-08 · proyeccion ≥ 2026-09
[0.2] fine 843 rows → forecast units 747 · pipeline conserved ($2,323,980)
[0.3] routes per series: {predecible 15, solo_futuro 1, solo_historia 1}
[0.4] raw profile (level 0): 20 líneas (calendario, dimensiones, medidas, plazo)
PHASE 1 — rate series, dimensions, support ladder
[1.1] 17 series · gaps 10 · below the floor: $19,800 of $242,100 projected      > 3 líneas de lectura
[1.1b] fu profile: dial 3 tramos (menos de 30: 5 % · 30-271: 5 % · más de 271: 90 %)
[1.2] dimension separation: η² / unique / ω² / collapse order (1 línea por dimensión)  > 3 líneas
[1.3] ladder: collapse order · 80 % reached the floor · money by risk level (8 niveles) · rule → meaning (10 líneas)  > 3 líneas
[1.4] mandatory-only view vs segmented ($) · where segmenting pays (top celdas) · composition 7 % · signals by sign  > 3 líneas
[1.5] DISCOUNT AND CHURN: rate by bucket (raw / standardized) · gaps inside each state · adjusted effects · importance · price  > 4 líneas
PHASE 2 — seasonality benchmark and pool reference
[bench 1] 4 series selected · 89 % of the pipeline
[2] SEASONALITY BENCHMARK: 1 línea por serie · DECISION  > 4 líneas
[2] pool reference: 12 ids · 9 with support · 1 with month effects
PHASE 3 — backtest, technique, bands
[3] backtest: 1,776 predictions · leaderboard by band (10 técnicas × 2 tramos) · champions per band  > 4 líneas
[3] candidates to look at in detail (3 tipos, con sheet("<id>"))
[3] HOLD-OUT per pool by h · HOLD-OUT OF THE TOTAL by h · COMMON ERROR BAND by h  > 4 líneas
PHASE 4 — uplift
[4] 3 cells · range · below floor · clipped
PHASE 5 — assembly, extended horizon, bands
[5] extended horizon: 366 simulated rows · forecast $633,345 over 17 months · origins
[5] month · expected · band (17 líneas) · PIPELINE SUMMARY (3 bloques)  > 5 líneas
[5] BUSINESS ANSWERS (2 años × 2 líneas + ajustado)  > 3 líneas
[5] BY REGION (1 línea por región)  > 3 líneas
[5] SIGNAL MATURATION: composición final vs hoy · maduración en $ · alertas  > 4 líneas
[5] BASELINE: grano × ventana vs framework, walk-forward lag 1 / 4 (9 líneas)
[5] TOP MOVERS: 6 tipos × hasta 15 filas  > 4 líneas
SHEETS — the 5 series with the most projected money (5 líneas)
VALIDATION PANEL — 23 comprobaciones
[informe] <outdir>/informe/informe.md · 10 figuras
```

Lectura honesta: son **veintitrés bloques**. Para el analista que ya conoce el framework es
manejable y las explicaciones se apagan con `console_explanations=False` (quedan 337
líneas) y los `[write]` deberían ir a un log aparte (quedarían 276). Para cualquier otra
persona la consola no es el producto: lo es el informe.

## 3 · El informe, capítulo a capítulo (lo que se lee de verdad)

| Capítulo | Líneas | Figura | Tablas incrustadas |
|---|---|---|---|
| Portada: tres números, tres decisiones | 15 | 00 mes a mes con banda y ajustado | — |
| 1 Pipeline por origen | 8 | 01 apilada por origen | business_summary |
| 2 Ruido: dial y niveles | 10 | 02 dinero por nivel con error | — |
| 3 Composición | 8 | 03 Kitagawa top celdas | — |
| 4 Estación | 12 | 04 efectos de mes | decision_estacionalidad |
| 5 Precisión | 12 | 05 examen del total | — |
| 6 Riesgo: maduración, regiones, movers | 15 | 06 regiones · 07 top movers | forecast_by_region |
| 7 Frente a la hoja | 8 | 08 baseline | — |
| 8 Precio y churn | 12 | 09 descuento por estado | discount_churn_adjusted |
| Anexo: fichas, leyenda (12 métricas), tablas producto, debilidades | 60 | — | metric_legend |

Unas 250 líneas y 10 figuras: dos páginas de portada y una por capítulo. Es la medida
correcta para dirección; lo que se recorta de aquí en adelante es prosa, no información.

## 4 · Las 59 tablas: quién las usa

La revisión se hizo buscando el nombre de cada tabla en los módulos que leen tablas de
vuelta (informe, ficha/auditoría/diagnósticos, run mensual, validación) y en los que las
consumen desde `results` en memoria. Cuatro grupos:

**A · Leídas por el informe o el run mensual (28).** Son las que producen los cinco
productos: `business_summary`, `pipeline_summary`, `horizon_report_total`,
`forecast_by_region`, `top_movers`, `signal_adjustment`, `signal_alerts`, `dial_buckets`,
`series_card`, `mix_shift`, `mandatory_only_cost`, `decision_estacionalidad`,
`backtest_holdout`, `backtest_holdout_agg`, `decision_agg_bands`, `baseline_summary`, las
cinco `discount_churn_*`, `metric_legend`, y las decisiones que el run mensual lee:
`decision_eta2`, `decision_support`, `pool_reference`, `decision_technique`,
`decision_error_bands`, `decision_uplift`, `forecast_detail`, `forecast_bands`.

**B · Leídas solo por la ficha / auditoría (9).** `fact_fu`, `fact_fu_gaps`, `fs_summary`,
`parent_ladder`, `support_chain`, `backtest_pred`, `uplift_chain`, `fu_extended`,
`key_bridge`. Son la trazabilidad: cuando alguien pregunta "¿de dónde sale este número?".
Necesarias, no para leer de corrido.

**C · Solo para Power BI (5).** `fact_fine`, `lookup_fu`, `lookup_comb`,
`signal_snapshot` (la foto acumulable: su lector es el futuro), `key_bridge` (también en B).
Justificadas por el modelo de BI de `AUDITORIA.md`.

**D · Nadie las lee (14).** Aquí está la respuesta a tu pregunta:

| Tabla | Filas (sint.) | Qué es | Veredicto |
|---|---|---|---|
| `fu_summary` | 747 | la antigua tabla de cotas; ya se fundió en `fact_fu` pero **sigue en el registro y en una función de compatibilidad** | borrar del registro |
| `raw_profile`, `dim_domains`, `fu_profile` | 28, 19, 16 | los perfiles de nivel 0 y 1; se imprimen en consola y no se leen de vuelta | el capítulo 1 del informe debería leer `dim_domains` (valores que aparecen/desaparecen: es el mix-shift de catálogo) y `fu_profile` (series que nacen dentro); hoy no lo hace |
| `risk_levels` | 8 | el dinero por nivel | **`TABLE_KIND` la lista como `risk_levels_report`, un nombre que no existe**: el informe recalcula lo mismo desde `series_card` en vez de leerla |
| `decision_eta2_pairs` | 3 | pares de dimensiones (η² conjunto) | útil una vez para la taxonomía; no la lee nadie |
| `tv_calibration` | 344 | tasa realizada por flag y mes | debería ser la evidencia del capítulo 6 y de `ESTRATEGIA_POR_REGION`; hoy solo consola |
| `bench_panel`, `bench_flags` | 172, 96 | el panel mes × año del benchmark y la estación de los flags | `bench_panel` está pensada para Power BI (figura por serie); `bench_flags` no produce veredicto ni entra en el informe (debilidad M9 de la auditoría) |
| `dim_tecnica` | 10 | el catálogo de técnicas | dimensión para BI; correcto que nadie la lea |
| `backtest_agg_error` | 12 | el error agregado por mes y h en decisión | es la base de `decision_agg_bands`; solo auditoría |
| `forecast_by_level` | 7 | forecast y banda por nivel | el informe la recalcula parcialmente; debería leerla |
| `signal_composition`, `signal_final_comp` | 747, 16 | la composición por celda y la final | intermedias de la maduración; la ficha debería enseñar la final de la celda de la serie |
| `baseline_forecast` | 102 | la hoja mes a mes | solo el resumen se usa; el detalle es para BI |

Y tres cosas que la revisión ha destapado y que anoto para corregir (no hechas):

1. **`TABLE_KIND` usa cuatro nombres que no existen en el registro** (`forecast_units`,
   `fine_table`, `lookup_forecast_units`, `risk_levels_report`): la clasificación de esas
   tablas cae en "intermedia" por error. El anexo C del informe lista tablas mal.
2. **La validación del raw avisa "role 'entrenamiento' is EMPTY in the raw"**: comprueba
   los roles del raw contra el vocabulario nuevo antes de traducirlos. Tres avisos falsos
   por ejecución.
3. **`fu_summary` sigue registrada** aunque ya no se escribe; y un mensaje de la fase 0
   conserva el texto "no_impact is labeled".

## 5 · Lo que sobra y lo que falta, en una frase cada uno

- **Sobra**: `fu_summary` (registro), la duplicación entre `risk_levels` /
  `forecast_by_level` y lo que el informe recalcula, y los tres avisos falsos.
- **Falta que el informe lea lo que ya existe**: `dim_domains` y `fu_profile` (qué cambia
  en el catálogo), `tv_calibration` (qué señal funciona como señal), `risk_levels` y
  `forecast_by_level` (en vez de recalcular), `bench_flags` (con un veredicto).
- **Bien como está**: el grupo A (28 tablas) y la trazabilidad (B).

Si se hacen esas cuatro cosas, las 59 tablas quedan en 58 y todas tienen un lector con
nombre: el informe, la ficha, el run mensual, la validación o Power BI.
