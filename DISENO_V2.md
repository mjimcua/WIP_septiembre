# DISEÑO V2 — checkpoint de consenso y fuente única de implementación

*SFF_v4 · consolidación de las conversaciones de rediseño (jul-2026). Este documento **sustituye** a PLAN_FASES.md y EL_RAZONAMIENTO.md como fuente de obra: la implementación limpia se hará en sesión nueva leyendo **exclusivamente** este documento. El código anterior queda congelado como cantera (§9): se copia y adapta lo probado, jamás se importa.*

---

## 1 · El problema esencial y dónde vive la ventaja

Negocio de suscripción: proyectar el revenue futuro **en función del pipeline** — los contratos que vencen. «La pipeline del futuro es tan conocida para nosotros como para cualquiera»: no se predice, se lee. Por tanto:

**revenue futuro = pipeline conocido × tasa de renovación × revalorización**

La ventaja solo puede vivir en los dos factores estimados, y nace de la **homogeneidad**: «que los clientes que componen cada serie tengan propiedades, comportamientos, situaciones y contextos más similares», porque una probabilidad aplicada a un grupo solo es legítima si sus miembros son comparables — independientes, pero con características comunes. Sin homogeneidad, la tasa del grupo «no es la probabilidad de nadie: es una media contable sin poder predictivo».

En una frase: *el pipeline lo conoce cualquiera; nuestra ventaja es asignarle probabilidades que signifiquen algo — series homogéneas con evidencia suficiente, tiempo bien leído, y un solo umbral honesto: nada actúa si no supera su propio ruido.*

La readquisición queda **fuera** de este estudio (su track aparte); la adquisición nueva es fase aparte por naturaleza — su pipeline no es conocido.

## 2 · Principios de diseño

**P1 · La referencia propia como único umbral.** «Un número mágico es discutible, una referencia propia, no tanto.» Toda señal se juzga contra el error propio de su serie/celda: lo supera → real; no → fantasma, no se actúa. «Uno de los grandes punch del framework es que utiliza una estimación estadística de error como base para todo: la pueden calcular ellos en cualquier momento, y hay referencias.» Constantes de negocio supervivientes: el suelo de soporte y el techo de saturación de tasa (≤100%, en la práctica ~95%: «el 95% ya me parecería mucho»).

**P2 · Dos ramas, dos errores, una simetría.** La tasa de renovación es un sí/no por unidad → error **binomial** √(p(1−p)/n). La revalorización «es un número continuo, no es sí y no» → **error estándar de la media** s/√n (n = renovadores, ponderado por dinero). Matiz fundamental: la vara binomial se calcula sin mirar los datos (solo p y n); la continua exige **medir s** — la propia dispersión del segmento es parte del diagnóstico. El esqueleto de mejora es simétrico; la aritmética, no.

**P3 · Config exhaustivo o excepción.** «En la configuración tiene que estar todo.» Cada columna del raw declarada en un rol válido; cualquier huérfana **para el programa en el acto**, listándola. Primera validación de todas. Muere el "complemento": una columna nueva en SQL ya no se convierte en dimensión en silencio — rompe ruidosamente y obliga a decidir su papel.

**P4 · Raw inmutable — etiquetar, no amputar.** Nada se borra: las series sin impacto se marcan (ruta) y las fases posteriores filtran. El censo queda siempre completo y la referencia intacta.

**P5 · Las filas nunca se consolidan.** Las mejoras de soporte añaden identificadores; el cálculo agrega por identificador y **el resultado se estampa en cada miembro**: «si una tenía diez unidades a renovar y otra veinte, el cálculo se hace con treinta, pero el resultado se pone dos veces, una en la de diez y otra en la de veinte». Lo estampado es la **estimación** (tasa del grupo, su error) — jamás los insumos: pipeline y dinero siguen siendo los propios de cada serie; nada se cuenta dos veces al agregar.

**P6 · Estimación ≠ aplicación.** «Las agrupaciones son estructuras de estimación, no de aplicación: el pool es de dónde sale el número, no a qué se aplica.» Cada serie conserva identidad y pipeline futuro; solo *lee* la tasa de su grupo.

**P7 · Claves y trazabilidad.** `*_id` legible (dims con `|`) + `*_key` = **hash determinista int64 del id**: mismo id → misma key, siempre, sin estado que persistir. Lookups id↔key regenerados en cada carga del raw; los sintéticos **amplían** el lookup dentro de la ejecución. **`process_date`** en toda tabla al persistir (horneado en `config.write`), más `execution_id` en summaries y evaluaciones.

