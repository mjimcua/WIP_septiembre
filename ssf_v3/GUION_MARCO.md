# EL GUION DEL FRAMEWORK — de qué va, en el orden en que se piensa

Este es el marco. Cada fase del código existe porque responde a un paso de este guion; lo
que no responde a ningún paso, sobra.

## 1 · El objeto: una pipeline conocida y un rendimiento por proyectar

Tenemos una **pipeline**: los clientes que van a vencer en cada mes futuro, conocidos con
antelación (un año para los contratos anuales; los de dos y tres años que vencen en
2026-2027 ya existen). De cada grupo de clientes sabemos qué hizo en el pasado; lo que
hay que proyectar es qué hará, aprendiendo del pasado y sobre todo del pasado reciente.

Lo modelamos como un **valor esperado**: renovado $ = pipeline $ × probabilidad de renovar ×
revalorización. La probabilidad es la tasa de renovación del grupo; la revalorización
(uplift) depende del descuento y de las subidas de precio.

## 2 · Reportar no es predecir

Una región, un producto, contratos de un año, clientes no dormidos: vencieron 5,
renovaron 3. Como dato de reporting, ese 60 % es perfecto: cuenta exactamente lo que
pasó. Como predicción para el mes que viene, con otros 5 clientes, es una trampa: con
n = 5 el resultado puede ser cualquiera entre 1 y 5 sin que nada haya cambiado. Predecir
exige una **banda de confianza**, porque hay variabilidad, ruido, cambios de nivel y
composición de la cartera.

## 3 · Primero, el ruido irreducible: el binomial

Antes de buscar nada, calculamos cuánto se mueve una tasa por puro azar de muestreo:
√(p(1−p)/n). Es el error que ninguna técnica puede bajar, y es la primera estimación
del error que vamos a tener. Con él describimos la pipeline (cuánto dinero está en
unidades de 5, de 50, de 500 clientes: el dial 30 / 271 / 752), el riesgo de cada
predicción, y decidimos dónde hace falta ayuda.

*Código*: `binomial_reference.py`, `fact_fu` (columnas se_pp_max / moe_pp_max / moe_usd_max), `dial_buckets`, `fu_profile` (fases 0 y 1.1).

## 4 · Segmentar para ganar homogeneidad, agrupar para recuperar soporte

Segmentamos por las dimensiones que separan comportamiento (región, producto, tipo de
compra, plazo, banda…): cada serie es más homogénea, pero más pequeña, y el ruido
binomial sube. Para bajarlo, la **escalera**: la serie pequeña toma prestada la tasa del
grupo más parecido que tenga soporte (30 clientes como mínimo para que un grupo hable;
271 para hablar solo), y se cree a sí misma en proporción a lo que tiene (credibilidad).
El orden en que se dejan caer dimensiones lo decide cuánto separa cada una (η²,
pérdida secuencial), de menos a más.

*Código*: `run_rate_series.py`, `analysis_dimensions.py` (separación, orden de colapso),
`run_support_ladder.py` (fases 1.1-1.3). Salida: `series_card`, niveles de riesgo.

## 5 · Las señales: sacar a los clientes en situación extrema

Las banderas timevarying (dormido, cancelación anunciada, no instalado, autorenovación)
extraen de cada cohorte el subconjunto con mucho o poco riesgo. Los que quedan son más
homogéneos, y los extraídos se predicen con los suyos: los negativos nunca se mezclan con
los positivos ni con los neutros. Es la puerta de entrada de los modelos predictivos al
forecast, y cada bandera se audita sola (su tasa realizada mes a mes).

*Código*: el signo en `run_rate_series.py` y la escalera por signo en
`run_support_ladder.py`; `timevarying_calibration` (fase 1.4).

## 6 · La composición: contarla, no buscarla

Cuando cambia el peso de los grupos que vencen cada mes, la tasa agregada se mueve
aunque nadie cambie de comportamiento; el caso extremo es la paradoja de Simpson. **No la
buscamos**: la contamos. Dos cuentas por celda mandatory: cuánto del movimiento mes a mes
es composición y cuánto comportamiento (Kitagawa), y cuánto estaríamos sobre o
infraestimando si predijéramos con las mandatory solas (una tasa por celda) en vez de con
las series segmentadas, en dólares y contra lo que pasó.

