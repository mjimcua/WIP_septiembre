# CATÁLOGO DE TÉCNICAS × FENÓMENOS — insumo de diseño para la FASE 4

*SFF v2 · borrador para discusión. Dos piezas: (1) el catálogo escalonado de técnicas de proyección, de lo rudimentario a lo sofisticado, con sus requisitos; (2) el catálogo de los 24 fenómenos (recuperado íntegro de la guía anterior) mapeado a qué técnica o mecanismo del framework lo trata. Cierra con la doctrina de horizonte.*

---

## 1 · Catálogo de técnicas (tasa de renovación; el uplift usa el mismo escalón con su vara)

*«Elegibilidad»: lo que la serie debe tener para que la técnica pueda aplicarse — el filtro duro previo al backtest.*

| ID | Técnica | Qué hace | Elegibilidad mínima | Dónde brilla | Contras / riesgos |
|---|---|---|---|---|---|
| T0 | **Naive último mes** | proyecta el valor del mes anterior | 1 mes | h=1 en series estables; el retador universal barato | ciego a estación y tendencia; arrastra outliers |
| T1 | **Naive estacional** | proyecta el mismo mes del año anterior | 13 meses | h cualquiera con estación fuerte y nivel estable | ciego a tendencia; un mal año se repite |
| T2 | **Promedio histórico** | media de toda la historia | 3 meses | series planas y ruidosas (el gate apto_promedio) | diluye cambios recientes; ciego a todo lo temporal |
| T3 | **Media móvil k meses** (3/6) | media de la ventana reciente | k meses | nivel que deriva despacio | elige k a mano; retardo ante cambios |
| T4 | **Recencia-ponderada (EWMA)** | media con pesos decrecientes hacia atrás | 3 meses | cambio de régimen reciente (A2): olvida el pasado | half-life a calibrar; sin estación |
| T5 | **Drift** | último valor + pendiente media histórica | 6 meses | tendencia suave sin estación, h corto | extrapola línea recta: exige saturación |
| T6 | **Promedio mismo-mes** | media de cada mes a través de los años | 24 meses (2 ocurrencias/mes) | estación estable multianual | hambriento de historia; ciego a tendencia |
| T7 | **Nivel reciente × índice estacional** | nivel de los últimos meses corregido por índice mensual | 13 meses | estación + nivel que se mueve; barato y explicable | índice ruidoso con 1 solo año |
| T8 | **Tendencia lineal saturada** | regresión temporal con techo (~95%) y suelo | 12 meses | pendiente sostenida (A1) que supere su cota | sin estación; peligrosa sin el techo |
| T9 | **Suavizado exponencial simple (SES)** | nivel adaptativo óptimo | 6 meses | T4 con α ajustado por sí mismo | sin tendencia ni estación |
| T10 | **Holt amortiguado** | nivel + tendencia que se atenúa hacia el futuro | 18 meses | tendencia real que no debe extrapolarse infinita | dos parámetros; necesita historia decente |
| T11 | **Holt-Winters** | nivel + tendencia + estación, y los **reporta** | 24 meses | la prioridad declarada: series homogéneas con historia — banderas gratis | tres parámetros; frágil bajo 2 ciclos |
| T12 | **SARIMA** | autocorrelación + estación + tendencia | 36 meses | h medio/largo en series largas y ricas | artillería: coste, fragilidad, difícil de explicar |
| T13 | **Croston / intermitentes** | separa "¿hay evento?" de "¿cuánto?" | series con muchos ceros | pools intermitentes que L1 no resolvió | nicho; raro tras la reparación de soporte |
| T14 | **Credibilidad temporal** | z·reciente + (1−z)·histórico, z=n/(n+k) | 6 meses | la casa: la misma credibilidad, aplicada al tiempo | k a calibrar; sin estación |
| T15 | **T-herencia (del padre)** | la serie joven usa la proyección de su padre, reescalada a su nivel si lo tiene | padre elegible | series nuevas/cortas: nadie queda sin técnica | hereda también los errores del padre |
| T16 | **Composicional desde-abajo** | Σ composición futura conocida × tasa de cada régimen (el ensamblaje como técnica de celda) | ramas resueltas | celdas con mix cambiante (D1–D4): nuestra ventaja estructural | tan buena como sus tasas de régimen |
| T17 | *(opcional)* Descomposición con changepoints (tipo Prophet) | aditivo nivel+estación+quiebres | 24 meses + librería externa | series largas con quiebres múltiples | dependencia externa — contra la doctrina de cantera |

Notas: (a) toda técnica que proyecte tasa pasa por los **guardarraíles** (clip a 1.0; aviso >0.85–0.95); (b) para el **uplift**, el escalón es el mismo con su vara (s/√n̄) y su rey suele ser el punto de partida — muchas combinaciones serán T2/T14 y pocas necesitarán T11; (c) el catálogo vive en `dim_tecnica`; añadir una técnica es añadir filas en el backtest, no columnas.

## 2 · Los 24 fenómenos (recuperados de la guía) y quién los trata