**P8 · Summaries = tablas estrella, no prints.** «Dejar los datasets preparados para ir generando estrellas, que permitan trabajar en paralelo.» Cada análisis persiste como tabla joinable por key; los reports-que-imprimen se disuelven en summaries + un group by del usuario. Ejemplo canónico: raw-sin-extras ⋈ `forecast_units_raw_summary` por `fu_key` → dinero por rol.

**P9 · Diagnóstico en dos tandas — el soporte legitima la medición.** «Si tenemos una gran tendencia pero el soporte es bajo, no podemos fiarnos de esa tendencia; probablemente no sea de verdad.» Medir dinámica antes de consolidar no es medir pronto: es medir mal (la varianza de una pendiente cae con el soporte). Tanda 1 (tras cargar): soporte, Simpson, ANOVA. Tanda 2 (tras reparar): historia y dinámica. «Hemos hecho todo lo posible por mejorar el soporte; esa foto es la que ya deberíamos mirar: la estacionalidad, la tendencia.»

**P10 · Pocas funciones, contratos regenerables, evals con harness compartido.** Bloques de 3–5 por fase; cada fichero con **prompt-contrato** de cinco secciones (ENTRADA · SALIDA · REGLAS numeradas · BORDES · REGISTRO) escrito para regenerar la función sin ver el código; mini-eval de tres casos (control/edge/frontera) con el andamiaje en un `eval_harness.py` común (~15 líneas por fichero). El vocabulario `gate` se conserva en inglés.

## 3 · Taxonomía de variables (muere «covariables»)

| Grupo | Tasa renovación | Revalorización | Reglas |
|---|---|---|---|
| `mandatory` | ✓ siempre | ✓ siempre | excluyente con todo |
| `timevarying` (con signo `negative`/`positive`) | ✓ (vía L1) | ✗ | excluyente con mandatory y extras |
| `extra_renovacion` | ✓ | — | solapable con extra_revalorizacion |
| `extra_revalorizacion` | — | ✓ | solapable con extra_renovacion |
| medidas · `ignore_cols` | — | — | — |

Una variable puede estar en ambos grupos extra, en uno, o en ninguno. Las exclusiones se validan al construir el config. Los granos quedan **derivables por fórmula**:
- Grano tasa = `mandatory + timevarying + extra_renovacion`
- Grano uplift = `mandatory + extra_revalorizacion`
- Tabla fina de fase 0 = la unión; la vista-tasa colapsa sobre las que son *solo* de revalorización (ratios **recalculados** del agregado — jamás promedios de promedios — con **conservación exacta** verificada: un dólar que no cuadra, para).

El porqué de la asignación (la vieja tensión del descuento, resuelta): **«cada columna trabaja en el factor donde su señal paga el soporte que consume».** En la tasa, el descuento multiplica el grano y destruye el soporte binomial; en el uplift es casi mecánico — quien entró con 40% y renueva a pleno tiene uplift ≈ 1/0,6 por aritmética: la retirada del descuento *es* la revalorización. Aparcado con nombre: en el futuro, una señal derivada «tipo descuento sí/no, o intervalos» podría entrar como extra_renovacion; no se recomprueba hasta su momento.

Las timevarying son especiales por su naturaleza: «hoy hay pocas, pero cerca de la expiración hay muchas más; la estimación de hoy no es la misma que la de dentro de dos meses, porque varía en el tiempo». Llevan la señal de régimen y crecerán — por eso ni pasan por ANOVA («seguro que van a tener una gran diferencia») ni se anulan con asterisco: se gestionan en L1.

