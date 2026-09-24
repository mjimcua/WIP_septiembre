# REVISIÓN PROFUNDA — SFF v2 → v3 · 12-sep-2026

*Revisión del código completo (fase 0 nueva + fases 1-4 y validación legacy), de su coherencia con el refactor y con la misión de la librería, puntos débiles con evidencia numérica sobre la salida de referencia, contraste con la literatura, inventario de lo no implementado, y ejemplo de la escalera de soporte. Lenguaje técnico directo.*

---

## 0 · Resumen ejecutivo

Diez hallazgos, por impacto. Los cuatro primeros son defectos de lógica: el código no hace lo que la doctrina dice que hace.

| # | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| 1 | **La técnica campeona del backtest NO se usa en el forecast puntual.** `forecast_detail.tasa` = `tasa_final` de fase 1 (tasa histórica con credibilidad, equivalente a T2_promedio sobre toda la historia). El campeón (T8, T4…) solo alimenta bandas y tablas informativas. | `f3_ensamblaje` lee `series_estimates.tasa_final`; `_tecnicas()` no se llama en fase 3 | Alta: el backtest elige, la ejecución ignora |
| 2 | **La credibilidad del uplift es un no-op.** El "padre" se agrupa por `(uplift_cells, padre)` y `uplift_cells` ya contiene las extras, así que cada padre es la propia celda: `1_padre == 0_fino == 2_shrink` en el 100 % de las celdas. Los "ejes mudos" se listan y no se aplican. | `sff_uplift_chain`: 3/3 celdas con las tres etapas idénticas | Alta: la rama de valor no repara soporte |
| 3 | **L2 (asterisco) no incluye a la hermana con soporte.** El id `*` solo se asigna a series bajo el suelo; la hermana grande conserva su id y queda fuera del pool. Una serie de n=12 anulada a `EU\|0\|0\|0\|0\|A\|*` sigue con n=12. | `sff_support_chain`: `EU\|0\|0\|0\|0\|A\|tele` n=12 en 0_raw, 1_L1 y 2_L2 | Alta: L2 solo actúa si hay varias hermanas pequeñas |
| 4 | **La escalera salta la celda mandatory.** El peldaño 1 ya colapsa una mandatory; la celda completa nunca es peldaño. Con una sola mandatory, la credibilidad encoge directamente hacia la tasa **global** (0,737), no hacia EU. La docstring dice "toward the mandatory cell"; el código no. | `sff_parent_ladder`: peldaño 1 = `*` (n=1674), único | Alta con pocas mandatory; media con 10 |
| 5 | **Bandas agregadas en cuadratura fila a fila dentro del mismo pool.** Las filas de un pool comparten la misma tasa: su error es perfectamente correlado, se suma linealmente, no en cuadratura. En el sintético la banda total está un 16-23 % por debajo; en Kamelot (647 k filas en pocos pools) la infravaloración escala como √(filas por pool). | Recalculado sobre `sff_forecast_bands` | Alta: la banda del total es la cifra que se enseña |
| 6 | **Banda medida sin escalar por n.** El p90 del error se calcula por (técnica, h) sobre TODOS los pools; un pool de n=1000 y otro de n=35 reciben la misma banda. Y los horizontes están desalineados: backtest 1-4, rolling 1-3, forecast hasta 5+ → **100 % fallback binomial en h≥4**, y la banda h=4 ($1.041) es menor que la h=1 ($3.661): una banda que se estrecha con el horizonte es señal inequívoca de descalibración. | `sff_forecast_bands` por h | Alta |
| 7 | **Error de estimación confundido con error de predicción.** Tras el shrink, una serie de n=12 aparece con `n_efectivo = 418` y `se_pp = 2,1`. Eso es la incertidumbre sobre *p*; la tasa realizada del mes que viene con 12 unidades seguirá oscilando ±11,5 pp. La cadena de soporte y las bandas de fila no separan `Var(p̂)` de `p(1−p)/n_mes`. | `sff_support_chain` 3_shrink | Media-alta: afecta a lo que se comunica |
| 8 | **Dos jueces distintos.** El campeón se elige con `backtest_long` (3 orígenes por horizonte); las bandas usan `rolling_table` (todos los orígenes). Tres orígenes es una muestra minúscula para elegir entre 15 técnicas. | `f4_backtest` vs `f4_rolling_next_month` | Media |
| 9 | **`k_cred = 60` fijo.** Bühlmann lo define como σ²/τ² y se estima de los datos; con k fijo, una serie de n=600 se desplaza 0,6 pp hacia el global sin evidencia de que deba. | `EU\|0\|0\|0\|0\|A\|web`: 0,7996 → 0,7939 | Media |
| 10 | **Las tablas de decisión (DISENO_SPLIT §3) no existen.** RUN sigue recalculando η², backtest y bandas en cada ejecución: no hay separación efectiva análisis → ejecución todavía. | Ninguna tabla `decision_*` | Estructural |

