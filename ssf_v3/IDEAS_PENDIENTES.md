# IDEAS PENDIENTES — acordadas, especificadas, no implementadas

## 1 · Comparativa 2026 vs 2027, por región, con el potencial mejor y peor (foco en 2027)

**Pregunta que responde.** Cómo ha ido 2026, cómo irá 2027, cuál es la diferencia y de
qué se compone, y cuál es el mejor y el peor resultado plausible de cada región en cada
año. Es la página que un responsable de región llevaría a una reunión de plan.

**Tabla `comparativa_anual`** (una fila por región y una para el total):

| Grupo de columnas | Columnas | De dónde salen |
|---|---|---|
| 2026 | `renovado_real_2026`, `forecast_resto_2026`, `total_2026`, `banda_low/high_2026` | `business_summary`, `forecast_by_region` |
| 2027 | `pipeline_2027` (real / proyectada / simulada), `forecast_2027`, `forecast_ajustado_2027`, `banda_low/high_2027` | `business_summary`, `horizon_report_total`, `signal_adjustment` |
| Diferencia | `delta_usd`, `delta_pct` | 2027 − 2026 |
| Descomposición de la diferencia | `por_volumen_usd` (cambia lo que vence), `por_tasa_usd` (cambia la probabilidad), `por_precio_usd` (cambia el uplift), `por_composicion_usd` (cambia la mezcla de series) | Kitagawa entre los dos años: Δ = Σ Δpipeline·tasa·uplift + Σ pipeline·Δtasa·uplift + Σ pipeline·tasa·Δuplift + término de mezcla |
| Mejor potencial 2027 | `mejor_2027` = forecast + banda alta + dinero disputable de señales negativas (cota superior de recuperación) + oportunidad de precio (celdas bajo el uplift medio) | `forecast_by_region`, `top_movers` (`senal_negativa`, `precio`) |
| Peor potencial 2027 | `peor_2027` = forecast + banda baja + ajuste por maduración de señales + pérdida si la adquisición simulada no llega (pipeline simulada × tasa × uplift) | `signal_adjustment`, `horizon_report_total` |
| Lectura | `situacion`: mejora / estable / deterioro, según si `delta_pct` supera la banda | — |

**Dos matices para que sea honesto.** El mejor y el peor potencial no son simétricos ni
probabilísticos: el mejor es una cota (todo lo recuperable, recuperado); el peor es un
escenario (nada madura bien, la adquisición no llega). Se presentan como "hasta" y "no
menos de si…", no como intervalos. Y la descomposición de la diferencia usa Kitagawa
entre dos años completos, con la mezcla de series como cuarto término, para que
"2027 cae un 4 %" tenga respuesta: cuánto por volumen, cuánto por tasa, cuánto por precio.

**Informe.** Capítulo 9, "2026 frente a 2027, por región": una figura de barras
emparejadas (2026 total, 2027 forecast) con el rango mejor/peor de 2027 como segmento
vertical, una por región, ordenadas por dinero; la tabla con la descomposición; y para
cada región una frase generada: "DACH: 2027 cae $1,2M (−6 %), de los que $0,9M son
volumen (vence menos) y $0,3M tasa; mejor potencial $21,4M si se recupera la señal
negativa; peor $18,1M si la maduración y la adquisición fallan".

**Lo que hace falta antes.** El mapa de transición de reentradas (precio tope, idea 2),
porque sin él el 2027 sobreestima el precio de los renovados; y `forecast_ajustado_usd`
ya existe para el peor potencial.

## 2 · Reentradas: lo que queda tras el uplift por contrato

El precio de las reentradas ya está resuelto por la vía de contrato (la `proyectada`
reentra con descuento 0; su uplift es solo la subida de lista). Queda el cambio de las
otras dimensiones al reentrar: `net_new → False` (ya no es primera renovación) y señales
neutras en la `proyectada`; `net_new → True` en la `simulada`. Pendiente de cómo marca el
raw la segunda renovación. Y tres cosas de la vía de contrato por confirmar con Kamelot:
que la vía estadística se estime solo con descuento nulo (`statistical_uplift_from_unknown_only`),
el resultado de `uplift_contract_check` por autorenovación sí/no, y el calendario de
subidas para `price_increase_by_period`.

## 3 · Curva de maduración medida

Cuando `signal_snapshot` tenga seis meses de fotos, la maduración pendiente se mide por
distancia (fase B de `ETAPA_MADURACION_SENALES.md`) y sustituye a la aproximación.

## 4 · Correcciones detectadas en el mapa de salida (no hechas)

- `TABLE_KIND` usa cuatro nombres que no existen en el registro (`forecast_units`,
  `fine_table`, `lookup_forecast_units`, `risk_levels_report`).
- La validación del raw avisa "role 'entrenamiento' is EMPTY in the raw": comprueba el
  vocabulario nuevo contra los roles en inglés del raw antes de traducirlos.
- `fu_summary` sigue registrada sin escribirse; un mensaje de fase 0 conserva "no_impact".
- El informe debería leer `dim_domains`, `fu_profile`, `tv_calibration`, `risk_levels`,
  `forecast_by_level` y `bench_flags` (con veredicto) en vez de recalcular o ignorarlas.
- Los `[write]` de la consola, a un log aparte.

## 5 · Cuando haya datos de Kamelot

Examen más largo si el extracto lo permite; bandas propias en los pools con 20
predicciones; retrospectiva de la maduración de señales; veredicto de `bench_flags`.