**Timevarying alimentadas por modelos predictivos.** Las timevarying son «el puerto de inyección de los predictivos en el forecast»: columnas dicotómicas producidas por modelos cliente-a-cliente (p. ej. `alta_prob_abandono_no_instalacion`, `alta_prob_abandono_no_uso` — alta probabilidad de abandono *con su motivo*). La predicción individual se convierte en dimensión: targetea un conjunto de clientes en situación homogénea — el conocimiento por cliente, sintetizado a comportamiento de cartera; para acciones están las predicciones individuales, para el forecast se necesita volumen, y eso lo pone esta maquinaria. Cada motivo conserva su identidad en el id fino; el forecast los junta por signo cuando el soporte manda («pueden cambiar un poco los motivos, pero el resultado es homogéneo»). Dos reglas innegociables: (a) **as-of** — el histórico de estas columnas es *lo que el modelo predijo entonces*, jamás re-puntuado con el modelo de hoy (re-puntuar contamina la tasa histórica con información futura); (b) **la versión del modelo es una bandera** — al reentrenar, el significado del flag cambia y las tasas por flag pueden saltar: se anota, no se descubre. Regalo de vuelta: la tasa realizada del pool `SIG=neg` es la **calibración empírica del predictivo** — el forecast audita al modelo sin coste añadido.

## 4 · La cadena de identificadores

```
fu_id  = dims | mes                      (fase 0 · la unidad)          + fu_key
fs_id  = dims                            (fase 1 · «porque queremos predecir series»;
                                          huecos ya rellenos)           + fs_key
   └─ fs_id_L1 : timevarying del MISMO SIGNO fusionadas → SIG=neg / SIG=pos
        └─ fs_id_L2 : dims hermanas anuladas con * según ANOVA
```

Cada nivel deriva del anterior; «los levels son una manera de no perder mucha información y tener una dirección de reducción». Padres (`parent_fs_ids`): cada dim de nivel anulable con `*` — la familia para heredar y encoger.

## 5 · FASE 0 — Contrato, carga, acondicionado y referencia

*«Cargar, revisar, acondicionar y establecer referencia para comparar.» No se modifica un dato.*

**0.1 `load_and_validate`** — Config exhaustivo primero (P3). Carga SQL. Validaciones bloqueantes: columnas de licencias y de tasas presentes; periodo normalizado a mensual (imparseable = parar); dinero no negativo; revalorización ≠ 0 en históricos («renovar gratis no existe»); roles censados con alarma de rol vacío; mes en curso detectado y declarado («test incompleto: fuera del backtest y de la elección de método»).

**0.2 `split_and_key`** — Las **dos tablas**: vista-tasa (grano tasa, ratios recalculados) y tabla fina (grano completo con extras de revalorización). `fu_id`+`fu_key`, claves de la fina, lookups, conservación exacta, ids sin redundancia — reconstruible el raw original desde las dos.

**0.3 `assign_universe_and_routes`** — Universo (normal / time_series), patrón de cobertura, **ruta** (trainable / heuristic / no_impact) — como etiquetas (P4).

**0.4 `build_fu_summary`** — `forecast_units_raw_summary` por `fu_key`: soporte para la tasa (sin extras), **error binomial esperado** (p=0.5 como cota conservadora: el peor caso honesto), rol, mes en curso, universo, ruta, dinero. **La referencia inmutable.**

## 6 · FASE 1 — Rama renovación (el camino binomial)

**1.1 `build_series_and_gaps`** — `fs_id`+`fs_key`+lookup; padres. Relleno de huecos con sintéticas (medidas a 0 — «el mes vacío es un cero legítimo»), solo en trainable y solo dentro de la historia; rol heredado del mes real anterior; lookup **ampliado**. `forecast_series_raw_summary` por `fs_key`: soporte de la serie («los criterios de soporte emergen del promedio o la mediana de todas las units que forman la serie»), error binomial con tasa real, meses de historia, **huecos contados**, dinero.

**1.2 `diagnose_round1`** — Lo medible honestamente con el dato crudo:
- *Foto binomial*: distribución del error por serie en pp y $; cuánto dinero vive en series «que no tienen derecho a hablar solas».
- *Simpson medido, dos piezas sobre la referencia mandatory fija*: (a) **descomposición** del cambio de tasa en efecto-comportamiento y efecto-mezcla (recomposición con la mezcla antigua congelada — el what-if de la cantera); (b) **contrafactual en dólares**: walk-forward mes a mes, método plano vs método segmentado con la composición real de cada mes, ambos contra lo ocurrido → `celda × mes → error_plano, error_segmentado, ahorro_pp, ahorro_$`; solo se reclama ahorro donde supera la cota binomial de la celda. La cifra-titular: «cuánto nos habríamos equivocado si no hubiéramos usado las dimensiones adicionales».
- *ANOVA de evidencia*: η² ponderado (pesos = soporte) por cada extra_renovacion — **sin las timevarying**. 
- *Combinaciones* **[NUEVO — no implementado antes]**: η² de pares de extras (clave conjunta) comparado con sus individuales → interacción/sinergia; acotado a los top-k pares por dinero para no explotar. «Inicialmente usábamos las variables de manera individual; dijimos que había que ver la combinación — creo que no lo llegamos a implementar.»