Lo que sí está bien y conviene no tocar: la fase 0 (contrato exhaustivo, doctrina del mes en curso, conservación del dinero, claves deterministas), la disciplina null≠zero, el contrafactual walk-forward, φ como detector de motor, el puente de claves, y la validación con familias INTEGRITY/DOCTRINE/QUALITY.

---

## 1 · Coherencia del refactor

**Estado.** Reescritos y testeados: `config.py` (102 checks), `raw_data_validation.py` + `support_reference.py` (67 checks), `pipeline.py`, `main.py`, `test_pipeline.py` (lógica ×2 taxonomías + 25/25 contra referencia). Legacy en uso: `fase1..fase4`, `validation`, `synthetic`.

**Nomenclatura acordada y aplicada en lo nuevo:** identificadores en inglés; `rate_series_columns` / `uplift_cell_columns` en vez de "grano"; `mandatory_cell` / `uplift_cell` nunca "cell" a secas; forecast unit / forecast series / celda como cadena de identidad; docstring INPUT · OUTPUT · RULES · EDGE CASES · CONSOLE + STEPS; constantes con nombre; ≤ 50 líneas por función; `read_raw()` sobreescribible; sin CSV ni SQL de lectura en el código.

**Incoherencias que quedan (todas en la frontera con el legacy):**
- `config.py` conserva cinco alias en español (`grano_tasa`, `grano_uplift`, `medidas`, `medidas_declaradas`, `validar_columnas`) porque fase 1-4 los leen. Se borran con la última fase.
- `pipeline.py` importa de `sff_v2/` y mezcla vocabulario: `labeled_view`, `repaired_view`, `v2`. Al reescribir fase 1 se unifican los nombres de los frames (`forecast_units`, `labeled_units`, `repaired_units`).
- Los tests de fase 1-4 no existen: solo la comparación con la referencia. Y la referencia **codifica los defectos 1-9**: cuando se corrijan, la referencia cambia por diseño. Hay que decidirlo explícitamente (§8).
- `test_config.py` fija `PHYSICAL_TABLE_NAMES` en 27 entradas incluyendo las dos `simpson_showcase*` que se van a eliminar. Cambiará con ellas.
- Plano: al aplanar el directorio se perdió la separación RUN/ANALYSIS en carpetas. Se propone por prefijo (§2).

---

## 2 · Separación ejecución (RUN) vs análisis (ANALYSIS), función a función

Criterio: RUN = lo que produce `forecast_detail` y sus bandas cada mes **sin tomar decisiones**; lee decisiones de tablas. ANALYSIS = lo que decide y lo que mide.

