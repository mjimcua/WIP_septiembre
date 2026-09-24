# EL INFORME — qué cuenta cada capítulo y cómo leerlo

`run_analysis` termina escribiendo `<outdir>/informe/informe.md` con nueve figuras al lado.
Es el producto para quien no va a abrir una tabla: un director, un responsable de
región, alguien de finanzas. Este documento explica qué hay en cada capítulo, con qué
evidencia se escribe y cómo se lee, con los ejemplos del dataset sintético (una cartera
de $2,3M de pipeline y 30 series; en Kamelot las cifras son 300 veces mayores, la forma
es la misma).

## Las tres reglas del informe

1. **La pirámide.** Primero la respuesta (los tres números y las tres decisiones), después
   la evidencia, capítulo a capítulo. Quien lea solo la portada sabe lo que tiene que saber.
2. **Ninguna cifra sin unidad, referencia y lectura.** Cada métrica se explica la primera
   vez que aparece, con una nota `>` que dice qué es, frente a qué se compara y qué es
   mucho y qué es poco. La tabla completa está en el anexo B y en `sff_metric_legend`.
3. **Los títulos de las figuras afirman el hallazgo.** No "perfil estacional por mes" sino
   "los efectos de mes no son materiales: el nivel reciente predice mejor que la forma anual".

## Portada · los tres números y las tres decisiones

**Qué dice.** Cuánto cierra este año (ya renovado + previsto, con y sin la maduración de
las señales), la banda en dólares y en % del total frente a la promesa de ±5 %, y cuánto
se prevé para el año siguiente sobre qué pipeline (cuánto de ella existe hoy). Después,
tres decisiones sacadas de `top_movers` y `signal_alerts`: dónde defender (la mayor caída
prevista de tasa en dólares), dónde recuperar (la mayor bolsa de señal negativa), dónde
vigilar (la alerta de nivel más fuerte), más la advertencia de comunicar la banda total.

**Ejemplo (sintético).** "2026 cierra en $422k si nada cambia: $250k ya renovados en 7
meses cerrados y $172k previstos para los 5 que quedan. La banda es −$5k / +$11k (−1,2 % /
+2,7 %). 2027: $461k previstos sobre una pipeline de $635k, de la que el 0 % son contratos
que existen hoy." Y las decisiones: "Defender EU·A·web: la tasa prevista cae 3,3 pp frente
a los últimos tres meses cerrados; son $7k sobre 12 meses de pipeline."

**Figura 00.** Barras mes a mes con la banda del 90 % y la línea del forecast ajustado por
maduración de señales.

## 1 · La pipeline: qué vence y cuánto de ello es firme

**Evidencia.** `horizon_report_total` (pipeline por mes y origen) y `business_summary`.
**Lectura.** El % de la pipeline que son contratos reales frente a renovaciones previstas
(proyectada) y adquisición futura (simulada). Cuanto más lejos el mes, menos firme: el
forecast sobre pipeline proyectada o simulada es un forecast sobre un forecast.
**Figura 01.** Barras apiladas por origen; el título dice desde qué mes el forecast se
apoya en lo que aún no ha ocurrido.

## 2 · El ruido: qué parte del dinero se puede predecir bien

**Evidencia.** `dial_buckets` (antes de prestar) y `series_card` / `risk_levels` (después de
la escalera). **Métricas explicadas:** error binomial, nivel de riesgo.
**Lectura.** "El 90 % del dinero está en series con más de 271 contratos al mes (±5 pp o
mejor por puro muestreo)"; "después de la escalera, el 92 % se predice con precisión
propia". El resto es dinero prestado (B, C), con señal y sin pool (S) o sin historia (D).
**Figura 02.** Dinero por nivel, con el % del total y el error típico de un mes.
**Y entonces.** Donde el dinero está en B/C/S, invertir en datos estrecha la banda; donde
está en A, el forecast es un compromiso y se gestiona por desviación.

## 3 · La composición: ¿se mueve la tasa por comportamiento o por cartera?

**Evidencia.** `mix_shift` (Kitagawa por celda y mes) y `mandatory_only_cost`.
**Métrica explicada:** composición (referencia: por encima del 30 % la tasa agregada
engaña).
**Lectura.** "El 7 % del movimiento mensual de las tasas es composición; predecir con las
mandatory solas habría costado $11k en los últimos meses." En Kamelot fue el 33 %: ahí el
KPI regional sube y baja sin que nadie cambie.
**Figura 03.** Para las celdas que más se mueven, cuánto es comportamiento y cuánto mezcla.

## 4 · La estación: ¿hay forma anual en la tasa?