*Seis familias: A tasa · B volumen · C uplift · D composición · E método · F agregado. Las tres primeras son los tres factores del valor esperado; las tres últimas, transversales.*

**Familia A — Cambios en la tasa de renovación**

| ID | Fenómeno | Lo trata / lo detecta |
|---|---|---|
| A1 | Trend gradual del rate | T8/T10 lo modelan; T0/T2 lo sufren · bandera de tendencia (tanda 2, contra cota propia) |
| A2 | Regime change reciente | T4/T9/T14 (recencia) lo absorben; promedios largos lo sufren · bandera «cambio reciente no estacional» (el reciente vs mismo-mes de años previos) |
| A3 | Volatilidad alta del rate | promedios largos (T2/T6) la domestican; naives la sufren · la propia vara binomial la mide |
| A4 | Estacionalidad del rate | T1/T6/T7/T11/T12 · bandera estacional (amplitud > cota) |
| A5 | Outliers del rate | ninguno lo modela: se detecta (|z| vs cota) y se decide — bandera + posible winsorización declarada |

**Familia B — Cambios en el volumen de pipeline** — *en renovación, el volumen futuro es CONOCIDO (se lee del pipeline): B1–B4 no se predicen, se heredan del dato. Reaparecen como problema real solo en la fase de adquisición/proyección extendida (fase 6), donde el volumen sí se modela (nivel + índice estacional).*

**Familia C — Cambios en el AUV / uplift**

| ID | Fenómeno | Lo trata / lo detecta |
|---|---|---|
| C1 | Trend del AUV | escalón de técnicas del uplift (T8 saturada sobre uplift) |
| C2 | Shock de AUV de duración limitada | recencia (T4) + bandera de shock; no extrapolar el pico |
| C3 | Drift del uplift | la rama entera de revalorización existe para esto: punto de partida + jerarquía |
| C4 | Outliers del AUV | como A5, con la vara continua (s/√n̄) |

**Familia D — Cambios en la composición (mix)**

| ID | Fenómeno | Lo trata / lo detecta |
|---|---|---|
| D1 | Mix shift entre grupos | **T16 estructuralmente**: la composición futura es conocida |
| D2 | Crecimiento de un comportamiento direccional | las **timevarying con signo**: el pool SIG=neg crece y el forecast se degrada correctamente |
| D3 | Cambio adquisición vs renovación | fuera del alcance de renovación; fase 6 |
| D4 | Paradoja de Simpson | el **contrafactual en $** (1.2) la mide; T16 la neutraliza |

**Familia E — Capacidad del método** — *es la FASE 4 entera:*

| ID | Fenómeno | Lo trata |
|---|---|---|
| E1 | Generalización a test | walk-forward con meses reservados; mes en curso fuera |
| E2 | Cobertura de la banda | calibración empírica: ¿el 90% cubre el 90%? (monográfico de bandas) |
| E3 | Sesgo del método | error medio (con signo) por técnica en `backtest_predictions`, no solo error absoluto |
| E4 | Fiabilidad del portfolio | el mapa: % del dinero en series/celdas con técnica fiable vs herencia/polvo |

**Familia F — Riesgos al revenue agregado**

| ID | Fenómeno | Lo trata |
|---|---|---|
| F1 | Atribución del cambio | la descomposición tasa/volumen/precio/mix (mezcla congelada + factores) |
| F2 | Riesgo de la cola de pequeños | `support_chain`: el polvo residual, cuantificado en $ |
| F3 | Concentración del top | summary por serie: cuota de dinero (k_share) — se hereda del H1 |
| F4 | Bandas agregadas | cuadratura √Σmoe² con independencia declarada (monográfico de bandas) |

*(La guía los cuenta como veinticuatro; el recuento por familias da 25 — A tiene cinco. Se conserva tal cual y se corrige el titular al implementar.)*

## 3 · Doctrina de horizonte

«Cuanto más alejados en el tiempo, más difíciles de predecir y más error»: el backtest mide el error **por horizonte h** (h=1, 2, 3…), no solo global — y el campeón puede cambiar con h: T0 suele ganar h=1 en series estables; la estación y los modelos temporales pagan en h=3–6. Consecuencia de diseño: `backtest_predictions` lleva columna `h`, y la selección es por `(elegibilidad, gate, h)` con el plano (T2) y el naive (T0) como retadores permanentes — una técnica solo gana donde bate a los baratos por más que la cota.

## 4 · Lo que este catálogo deja decidido de facto y lo abierto

Decidido de facto: elegibilidad como filtro duro previo · banderas como apellidos del número · T-herencia cierra el "no siempre tendremos histórico" · guardarraíles universales · formato largo con `dim_tecnica`. Abierto (fase 4): selección por rama independiente (voto: sí) · por-serie/celda vía gate+backtest vs ganador global (voto: por gate, retadores permanentes) · política de outliers (¿winsorizar con bandera o dejar?) · el subconjunto inicial de técnicas para la v1 (propuesta: T0–T2, T4, T7, T8, T11, T14, T15, T16 — diez; T12 y demás, cuando el volumen de datos las legitime).