→ Con esto, la **decisión humana de grano**: qué extras entran (η² alto), pagando el soporte que digan los números.

**1.3 `improve_support`** — Las tres mejoras, en orden:
- **L1 · signo a través de columnas**: las timevarying «no se agrupan de manera vertical en la misma dimensión, pero se pueden agrupar de otra manera»: dormant=sí se une con softcancel=sí y con no_instalado=sí «porque las dos serían negativas» → pool `SIG=neg` por celda estable; positivas aparte («será mucho más pequeño el segmento de las positivas»). Mandatory intactas siempre. *(Corrige la implementación anterior, que agrupaba por conjunto exacto de señales — con binarias, pools de uno.)*
- **L2 · asterisco por ANOVA**: para lo que siga pequeño, juntar hermanas anulando la dim de menos señal, siguiendo los levels; mandatory jamás, timevarying tampoco (ya en L1).
- **L3 · credibilidad**: «mezclar series pequeñas con otras más grandes y promediar» — no se mezclan filas: se mezcla la estimación. `tasa_final = z·propia + (1−z)·padre`, `z = n/(n+k)` — la fórmula de credibilidad actuarial (Bühlmann): frecuencia×severidad es exactamente tasa×uplift, y z es el factor de credibilidad. k calibrable como varianza-dentro/varianza-entre (pendiente con datos). Hacia el padre del mismo régimen. Cierra con destinos: habla-sola / reparada / encogida / polvo-hereda.

**1.4 `build_support_chain`** — El indicador por rondas: tabla `fs_key × etapa (0_raw/1_L1/2_L2/3_shrink)` con `id_efectivo, n_efectivo, error_pp, error_$` (sobre el dinero propio), `ganancia`, `actuó`. En la etapa 3 el error no viene de sumar n sino de la mezcla: `√(z²SE²propio+(1−z)²SE²padre)`; se añade el **n implícito** (invirtiendo la binomial) para leer toda la cadena en unidades de soporte. Agregados-titular: *waterfall del dinero bajo el suelo* por etapa; *atribución por estrategia*; y el impacto honesto — «para lo que tiene soporte no es necesario»: el % del dinero que nunca necesitó reparación también se cuenta.

**1.5 `diagnose_round2`** — El tiempo, sobre la base consolidada: historia suficiente (ciclo anual completo, continuidad; si no: heredar o esperar) y dinámica — estacionalidad y tendencia juzgadas contra la **cota binomial propia**; la tendencia que supere su ruido se proyecta **con saturación** (nunca por encima del techo ~95%). Veredicto `gate` por celda/serie: la primera pregunta que suspende, o apta-promedio.

## 7 · FASE 2 — Rama revalorización (el camino continuo)

Fundamento: «la revalorización es un porcentaje que se aplica sobre el valor que tenía anteriormente» y **el punto de partida determina el recorrido** — el cliente nuevo entra con descuento de captación, «toda la gente de primera vez tendrá un valor en torno a una media»: su renovación tiene un uplift grande y predecible (el aterrizaje). Se mide **condicionada a renovar** — solo renovadores; readquisición fuera. Consecuencia exacta: `revenue = pipeline × P(renovar) × E(uplift | renovó)` — descomposición condicional, sin supuestos de independencia. (Nota para su momento: al ser condicional, si cambia *quién* renueva cambia la mezcla de renovadores — el Simpson existe también en el valor y se mide con la misma maquinaria.)

**2.1 `uplift_fine`** — Estimación al grano más fino (grano uplift × lo que aporten extras), solo renovadores, uplift ponderado por dinero. **El n son los renovadores, no el pipeline** (pipeline 100 × tasa 60% → n=60): el soporte del valor es estructuralmente menor — la reparación aquí es aún más necesaria. Guardarraíles: uplift>0 siempre; saturación de negocio.

**2.2 `diagnose_uplift`** — Por celda: n, **s medida**, vara s/√n en % y $; ANOVA-uplift por eje (ranking propio — el descuento arrasará; región quizá calle) + combinaciones (mismo NUEVO de 1.2). Lectura: n bajo o vara ancha → no habla sola; **s alta con n decente → heterogeneidad interna**: falta un eje, o hay mezcla de puntos de partida dentro.