| Fase | Función legacy | Clasificación | Módulo propuesto | Nota |
|---|---|---|---|---|
| 0 | validate_raw, apply_current_month_doctrine, build_fine_table, aggregate_to_forecast_units, build_key_lookups, label_universe_and_routes | RUN | `run_raw_data_validation.py` | hecho |
| 0 | build_support_reference | ANALYSIS | `analysis_support_reference.py` | hecho |
| 1 | f1_series_and_gaps (fs_key, huecos, tasa por fila, resumen por serie) | RUN | `run_rate_series.py` | el resumen `fs_summary` es reporte → ANALYSIS |
| 1 | f1_diagnose_round1: foto binomial, contrafactual Simpson, η², pares | ANALYSIS | `analysis_rate_diagnostics.py` | escribe `decision_eta2` |
| 1 | f1_improve_support: signo, L1, L2, pools, escalera, credibilidad | RUN (lee η²) | `run_rate_support_repair.py` | orden de colapso y dim anulable vienen de `decision_eta2` |
| 1 | f1_support_chain (cascada de dinero por etapa) | ANALYSIS | `analysis_rate_diagnostics.py` | reporte |
| 1 | f1_diagnose_round2 (gate, φ) | ANALYSIS | `analysis_rate_diagnostics.py` | `diagnostico_dinamica` |
| 2 | f2_uplift_fine | RUN | `run_uplift_cells.py` | |
| 2 | f2_diagnose (η² uplift) | ANALYSIS | `analysis_uplift_diagnostics.py` | escribe `decision_eta2` rama uplift |
| 2 | f2_improve (padre, credibilidad) | RUN (lee η²) | `run_uplift_support_repair.py` | hoy no-op: rehacer |
| 3 | f3_build_key_bridge | RUN | `run_key_bridge.py` | |
| 3 | f3_ensamblaje | RUN (lee técnica) | `run_forecast_assembly.py` | debe aplicar la técnica elegida |
| 4 | f4_backtest (juez, campeón) | ANALYSIS | `analysis_backtest.py` | escribe `decision_technique` |
| 4 | f4_rolling_next_month | ANALYSIS | `analysis_backtest.py` | escribe `decision_error_bands` |
| 4 | f4_forecast_bands | RUN (lee bandas) | `run_forecast_bands.py` | |
| 4 | f4_tablas_fu (dim_tecnica, backtest_fu, forecast_fu) | ANALYSIS | `analysis_backtest.py` | tablas de auditoría |
| 4 | f4_horizon_report | ANALYSIS | `analysis_backtest.py` | reporte |
| — | validation.run_validation | RUN (panel mínimo) + ANALYSIS (QUALITY) | `run_validation.py` / `analysis_validation.py` | INTEGRITY y DOCTRINE bloquean en RUN; QUALITY es análisis |
| — | `_tecnicas` (catálogo) | compartido | `techniques.py` | lo usan ambos |
| — | fase_pre (buscador Simpson) | eliminar | — | decisión del usuario |

**Dos runners:** `run_pipeline(configuration)` (mensual, delegable; lee `decision_*`) y `run_analysis(configuration)` (periodo de evaluación; escribe `decision_*` y los reportes). `test_pipeline.py` ejecuta los dos en secuencia sobre el sintético.

**Prefijo en el nombre de fichero** (`run_*.py`, `analysis_*.py`) para que la separación se vea en un directorio plano.

---

## 3 · Puntos débiles, con detalle

### 3.1 El campeón no gobierna el forecast (hallazgo 1)

`forecast_final_seleccion` dice "para el pool X, la técnica con menor error es T8_tendencia_sat". `forecast_detail` ignora eso y usa la tasa histórica con credibilidad para todos. `forecast_predictions_fu` sí calcula la predicción de cada técnica por FU futura (15 técnicas × h), pero no se selecciona ninguna.

Dos formas coherentes de cerrarlo; hay que elegir una:
- **(a)** El forecast puntual = predicción del campeón del pool a horizonte h, aplicada a la serie (P5: calculada en el pool, estampada en cada miembro), con `tasa_final` de fase 1 como *nivel* y el campeón aportando la *dinámica*. Requiere definir cómo se combinan nivel de serie y dinámica de pool (p. ej. multiplicativo: tasa_serie × pred_pool(h)/media_pool).
- **(b)** Declarar que el forecast puntual es la tasa de credibilidad (estática) y que el backtest solo calibra bandas. Es lo que hace hoy; hay que decirlo en la doctrina y quitar "campeón" del vocabulario.

Con φ mediano ≈ 1 en la mayoría de pools (no hay motor), (b) no pierde mucho; donde φ > 1,5 y el gate dice `tendencia`/`estacional`, (a) es lo que justifica todo el backtest.

### 3.2 Uplift: credibilidad no-op y ejes mudos sin aplicar (hallazgo 2)

