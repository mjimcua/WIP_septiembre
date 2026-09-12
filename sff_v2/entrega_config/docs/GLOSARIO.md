# GLOSARIO — términos del framework y su equivalente en español

*SFF v2 · vivo desde el 12-sep-2026. Se amplía con cada término que el usuario pregunta. Complementa a DISENO_V2.md (doctrina) y POR_QUE_ESTE_FORECAST.md (motivación). Cada entrada: qué es, cómo pensarlo en español, dónde vive en las tablas o en el código, ejemplo con la configuración del golden (`mandatory=[region]`, `timevarying=[dormant, softcancel, no_instalado, autorenew]`, `extra_renovacion=[product, channel]`, `extra_revalorizacion=[discount, newcust]`).*

*Convención: los nombres de columnas y valores persistidos siguen en español (`celda`, `gu`, `tasa`, `etapa`…); los identificadores de código en inglés. Cuando un término tiene dos nombres, se dan ambos.*

---

## 1 · La cadena de identidad (rama tasa)

Tres niveles de agrupación, de fino a grueso. Un nivel está contenido en el siguiente: **una FU pertenece a exactamente una serie, y una serie a exactamente una celda.**

```
celda mandatory        EU
  └── forecast series  EU|0|0|0|0|A|web           (una por combinación del grano tasa)
        └── forecast unit  EU|0|0|0|0|A|web|2026-01   (una por serie × mes)
```

### Forecast unit (FU)
- **Qué es**: una observación. En un mes concreto, en una combinación concreta de dimensiones, vencían n unidades y renovaron k. Es la fila atómica de la rama tasa.
- **En español**: *unidad de forecast*; la casilla serie × mes.
- **Columnas del id**: `rate_series_columns` + mes. Separador `|`.
- **Dónde vive**: `fu_id`, `fu_key`; una fila de `fact_fu`; la referencia inmutable `fu_summary` (soporte y error binomial peor-caso por FU).
- **Ejemplo**: `EU|0|0|0|0|A|web|2026-01`.

### Forecast series (FS)
- **Qué es**: la serie temporal de FUs de una combinación. Es lo que recibe una tasa estimada, un pool y una técnica de forecast.
- **En español**: *serie de forecast*; la secuencia mensual de una combinación.
- **Columnas del id**: `rate_series_columns` (sin mes).
- **Dónde vive**: `fs_id`, `fs_key`; `fs_summary`, `support_chain`, `parent_ladder`, backtest, `forecast_seleccion`.
- **Ejemplo**: `EU|0|0|0|0|A|web` → 30 FUs, una por mes desde 2024-01.

### Celda mandatory (mandatory cell)
- **Qué es**: el grupo de series que comparten los valores de las dimensiones `business_mandatory_dims` (las que nunca se colapsan en pools). Es el padre natural de toda serie.
- **En español**: *celda*; el segmento de negocio irreducible.
- **Columnas del id**: solo `business_mandatory_dims`.
- **Dónde vive**: `celda` (contrafactual Simpson, cascada de fallback), `celda_id` (`key_bridge`). En código: `mandatory_cell`. En producción son 10 columnas (`tr_regional_level_1..3`, `tr_product_level_1..2`, `tr_origin_type_SKU_based`, `tr_term_level_1..2`, `tr_band_level_1..2`).
- **Ejemplo**: `EU` → todas las series de Europa.

### Celda de uplift (uplift cell)
- **Qué es**: la unidad de estimación del uplift. NO es una serie: el uplift se estima con todos los renovadores de todos los meses juntos, no tiene eje temporal ni backtest por horizonte.
- **En español**: *celda de revalorización*; grupo estático mandatory × extras de precio.
- **Columnas del id**: `uplift_cell_columns` = `business_mandatory_dims` + `extra_revalorizacion`.
- **Dónde vive**: `gu` y `uplift_cell_key` en `uplift_chain`. En código: `uplift_cell`.
- **Ejemplo**: `EU|d40|1`.
- **Aviso de vocabulario**: en el legacy «celda» está sobrecargado (celda mandatory en fase 1/3, celda de uplift en fase 2). En código se usa siempre el nombre completo: `mandatory_cell` o `uplift_cell`, nunca «cell» a secas.