**2.3 `improve_uplift`** — Las mejoras adaptadas: (a) ejes mudos fuera del grano (el asterisco, versión valor); (b) **agrupar niveles**: el descuento continuo a intervalos (p.ej. 0 / 1–20 / 21–40 / 40+), price caps agrupados — el análogo de L1 por *proximidad de nivel en un eje ordenado*, no por signo; (c) **credibilidad hacia el padre del mismo punto de partida** — el pool de nuevos-con-descuento-alto, jamás el vecino veterano. Jerarquía de padres: marginalizar ejes en orden inverso de η² (primero cae el más mudo) → fino → ... → global.

**2.4 `build_uplift_chain`** — La cadena de ganancia simétrica a 1.4, con la vara continua.

## 8 · FASE 3 — Ensamblaje (esbozo; se detalla en próxima conversación)

Las dos ramas **ni se tocan ni lo necesitan** hasta aquí. El punto de unión es **la fila fina del pipeline futuro** — conocida, y con las dos llaves a la vez: su serie (→ tasa por la cadena propia→L1→L2→encogida) y su combinación de extras (→ uplift por la jerarquía del valor). «Dos lookups de medida contra el hecho atómico futuro», multiplicación fila a fila, agregación al grano que se quiera reportar:

```
fila futura            pipeline   tasa(serie)   uplift(comb)   esperado
A · descuento_alto      10.000$  ×   0,62    ×    1,45      =  8.990$
A · sin_descuento        5.000$  ×   0,62    ×    1,04      =  3.224$
```

La tasa es constante dentro del pool; el uplift varía dentro de cada serie según su composición futura. El ensamblaje estampa además las **etiquetas semánticas** configurables: un mapeo en config `condición sobre timevarying → etiqueta` (p. ej. `no_instalado=1 → «residuo»`) que permite agregar el forecast por calidad del revenue — «cuando un cliente no instala el producto y renueva porque se había olvidado, esa renovación es un residuo del modelo suscriptivo, no una renovación con intención». La etiqueta no mide intención (inobservable): la *define operativamente* por columnas observables, y esa definición queda escrita en config — discutible y versionable. El juez final: **backtest al grano de la celda mandatory** — promedio plano vs forecast por series reagregado con la composición futura conocida; el Simpson medido en 1.2 es la ganancia que el backtest debe confirmar («el análisis hace una predicción sobre sí mismo, y el backtest la juzga»). El mes en curso queda fuera. Después: forecast con el método ganador, proyección del año siguiente (con el componente de adquisición: «simular la adquisición y cómo renovaría»).

## 9 · La cantera — piezas del código anterior que merecen copiarse y adaptarse

*Regla: copiar y adaptar, jamás importar. Cada pieza con su especificación esencial para evaluar el fit.*

| Pieza (fichero actual) | Especificación esencial | Fit |
|---|---|---|
| ANOVA ponderada ad hoc (`_weighted_ss_total`, `_weighted_eta2`) | η² con pesos=soporte, sin librerías externas; SS-total precomputada | **Copiar-adaptar** a 1.2 y 2.2 (dos varas) |
| Motor de mezcla congelada (what-if de `step_6_add_story_columns`) | tasa reciente recompuesta con composición antigua; ventanas A/B = dos últimos años naturales completos; cota binomial como escala | **Copiar-adaptar** → descomposición Simpson de 1.2 |
| Precisión binomial (`step_2_add_binomial_precision`) | SE a grano mensual (no pooled) √(p(1−p)/n̄); z por bisección de erf (sin scipy); moe en pp y $ | **Copiar-adaptar** (núcleo de P1) |
| Colapso con conservación (`step_1_collapse_covariates`) | ratios recalculados del agregado; conservación exacta o parar; flag mes-curso viaja con max | **Copiar-adaptar** → 0.2 |
| Relleno de huecos (`step_1_fill_gaps`) | sintéticas a 0, solo trainable, solo dentro de historia, rol heredado | **Copiar-adaptar** → 1.1 |
| Padres con asterisco (`step_2_build_identity`) | anulación por levels, JSON de caminos | **Copiar-adaptar** → 1.1/1.3 |
| Credibilidad z=n/(n+k) (doctrina H2 + destinos de `classify_small_series`) | destino por evidencia; el dinero decide, no el censo | **Solo-spec** (reimplementar sobre ids nuevos) |
| L1 actual (`collapse_signal_support`) | ⚠ agrupa por conjunto exacto — **contradice la doctrina de signo**; `signo_por_col` calculado y sin usar | **Solo-spec** (la lógica nueva es por dirección) |
| Diagnóstico integral (`run_raw_diagnosis`) | fingerprint del dataset; heurística de pricing blindada con try/except | **Copiar-adaptar** parcial (secciones útiles a summaries) |
| Ejemplo dormant (`_example_dormant_split`) | el caso didáctico del coste de agregar | **Copiar-adaptar** (documentación viva) |
| `config_sqlserver.py` | write replace/truncate, fast_executemany, NVARCHAR(n) ajustado, chunks 50k, period→str+`period_date`, rechazo de objetos anidados | **Sobrevive tal cual** (+ `process_date` de P7) |
| Patrón prompt+eval | PROMPT reescrito a contrato de 5 secciones (los actuales «no están bien construidos» para regenerar); eval a 3 casos con `eval_harness.py` común | **Evoluciona** (P10) |

