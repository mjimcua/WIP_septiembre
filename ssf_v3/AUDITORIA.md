# AUDITORÍA DE UNA FORECAST SERIES — Power BI y notebook

**Confirmación**: sí, está diseñado para eso. Cada tabla lleva las claves que hacen falta
para que seleccionar una serie filtre todo lo demás. Desde esta versión las claves se
estampan automáticamente al escribir (`Config.stamp_derived_keys`): toda tabla que tenga
`fs_id` lleva `fs_key`; `id_estimacion` → `estimacion_key`; `uplift_cell_id` →
`uplift_cell_key`; `celda_id` → `celda_key`. Las claves son hashes cortos (md5 12 hex) de
los ids; los ids siguen ahí porque son legibles.

## La cadena de filtrado

Una serie no se explica sola: toma la tasa de su **id de estimación** (ella misma o el
pariente elegido), el uplift de sus **celdas de uplift** (una por combinación de extras de
revalorización) y vive en una **celda mandatory**. Cuatro claves, cuatro saltos:

```
series_card (1 fila por serie)  ──fs_key──▶  parent_ladder, support_chain, decision_support,
   │                                         fact_fu_gaps, key_bridge, forecast_detail,
   │                                         forecast_bands, fu_extended
   ├──estimacion_key──▶  pool_reference (1 fila por id)  ──▶  decision_technique,
   │                                                             decision_error_bands,
   │                                                             backtest_holdout, backtest_pred
   ├──celda_key──▶  mandatory_only_cost, mix_shift
   └──(vía key_bridge)──uplift_cell_key──▶  decision_uplift, uplift_chain
```

## Modelo en Power BI

Tablas de dimensión (una fila por clave) y relaciones:

| Dimensión | Clave | Hechos que filtra (1 → *) |
|---|---|---|
| `sff_series_card` | `fs_key` | `sff_parent_ladder`, `sff_support_chain`, `sff_decision_support`, `sff_fact_fu_gaps`, `sff_key_bridge`, `sff_forecast_detail`, `sff_forecast_bands`, `sff_fu_extended` |
| `sff_pool_reference` | `estimacion_key` | `sff_decision_technique`, `sff_decision_error_bands`, `sff_backtest_holdout`, `sff_backtest_pred`, y **`sff_series_card`** (* → 1) |
| `sff_decision_uplift` | `uplift_cell_key` | `sff_uplift_chain`, `sff_key_bridge`, `sff_forecast_detail` |
| celda (tabla calculada `DISTINCT(sff_series_card[celda_key])` o `sff_risk_levels` no vale: crea `dim_celda`) | `celda_key` | `sff_mandatory_only_cost`, `sff_mix_shift`, `sff_series_card` |

Para que seleccionar una serie filtre las tablas del id de estimación y del uplift, las
relaciones `series_card → pool_reference` y `key_bridge → decision_uplift` deben ser
**bidireccionales** (o usar `CROSSFILTER` en las medidas). Es la única configuración que
no es la de por defecto.

Página de auditoría recomendada (un slicer sobre `series_card[fs_id]`):
1. Tarjeta: ruta, universo, signo, n_propio, meses, tasa_propia ± error, nivel de riesgo.
2. Tabla `parent_ladder` ordenada por `peldano`, con `elegido` en negrita.
3. Tarjeta: `id_estimacion`, `peldano`, `k`, `z`, `tasa_estimada`, `se_estimacion_pp`, `se_prediccion_pp`.
4. `pool_reference` (una fila): φ, gate, perfil estacional, tendencia.
5. `decision_technique` (una fila) + `decision_error_bands` (línea por h).
6. `backtest_holdout`: gráfico real vs predicho por mes, con banda.
7. `decision_uplift` de sus celdas.
8. `forecast_detail` + `forecast_bands`: barras mensuales de `esperado_usd` con la banda, `simulada` sombreado.

## En notebook: la ficha por clave

`sheet(key, configuration)` acepta cualquiera de las claves del modelo (`fs_key`, `estimacion_key`, `celda_key`, `uplift_cell_key`, `fu_key`, `fu_comb_key`) o un `fs_id`, resuelve a la serie (o a la serie con más dinero del grupo, listando los miembros) y devuelve tablas filtradas, resumen en palabras y la figura. Las claves son enteros (bigint = primeros 12 hex de MD5 del id), los mismos que usa el BI.

## En notebook: la auditoría

```python
from audit_series import audit_series
audit = audit_series("EU|0|0|0|0|A|tele", configuration)          # lee las tablas sff_*
audit = audit_series("EU|0|0|0|0|A|tele", results=results)        # desde el dict de run_analysis
audit["parent_ladder"]                                            # cada tabla filtrada
```

Imprime la historia en el orden en que se construyó (historia → escalera → estimación →
dinámica → técnica → bandas → hold-out → uplift → forecast). El ejemplo completo sobre el
sintético está en `AUDITORIA_EJEMPLO_SINTETICO.txt`. Es el mismo camino que sigue el BI:
si aquí se puede contar, allí se puede filtrar.

## Qué mirar al auditar (los tres "¿por qué?")

- **¿Por qué esta tasa?** `parent_ladder` dice de quién viene y por qué no de más cerca
  (los peldaños anteriores no llegaban al suelo); `z` dice cuánto pesa la propia.
- **¿Por qué esta técnica?** `decision_technique`: si es `retador`, ninguna técnica ganó
  a la media por el margen; si es `campeon`, `err_norm_medio` vs `retador_err_norm` es
  cuánto gana, y `pool_reference` dice qué motor había (φ, estacional, tendencia).
- **¿Por qué esta banda?** `decision_error_bands`: `propia` (medida en este id) o
  `familia` (prestada de la técnica); los cuantiles con signo dicen hacia dónde se
  equivoca; y en `forecast_bands` la banda de cada fila añade el muestreo de la propia
  fila (por eso una serie de 12 unidades tiene ±20 pp aunque su pool tenga ±3).
