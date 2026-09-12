# Fase 0 — Lectura de la materia prima

*Qué sabemos del pipeline antes de predecir nada. Recorrido inductivo por los cuatro bloques: cada uno cierra con lo que queda establecido y lo que obliga a decidir.*

---

## Antes de empezar: qué es esta fase

La fase 0 no predice. Su trabajo es más humilde y más importante: **convertir un extracto de SQL en materia prima gobernada**. Cargar, revisar, acondicionar y dejar una referencia contra la que medir todo lo que venga después. Y su regla de oro es que **el raw es inmutable**: no se corrige, no se filtra, no se descarta. Se etiqueta. Todo lo que parezca sucio se queda dentro con un apellido que dice qué le pasa — porque el dinero que se aparta en silencio reaparece siempre en la reunión de cierre.

---

## 0.1 · El censo: ¿de qué está hecho lo que nos han dado?

**El contrato de columnas.** Lo primero que ocurre no es un cálculo: es una **revisión de aduana**. Cada columna del extracto tiene que estar declarada en el config con un papel — medida, dimensión obligatoria, señal que varía en el tiempo, extra de renovación, extra de revalorización, o explícitamente ignorada. Si aparece una columna huérfana, el programa **para** y la nombra.

Esto no es burocracia. Una columna sin adscripción es una pregunta sin responder: ¿segmenta el comportamiento, o es ruido de la extracción? Si el framework decidiera solo, decidiría mal en silencio. La disciplina es incómoda a propósito: obliga a que alguien con conocimiento de negocio diga qué es cada cosa **una vez**, y a que esa decisión quede escrita.

> **Conclusión operativa**: al terminar 0.1 sabemos que todas las columnas tienen dueño. Si el extracto cambia mañana —alguien añade un campo al SELECT—, el framework lo detecta el primer día, no tres semanas después en una cifra rara.

**Las validaciones bloqueantes.** Tres preguntas que, si se responden mal, invalidan todo lo posterior: ¿hay dinero negativo en el pipeline? ¿hay renovaciones con importe cero o negativo (renovar gratis no existe)? ¿hay nulos en alguna dimensión (una dimensión vacía rompe los identificadores y fabrica celdas fantasma)? Cualquiera de las tres detiene la ejecución con la lista completa de problemas — no el primero: todos, para que la corrección sea una sola vuelta al SQL.

**El censo de roles.** Cuántas filas son historia (`train`), cuántas reserva de examen (`test`) y cuántas futuro a predecir (`projection`). Un rol vacío no detiene nada, pero **avisa en voz alta**: casi siempre significa que el etiquetado en SQL no es el que creíamos.

**La doctrina del mes en curso.** El mes que está corriendo no es pasado: tiene pipeline conocido y resultado a medio llegar. Se le reasigna a **projection** —es el primer mes a proyectar, nunca examen— y, con él, todo projection se **limpia** de renovaciones y readquisiciones ya contabilizadas: el futuro debe parecer que aún no ha empezado. Se imprime exactamente cuánto se ha borrado, en filas, unidades y dólares.

> **Conclusión operativa**: aquí nace la frase que gobierna el resto — *a partir de este punto, ESTO es el raw*. Y el resumen de limpieza es, de propina, un dato de negocio interesante: cuánta renovación anticipada traía el mes en curso.

**Lo que ya se puede contar de la materia prima**: número de filas, columnas declaradas, reparto por rol, meses cubiertos, y qué mes se está proyectando primero.

---

## 0.2 · La partición: una realidad, dos tablas

Aquí ocurre la decisión estructural del framework: **el mismo dato se mira a dos granos distintos** porque hay dos preguntas distintas.

- **La tabla fina** conserva el detalle completo del raw, incluidos los extras que afectan al **valor** (descuento, tipo de compra, grupo de operación previo). Es el ancla: aquí vive el dinero, y de aquí saldrá cualquier informe a nivel de fila.
- **La vista al grano de la tasa** agrega esas filas al nivel donde tiene sentido hablar de **renovar o no renovar**. Menos filas, y sobre todo: los ratios se recalculan del agregado, nunca se promedian ratios.

Ambas reciben identificadores legibles (`fu_id` = dimensiones + mes) y **claves hash** para unir sin arrastrar cadenas de 200 caracteres.

**La conservación es el examen de la partición**: la suma de dólares de la tabla fina tiene que ser idéntica, al céntimo, a la de la vista. Si no lo es, el programa para. Es la garantía de que agregar no perdió nada — y de que cualquier número que se enseñe después es el mismo dinero, mirado desde otra altura.

**La unicidad es el examen del grano**: si un `fu_id` aparece dos veces, el grano está mal declarado. También detiene la ejecución.

> **Conclusión operativa**: al terminar 0.2 sabemos que la partición es reversible y sin pérdidas, y tenemos la primera cifra de contexto real: cuántas filas del raw se convierten en cuántas unidades de forecast. La distancia entre ambos números dice cuánta variedad interna de precio conviven dentro de cada celda.