`f2_improve` calcula `padre = comb_id con '*' salvo newcust` pero agrupa por `(uplift_cells, padre)`, y `uplift_cells` = mandatory + extras completas. Cada grupo tiene una fila. Corrección: el padre debe agruparse por **mandatory + padre** (las extras anuladas), no por `uplift_cells`. Además `anular` (ejes con η² < 0,05) se calcula y no se usa. Y el `se` del uplift (`s/√meses`) es la desviación de la media mensual, no del ratio ponderado: para un ratio de sumas el error estándar correcto es el del cociente (delta method) o bootstrap sobre renovadores.

También: `newcust` está cableado por nombre (`d == "newcust"`) — viola P3 (todo declarado en config). Debe ser un campo `uplift_parent_keep_columns`.

### 3.3 L2 sin la hermana grande (hallazgo 3)

El `*` se asigna solo a series con `n1 < floor`. La hermana con soporte conserva su id, y `pool("fs_id_L2")` agrupa por ese id: el pool `A|*` contiene solo pequeñas. Corrección: el **pool** se calcula con todas las series que casan con el patrón `*` (grandes incluidas); la asignación del id sigue siendo solo para las pequeñas (la grande se queda con su tasa propia). Es decir, separar "quién recibe la tasa del pool" de "con quién se calcula el pool". Lo mismo vale para L1: hoy el pool `SIG=neg` solo suma pequeñas del mismo signo; debería incluir todas las series activas del signo, para que su tasa sea la del régimen y no la de sus miembros más débiles (aunque aquí es discutible: las grandes del mismo signo pueden tener régimen propio; declarar).

### 3.4 Peldaño 0 = la celda mandatory (hallazgo 4)

La escalera debe empezar en la celda mandatory completa (todas las mandatory, extras y timevarying colapsadas). Solo si esa celda no alcanza el suelo se sube al peldaño 1. Con 10 mandatory en Kamelot el error es menor (peldaño 1 colapsa `band_level_2`, un padre muy parecido), pero con la taxonomía de prueba el shrink va al global, y en cualquier caso la docstring promete la celda.

### 3.5 Bandas (hallazgos 5, 6)

Cuatro problemas independientes:

1. **Correlación dentro del pool.** Todas las filas futuras de un pool y un mes reciben la misma tasa; si la tasa yerra +3 pp, yerra +3 pp en todas. Agregación correcta: suma lineal dentro de (pool, mes), cuadratura entre pools (y entre meses, con reservas: los errores de una técnica a h y h+1 también están correlados). Con la referencia: +16-23 %; en Kamelot, mucho más.
2. **Escala por n.** El p90 de |err| por (técnica, h) mezcla pools de tamaños dispares. Solución estándar: normalizar el error por la cota binomial del pool-mes (`err/se_binom`), tomar el p90 del error **normalizado**, y devolverlo a cada pool multiplicando por su propia cota. Es conformal prediction con no-conformidad normalizada (Papadopoulos 2008); mantiene "banda medida, no teórica" y respeta el tamaño.
3. **Horizontes.** `horizontes=(1,2,3,4)` en backtest, `ROLLING_HORIZONS=(1,2,3)` en rolling, y el forecast llega hasta donde llegue el pipeline. Hay que medir hasta el horizonte máximo proyectado (config: `max_forecast_horizon`), y si no hay historia para medirlo, extrapolar la banda con una regla declarada (p. ej. banda(h) = banda(3)·√(h/3)), nunca caer al binomial de fila, que es más pequeño que el error medido a h=1.
4. **Monotonía.** Añadir un check de validación: la banda relativa del total no puede decrecer con h. Hoy decrece.

### 3.6 Estimación vs predicción (hallazgo 7)

Para una fila futura de una serie con n unidades en ese mes, la varianza de la tasa realizada es `Var(p̂_est) + p(1−p)/n_fila`. El shrink reduce el primer término; el segundo no se reduce nunca (es la moneda del mes). Hoy `se_final` es solo el primero y `n_efectivo` lo presenta como si fuera soporte real. Propuesta: mantener `se_est_pp` (estimación) y `se_pred_pp` (predicción a un mes con el n de la fila) como dos columnas, y usar la segunda en las bandas de fila cuando no hay banda medida. Cambia la comunicación: "conocemos la tasa de esta celda con ±2 pp; el mes que viene con 12 unidades verás ±12 pp".