**Muere sin herencia**: el sistema de marks/run_metadata como API (lo sustituyen los summaries persistidos), los satélites en config (la fina es tabla de primera clase), el registro de 46 ficheros-step (lo sustituyen ~17 bloques), el drop físico, el nombre «covariables».

## 10 · Contrato de implementación limpia

Carpeta nueva. Funciones puras `(tablas, config) → tablas` + config exhaustivo + persistencia SQL/CSV por `config.write` (con `process_date` y `execution_id` automáticos). Un runner por fase. Prompts-contrato y evals-con-harness desde el primer fichero. **Estrategia recomendada: implementación de golpe de las fases 0–2 en una sesión limpia cuyo único contexto sea este documento** — con los mini-evals como red y una puerta de equivalencia selectiva contra la cantera donde aplique (conservación, binomial, mezcla congelada). Mejor una obra coherente que remiendos por piezas.

## 11 · Decisiones selladas (consolidado)

1. Claves = hash determinista int64; lookups por carga; sintéticos amplían. 2. `process_date` + `execution_id` en toda persistencia. 3. Config exhaustivo o excepción; muere el complemento. 4. Taxonomía de 4 grupos; muere «covariables»; extras solapables entre sí; exclusiones validadas al construir. 5. Raw inmutable: etiquetar, no amputar. 6. Filas nunca se consolidan; estimación estampada por miembro. 7. L1 por **signo a través de columnas** (neg con neg, pos con pos). 8. ANOVA sin timevarying. 9. Dinámica pospuesta a post-consolidación; dos tandas. 10. Un umbral: la referencia propia (binomial / s√n); constantes: suelo de soporte y techo ~95%. 11. Revalorización condicionada a renovar; n = renovadores; readquisición fuera. 12. Credibilidad hacia el padre del mismo régimen / mismo punto de partida. 13. `support_chain` y `uplift_chain` como tablas de ganancia por etapa. 14. Contrafactual Simpson en $ (walk-forward). 15. Análisis de combinaciones de variables (nuevo). 16. `gate` se queda en inglés. 19. Timevarying alimentadas por predictivos: histórico as-of, versión del modelo como bandera, calibración vía tasa realizada del pool. 20. Etiquetas semánticas configurables en el ensamblaje (p. ej. «residuo»). 17. Summaries persistidos joinables; reports se disuelven. 18. Implementación limpia en carpeta nueva; cantera congelada.

## 12 · Abierto para las próximas conversaciones

- Detalle de FASE 3+ (sobre el anexo §13; cada fase, su conversación con este documento como semilla).
- Intervalos concretos del descuento y calibración de k (con datos delante).
- Suelo de soporte: valor por defecto y si admite modo «auto» por backtest.
- Matriz de mapeo fina bloque-a-bloque si se quiere auditoría previa a la obra (opcional dada la estrategia de golpe).
- Doctrina de la serie **mixta** (señales activas de ambos signos, p. ej. softcancel+autorenew): ¿pool propio `SIG=neg+pos` o dominancia del negativo?
- Fase 4: ¿selección de técnica independiente por rama? ¿por-serie/celda guiada por gate+backtest o ganador global? ¿nombres «elegibilidad» y «banderas»?