---

## 0.3 · Los apellidos: universo, cobertura y ruta

Todavía sin calcular una sola tasa, cada serie recibe tres etiquetas que deciden **cómo se la va a tratar**:

- **Universo**: normal o serie temporal — dos maquinarias distintas.
- **Cobertura**: qué roles tiene esa serie a lo largo del tiempo (`train_test_projection`, `train_only`, `projection_only`...). Es la radiografía de su historia.
- **Ruta**, que se deriva de la anterior y es la etiqueta accionable:
  - **`trainable`** — tiene historia y tiene futuro: el caso completo, el que puede aprender de sí mismo.
  - **`heuristic`** — tiene futuro pero **no tiene historia**: hay que predecirle algo sin que nos haya contado nada. Aquí actuarán después la herencia del padre y la credibilidad.
  - **`no_impact`** — tiene historia pero **no tiene futuro**: nada que predecir. No se borra: se etiqueta, y su dinero queda visible en los informes como lo que es — cartera que ya no vence en el horizonte.

> **Conclusión operativa**: el reparto de dinero entre las tres rutas es la primera cifra que un directivo entiende sin explicación. *"El 88% del dinero a predecir viene de series con historia propia; un 12% habrá que estimarlo por analogía; y hay cartera que ya no vence en el horizonte."* Ese reparto, además, dimensiona el trabajo: cuanta más ruta heurística, más peso tendrá la maquinaria de préstamo de información.

---

## 0.4 · La referencia: cuánto se puede saber, como mucho

El último bloque no mide comportamiento: mide **capacidad de conocimiento**. Por cada unidad de forecast (celda × mes) calcula, a partir de su soporte, cuál es el **máximo error estadístico** que cabe esperar — usando deliberadamente el peor caso (la tasa que maximiza la varianza), porque a estas alturas aún no hemos estimado ninguna tasa y no queremos que la referencia sea optimista.

Ese error se expresa en tres monedas: puntos de error estándar, margen al 90% de confianza, y —la que llega a negocio— **dólares en riesgo estadístico**.

De aquí salen las lecturas más potentes de toda la fase:

1. **La foto binomial**: qué proporción del dinero vive en celdas con soporte suficiente para hablar por sí mismas y cuánto vive en el polvo. La sorpresa habitual es que *el polvo es numeroso y ligero*: la mayoría de las celdas son pequeñas, pero concentran una fracción menor del dinero. Eso convierte un problema aparentemente inmenso en un problema acotado.
2. **El dial de tolerancia**: elegido un umbral de negocio (*"acepto ±5 puntos con 90% de seguridad"*), qué porcentaje del dinero es predecible dentro de él **ya en crudo**, antes de que el framework haga nada. Es la línea de salida contra la que se medirá la mejora.
3. **La separación del error en dos mitades**: la irreducible (la que impone el tamaño de cada mes; ningún modelo la baja) y la reducible (la que se ataca con pools, credibilidad y técnicas). Sin esta distinción, cualquier discusión sobre "precisión del forecast" es una discusión sin unidades.
4. **El mapa de riesgo**: qué celdas concretas concentran dinero **y** error a la vez. No las más grandes ni las más ruidosas: las dos cosas. Esa es la lista de trabajo real.

> **Conclusión operativa**: la fase 0 entrega un contrato de honestidad. Dice, antes de predecir, *hasta dónde se puede predecir bien*, y deja una referencia inmutable que ninguna fase posterior puede tocar. Todo lo que la maquinaria consiga después se demuestra **contra este número**, no contra una impresión.

---

## El resumen inductivo, en una página

1. Nos dan un extracto. **Lo primero no es calcular: es entenderlo.** Cada columna declarada, cada regla verificada, cada rol censado. Lo que no cuadra, para el programa.
2. El mes en curso no es pasado. Se manda al futuro y se limpia lo que ya había llegado, dejando constancia de cuánto era.
3. La misma realidad se mira a dos alturas —el detalle donde vive el precio, la celda donde vive la renovación— y se demuestra que agregar no perdió ni un dólar.
4. Cada serie recibe sus apellidos: de qué universo es, qué historia tiene, y qué ruta le corresponde. **Nada se borra; todo se etiqueta.**
5. Y antes de predecir nada, se declara cuánto error es inevitable en cada celda-mes, en puntos y en dólares — la línea de salida.

**Lo que queda establecido al cerrar la fase**: el dinero total a predecir, cómo se reparte entre rutas, cuánto vive en celdas con soporte y cuánto en el polvo, qué porcentaje entra dentro de la tolerancia de negocio, y qué celdas concentran a la vez dinero y riesgo.

**Lo que queda obligado a decidir**: el umbral de tolerancia (una decisión de negocio, no estadística), el suelo de soporte, y si alguna ruta `heuristic` con mucho dinero merece tratamiento manual antes de dejarla en manos de la analogía.
