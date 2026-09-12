# Por qué hacemos este forecast así

*SFF v2 · 12-sep-2026 · Resumen de motivación y retos. Complementa a DISENO_V2.md (doctrina) y HANDOVER.md (estado). Lenguaje técnico directo, sin metáforas.*

---

**Qué se proyecta.** Ingresos por renovación de una base de suscripciones B2C. La descomposición de partida es:

```
revenue futuro = pipeline conocido × tasa de renovación × revalorización
```

El pipeline (qué contratos vencen en cada mes futuro, cuántas unidades, cuánto pagaban) **es dato, no pronóstico**: está en la base. Lo único que hay que estimar son dos factores: la tasa (qué fracción renueva) y el uplift (cuánto pagan los que renuevan respecto a lo que pagaban).

**Por qué no una serie temporal sobre el total.** El total de ingresos se mueve por dos causas que un modelo sobre el agregado no puede separar: cambio de comportamiento de los clientes y cambio de **composición** del pipeline (más contratos de un producto barato, más clientes en su primera renovación, más en softcancel). La composición futura ya la conocemos; predecirla es tirar información. Y peor: cuando la composición rota, la tasa agregada se mueve aunque ningún grupo cambie su tasa (mix-shift; en su versión extrema, la paradoja de Simpson). Un modelo del total aprende ese movimiento como si fuera tendencia.

**Por qué segmentar.** Una probabilidad aplicada a un grupo solo tiene sentido si los miembros del grupo son comparables. La tasa de un grupo heterogéneo es una media contable, no la probabilidad de nadie. Segmentar por las dimensiones que separan comportamientos (región, producto, término, banda, softcancel…) hace que cada tasa signifique algo, y elimina el sesgo de mezcla porque la composición se aplica después, fila a fila, con el pipeline real.

**El reto central: segmentar tiene coste.** Cada división reduce n. La tasa es un sí/no por unidad, así que su error de muestreo es binomial, √(p(1−p)/n): con n=30 y p=0,5 la banda al 90% es ±15 pp; con n=300, ±4,7 pp. Hay una tensión sesgo–varianza explícita:
- Agregar mucho → sesgo de mezcla. Medido en dólares con el contrafactual (método plano vs segmentado, últimos 6 meses con verdad): **$166.370** en la ejecución de septiembre.
- Segmentar mucho → error de muestreo. Medido en dólares como pipeline en celdas por debajo del suelo de soporte: **$21,2M de $173,3M** (12%).

El framework no minimiza ninguno de los dos por separado; minimiza la suma, celda a celda.

**Los retos derivados, y qué pieza los trata:**

1. **Qué dimensiones separan de verdad.** No todas pagan el soporte que consumen. ANOVA (η²) por dimensión: la que no separa se anula antes que las demás. Las mandatory nunca se anulan.
2. **Dimensiones que cambian con el calendario.** `softcancel` hoy es bajo y cerca del vencimiento es alto; su tasa es distinta y su peso rota solo. Se tratan aparte (timevarying con signo) y con histórico as-of: lo que se sabía entonces, nunca re-puntuado.
3. **Recuperar soporte sin destruir la segmentación.** Tres estrategias por orden de coste: agrupar timevarying del mismo signo (L1), anular la dimensión extra de menor η² (L2), y credibilidad z = n/(n+k) hacia el primer padre de la jerarquía que alcanza el suelo (L3). Regla P5/P6: el cálculo se hace con el pool, pero la estimación se estampa en cada serie y cada serie conserva su propio pipeline. Nada se cuenta dos veces.
4. **Cuándo medir dinámica.** Estacionalidad y tendencia solo se miden después de reparar el soporte (P9): con n pequeño, cualquier pendiente es ruido. El criterio de «hay señal» no es un umbral fijo sino la cota binomial propia de cada pool (P1): φ = varianza observada / varianza binomial esperada. φ≈1 es solo muestreo; φ>1 hay motor.
5. **Elegir técnica y dar bandas honestas.** Backtest multi-origen con 15 técnicas, campeón por pool; banda = p90 del error **medido** por técnica y horizonte, no una fórmula teórica; al agregar series, las bandas se combinan en cuadratura.
6. **El mes en curso.** Tiene pipeline completo pero resultado incompleto. Se trata como el primer mes a proyectar y se limpian sus resultados parciales; si no, contamina el backtest.
7. **El uplift.** Rama distinta, error distinto: ratio de sumas ponderado por dinero, error s/√n con n = renovadores. El descuento va a esta rama y no a la tasa porque su efecto en el uplift es aritmético (retirar un 40% de descuento *es* la revalorización) y en la tasa multiplicaría el grano.

