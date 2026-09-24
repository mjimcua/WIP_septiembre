# AUDITORÍA PROFUNDA — SFF v3 · 20 de septiembre de 2026

Alcance: 25 módulos (7.900 líneas), 8 baterías de test (2.700 líneas, todas en verde), 54
tablas, 20 documentos, y la consola de un análisis completo (≈ 230 líneas). Criterio:
lo acordado en las últimas dos semanas prevalece sobre lo anterior; lo que no sirve a la
historia sobra. El tono es el que pides: honesto, sin cortesías.

---

## 0 · Resumen ejecutivo

**Lo que hay.** Un framework metodológicamente serio, mejor fundamentado que casi
cualquier forecast de renovaciones que se hace en una empresa B2C: ruido binomial como
suelo, escalera con credibilidad, decisión única de estacionalidad con potencia medida,
backtest sin fuga, banda con componente común, composición contada y no perseguida,
maduración de señales, y trazabilidad hasta la fila del raw. Los tests de estadística
demuestran propiedades, no solo que el código corre.

**Lo que no hay.** Una historia. El framework calcula mucho y **cuenta poco**: la consola
es una secuencia de bloques técnicos en inglés con etiquetas en español, sin hilo, sin
"y esto qué significa", con números que el lector no puede situar (¿2,1 unidades
binomiales es bueno? ¿−$3.386 es mucho?). Las 54 tablas son un almacén, no un informe. La
documentación son 20 ficheros con solapes y seis de ellos superados. El lector de negocio
no tiene por dónde entrar, y el lector técnico tiene demasiadas puertas.

**Cinco hallazgos que importan:**

1. **El mensaje llega al final y sin contexto.** Las tres respuestas de negocio salen en
   la línea 200 de la consola, después de η², φ, LRT y bandas normalizadas. La pirámide
   está invertida: primero la evidencia, al final la conclusión.
2. **Ninguna métrica lleva referencia.** Se imprime el número, a veces la unidad, casi
   nunca "frente a qué". Un error de 4 pp sin decir que el suelo es 1,3 y la banda 6 no
   es información.
3. **Sobran 20 tablas, 6 documentos y 2 parámetros; faltan 1 informe y 1 leyenda.**
   Veinte de las 54 tablas no las lee nada (ni la ficha, ni la auditoría, ni la
   validación): existen para Power BI o para nadie. Seis documentos son diseño previo ya
   superado. Y no existe el artefacto que un director abriría: un informe.
4. **La metodología tiene tres puntos débiles que hay que decir en voz alta**: el examen
   son 6 meses (las bandas son cuantiles de 6 puntos: extremos de la muestra), casi
   todas las bandas son "de familia" (misma forma de error para pools distintos), y el
   ajuste por maduración de señales es una aproximación sin curva medida hasta que haya
   fotos. Ninguno invalida el resultado; los tres deben aparecer en el informe como lo
   que son.
5. **El código está limpio pero desequilibrado.** `run_forecast_assembly.py` (775 líneas)
   hace ensamblaje, bandas, resumen de pipeline, respuestas de negocio y región: cinco
   capítulos en un módulo. Y la convención de idioma se rompe en los valores
   (`trainable`, `neutral`, `projection` junto a `peldano`, `campeon`, `propia`).

**Cinco recomendaciones, en orden:**

1. **Construir el informe** (`informe.md` + figuras, generado por `run_analysis`): una
   página de portada con tres números y tres decisiones, y siete capítulos que siguen
   el guion. La consola pasa a ser el registro de ejecución; el informe es el producto.