### 3.7 Un solo juez (hallazgo 8)

Elegir campeón sobre `rolling_table` (todos los orígenes, mismo conjunto de datos que las bandas) y eliminar `backtest_long` de 3 orígenes, o al revés. Un juez, una tabla, una decisión (`decision_technique` con `n_predicciones` para saber cuánta evidencia respalda la elección). Con pocos orígenes, exigir un mínimo de predicciones para destronar al retador T2.

### 3.8 k fijo (hallazgo 9)

Bühlmann-Straub: `z = n/(n+k)` con `k = E[σ²_dentro]/Var(medias)`. Ambos se estiman del propio grupo de hermanas (método de momentos; beta-binomial de Kleinman 1973 para proporciones). Propuesta: estimar k **por padre** en ANALYSIS, escribirlo en una tabla de decisión (`decision_credibility`: padre_id, k, n_series, decision_date), y que RUN lo lea; `k_cred=60` queda como valor por defecto cuando no hay estimación. Con eso la serie de n=600 no se mueve si sus hermanas se parecen, y sí se mueve si son heterogéneas.

### 3.9 Otros puntos concretos

- **Fallback de celda** en fase 3: `mean()` sin ponderar de `tasa_final` de las series de la celda. Debe ponderarse por pipeline (o mejor, tomar la tasa del pool de la celda calculada en fase 1).
- **Wald con clip `pq ≥ 0,0025`** en todas las `se`. Para p cerca de 0 o 1 y n pequeño, Wald es malo (Brown-Cai-DasGupta 2001). Wilson score o Agresti-Coull dan intervalos honestos sin el clip.
- **`rate_cap` en fase 3** recorta `tasa_final` en 0,95 sin re-normalizar la banda ni registrar cuántas series se recortan (hay check de "tasa bajo el techo", pero no de "tasa recortada"). Añadir `tasa_recortada` (0/1).
- **Detección del mes en curso duplicada** en fase 4 (`isin([1, True, "1"])`) y fase 0 (`CURRENT_MONTH_TRUTHY_VALUES` más amplia). Tras fase 0 el mes en curso ya es `projection`, así que en fase 4 es redundante y debe eliminarse (una sola fuente de verdad).
- **`fu_comb_key` no se aserta única en fase 0**; solo la validación al final lo mira. Moverlo a `build_fine_table` (P3: fallar al principio).
- **Columnas declaradas ausentes** no las comprueba el contrato (documentado). Es barato añadirlas: `missing = declared − raw.columns`; parar si falta alguna de las core.
- **Rendimiento.** `iterrows` en `f4_forecast_bands`, `f4_tablas_fu`, `f2_improve`, y `apply` fila a fila en el contrafactual. Con 647 k filas (Kamelot) esto es lento; vectorizar con merges. `key_bridge` 103 s (HANDOVER): `category` en dimensiones y `drop_duplicates` sobre claves int, no strings.
- **`gap_rate_policy = "zero_rate"`**: opción legacy que contradice la doctrina. Si nadie la usa, eliminar (P3: menos superficie, menos error).
- **Colisiones de hash** (48 bits): probabilidad ≈ N²/2⁴⁹; con 10⁶ ids, 1,8·10⁻³ por ejecución. Aceptable pero no cero; ya se aserta la unicidad de `fu_id`; asertar también la de `fu_key` (una colisión es un bug invisible si no se comprueba).

---

## 4 · Coherencia con la misión (POR_QUE_ESTE_FORECAST.md)

| Promesa del documento | Estado en el código |
|---|---|
| "Banda = p90 del error **medido** por técnica y horizonte" | Cierto en h≤3 de pools elegibles; **100 % teórica en h≥4** y en pools no elegibles (`len ≥ 10 y n ≥ floor/2`) |
| "Al agregar series, las bandas se combinan en cuadratura" | Se hace, pero también entre filas del mismo pool: incorrecto (§3.5) |
| "Backtest multi-origen con 15 técnicas, campeón por pool" | Se elige, **no se aplica** al forecast (§3.1) |
| "Credibilidad z = n/(n+k) hacia el primer padre de la jerarquía que alcanza el suelo" | Cierto, pero el primer padre nunca es la celda mandatory (§3.4) |
| "L2: anular la dimensión extra de menor η², juntando a las hermanas" | Junta solo a las hermanas pequeñas (§3.3) |
| "El uplift: ratio de sumas ponderado, error s/√n, credibilidad hacia el padre con el mismo punto de partida" | Ratio sí; credibilidad no-op; `se` mal definido (§3.2) |
| "Las decisiones se separan de la ejecución mensual para poder delegarla" | No hay tablas de decisión; RUN recalcula todo (§2) |
| "Cada estimación tiene su error propio calculable por cualquiera" | Cierto para la cota binomial; el error del shrink mezcla estimación y predicción (§3.6) |