**Por qué un framework y no un modelo.** Porque lo que se entrega no es un número sino una cadena auditable: cada estimación tiene su error propio calculable por cualquiera, cada serie sabe de qué pool salió su tasa y por qué, cada tabla es joinable desde la fila cruda hasta el forecast, y las decisiones (η², técnica, bandas) se separan de la ejecución mensual para poder delegarla.

---

## Ejemplos para la presentación

*Cifras calculadas y verificadas; z = 1,645 (banda al 90%) salvo que se indique.*

### Ejemplo 1 · Reportar no es predecir

Celda: `META | Producto legacy | Producto 1 | 1 año | 3 dispositivos`. Este mes vencían 5 dispositivos y renovaron 3.

**Como reporte, el dato es exacto.** Tasa = 3/5 = 60%. No hay incertidumbre: pasó, está contado, cuadra con el dinero.

**Como predicción, el mismo dato es casi inútil.** El mes que viene vencen otros 5 dispositivos de la misma celda. ¿Renovarán 3? Si la probabilidad real de renovar de ese tipo de cliente fuera exactamente 60%:

- La probabilidad de que renueven **exactamente 3** es del 35%. Dos de cada tres meses saldrá otro número.
- Renovarán 0 o 1 con probabilidad 9%; los 5, con probabilidad 8%.
- El error estándar de la tasa es √(0,6·0,4/5) = ±21,9 pp; la banda al 90% es **±36 pp**: la tasa del mes que viene puede caer, sin que nada haya cambiado, entre el 24% y el 96%.

Y eso asumiendo que el 60% fuera la tasa real. Con n=5 tampoco sabemos eso: el 60% observado es una muestra de 5 de una probabilidad que desconocemos.

**La diferencia entre reportar y predecir es el tamaño de la muestra.** Para que la tasa de esta celda fuera una predicción con ±5 pp de banda harían falta 271 dispositivos venciendo al mes, no 5. Con 30 (el suelo de soporte del framework) la banda es ±15 pp: suficiente para entrar en el cálculo, no para fiarse a ciegas. Ese es el motivo de toda la maquinaria de soporte: cuando una celda tiene 5, hay que buscar con quién juntarla para tener 30, sin juntarla con clientes que no se le parecen.

Regla de la ley 1/√n: para reducir la banda a la mitad hay que cuadruplicar n.

| Banda al 90% (τ) | n mínimo = (z·50/τ)² |
|---|---|
| ±15 pp | 30 |
| ±5 pp | 271 |
| ±3 pp | 752 |

Y al revés: los errores de muchas celdas pequeñas **no se suman, se combinan en cuadratura** (√Σ moe²). 100 celdas de n=30, cada una con ±15 pp, agregadas dan ±1,5 pp sobre el total. El forecast del total es preciso aunque el de cada celda no lo sea; por eso se puede segmentar mucho sin que el total se vuelva ruido.

### Ejemplo 2 · El contrafactual Simpson, con números

**El problema.** Una celda mandatory (región NA) contiene dos series con tasas distintas y estables:

| Serie | Tasa de renovación (histórica y real) |
|---|---|
| Producto A | 90% |
| Producto B | 50% |

