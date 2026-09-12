# Catálogo de tablas — orden de escritura del main y el análisis de cada una

*Una fila por `cfg.write`, en el orden exacto de ejecución. Nombre físico con prefijo `sff_`. Grano entre paréntesis.*

## FASE 0 — contrato, carga, referencia

| # | Tabla | Grano | El análisis |
|---|---|---|---|
| 1 | `fact_fu` | serie × mes | **El raw agregado al grano de la tasa, intocado.** Base de toda tasa: `Σren/Σtr` por cualquier corte. Sus ceros son tuyos, no del framework. |
| 2 | `fact_fine` | fila del raw | **El ancla.** Todo informe a nivel raw parte de aquí (dinero y unidades SIEMPRE de esta tabla). Une al puente por `fu_comb_key`. |
| 3 | `lookup_fu` | fu | Traductor id↔key para usar las claves fuera del framework (queries a mano, auditoría). |
| 4 | `lookup_comb` | combinación | Ídem para las combinaciones de revalorización. |
| 5 | `fu_summary` | fu (serie×mes) | **La referencia inmutable**: soporte y error binomial peor-caso por celda-mes. Análisis: el dial de tolerancia (% del $ predecible a ±τ pp), la foto binomial en buckets de moe, el scatter soporte vs $ en riesgo con la línea del suelo. Todo lo posterior se mide CONTRA esto. |

## FASE 1 — rama renovación

| # | Tabla | Grano | El análisis |
|---|---|---|---|
| 6 | `fs_summary` | serie | **La lista de la compra de la reparación**: filtra `n_avg<30`, ordena por `moe_usd` desc → a quién rescatar primero, en $. También salud temporal (meses, huecos). |
| 7 | `fact_fu_gaps` | fu imputada | Los meses que NO existían en tu extracto, confesados (`sintetica=1`). Análisis: puntos huecos sobre las líneas de serie; auditoría de calidad del extracto por segmento. |
| 8 | `simpson_contrafactual` | celda × mes | **El sueldo del framework en $**: error del método plano vs segmentado, walk-forward. Análisis: Σ`ahorro_usd` (el titular), y por celda: dónde el mix miente más. |
| 9 | `support_chain` | serie × etapa | **El waterfall**: $ bajo el suelo por etapa (0_raw→L1→L2→shrink) y el % que nunca necesitó nada. Análisis: barras por etapa; por serie, la película de su reparación (`id_efectivo`, `n_efectivo`, `actuo`). |
| 10 | `diag_dinamica` | pool L2 | **El censo de comportamientos**: gate (soporte/temporal/estacional/tendencia/apto), amplitud y pendiente vs su cota, y **phi** (¿hay motor?). Análisis: ranking por phi desc = dónde pasa algo de verdad; distribución de gates = qué técnicas harán falta. |

## FASE 2 — rama revalorización

| # | Tabla | Grano | El análisis |
|---|---|---|---|
| 11 | `uplift_chain` | celda uplift × etapa | La cadena del valor: uplift fino → padre (mismo punto de partida) → shrink. Análisis: distribución de `uplift_final` por `discount_interval`/`newcust` (¿quién aterriza, quién revaloriza?); comparar etapa 0 vs 2 = cuánto corrigió la credibilidad. |

## FASE 3 — ensamblaje

| # | Tabla | Grano | El análisis |
|---|---|---|---|
| 12 | `key_bridge` | fu × comb | **El pegamento.** No se analiza: se une. Una relación desde el raw y llegas a serie, pool, celda de uplift, celda mandatory, universo y ruta. |
| 13 | `forecast_detail` | fila futura | **EL forecast**: `esperado_usd = pipeline × tasa × uplift`, fila a fila, con etiqueta semántica. Análisis: el número por cualquier corte del raw; tasa y uplift aplicados auditables por fila; $ por etiqueta (residuo vs genuino). |

## FASE 4 — el juez y la fiabilidad

| # | Tabla | Grano | El análisis |
|---|---|---|---|
| 14 | `backtest_pred` | pool × técnica × h | La competición en formato largo. Análisis: leaderboard de técnicas por horizonte; dónde el campeón bate a los retadores T0/T2 y por cuánto. |
| 15 | `forecast_seleccion` | pool | El palmarés: técnica elegida por serie con su error de backtest. Análisis: censo de campeones (¿domina la estación? ¿la recencia?); series donde ganó el retador barato = series sin señal explotable. |
| 16 | `rolling_next_month` | pool × mes × técnica × h | **La otra herramienta**: origen móvil, error real mes a mes con `dentro_de_cota`. Análisis: fiabilidad por segmento y horizonte; meses fuera de cota = noticias, no ruido. |
| 17 | `rolling_nm_resumen` | técnica × h | El titular ejecutivo: "a h=1, error X pp, WAPE Y%, Z% dentro de su cota". El relevo de campeones por horizonte, en una tabla. |
| 18 | `dim_tecnica` | técnica | Maestra del catálogo (familia, elegibilidad). Dimensión para todo lo anterior. |
| 19 | `backtest_pred_fu` | fu × técnica × h | El backtest estampado por FU miembro (P5), con error en $ propio. Análisis: ¿qué FUs concretas sufren más con cada técnica? El puente entre el juez y el raw. |
| 20 | `forecast_pred_fu` | fu futura × técnica | Todas las técnicas aplicadas a cada FU futura con su uplift y su $ — sin error (no hay verdad aún). Análisis: sensibilidad del forecast a la elección de técnica, por celda. |

## FASE P — introducción (runner aparte, no en main)

| # | Tabla | Grano | El análisis |
|---|---|---|---|
| P1 | `simpson_showcase` | celda | Ranking de escaparates Simpson por dramatismo visual (giro de mix, pureza). Análisis: elegir LA celda para la slide de apertura. |
| P2 | `simpson_showcase_series` | celda × mes | Las cuatro líneas listas para pintar: share, tasa activa, tasa resto, agregado. |

---

**El arco de lectura** (la historia que cuentan en orden): *referencia* (5) → *quién necesita ayuda* (6) → *cuánto cuesta la mentira del mix* (8) → *cuánto rescató la maquinaria* (9) → *qué comportamiento tiene cada pool* (10) → *cuánto vale lo que renueva* (11) → **el forecast** (13) → *con qué técnica y qué fiabilidad demostrada* (15-17).