La misión es correcta; el código está a medio camino de cumplirla. La mayor parte de las distancias son de fase 1.3, 2.3 y 4c.

---

## 5 · Literatura: qué se puede hacer mejor

Referencias de lo estándar en cada pieza; en todos los casos la propuesta mantiene el principio P1 (referencia propia, no número mágico) y añade poca complejidad.

| Pieza | Lo que hacemos | Lo que dice la literatura | Propuesta |
|---|---|---|---|
| Credibilidad | z = n/(n+k), k fijo | **Bühlmann-Straub (1970)**: k = σ²/τ² estimado por grupo; **beta-binomial empírica** (Kleinman 1973; Gelman et al., *BDA* cap. 5) para proporciones; jerarquías multinivel (Gelman & Hill 2007) hacen la escalera en un solo modelo | Estimar k por padre en ANALYSIS; mantener la escalera explícita (auditable) en vez de un modelo jerárquico completo |
| Intervalo de una proporción | Wald con clip | **Wilson (1927)** / **Agresti-Coull (1998)**; Brown, Cai & DasGupta (2001) muestran que Wald falla con n pequeño y p extremo | Wilson en `se()`; quitar el clip |
| Sobredispersión | φ medido, no usado | Quasi-binomial (**McCullagh & Nelder 1989**): var = φ·p(1−p)/n | Banda = cota·√φ cuando φ>1 y gate ≠ soporte (ya en backlog: hacerlo) |
| Bandas empíricas | p90 de \|err\| por (técnica, h), global | **Conformal prediction** con no-conformidad normalizada (Papadopoulos et al. 2008; Romano, Patterson & Candès 2019 para cuantiles) | p90 de \|err\|/cota_pool, devuelto a cada pool × su cota |
| Agregación de errores | Cuadratura por fila | Varianza de una suma = Σ var + 2Σ cov; con tasa compartida, cov = var (correlación 1) dentro del pool | Suma dentro de (pool, mes), cuadratura entre pools; documentar la aproximación entre meses |
| Selección de técnica | Media de \|err\| en 3 orígenes, margen 0,1 pp vs T0/T2 | **Rolling-origin evaluation** (Tashman 2000); comparación contra benchmark naive con margen (Hyndman & Athanasopoulos, *FPP3* §5.8) | Un juez sobre todos los orígenes; exigir n_pred mínimo; el margen en unidades de la cota, no en pp fijos |
| Descomposición del cambio agregado | Contrafactual plano vs segmentado | **Kitagawa (1955) / Oaxaca-Blinder**: Δtasa = Σ w·Δp (comportamiento) + Σ p·Δw (composición) | Reportar los dos términos por celda y mes: es la explicación "teórica" de Simpson que quieres dar, con números propios, sin buscar casos |
| Reconciliación jerárquica | Bottom-up con pesos del pipeline (coherente por construcción) | **Hyndman et al. (2011)**, **MinT (Wickramasuriya 2019)** | No hace falta reconciliar el punto (los pesos son dato); sí importa la covarianza para las bandas (fila anterior) |
| Series intermitentes | Croston listado en catálogo | Croston (1972), SBA (Syntetos-Boylan 2005), TSB | Correcto tener Croston; SBA corrige el sesgo de Croston y es un cambio de una línea |
| Nulos e imputación | Huecos con tasa NaN (`no_rate`) | Correcto: un mes sin vencimientos no informa la tasa; no imputar | Mantener |
| Mes en curso | Excluido y proyectado | Estándar en *nowcasting*: el periodo parcial se trata aparte | Mantener; a futuro, curva de maduración intra-mes (backlog Simpson/snapshot) |