### Grano (grain) → `rate_series_columns`, `uplift_cell_columns`
- **Qué es**: término de modelado dimensional (Kimball): la lista de columnas que identifica una fila de una tabla; el nivel de detalle al que se agrega.
- **En español**: *nivel de detalle*; «qué columnas definen una fila».
- **En código**: se sustituyó por nombres que dicen qué definen: `rate_series_columns` (las columnas que definen una serie de tasa) y `uplift_cell_columns` (las que definen una celda de uplift). Ambas son propiedades derivadas de la taxonomía, nunca escritas a mano:
  - `rate_series_columns` = `mandatory + timevarying + extra_renovacion`
  - `uplift_cell_columns` = `mandatory + extra_revalorizacion`

---

## 2 · Soporte y su reparación

### Soporte (support) y suelo de soporte (support floor)
- **Qué es**: n = unidades del pipeline de una serie (mediana mensual de los meses con vencimientos). Es el denominador del error binomial √(p(1−p)/n). El suelo (`support_floor` = 30) es el n mínimo para que una serie estime su tasa sola: con n=30 y p=0,5 la banda al 90% es ±15 pp.
- **En español**: *soporte* = cuánta evidencia tiene la serie; *suelo* = umbral de admisión, no promesa de calidad.
- **Dónde vive**: `n_avg`, `soporte`, columnas `n_efectivo` en `support_chain`.

### Pool
- **Qué es**: el conjunto de series con el que se **calcula** una tasa cuando una serie sola no llega al suelo. Regla P5/P6: el cálculo se hace con la suma de todas las series del pool (mes a mes, sumando unidades), y el **resultado se estampa en cada miembro**; cada serie conserva su propio pipeline y su propia identidad. El pool es de dónde sale el número, no a qué se aplica.
- **En español**: *grupo de estimación*, *agrupación*, *conjunto de préstamo*. Si una serie tiene 10 unidades y su hermana 20, la tasa se calcula con 30 y se escribe dos veces, una en cada serie.
- **Regla fija**: un pool nunca mezcla celdas mandatory distintas en L1 ni en L2.
- **Dónde vive**: `fs_id_L1`, `fs_id_L2` (el id del pool al que pertenece la serie en cada nivel), `id_efectivo` en `support_chain`.
- **Ejemplo**: las series `EU|1|0|0|0|A|web` (dormant, n=15), `EU|0|1|0|0|A|web` (softcancel, n=12) y `EU|0|0|1|0|A|web` (no_instalado, n=10) forman el pool L1 `EU|SIG=neg|A|web` con n=37, que supera el suelo.

### Las tres estrategias de reparación (L1, L2, L3)
Por orden de coste de información. Se aplican solo a series por debajo del suelo (L1, L2); la credibilidad (L3) se aplica a todas.
- **L1 · agrupar por signo**: las series con timevarying activas del mismo signo (neg/pos) se juntan en un pool `SIG=neg` / `SIG=pos`. Los motivos se pierden, el signo se conserva.
- **L2 · asterisco**: para lo que sigue pequeño sin señal timevarying, se anula la dimensión extra con menor η² (se sustituye su valor por `*`), juntando a las hermanas que solo difieren en ella.
- **L3 · credibilidad**: ver siguiente entrada.

### Credibilidad (credibility shrinkage)
- **Qué es**: la tasa final de una serie es una media ponderada entre su propia tasa (tras L1/L2) y la tasa de su padre: `tasa_final = z·tasa_propia + (1−z)·tasa_padre`, con `z = n/(n+k)` y `k_cred` = 60. Con n=60, z=0,5 (mitad y mitad); con n=600, z=0,91 (casi toda propia); con n=6, z=0,09 (casi toda del padre). El error se combina en cuadratura.
- **En español**: *encoger hacia el padre*, *cuánto te fías de la serie frente a su grupo*. Es la fórmula clásica de Bühlmann en actuarial.
- **Dónde vive**: etapa `3_shrink` en `support_chain` (`id_efectivo = "z=0.43→EU|*"`); `tasa_final`, `se_final`.