## 13 · Anexo — pinceladas de las fases 3–6 (boceto consensuado, pendiente de detalle)

**FASE 3 · Ensamblaje.** Fila futura fina × dos lookups (tasa por cadena de serie; uplift por jerarquía de combinación) → `forecast_detail` al grano atómico, guardarraíles aplicados (techo de tasa, uplift>0), agregable a cualquier grano de reporting. Sin supuestos nuevos.

**FASE 4 · Backtest y selección de método.** Juez: celda mandatory, walk-forward con meses reservados, mes en curso fuera. **El `gate` de la tanda 2 es el selector de método** — apto_promedio→promedio; estacional→índice; tendencia→pendiente saturada — compitiendo contra el plano y contra un único método global. Error en $ ponderado por pipeline. El contrafactual Simpson de 1.2 es una predicción que este backtest debe confirmar.

**FASE 5 · Forecast.** Método ganador sobre el horizonte real, con bandas de incertidumbre **propagadas desde las varas propias** (SE del producto tasa×uplift). Tabla final para Power BI.

**FASE 6 · Proyección del año siguiente.** Dos componentes: la **cascada** (lo renovado hoy es pipeline de mañana — la recursión del forecast sobre sí mismo) + la **adquisición** (grano alto: nivel + índice estacional; composición fina por proporciones recientes; banda declarada más ancha; «simular la adquisición y cómo renovaría»).

**Transversal.** La película entre ejecuciones: evaluaciones y cadenas de ganancia en **append** con `execution_id` — comparar julio contra agosto es un group by.

---

## Anexo D — Nota didáctica sellada: el dato es exacto; lo que enseña, no

*(Texto consagrado de conversación, para explicar el error de fase 0 a terceros.)*

**El dato es exacto; lo incierto es lo que el dato *enseña*.** Tiraste una moneda 10 veces y salieron 8 caras. Como *hecho*, 8/10 es perfecto, indiscutible, sin error — ocurrió. Pero no queremos el hecho: queremos saber **cómo es la moneda**, porque es la moneda la que va a tirar otra vez el mes que viene. ¿Es una moneda del 80%? ¿Del 65% que tuvo suerte? ¿Del 90% con mala racha? Con 10 tiradas, cualquiera de esas monedas produce un 8/10 sin despeinarse. El dato es nítido; **la foto que el dato hace del mecanismo es borrosa** — y el `se` mide exactamente esa borrosidad.

La tasa de renovación **no es una propiedad del mes pasado; es una propiedad del *proceso*** (esa combinación de clientes, producto, precio) que el mes pasado solo *muestreó*. El 45% observado con n=8 es un hecho exacto — y un testigo poco fiable del proceso. El 80,3% con n=600 es igual de hecho — y un testigo excelente.

Por eso la misma fórmula sirve en las dos direcciones del tiempo:
- **FU pasada**: el `se` dice *cuánto me fío de este mes como testigo* de la tasa verdadera — lo que usan pools y credibilidad para ponderar quién habla.
- **FU futura**: el `se` dice *cuánto puede desviarse la realidad* de la tasa verdadera cuando el proceso vuelva a tirar sus monedas — el **error irreducible**: el que existiría aunque la tasa fuera perfecta; física del tamaño de la muestra, no ignorancia mejorable.

**La frase para terceros**: *«El pasado es exacto como registro y borroso como evidencia. Este número no duda de lo que pasó — mide cuánto puedes generalizar desde lo que pasó.»* La referencia de fase 0 separa así el error en sus dos mitades: la irreducible (esta tabla) y la reducible (donde el framework se juega el sueldo).

**Aterrizaje operativo** (cómo comunicarlo accionable): el `se` nunca se entrega desnudo — se entrega el **intervalo**: tasa ± moe (moe = z·se; z=1,645→90%), recortado a [0,100], y traducido a las dos monedas del negocio: puntos y dólares (moe_usd = moe% × pipeline$). En celdas minúsculas, mejor aún en **unidades**: «de las 4 licencias, renovarán entre 2 y 4 (90%)». El moe es métrica estándar de la estadística (el «±3 puntos» de las encuestas), no invención propia; lo nuestro es solo la elección del 90%, la versión peor-caso p=0,5 de fase 0 (cota estándar de planificación muestral) y su traducción a dólares. El intervalo es **simétrico y bilateral**: cuantifica por igual excederse y quedarse corto (la dirección del sesgo es asunto del backtest, fenómeno E3; la asimetría fina en tasas extremas, del monográfico de bandas).