Lo que **no** recomiendo: sustituir la cadena explícita (L1/L2/escalera/credibilidad) por un modelo jerárquico bayesiano o por gradient boosting. Perderías la auditabilidad fila a fila que es la razón de ser del framework, y con φ≈1 en la mayoría de pools no hay señal que un modelo más complejo pueda capturar. Las mejoras de arriba son locales y verificables una a una con la referencia.

---

## 6 · Sin implementar o a medias

| Ítem | Estado | Origen |
|---|---|---|
| Tablas de decisión `decision_eta2`, `decision_technique`, `decision_error_bands` (+ `decision_credibility` propuesta) | No existen | DISENO_SPLIT §3 |
| Campeón aplicado al forecast puntual | No | §3.1 |
| Credibilidad del uplift | No-op | §3.2 |
| Ejes mudos del uplift | Calculados, no aplicados | §3.2 |
| L2 con hermanas grandes; peldaño 0 = celda | No | §3.3, §3.4 |
| Bandas en h ≥ 4 | Fallback teórico siempre | §3.5 |
| φ como palanca de banda | Medido, no aplicado | HANDOVER §6.7 |
| Universo `time_series` | Solo etiquetado; `ts_revenue_col` reservado | DISENO_V2 |
| `semantic_labels` | Soportado; vacío en producción | config |
| Test estacional con varios años | No (13 meses = 1 ciclo) | HANDOVER §6.7 |
| Wilson/Clopper-Pearson | No | HANDOVER §6.7 |
| `uplift_cap` + investigación del 466× | No | HANDOVER §6.2 |
| `staging_swap` para carga con BI vivo | No | HANDOVER §6.7 |
| Fases 5-8 (adquisición, año siguiente) | No | DISENO_V2 |
| `fase_pre` / `simpson_showcase*` | A eliminar | decisión 12-sep |
| Tests unitarios de fases 1-4 | No | este chat |
| `PROMPT_COMMON.md`, `PROMPT_PHASE_0.md` | No escritos | alcance de este chat |
| ASUNCIONES.md, HANDOVER.md actualizados | Pendiente | alcance de este chat |
| Glosario técnico ↔ metáforas | Iniciado (`GLOSARIO.md`) | HANDOVER §6.4 |
| `key_bridge` 103 s | No optimizado | HANDOVER §6.3 |

---

## 7 · La escalera de soporte, paso a paso, con números

Los pasos, **en el orden en que se aplican**, con la serie `EU|0|0|0|0|A|tele` de la salida de referencia (taxonomía de prueba: `mandatory=[region]`, `timevarying=[dormant, softcancel, no_instalado, autorenew]`, `extra_renovacion=[product, channel]`; suelo 30; k=60).

| Paso | Qué se pregunta | Esta serie | Resultado |
|---|---|---|---|
| **0 · raw** | ¿Cuánto soporte tiene sola? n = mediana mensual de unidades venciendo | n = 12, tasa histórica 0,800 | 12 < 30: **no puede hablar sola**. se = 11,5 pp |
| **1 · L1, agrupar por signo** | ¿Tiene alguna timevarying activa? Si sí y n < suelo, se une a las series del mismo signo (`…\|SIG=neg`) | Ninguna activa (0,0,0,0) | No aplica: id y n sin cambio |
| **2 · L2, asterisco** | ¿Sigue bajo el suelo sin señal? Se anula la extra con menor η² (aquí `channel`): `EU\|0\|0\|0\|0\|A\|*` | Id anulado | **n sigue 12** — defecto §3.3: la hermana `A\|web` (n=600) no entra en el pool |
| **3 · escalera de padres** | ¿Sigue bajo el suelo? Subir peldaño a peldaño colapsando una mandatory más, hasta el primer padre con n ≥ suelo | Peldaño 1 = colapsar `region` → `*` (todo) | n = 1674, tasa 0,737, **elegido** |
| **4 · credibilidad** | z = n/(n+k) con el n de la etapa anterior; tasa_final = z·propia + (1−z)·padre | z = 12/(12+60) = **0,17** | 0,17·0,800 + 0,83·0,737 = **0,7475** ✓ (coincide con la tabla) |
| se final | cuadratura de las dos se ponderadas | √(0,17²·11,5² + 0,83²·1,2²) | 2,1 pp (es el error de *p̂*, no de la tasa del mes que viene: §3.6) |