2. **Estándar de métrica**: ninguna cifra sin unidad, referencia y lectura ("4,1 pp de
   error; suelo 1,3; banda 6,0: dentro"). Una tabla `leyenda_metricas` que el informe y
   Power BI comparten.
3. **Podar**: 6 documentos, 20 tablas (o declararlas explícitamente "para BI"), 2
   parámetros, 4 funciones, y unificar idioma en valores persistidos.
4. **Repartir `run_forecast_assembly.py`** en ensamblaje, bandas y respuestas, y mover
   los resúmenes a un módulo `informe.py` que sea el único que escribe prosa.
5. **Declarar las tres debilidades metodológicas** en el informe con su remedio y su
   fecha: examen más largo cuando el extracto lo permita, bandas propias cuando haya 20
   predicciones, curva de maduración cuando haya 6 fotos.

---

## 1 · Fortalezas (con evidencia)

- **El suelo binomial como eje.** Todo se mide contra √(p(1−p)/n): el dial, los niveles,
  el error normalizado, la cota mínima. Es la idea que hace comparable un pool de 50 y
  uno de 5.000, y es correcta. `COTA_BINOMIAL.md` la explica bien.
- **La escalera con credibilidad y dos suelos** (30 para hablar, 271 para hablar solo)
  resuelve el dilema segmentar/agrupar sin saltos; el test S2 demuestra que la mezcla
  nunca sale del intervalo [propia, pool] y que la serie pequeña se fía menos de sí misma.
- **Decidir la estacionalidad una vez, donde hay potencia.** Es la decisión metodológica
  más valiosa del framework: evita que 17 técnicas encuentren estaciones en el ruido.
  El test S5 midió falsos positivos (10 % → 0 con la regla |z| ≥ 1) y potencia (34/40).
- **Backtest sin fuga.** Decisión con meses anteriores al examen; el test S4 reescribe
  el examen y comprueba que ningún campeón cambia. Es lo que separa este backtest de la
  mayoría.
- **La banda con componente común.** Reconocer que 2.000 pools no fallan por su cuenta
  y medirlo es lo que convierte ±0,25 % (falso) en ±4 % (defendible).
- **Trazabilidad**: `sheet(clave)` desde cualquier fila del raw hasta su técnica y su
  banda; claves estampadas para Power BI.
- **Tests con verdad conocida** (S1-S8, E1-E6): 359 comprobaciones, y varias encontraron
  fallos reales (cero series entrenables, futuro vacío, falsos positivos del benchmark).

## 2 · Debilidades

### 2.1 · Metodología

| # | Debilidad | Efecto | Remedio |
|---|---|---|---|
| M1 | **Examen de 6 meses.** Los cuantiles 5/95 de 6 puntos son el mínimo y el máximo de la muestra; la banda "90 %" es en realidad "todo lo visto". | Banda gruesa y sensible a un mes raro. | Declararlo; permitir `test_months` mayor cuando el extracto tenga más historia estable; usar cuantiles de familia (miles de puntos) como ya se hace, pero decirlo. |
| M2 | **Bandas de familia casi siempre.** Con 6 objetivos ningún pool llega a 20 predicciones; todos los pools con la misma técnica comparten forma de error. | Un pool bien predicho hereda la banda de los mal predichos. | Umbral `band_min_predictions` a 12; bandas propias escaladas por el se del pool ya existen; reportar % de dinero con banda propia. |
| M3 | **Banda común con 6 puntos por horizonte.** | La parte más importante de la banda es la peor estimada. | Usar también los 6 meses de examen para la banda común (no decide técnica, no hay fuga de selección); declarar el número de puntos. |
| M4 | **Sesgo negativo del hold-out no resuelto.** Vimos −2 a −3 pp a horizontes largos en Kamelot; la maduración de señales es la explicación candidata, no probada. | El centro puede estar bajo. | La retrospectiva de la maduración (§4.5 de su documento) es la prueba; hasta entonces, mostrar sesgo y ajuste juntos. |
| M5 | **Uplift estático.** Ratio de sumas, sin tiempo salvo la ventana. | Una subida de precio se promedia con el antes. | `uplift_window_months = 12` por defecto y serie mensual de uplift por celda en la ficha. |
| M6 | **Adquisición simulada con las dimensiones del renovador.** | Sobreestima el segundo año (precio tope) y asigna al adquirido tasa de veterano. | El mapa de transición de reentradas (precio tope, `net_new`), pendiente de tus valores del raw. |
| M7 | **Horizonte con tope en 6.** A 12-16 meses se predice como a 6, con la banda de 6. | Banda optimista lejos. | Decirlo en el informe ("más allá de 6 meses la banda es la de 6; el error real será mayor"); cuando haya fotos, medir h=12. |
| M8 | **La escalera usa los meses de examen** para decidir pertenencia y credibilidad. Fuga menor: el examen juzga técnicas sobre pools cuya composición vio el examen. | Pequeña. | Aceptable; documentar. |
| M9 | **Benchmark solo en neutras grandes.** Si la estación vive en las series con señal (softcancel cerca del vencimiento es estacional por construcción), el benchmark no la ve. | La comprobación de flags (`bench_flags`) la mira, pero no decide nada. | Que `bench_flags` produzca un veredicto y entre en el informe. |

### 2.2 · Código

| # | Debilidad | Dato |
|---|---|---|
| C1 | `run_forecast_assembly.py` hace cinco cosas (ensamblaje, bandas, resumen de pipeline, respuestas, región). | 775 líneas, 3 responsabilidades ajenas al ensamblaje. |
| C2 | Idioma mixto en valores persistidos. | `trainable/no_impact/heuristic`, `neutral/neg/pos/mixed`, `normal/time_series`, `train/test/projection/pending_close` frente a `campeon/retador`, `propia/familia`, `peldano`. Acordado renombrar; sigue pendiente. |
| C3 | Parámetros sin uso. | `gap_rate_policy` (no se lee en ningún módulo); `console_explanations` se lee vía `getattr` (bien, pero invisible al análisis estático). 68 parámetros en total: muchos para quien empieza; falta agruparlos en "los 8 que se tocan" y "los 60 que no". |
| C4 | Funciones sin uso. | `seasonal_index_logit` (techniques), `showcase_sheets`, `guess_game`, `technique_error_by_horizon` (diagnostics: útiles pero nadie las llama). |
| C5 | Tablas que nadie lee. | 20 de 54: `dim_domains`, `dial_buckets`, `risk_levels`, `decision_eta2_pairs`, `tv_calibration`, `bench_panel`, `bench_flags`, `dim_tecnica`, `backtest_agg_error`, `horizon_report_total`, `forecast_by_level`, `pipeline_summary`, `forecast_by_region`, `signal_*` (4), `baseline_*` (2), `fu_summary`. Existen para BI o para la consola. Hay que decidir cuáles son producto (informe/BI) y cuáles son intermedias. |
| C6 | `fu_summary` duplica `fact_fu` + 3 columnas. | Acordado fundir; pendiente. |
| C7 | Constantes duplicadas entre módulos (`TRUTH_ROLES`, `PROJECTION_ROLE`, `NEUTRAL_SIGN` definidas en 6 sitios). | Riesgo de divergencia; deberían vivir en un módulo `vocabulario.py`. |
| C8 | La consola mezcla registro de ejecución (`[write] 660,200 rows → …`) con hallazgos. | El lector no distingue lo que importa. |
| C9 | Los tests son buenos pero lentos (≈ 4 min la batería). | Aceptable; separar "rápidos" de "completos". |

### 2.3 · Salidas y capacidad de contar la historia

Esta es la debilidad principal, y la más fácil de arreglar porque los datos ya están.

- **No hay pirámide.** El orden es el de ejecución (raw → series → dimensiones → escalera →
  benchmark → backtest → uplift → forecast → respuestas), que es el orden de *construir*,
  no el de *contar*. Un director quiere: cuánto, con qué confianza, dónde está el riesgo,
  qué hacer; y solo después, por qué creerlo.
- **Números sin referencia.** Ejemplos reales de la consola: "leaderboard … T3_ma3 2.11";
  "η²=0.334"; "φ median 2.88"; "band −0.7 % / +0.5 %"; "pending maturation priced: −3.386 $".
  Ninguno dice si es mucho o poco. Cada cifra necesita tres cosas: unidad, referencia
  (el suelo, la media de la cartera, el año pasado, el % del total) y lectura.
- **Las explicaciones `>` ayudan, pero son genéricas**: explican la métrica, no el
  hallazgo. "φ = varianza / varianza binomial" está bien una vez; lo que falta es "en
  Kamelot φ mediana 2,9: la tasa se mueve tres veces más que el azar: hay que seguir el
  nivel, no la media".
- **Idioma**: la consola está en inglés con etiquetas en español; el informe para negocio
  debe estar en español entero. Decidir uno y aplicarlo.
- **Figuras**: solo la ficha (6 paneles) y 4 diagnósticos, y nadie las enlaza con el
  texto. No hay figura de "el dinero por nivel de riesgo", ni de "banda del total mes a
  mes", ni de "composición por región", ni de "movers".
- **Nombres que no se explican solos**: `A3_propio_reforzado`, `S_signo_bajo_suelo`,
  `medio_largo`, `err_norm`. Necesitan leyenda cada vez que aparecen en un producto.
- **Las tablas no llevan descripción.** Ni columna a columna ni de conjunto. `ANALYSIS_POINTS.md`
  lo hace en parte, en otro fichero.

### 2.4 · Documentación

20 documentos, 260 KB. Se lee mejor con esta clasificación:

| Estado | Documentos | Acción |
|---|---|---|
| **Vigentes y necesarios** | `GUION_MARCO.md`, `README_V3.md`, `FLUJO.md`, `METODOS.md`, `PARAMETROS.md`, `COTA_BINOMIAL.md`, `RECORRIDO_DE_UNA_SERIE.md`, `PREGUNTAS_NEGOCIO.md`, `ESTRATEGIA_POR_REGION.md`, `ETAPA_MADURACION_SENALES.md`, `USO_NOTEBOOK.md`, `ANALYSIS_POINTS.md`, `AUDITORIA.md` (Power BI) | Mantener; unificar idioma; que `README` sea el índice único. |
| **Superados** | `GUION_V3.md` (diseño del 12-sep, antes de todo), `PLAN_V3.md` (idem), `REVISION.md` (revisión v2→v3), `PENSAR_JUNTOS.md` (observaciones ya resueltas), `COTAS.md` (duplicado de `COTA_BINOMIAL.md`), `POR_QUE_ESTE_FORECAST.md` (solapa con `GUION_MARCO.md`) | Mover a `historico/` o borrar. |
| **Solapes** | `README` ↔ `FLUJO` ↔ `METODOS` ↔ `GUION_MARCO` repiten el flujo con distinto nivel. | `GUION_MARCO` = el qué y el por qué; `FLUJO` = el cómo por función; `METODOS` = la matemática; `README` = índice. Quitar de cada uno lo que es de otro. |
| **Falta** | Un documento para el lector de negocio que no quiera abrir nada más. | El informe generado. |

---

## 3 · Lo obsoleto o superado (lista para actuar)

- **Documentos**: los seis de la tabla anterior.
- **Parámetros**: `gap_rate_policy`. Revisar también `intermittent_zero_share` (sin
  técnica intermitente ya no decide nada), `richer_family_min_history_months` (solo
  afecta a empates), `backtest_workers` (útil, pero nadie lo ha usado).
- **Funciones**: `seasonal_index_logit`, `showcase_sheets`, `guess_game`,
  `technique_error_by_horizon` (esta última merece vivir: enlazarla desde el informe).
- **Tablas**: fundir `fu_summary` en `fact_fu`; declarar en `PHYSICAL_TABLE_NAMES` un
  atributo por tabla (`producto` / `intermedia` / `bi`) y que el informe liste solo las de
  producto.
- **Vocabulario**: los valores en inglés listados en C2, con el cambio de claves de pools
  con signo que implica (ahora, antes de que haya Power BI encima).
- **Consola**: los `[write]` a un log aparte (o a una línea por fase), y los bloques
  técnicos detrás de un `verbose`.

---

## 4 · El hilo argumental: la historia que el código debe contar

Siete capítulos, cada uno con la pregunta, la evidencia, la métrica con referencia, el
"y entonces", y la figura. Es el orden del informe, no el de ejecución.

| Cap. | Pregunta | Evidencia (ya existe) | Métrica con referencia | Y entonces | Figura |
|---|---|---|---|---|---|
| 0 Portada | ¿Cuánto, con qué confianza, qué hacer? | `business_summary`, `pipeline_summary`, `top_movers` | Total esperado del año (y % ya real); banda total en $ y %; los 3 movers mayores | Las 3 decisiones del mes | Un gráfico: barras mes a mes (real / previsto / ajustado) con banda |
| 1 La pipeline | ¿Qué vence y cuánto es firme? | `horizon_report_total`, `business_summary` | $ real / proyectada / simulada por mes, % del total | Cuánto de 2027 se apoya en contratos que existen | Área apilada por origen |
| 2 El ruido | ¿Qué parte del dinero se puede predecir bien? | `dial_buckets`, `risk_levels` | $ por tramo del dial y por nivel, con el error de cada uno frente al ±5 % prometido | Dónde invertir en datos | Barras de $ por nivel con su error |
| 3 La composición | ¿La tasa se mueve por comportamiento o por cartera? | `mix_shift`, `mandatory_only_cost` | % composición (referencia: > 30 % = el agregado engaña); $ que costaría la vista solo-mandatory | Qué KPI mirar por región | Kitagawa apilado para las 5 celdas mayores |
| 4 La estación | ¿Hay estación en la tasa? | `decision_estacionalidad`, `bench_flags` | Amplitud pp vs 2 pp; mejora vs 10 %; φ vs 1 | Técnicas de nivel, o efectos de mes en N series | Panel mes × año de las 3 mayores |
| 5 La precisión | ¿Cuánto nos equivocamos y cuánto es azar? | `backtest_holdout`, `backtest_holdout_agg`, `decision_agg_bands` | Error del total en pp y $ frente al suelo binomial y a la banda; % dentro de banda vs 90 % | La banda que se promete y sus dos partes | Real vs previsto en el examen, con banda |
| 6 El riesgo que entra | ¿Qué cambiará antes del vencimiento? | `signal_adjustment`, `signal_alerts`, `top_movers` | Ajuste $ y % del forecast; alertas con z | Recuperación, precio, datos: por región | Composición hoy vs final por región |
| 7 Frente a la hoja | ¿Es mejor que lo que se hacía? | `baseline_summary` | Diferencia $ y %; error walk-forward de cada uno | Qué aporta: el número, la banda o ambos | Dos líneas de error por lag |
| Anexo | ¿De dónde sale cada número? | `sheet` de las 5 series mayores; leyenda de métricas; tablas producto | — | — | Las fichas |

El principio es el de la pirámide: la respuesta primero, la evidencia después, y cada
figura con un **título que afirma el hallazgo** ("La estación vive en el volumen, no en la
tasa"), no que describe el contenido ("Perfil estacional por mes").

## 5 · Estándar de métricas y leyendas

Regla: **ninguna cifra sin unidad, referencia y lectura.** Tres formas de referencia,
siempre al menos una:

- **Frente al azar**: el suelo binomial (pp o $). "Error 4,1 pp; el azar solo explica 1,3."
- **Frente al total**: % del dinero. "S: $8,3M = 4,7 % del proyectado."
- **Frente al tiempo**: el año pasado, los últimos 12 meses. "Composición 33 %; en el
  mismo periodo del año pasado, 21 %."

Y una lectura fija por métrica (tabla `leyenda_metricas`, columnas `metrica`, `unidad`,
`definicion`, `referencia`, `mucho_es`, `poco_es`), que el informe imprime la primera vez
que la métrica aparece y Power BI muestra como tooltip. Ejemplos:

| métrica | unidad | definición | referencia | mucho es | poco es |
|---|---|---|---|---|---|
| error binomial | pp | √(p(1−p)/n)·100: lo que la tasa oscila por azar en un mes | 271 clientes → ±5 pp | > 15 pp (menos de 30 clientes) | < 3 pp (más de 752) |
| unidad binomial | ×suelo | error de una técnica ÷ error binomial del mes | 1,0 = el suelo | > 3: la técnica no sigue el nivel | 1-1,5: cerca del suelo |
| φ | ratio | varianza observada / varianza binomial, tras tendencia | 1 = solo muestrea | > 3: algo real la mueve | ≈ 1 |
| composición | % | Σ\|composición\| / (Σ\|composición\| + Σ\|comportamiento\|) | 0-100 | > 30 %: el agregado engaña | < 10 % |
| banda total | % del esperado | idiosincrática ⊕ común, 90 % | la promesa: ±5 % | > ±8 % | < ±2 % (revisar la común) |
| pendiente de maduración | pp de la celda | proporción final − actual | 0 a h ≤ 1 | > 5 pp | 0 |

## 6 · Ciencia + McKinsey: qué significa en la práctica

- **Ciencia**: cada afirmación con su medida, su error y su prueba (los tests S1-S8 son el
  aparato experimental; el informe los cita: "la potencia del benchmark es 34/40 sobre
  una estación de 8 pp"). Las debilidades M1-M9 declaradas en el propio informe, con
  fecha de remedio. Ninguna cifra con más precisión de la que tiene (bandas de 6 puntos
  no se imprimen con dos decimales).
- **McKinsey**: pirámide; una idea por página; títulos que afirman; tres números por
  capítulo, no treinta; "y entonces" al final de cada bloque; el dinero siempre en
  millones con un decimal y en % del total; las decisiones con dueño y fecha; y un anexo
  donde vive todo lo demás.

El artefacto: `informe.md` (y opcionalmente `informe.html`) generado por `run_analysis`
en `<outdir>/informe/`, con las figuras al lado, en español, con las leyendas la primera
vez que aparece cada métrica y con una tabla final "de dónde sale cada número". La
consola queda como registro técnico (en inglés, con `[write]` y tiempos).

## 7 · Plan en tres olas

**Ola 1 (una sesión): podar y ordenar.** Mover los 6 documentos superados; borrar los
parámetros y funciones sin uso; `vocabulario.py` con roles, signos, rutas y niveles en
español (un solo cambio de valores, ahora); clasificar las 54 tablas en producto /
intermedia / BI; separar `run_forecast_assembly.py` en `assembly.py`, `bands.py` y
`answers.py`.

**Ola 2 (dos sesiones): el informe.** `informe.py` con los 7 capítulos y la portada;
`leyenda_metricas`; las 8 figuras nuevas (barras por origen, $ por nivel con error,
Kitagawa de las 5 celdas, panel del benchmark, examen con banda, composición hoy vs
final, movers, baseline); títulos que afirman; referencias en toda cifra. La consola
reducida a una línea por fase más el enlace al informe.

**Ola 3 (cuando haya datos): cerrar las debilidades metodológicas.** Retrospectiva de la
maduración; curva medida con 6 fotos; examen de 12 meses si el extracto lo permite;
bandas propias en los pools grandes; el mapa de transición de reentradas (precio tope)
con tus valores del raw; veredicto de `bench_flags`.

---

## 8 · Lo que no cambiaría

El núcleo metodológico (suelo binomial, escalera con dos suelos, benchmark único,
backtest sin fuga, banda con común, composición contada) y las baterías de test. Es lo
que vale, y es lo que el informe tiene que hacer visible.