---

## Anexo E — La tensión fundacional: por qué existe este framework (sellado de conversación)

El diseño entero nace de UNA tensión con dos facturas, ambas en dólares:

**Acto 1 — la enfermedad.** El método plano (una tasa agregada) miente cuando el mix rota: la tasa del agregado se mueve sin que ningún cliente cambie (Simpson, D4; mix-shift, D1). Factura medida: el **contrafactual Simpson en $** (en la primera ejecución real: $738.612 en 6 meses de walk-forward).

**Acto 2 — la cura y su efecto secundario.** Segmentar elimina la mentira del mix… y adelgaza las celdas: nace el **error binomial** del soporte fino. Factura medida: el dinero bajo el suelo en `fu_summary`/`support_chain` (primera ejecución real: $17,5M de $153,4M — el 11,4%).

**Acto 3 — la segunda medicina.** La maquinaria de reparación (L1 por signo, L2 asterisco, credibilidad, escalera de padres, herencia) devuelve soporte a lo segmentado sin renunciar a la segmentación.

**El principio operativo**: no se minimiza el error binomial a secas (su mínimo trivial es la celda única — el método plano que Simpson destroza) ni se segmenta sin límite (su límite es el polvo). Se minimiza el **error total = mezcla + muestreo**, eligiendo en cada celda la factura menor: el η² dice dónde la segmentación paga; el suelo (umbral NUESTRO, declarado — P1) dice dónde empieza a cobrarse; la reparación abarata esa factura donde hay que pagarla. La clasificación resultante — «adecuado» (habla solo) vs «necesita acondicionamiento» (habla en pool) — no es control de calidad: es el punto de operación pactado sobre la curva sesgo-varianza, escrito para ser discutible.

---

## Anexo F — El doble oficio de la vara y el factor φ (sellado 2026-08-15)

**Motivación (insight de conversación).** La cota binomial no solo dice *cuánto fiarse* de una tasa: la moneda pura predice **exactamente cuánto debe bailar** la tasa mes a mes si no está pasando nada — es la *hipótesis nula con números*, una referencia propia (P1: «un número mágico es discutible; una referencia propia, no»). Comparar el baile real contra ese aburrimiento convierte la vara en **detector de señal**.

**La descomposición.** Var(tasa observada) = Var(moneda: muestreo) + Var(proceso: la tasa moviéndose de verdad). La primera es computable exacta desde n y p; la segunda es la señal. El cociente:

> **φ = varianza observada / varianza de moneda** · φ≈1 → todo es muestreo («tu tasa no se mueve; se muestrea») · φ>1 → existe un motor real. **φ dice QUE hay motor; los gates dicen CUÁL** (¿dirección? → tendencia · ¿calendario? → estación · ¿escalón? → régimen · ¿sin que nadie cambie? → mix/Simpson).

**Frase de negocio que habilita**: «de los ±7pp que veis cada mes, ±5 son azar puro — nadie puede reducirlos — y el resto es la tasa moviéndose de verdad, que sí modelamos».

**El triple oficio, resumido**: la binomial es a la vez la humildad (cuánto no sé), el pasillo (cuánto es normal) y el timbre (cuándo pasa algo) — un cálculo, tres usos.

**La escalera de bandas** (cada peldaño más fino): 1· fase 0, peor caso z·50/√n → 2· fase 1, z·√(p̂q̂/n) → 3· calibrada, peldaño 2 × √φ → 4· residual: distribución empírica de errores del rolling por técnica y horizonte (el destino; monográfico de bandas).

**Implementación (misma fecha)**: `diagnostico_dinamica` incorpora `sd_obs_pp`, `sd_binom_pp` y `phi` por pool (varianza de moneda con el n de CADA mes: media de 1/n_t). φ se **mide**, no se aplica todavía — ensanchar bandas con √φ pertenece al monográfico. Hallazgo en la primera ejecución: un pool con tendencia real (φ=4,8) que el gate de pendiente dejó pasar como plano — φ como primera línea del diagnóstico caza motores que los tests específicos con umbral fijo pierden; refuerza el backlog de umbrales auto-calibrados por tensión.