En el histórico (meses ≤ t−1), el pipeline de la celda era 70% producto A y 30% producto B. La tasa agregada histórica de la celda es por tanto:

```
0,70 × 0,90 + 0,30 × 0,50 = 0,63 + 0,15 = 78%
```

En el mes t vencen 1.000 dispositivos, pero la composición ha cambiado: **400 de A y 600 de B** (más clientes del producto barato llegan a su primera renovación). Esto no es una predicción: el pipeline del mes t es dato, se lee de la base.

**Dos formas de predecir el mes t, ambas usando solo lo que se sabía en t−1:**

- **Método plano** (una tasa por celda): 78% × 1.000 = **780 renovaciones**.
- **Método segmentado** (una tasa por serie, recombinada con los pesos reales de t): 400 × 0,90 + 600 × 0,50 = 360 + 300 = **660 renovaciones** (66%).

**Lo que pasó de verdad** (ningún cliente cambió de comportamiento; A siguió al 90% y B al 50%): 660 renovaciones.

| | Predicción | Real | Error |
|---|---|---|---|
| Plano | 780 (78%) | 660 (66%) | **+12 pp** |
| Segmentado | 660 (66%) | 660 (66%) | 0 pp |

Con un AUV de $30, el pipeline de la celda vale $30.000, y el **ahorro del contrafactual ese mes es (|+12| − |0|) pp × $30.000 = $3.600**: el dinero en que el método plano se equivocó de más.

**Lo que enseña.** La tasa agregada de la celda cayó del 78% al 66% **sin que ningún grupo cambiara su tasa**. Un modelo sobre el agregado (una serie temporal del 78%) vería una caída de 12 pp y la aprendería como tendencia negativa; el mes siguiente la extrapolaría. La caída no es comportamiento, es composición, y la composición futura ya la conocíamos.

**La versión fuerte (la paradoja).** Si además ambos productos *mejoran* — A sube al 92% y B al 55% — el agregado con la nueva composición es 0,4 × 0,92 + 0,6 × 0,55 = 69,8%: **sigue por debajo del 78% histórico**. Todos los segmentos mejoran y el total empeora. Esa es la paradoja de Simpson en sentido estricto. En Kamelot no encontramos un caso limpio de esta versión fuerte; lo que sí se mide cada mes es la versión débil (la distorsión del ejemplo anterior), y esa es la que cuesta dinero.

**Cómo se calcula en el framework** (`simpson_contrafactual`):
1. Para cada celda mandatory y cada uno de los **últimos 6 meses con resultado conocido** (t).
2. Plano: tasa agregada de la celda con datos ≤ t−1.
3. Segmentado: tasa de cada serie de la celda con datos ≤ t−1, recombinada con los pesos reales del pipeline de t.
4. Ambos contra la tasa real de t. `ahorro_usd = (|err_plano| − |err_seg|) × pipeline$ de t`.
5. Se suma **con signo** (los celda-mes donde el plano acertó más restan) y se reporta el % de celda-mes donde gana el segmentado.

Es un walk-forward honesto: en cada mes t solo se usa lo que se sabía en t−1, y el peso de t es legítimo porque el pipeline es dato. Se llama *contrafactual* porque responde a «¿cuánto nos habríamos equivocado si no hubiéramos segmentado?».

**Cifras reales (Kamelot):** $738.611 en 6 meses (12-ago, con el mes en curso contaminando el histórico) → **$166.370** (sep, con la doctrina del mes en curso). El segundo es el honesto. En la ejecución de agosto el mix explicaba +10,5 pp de movimiento del agregado mientras el agregado subió +8,4 pp: el comportamiento real había bajado 2 pp y el total lo ocultaba.

**Los dos costes, juntos.** El contrafactual mide lo que cuesta agregar ($166k). El dinero bajo el suelo de soporte mide lo que cuesta segmentar ($21,2M de $173,3M en celdas con n<30 antes de reparar). El framework existe para pagar la factura menor en cada celda.
