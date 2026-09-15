# ESTRATEGIA POR REGIÓN — cómo convertir el forecast en una forma de organizarse

La propuesta parte de una tabla que el análisis produce cada mes, `forecast_by_region`
(una fila por región), y la convierte en decisiones. No inventa datos: cada columna de la
tabla es una palanca distinta, y la estrategia es qué hacer con cada palanca en cada
región.

## 1 · La tabla, columna a columna, y qué decisión toca cada una

| Columna | Qué mide | Decisión que informa |
|---|---|---|
| `esperado_usd`, `pct_del_total` | cuánto dinero está en juego | cuánta atención merece la región |
| `pct_banda` | cuánto puede moverse el resultado si nada cambia | cuánto colchón necesita el plan |
| `pct_nivel_A` | % del dinero que se predice con precisión propia | dónde el forecast es firme y dónde es un préstamo |
| `pct_senal` | % del dinero en series con señal (dormidos, cancelación anunciada, no instalados, autorenovación) | cuánto dinero está *en disputa*: los negativos son la reserva de recuperación, los positivos, la que hay que proteger |
| `pct_nivel_S` | % del dinero con señal pero sin pool | dónde los modelos marcan clientes que después no podemos predecir: hace falta más historia o agrupar |
| `uplift_medio` | a qué precio relativo renueva | dónde el precio empuja o frena |
| `composicion_pct` | cuánto del movimiento de sus celdas es mezcla de cartera | dónde la tasa agregada engaña y hay que mirar por serie |
| `tasa_media` | la probabilidad media ponderada | el nivel de partida |

## 2 · Los cuadrantes

Cruzando peso (`pct_del_total`) y certeza (`pct_banda` y `pct_nivel_A`) salen cuatro
situaciones, y cada una pide una organización distinta:

**Grandes y firmes** (mucho dinero, banda estrecha, nivel A alto). Son el ancla del número.
Aquí el forecast es un compromiso: se gestiona por desviación (¿estamos dentro de la
banda este mes?), con revisión mensual corta. No hay que invertir en más datos; hay que
proteger el nivel: precio (`uplift_medio`) y positivos (autorenovación).

**Grandes y difusos** (mucho dinero, banda ancha o nivel A bajo). Es donde más vale cada
punto de precisión. Dos causas posibles, y la tabla las separa: si `pct_nivel_A` es bajo y
`pct_nivel_S` alto, es un problema de datos (series pequeñas, señales sin pool): agrupar,
revisar la taxonomía de esa región, dar historia a los flags; si `composicion_pct` es alto,
es un problema de cartera (productos que entran y salen): mirar por serie y no por
agregado, y explicar a negocio que el agregado se mueve por mezcla.

**Pequeñas y firmes.** Se agregan a su grupo regional superior y se revisan de trimestre en
trimestre. No merecen ritual propio.

**Pequeñas y difusas.** Se predicen por cascada (celda, global) y se declaran como tales.
Son el candidato natural a colapsar en la taxonomía si su dinero no crece.

## 3 · Las palancas, en orden de rentabilidad

1. **Recuperación**: donde `pct_senal` es alto y los negativos renuevan muy por debajo de los
   neutros (`tv_calibration`), el hueco × su pipeline es dinero disputable. Es la palanca
   más directa: campaña sobre dormidos y cancelaciones anunciadas, medida contra su tasa
   realizada, no contra el agregado.
2. **Precio**: donde `uplift_medio` está por debajo de la media de la cartera sin que la
   tasa sea mejor, hay margen de revalorización; donde está por encima con tasa peor, el
   precio puede estar costando renovaciones. La sensibilidad ($ por 1 % de uplift y por 1
   punto de tasa) dice cuál de las dos pesa más en esa región.
3. **Datos**: donde `pct_nivel_S` y `pct_nivel_A` dicen que el forecast es un préstamo,
   la inversión es en historia y agrupación, no en campañas: el retorno es una banda más
   estrecha, que es lo que hace posible comprometer un número.
4. **Cartera**: donde `composicion_pct` es alto, la organización tiene que dejar de mirar
   la tasa agregada de la región y mirar las series: el KPI regional cambia.

## 4 · El ritual mensual

- **Día 1-2 del mes** (el run mensual): `business_summary`, `pipeline_summary`,
  `forecast_by_region`. Se compara el mes que acaba de cerrar con lo que se predijo a un
  mes vista (`backtest_holdout` a h=1 y el mes pendiente del `business_summary` anterior):
  dentro de banda, nada que explicar; fuera, se explica por región y por palanca.
- **Cada trimestre** (el análisis): se rehacen las decisiones (escalera, benchmark,
  técnicas, bandas) y se revisa el cuadrante de cada región: una región que pasa de
  difusa a firme es una inversión en datos que ha funcionado.
- **Cada región** tiene un dueño del número (quien responde por la desviación) y las
  palancas tienen dueños funcionales (retención, precio, datos), que reciben de la tabla
  su parte y no la de los demás.

## 5 · Lo que esta propuesta no hace, a propósito

No convierte el forecast en un objetivo. El forecast es "si nada cambia": el objetivo es
lo que la organización decide mover con las palancas. La diferencia entre los dos, por
región y palanca, es el plan; y la banda es lo que permite saber, mes a mes, si la
diferencia se está consiguiendo o es azar.