**Evidencia.** `decision_estacionalidad` (el benchmark sobre las series grandes neutras).
**Métricas explicadas:** φ, amplitud estacional.
**Lectura.** El veredicto para la cartera y, por serie, φ, amplitud, si los meses extremos
se repiten entre años, y si la forma mejora al nivel reciente a uno y a seis meses. En el
sintético: una serie estacional (amplitud 11,8 pp, consistente, la forma mejora un 61 % a
seis meses) y tres que no lo son aunque tengan amplitudes de 4-7 pp (no consistentes, o
la forma empeora la predicción).
**Figura 04.** Efectos de mes de las cinco series mayores; la banda gris de ±1 pp es el
ruido.
**Y entonces.** Técnicas con efecto de mes solo donde el veredicto lo permite; nivel
reciente en el resto.

## 5 · La precisión: cuánto nos equivocamos y cuánto de ello es azar

**Evidencia.** `backtest_holdout` (por pool), `backtest_holdout_agg` (el total),
`pipeline_summary` (las bandas). **Métricas explicadas:** unidad binomial, banda total,
sesgo.
**Lectura.** "A un mes vista nos equivocamos 2,5 pp por pool; el azar explica 1,9. Sesgo
−0,3 pp. El 89 % de las predicciones cayó dentro de la banda del 90 %. El error del total
fue 1,7 pp de media y 3,3 en el peor mes." Y la banda que se promete: −2,1 % / +6,0 %, de
la que la parte idiosincrática es 1,5 % y la común −1,4 % / +5,7 %; suelo ±0,7 %; peor caso
±10,1 %.
**Figura 05.** Tasa agregada real contra la prevista en los meses de examen.
**Y entonces.** La banda idiosincrática sola sería engañosamente estrecha; la común es la
que protege. Si el error realizado del total cae dentro de la banda total, la banda es
honesta.

## 6 · El riesgo que entra: qué cambiará antes del vencimiento

**Evidencia.** `signal_adjustment`, `signal_alerts`, `forecast_by_region`, `top_movers`.
**Métricas explicadas:** maduración pendiente, dinero disputable.
**Lectura.** Cuánto vale la maduración de las señales que aún no han aparecido (en $ y en %
del forecast), cuántas alertas de nivel y de tendencia hay, y por región cuánto del dinero
es firme (nivel A) y cuánto está en series con señal.
**Figuras 06 y 07.** Regiones (precisión propia vs señal, con forecast y banda) y los top
movers ordenados por dinero.
**Y entonces.** La lista de acciones del mes: defender, recuperar, vigilar, revisar precio.

## 7 · Frente a la hoja de cálculo

**Evidencia.** `baseline_summary`.
**Lectura.** Cuánto da la previsión de hoja (tasa en dólares de los últimos N meses por
grupo × pipeline) respecto al framework, y cuánto se equivocó cada variante a uno y a
cuatro meses en los últimos doce.
**Figura 08.** Error de la hoja por grano y ventana.
**Y entonces.** Si la hoja acierta igual, el framework aporta banda y trazabilidad; si
acierta peor, aporta también el número.

## 8 · Precio y churn: ¿el descuento es un driver?

**Evidencia.** `discount_churn_bucket`, `discount_churn_state`, `discount_churn_adjusted`,
`discount_churn_importance`. **Métricas explicadas:** tasa estandarizada, importancia
relativa.
**Lectura.** La diferencia estandarizada entre tramos de descuento con la composición de
celdas fijada; el mismo contraste dentro de los clientes sin señal y dentro de los que no
instalaron; los efectos ajustados; y qué grupo de variables (señales, celda, descuento)
pierde más R² al quitarlo. En el sintético: los estados de señal explican 0,59 de R² y el
descuento 0,00; dentro de los neutros el tramo con descuento renueva +5 pp (ahí el
sintético lo construye así), y no hay contraste posible en los estados con señal.
**Figura 09.** Tasa por tramo dentro de cada estado: si las barras de un mismo color se
parecen, el descuento no es el driver en ese estado.
**Y entonces.** Evidencia descriptiva, no experimento; pero si las señales explican diez
veces más que el descuento, la retención empieza por la instalación y el uso.

## Anexo

A · Las fichas de las cinco series con más dinero (seis paneles cada una: tasa con banda
binomial, unidades, mes × año, examen, Kitagawa de su celda, forecast por origen).
B · La leyenda de todas las métricas. C · Las tablas producto. D · Las debilidades
declaradas y su remedio (examen corto, bandas de familia, banda común con pocos puntos,
maduración aproximada, tope de horizonte, adquisición simulada con dimensiones del
renovador).

## Cómo se extiende

Cada capítulo es una función `chapter_*` en `informe.py` que recibe `results` y escribe
prosa, figura y tabla a través de `Report` (`h`, `p`, `legend`, `figure`, `table`). Una
métrica nueva se añade a `LEGEND` y se invoca con `report.legend("nombre")` donde aparezca.