Cómo **debería** quedar con las correcciones de §3.3 y §3.4:

| Paso | Corregido |
|---|---|
| 2 · L2 | Pool `EU\|0\|0\|0\|0\|A\|*` = tele (12) + web (600) → n = 612, tasa ≈ 0,7996. **Ya supera el suelo**: la escalera no hace falta |
| 3 · escalera | Peldaño 0 = celda mandatory `EU` (colapsa timevarying y extras). Solo si `EU` < suelo, peldaño 1 = `*` |
| 4 · credibilidad | z = 612/(612+k) ≈ 0,91 → tasa_final ≈ 0,7996; y con k estimado de las hermanas (todas ≈ 0,80), k sería grande y z pequeña: la serie toma la tasa del pool, que es lo correcto cuando las hermanas son homogéneas |

**Orden de colapso de la escalera en producción** (10 mandatory, Kamelot sep-2026). Regla: dentro de una familia `x_level_1/2/3` cae primero el nivel más fino; entre familias, cae primero la de menor η² entre las que ya tienen sus niveles finos colapsados. Con la ejecución de septiembre el orden empezaba por `tr_band_level_2`, y con un solo peldaño el 100 % de las series encontró padre con soporte. Un ejemplo de escalera completa para una serie hipotética `EMEA|ES|MAD|Consumer|Antivirus|SKU|1Y|1Y-3dev|B1|B1a`:

```
peldaño 0  (propuesto)  EMEA|ES|MAD|Consumer|Antivirus|SKU|1Y|1Y-3dev|B1|B1a   celda mandatory
peldaño 1  −band_level_2   …|B1|*        (la sub-banda es lo que menos separa)
peldaño 2  −term_level_2   …|1Y|*|B1|*
peldaño 3  −product_level_2 …|Consumer|*|SKU|1Y|*|B1|*
peldaño 4  −regional_level_3 EMEA|ES|*|…
…
peldaño 10 *|*|*|*|*|*|*|*|*|*   el total (nadie debería llegar)
```

Cada peldaño se registra en `parent_ladder` (serie × peldaño: dims colapsadas, padre, n, tasa, elegido). La credibilidad encoge hacia el primer peldaño con n ≥ 30.

---

## 8 · Propuesta de orden de trabajo

1. **Decidir tres cosas de doctrina** (son decisiones tuyas, no de código): (a) ¿el campeón gobierna el forecast puntual o solo las bandas? (§3.1); (b) ¿la referencia actual se congela como "salida del legacy" y se acepta que cambie al corregir los defectos, con un test lógico por corrección?; (c) ¿k estimado por padre, o fijo?
2. **Fase 1 RUN** (`run_rate_series.py`, `run_rate_support_repair.py`) con las correcciones §3.3 y §3.4, Wilson, y las dos `se`. Tests unitarios con un raw de mano donde la escalera se comprueba a ojo (como en §7).
3. **Fase 1 ANALYSIS** (`analysis_rate_diagnostics.py`): contrafactual + descomposición Kitagawa (los dos términos), η² → `decision_eta2`, φ, cascada.
4. **Fase 2** con la credibilidad del uplift real y los ejes mudos aplicados; `newcust` a config.
5. **Fase 4 ANALYSIS**: un solo juez → `decision_technique`; bandas normalizadas → `decision_error_bands` hasta `max_forecast_horizon`.
6. **Fase 3 + 4 RUN**: ensamblaje que lee las tres tablas de decisión; bandas con suma-en-pool / cuadratura-entre-pools; check de monotonía en h.
7. Eliminar `fase_pre`, los alias legacy de config y `sff_v2/` del pipeline; regenerar la referencia como "salida de v3"; prompts y ASUNCIONES/HANDOVER.

Cada paso cierra con: test unitario nuevo en verde, `test_pipeline.py` en verde (lógica), y la diferencia con la referencia **explicada** número a número antes de regenerarla.