### Escalera de padres (parent ladder) y peldaño (rung)
- **Qué es**: la secuencia de padres cada vez más gruesos hacia los que puede encoger una serie. Cada peldaño se construye colapsando una dimensión mandatory más (su valor pasa a `*`). El orden de colapso lo fija `_build_collapse_order`: dentro de una familia `x_level_1/2/3` cae primero el nivel más fino; entre familias, cae primero la que menos separa (menor η²).
- **Primer peldaño que alcanza el suelo**: la serie sube peldaño a peldaño y se queda con el **primer padre cuyo n ≥ suelo**. Es el padre más parecido a la serie que ya tiene evidencia suficiente. Si ninguno llega, se toma el último (el total). Hacia ese padre encoge la credibilidad.
- **En español**: *escalera de padres* = jerarquía de agrupaciones; *peldaño* = un nivel de esa jerarquía; *el primer peldaño que alcanza el suelo* = el padre más cercano con evidencia suficiente.
- **Dónde vive**: tabla `parent_ladder` (serie × peldaño: `peldano`, `dims_colapsadas`, `padre_id`, `n_padre`, `tasa_padre`, `elegido`); `peldanos_padre` en `support_chain`.
- **Ejemplo Kamelot (sep-2026)**: orden de colapso empieza por `tr_band_level_2`; con 1 peldaño (`…|*` en band_level_2) el 100% de las series encontró padre con soporte.
- **Nota**: los peldaños están **por encima** de la celda mandatory (empiezan colapsando una mandatory). La celda mandatory completa no es un peldaño; es el punto de partida.

---

## 3 · Diagnóstico y ensamblaje

### Contrafactual Simpson (Simpson counterfactual)
- **Qué es**: la medida en dólares de cuánto cuesta NO segmentar. Para cada celda mandatory y cada uno de los últimos 6 meses con verdad (t), se calculan dos predicciones usando solo datos ≤ t−1:
  - **plano**: una tasa agregada de toda la celda.
  - **segmentado**: la tasa de cada serie de la celda, recombinada con los **pesos reales** del mes t (legítimo: el pipeline del mes t es dato conocido).
  Ambas se comparan con la tasa real de t. `ahorro = (|err_plano| − |err_seg|) × pipeline$`. Se suma con signo (los meses donde el plano acierta más restan) y se reporta además el % de celdas-mes donde gana el segmentado.
- **En español**: *cuánto dinero se equivoca el método plano de más que el segmentado*; el precio de la mezcla. Es «contrafactual» porque responde a «¿qué error habríamos tenido si no hubiéramos segmentado?».
- **Dónde vive**: tabla `simpson_contrafactual` (`celda`, `mes`, `err_plano_pp`, `err_seg_pp`, `ahorro_usd`).
- **Cifras**: $738.611 (12-ago, con el mes en curso contaminando) → $166.370 (sep, con la doctrina del mes en curso). El segundo es el honesto.
- **Distinto de**: la *búsqueda de casos* (`fase_pre.py`, tablas `simpson_showcase*`), que intentaba encontrar una paradoja visual limpia y no la encontró. Esa pieza es candidata a eliminarse; Simpson se explicará a nivel teórico.

### Cascada de fallback (fallback cascade)
- **Qué es**: en el ensamblaje (fase 3), cada fila futura del pipeline necesita una tasa. Se busca en orden y se anota de dónde salió:
  1. la tasa de **su propia serie** (`tasa_final`) → `tasa_origen = "serie"`;
  2. si la serie no tiene estimación (ruta heuristic: futuro sin historia), la **media de su celda mandatory** → `"celda"`;
  3. si la celda tampoco existe en el histórico, la **media global** → `"global"`.
- **En español**: *cadena de respaldo*, *a qué recurre una fila cuando no tiene tasa propia*. Nunca silenciosa: `tasa_origen` queda en `forecast_detail` y la validación cuenta cuántas filas y cuánto dinero van por cada vía.
- **Dónde vive**: `tasa_origen` en `forecast_detail`; check en `validation_report`; `smoke_multidim.py` exige que ninguna fila caiga a `global`.
- **Distinto de**: la escalera de padres (fase 1, mejora la *estimación* de series con historia) y de los pools (fase 1, de dónde sale el número). La cascada es de fase 3 y trata filas *sin* estimación.

---

## 4 · Herramientas de obra

### EDGE CASES (sección del docstring)
- Equivale a **BORDES** del contrato de cinco secciones (ENTRADA · SALIDA · REGLAS · BORDES · REGISTRO ↔ INPUT · OUTPUT · RULES · EDGE CASES · CONSOLE). Lista los casos límite y qué hace la función en cada uno: entrada vacía, nulo, índice duplicado, columna ausente, qué excepción lanza y con qué diagnóstico.

### Test de caracterización (vs TDD)
- **TDD**: test primero, código después; el test dirige el diseño.
- **Caracterización / regresión** (lo que hace `tests/test_config.py`): el código ya existe; el test fija su comportamiento para que un cambio futuro que lo rompa falle con una frase que diga qué se rompió. Es lo adecuado para un refactor. La puerta de equivalencia es lo mismo a nivel de sistema (golden test). Orden de uso: test de unidad primero, puerta después. Falla el test → contrato roto; pasa el test y falla la puerta → fase rota.