*Código*: `run_composition_analysis` (fase 1.4, tras la escalera). Salida:
`mix_shift`, `mandatory_only_cost`. Nada aguas abajo decide con esto.

## 7 · La estacionalidad: decidirla una vez, donde hay potencia

La composición puede parecer estacionalidad y no serlo (vence más gente en unos meses; no
renueva más). Y una técnica de series temporales siempre "encuentra" estación. Por eso se
decide **una vez para toda la cartera**, en las series grandes neutras (≥ 271 clientes todos
los meses, todas las dimensiones fijas: lo que se mueva ahí es comportamiento): amplitud
en puntos, consistencia entre años, y la prueba que decide: ¿la forma del calendario
mejora a "lo que pasó el último trimestre" a 1 y a 6 meses vista? Si no hay estación
material ahí, no se busca en el resto.

*Código*: `analysis_seasonality_benchmark.py` (fase 2). Salida: `decision_estacionalidad`.

## 8 · El backtest: elegir la técnica y medir la banda

Con todo lo anterior sabido, se prueba. Dos baterías sobre los últimos seis meses
cerrados: predecir el mes siguiente con datos hasta el anterior (h=1) y predecir un mes
con datos hasta seis antes (h=6). El retador es el último trimestre; las técnicas son de
nivel (media móvil, suavizado, nivel con pendiente amortiguada) y, solo donde el
benchmark lo permitió, nivel con efecto de mes. Si la composición es fuerte y el negocio
cambia de nivel, ganan las técnicas de horizonte reciente, y eso es correcto. Los meses
de examen no se usan para decidir; solo para comprobar. De los errores salen las bandas:
la de cada pool y la de la cartera entera (los pools que se equivocan juntos).

*Código*: `analysis_backtest.py` (fase 3). Salida: `decision_technique`, bandas, hold-out.

## 8b · Las señales maduran: la foto de hoy no es la del vencimiento

`softcancel` aparece justo después de una renovación y otra vez cerca del vencimiento;
`dormant` aparece en cualquier momento y solo crece. Un mes lejano tiene hoy menos
señales de las que tendrá al vencer, y las series con señal renuevan mucho peor. Se
compara la composición de cada celda (neutros / cada señal) en los meses cerrados —la
final— con la foto de los meses futuros; lo que falta por aparecer se valora en dólares
y se presenta como forecast ajustado, junto a la foto. Cada run guarda la foto: con
meses suficientes, la curva de maduración por distancia se mide y sustituye a la
aproximación. Y dos alertas: meses que ya van por encima de su proporción final, y
señales cuya proporción final crece mes a mes.

*Código*: `analysis_signal_maturation.py` (fase 5.9). Salida: `signal_adjustment`,
`signal_alerts`, `forecast_ajustado_usd`.

## 9 · La revalorización y el ensamblaje

El uplift por celda (descuento, cliente nuevo, precio reciente) multiplica. Cada fila
futura recibe tasa, uplift y banda; la pipeline que aún no existe (renovaciones y
adquisición de los meses de proyección) se etiqueta como proyectada o simulada. Y las
respuestas: cómo acaba el año, cuál es la pipeline del que viene, cómo acaba.

*Código*: `run_uplift.py`, `run_forecast_assembly.py` (fases 4 y 5). Salida:
`forecast_detail`, `pipeline_summary`, `business_summary`, `baseline_summary`.

## Cómo queda el orden de ejecución

0 raw y calendario · 1.1 series y ruido · 1.2 qué separa · 1.3 escalera · 1.4 composición
y señales (cuenta) · 2 benchmark de estacionalidad (decisión) · 3 backtest · 4 uplift · 5
ensamblaje y respuestas · validación.

## Lo que se ha simplificado para que el código sea este guion y no más

- Sin diagnósticos individuales de dinámica por pool (φ, perfil, tendencia, cambio de
  nivel, estación del volumen): la estacionalidad es una decisión del benchmark, no de
  cada serie.
- Sin técnicas que encuentren estación por su cuenta: nivel, Theta y Holt amortiguado siempre;
  las dos estacionales (T15, Holt-Winters) solo donde el benchmark lo declaró.
- Sin búsqueda de casos de Simpson: la composición se cuenta (Kitagawa) y se valora en
  dólares (coste de la vista solo-mandatory).
- El calendario se decide desde el mes en curso; el mes anterior no está cerrado.
