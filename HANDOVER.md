# SFF v2 — HANDOVER para nueva conversación
*Estado a 12 de septiembre de 2026. Léelo entero antes de tocar nada.*

---

## 0 · Cómo usar este documento

Este documento es el **punto de entrada** para retomar el proyecto en una conversación nueva. Contiene: qué es el proyecto, en qué estado exacto está, qué documentos y código existen, qué doctrina está sellada, qué discusiones hemos tenido (y qué se concluyó en cada una), las reglas de trabajo y vocabulario, y lo pendiente. Los documentos de detalle se referencian, no se duplican.

**Archivos que hay que adjuntar a la nueva conversación**: `sff_v2.zip` (el código completo, autoverificable), `DISENO_V2.md` (la fuente única de doctrina), este `HANDOVER.md`, y opcionalmente `CATALOGO_TECNICAS.md` y `CATALOGO_TABLAS.md`. Los transcripts completos de todas las sesiones están en `/mnt/transcripts/` con un `journal.txt` que los cataloga.

---

## 1 · Qué es el proyecto en una página

**SFF (Stratified Forecast Framework) v2** es un framework en Python para el **forecast de ingresos por renovación de suscripciones B2C** (empresa de ciberseguridad), construido por Miguel Ángel (BI/data analyst, lidera un equipo pequeño de analítica de renovación). Corre contra un extracto SQL Server (base `[Kamelot]`, ~600k filas, 33 columnas declaradas) y escribe **25 tablas en estrella** de vuelta a SQL con claves para reportar en Power BI desde el nivel de fila cruda hasta el forecast final.

**El problema esencial**: revenue futuro = pipeline conocido × tasa de renovación × revalorización. El pipeline (qué contratos vencen y cuándo) es DATO, no pronóstico. Lo que se predice son dos cosas: la **tasa** (rama binomial) y el **uplift** (rama continua: cuánto pagan los que renuevan respecto a lo que pagaban).

**La tensión fundacional** (Anexo E del diseño): agregar mucho → la tasa media miente cuando la composición interna rota (Simpson / mix-shift). Segmentar mucho → celdas con poco soporte y error binomial grande. El framework minimiza el **error total = mezcla + muestreo**, celda a celda, y ambas facturas se miden en dólares: el **contrafactual Simpson** (coste de agregar: $166.370 en 6 meses con la doctrina actual; $738.611 en la ejecución del 12 de agosto, pre-doctrina del mes en curso) y el **dinero bajo el suelo de soporte** (coste de segmentar: $21,2M de $173,3M, el 12%).

**El flujo** (5 fases + 1 previa + validación):
- **Fase P** (`fase_pre.py`, manual): buscador de escaparates Simpson para explicar el problema.
- **Fase 0**: contrato de columnas exhaustivo (columna no declarada = parar), validaciones bloqueantes, partición en dos tablas (fina con extras de precio / vista al grano de la tasa) con conservación exacta del dinero, universo/cobertura/ruta como etiquetas (nada se borra), y la **referencia inmutable** (`fu_summary`: error binomial peor-caso por celda-mes). Doctrina del mes en curso: pasa a projection y se limpia de resultados tempranos.
- **Fase 1** (rama renovación): series con relleno de huecos (tasa indefinida, no 0%), diagnóstico tanda 1 (foto binomial, contrafactual Simpson en $, ANOVA η² sin timevarying, pares), **tres estrategias de reparación de soporte** (L1: agrupar por signo de timevarying; L2: anular la dim extra de menor η²; L3: credibilidad z=n/(n+k) hacia el primer padre de la **escalera multinivel** que alcanza el suelo), support_chain (waterfall), diagnóstico tanda 2 (gates: soporte→temporal→estacional→tendencia→apto_promedio, y **φ** = varianza observada / varianza binomial esperada).
- **Fase 2** (rama revalorización): uplift = AUV renovado / AUV pipeline, condicional a renovar, ratio de sumas ponderado por $, ejes mudos anulados, credibilidad hacia el padre del mismo punto de partida.
- **Fase 3**: puente de claves (`key_bridge`) y ensamblaje (esperado = pipeline$ × tasa × uplift, fila a fila, con cascada de fallback trazada: serie→celda→global).
- **Fase 4**: backtest multi-origen con **15 técnicas** (T0-T14), campeón por pool con retadores T0/T2, rolling de fiabilidad a h=1,2,3 con cobertura de cota, bandas empíricas (p90 del error medido por técnica y horizonte), tablas por FU, informe de horizonte (degradación mes a mes, por serie y total).
- **Validación**: 19 checks (integridad, doctrina, calidad) persistidos en `validation_report`.

---

## 2 · Estado exacto del código (sff_v2.zip)

**12 módulos + 3 herramientas + modelo**: `config.py`, `synthetic.py`, `fase_pre.py`, `fase0.py`, `fase1.py`, `fase2.py`, `fase3_assembly.py`, `fase4_backtest.py`, `validation.py`, `main.py`, `eval_harness.py`, `equivalence_gate.py`, `smoke_multidim.py`, `generate_model.py`, `render_model.py`, carpeta `modelo/` (ERD en DBML/Mermaid/DDL/PNG/SVG), `raw_golden.csv`, `salida/sff_v2_golden.db`, `ASUNCIONES.md` (20 asunciones numeradas con motivación).

**Verificación** (todo en verde al cierre): `python eval_harness.py` → **EQUIVALENCE GATE 25/25 PASS** contra golden; `python smoke_multidim.py` → **SMOKE PASS** (prueba con varias dims obligatorias); `python main.py --golden` → panel de validación 19 checks, 0 FAIL.

**Estándar de código (contractual, PROMPT_OBRA regla 0)**: identificadores en inglés autoexplicativos (prohibidos `g`, `v`, `e2`, `qual`, `modo`, `fisico`, `nombre` y genéricos de forma); docstrings, comentarios y consola en **inglés**; cada función con GOAL/INPUT/OUTPUT/STEPS numerados y los `[N]` **espejados como comentarios en el cuerpo**; asserts con diagnóstico (filas, dinero, ejemplo, culpable); constantes con nombre; una sentencia por línea. **Excepción**: nombres de columna y valores persistidos siguen en español (`tasa`, `celda`, `gu`, `soporte`, `apto_promedio`...) porque son contrato del golden y del BI.

**Config** (`Config()` sin argumentos = producción): nombres de columna del notebook del usuario (`pipeline_units_col="total_tr_units"`, etc.), 10 mandatory `tr_*` (regional_1/2/3, product_1/2, origin_type_SKU_based, term_1/2, band_1/2), `structural_timevarying_dims={"softcancel":"negative"}`, `extra_revalorizacion=[price_cap, msrp_increased, discount_interval, prev_OperationGroup]` (antiguas covariate_cols — la palabra "covariables" está PROHIBIDA), `ignore_cols`, `semantic_labels=[]` (vacío a propósito), `gap_rate_policy="no_rate"`, `support_floor=30`, `z=1.645`, `rate_cap=0.95`, `k_cred=60`, `k_uplift=24`. Persistencia SQL con SQLAlchemy: `sql_schema` como dato, registro de nombres físicos `_NOMBRES` con prefijo `sff_`, modos `replace`/`truncate` (TRUNCATE real, DELETE solo fallback), `fast_executemany` forzado por evento en el cursor para cualquier engine, cronómetro filas/s.

**Rendimiento**: ids vectorizados (`join_columns`, x16 vs fila a fila); ~14.000 filas/s en escrituras; el puente (647k filas) tardó 103s en Kamelot — candidato a optimizar.

---

## 3 · Documentos y para qué sirve cada uno

| Documento | Qué es |
|---|---|
| **DISENO_V2.md** | FUENTE ÚNICA de doctrina: 10 principios, taxonomía de 4 grupos, cadena de ids, fases 0-3 detalladas, cantera, 20 decisiones selladas (§11), abiertos (§12), anexo fases 3-6, y los **Anexos D/E/F** (nota didáctica del error, tensión fundacional, doble oficio de la vara y φ). |
| **CATALOGO_TECNICAS.md** | 17 técnicas T0-T17 con elegibilidad, los 24 fenómenos en 6 familias (A-F) mapeados a quién los trata, doctrina de horizonte (§3). |
| **CATALOGO_TABLAS.md** | Las 25 tablas en orden de escritura, grano, y el análisis que soporta cada una. Arco narrativo. |
| **FASE0_LECTURA.md** | Lectura literaria e inductiva de la fase 0 (qué concluye cada bloque). Primera de una serie por fase. |
| **PROMPT_OBRA.md** | El prompt de sesión de obra con el estándar de código y la puerta de equivalencia como cierre exigido. |
| **ASUNCIONES.md** (en el zip) | 20 asunciones numeradas: cada divergencia intencionada con su motivación y fecha. |
| RATIONALE.md / IMPLEMENTATION.md / DECK.md | Superficies Minuteman del v4 (cantera). RATIONALE contiene el catálogo original de los 24 fenómenos. |
| EL_RAZONAMIENTO.md / PLAN_FASES.md | SUSTITUIDOS por DISENO_V2. Históricos. |
| simpson_showcase.sql / simpson_contrafactual_repro.sql | T-SQL puro para reproducir el buscador de escaparates y el contrafactual (con query de verificación contra la tabla del framework). |
| Gráficos y scripts didácticos | `fu_30_vs_100.png` (banda por tamaño de muestra), `binomial_pmf_100.png`, `band_vs_n.png` (ley 1/√n), `tolerance_dial.png` (dial de tolerancia), `simpson_softcancel.png` (dos paneles: paradoja y trampa del snapshot). Scripts `.py` parametrizados junto a cada uno. |

---

## 4 · Las discusiones y lo que se concluyó (exhaustivo, cronológico)

### 4.1 Diseño v2 (julio-agosto)
- **Muere «covariables»**: 4 grupos de variables — mandatory (nunca se colapsan en pools), timevarying con signo (neg/pos: dicotómicas que rotan solas con el calendario, p.ej. softcancel), extra_renovacion, extra_revalorizacion. Solapables.
- **Dos ramas, dos errores** (P2): binomial √(p(1−p)/n) para la tasa; s/√n̄ para el uplift, con n = renovadores.
- **P1**: «un número mágico es discutible; una referencia propia, no». Los umbrales se comparan contra la cota binomial propia de cada pool, nunca contra números fijos.
- **P5**: el cálculo se hace con el pool; el resultado se estampa en cada miembro. **P6**: estimación ≠ aplicación (el pool es de dónde sale el número, no a qué se aplica).
- **Levels**: la jerarquía `_level_1/2/3` da el orden de colapso DENTRO de familia (cae primero el más fino); ENTRE familias decide la evidencia (η²). Actúan en la escalera de padres, NUNCA en L1/L2 (mandatory intocable en pools).

### 4.2 Obra e implementación (agosto)
- Prototipo → refactor profesional con puerta de equivalencia (el golden se regenera solo cuando el cambio es intencionado y se declara en ASUNCIONES). El usuario criticó nombres crípticos y mezcla de idiomas → regla 0 del PROMPT_OBRA; luego pidió todo el texto en inglés.
- Persistencia SQL por fase; el usuario reportó writes lentos → `fast_executemany` a nivel de cursor; luego "¿puede bloquear el servidor?" → doctrina de locks (escalado, replace vs truncate, staging+swap ofrecido no implementado), y se descubrió/corrigió que `truncate` hacía DELETE.
- Puente de claves (`key_bridge`) para reportar desde el raw; el usuario verificó cardinalidades (fact_fu 1:N fact_fine por combinaciones de descuento).

### 4.3 Doctrina del mes en curso (agosto)
- Primero: excluido del backtest por partida doble. Después (decisión del usuario): **pasa a projection**, es el primer mes a proyectar, se limpian renovaciones/readquisiciones de todo projection, se imprime resumen. Golden regenerado. Consecuencia: el contrafactual bajó de $738k a $166k — el número honesto.

### 4.4 Explicaciones del error binomial (agosto) — Anexo D
- se vs moe (1σ vs banda al 90%); pp vs %; `_max` = peor caso p=0,5; se=50 ⇔ n=1.
- **«El dato es exacto; lo que enseña, no»**: la tasa es propiedad del PROCESO, el mes la muestrea. Hacia atrás el se mide fiabilidad como testigo; hacia adelante, variación natural. **Error irreducible** vs reducible.
- El suelo de 30 ≈ ±15pp NO es promesa de calidad sino umbral de admisión; la estimación puede ser precisa (viene del pool) aunque la realización del mes baile; y al agregar, los errores se combinan en **cuadratura** (√Σmoe², nunca suma) — 100 celdas de n=30 dan ±1,6pp.
- Dentro de la banda la plausibilidad es una campana (los bordes son 4× menos verosímiles que el centro). Ley 1/√n: cuadruplicar la muestra reduce la banda a la mitad.
- **Dial de tolerancia**: τ ↔ n_min = (z·50/τ)² — ±15pp↔30, ±5pp↔271, ±3pp↔752. Negocio elige τ y seguridad (dos números, no uno).
- **El doble oficio de la cota** (Anexo F): mide cuánto te fías Y detecta señal — φ>1 significa que hay motor (estación, tendencia, régimen, mezcla); los gates dicen cuál. Implementado como columnas `phi`, `sd_obs_pp`, `sd_binom_pp` en `diag_dinamica`. En Kamelot: φ mediana 2,76, 1.461 pools con φ>1,5.
- Agregar por tiempo (medias móviles, promedio histórico) es la cuarta estrategia de reparación de soporte, con el mismo trade-off: ganas n de meses, pagas sesgo temporal; los gates y el backtest arbitran.

### 4.5 Simpson y el contrafactual (agosto-septiembre)
- **Anexo E** (tres actos): Simpson es la enfermedad, segmentar la cura, el polvo el efecto secundario, la maquinaria la segunda medicina.
- El contrafactual: por celda mandatory × mes-examen (últimos 6 con verdad), PLANO = tasa agregada histórica ≤t−1; SEGMENTADO = tasas por serie ≤t−1 recombinadas con los pesos REALES del mes t (legítimo: el pipeline es dato); ambos contra la verdad; `ahorro = (|err_plano|−|err_seg|)×pipeline$`, **suma neta con signo** (los negativos cuentan), más `% de celdas-mes donde gana el segmentado` como métrica de robustez.
- **Explicación motivacional nivel bachillerato** escrita y aprobada (la media de la clase, los que avisaron que se van renuevan al 20%, la composición cambia sola con el calendario, la composición futura la conocemos). Pendiente de sellar como Anexo G.
- Búsqueda de escaparates visuales: `fase_pre.py` y su gemelo T-SQL. Con `softcancel` congelado a 1-ene no se encuentra Simpson limpio: los subgrupos no salen planos por construcción (contaminación de maduración). Conclusiones: (a) el argumento fuerte con esos datos es **la trampa del snapshot** (proyección vs realidad: el softcancel del futuro aún no ha llegado; justifica timevarying + histórico as-of, decisión 19); (b) probar otros ejes: `net_new` (η²=0,417, atributo fijo) y `tr_product_level_1`; (c) la promesa correcta no es «paradoja» sino **descomposición mix vs comportamiento** (Δ = efecto mix + efecto comportamiento), respaldada por literatura FP&A: la versión fuerte es rara, la débil (distorsión) es común. En Kamelot: mix explicaba +10,5pp y el agregado subió +8,4 → comportamiento −2.
- El usuario corrigió: los datos de 2025 SÍ contienen los resultados reales; lo incompleto es la FOTO del estado, no el resultado. De ahí la curva de maduración extraíble: cuota_pendiente(h) ≈ (tasa_limpio_maduro − tasa_limpio_asof(h)) / (tasa_limpio_maduro − tasa_soft).
- Simpson vive en dos pisos: por encima de las mandatory (los totales de reporting → mezcla congelada) y por dentro (softcancel → grano de tasa + pools SIG).

### 4.6 Power BI (agosto-septiembre)
- Relaciones: fact_fine↔key_bridge (1:1, `fu_comb_key`), luego unidireccionales desde el puente. Dinero siempre de la fina. Bandas en cuadratura (`SQRT(SUMX(...^2))`), jamás suma.
- Uplift observado en DAX: ratio de sumas con AUV **por fila dentro del SUMX**, filtro `ren_units>0`; nunca promedio de ratios. Identidad de control: ren_usd/tr_usd = tasa_unidades × uplift.
- Mock de página fu_summary (dial, foto binomial, scatter soporte vs $ en riesgo).
- Lección de la sesión de gráficos: sin el slicer aplicado y con `Sum` sobre varias celdas, las tasas no significan nada.

### 4.7 Ejecuciones reales contra Kamelot (agosto-septiembre)
- 12-ago (pre-doctrina): 10.216 series, 34.014 sintéticas, 8.529 bajo suelo ($17,5M/$153,4M), contrafactual $738.611, η² regional_3 0,423 / purchase_type 0,409 / net_new 0,41, waterfall se quedaba en $5,5M sin reparar (→ motivó la escalera multinivel).
- Sep (versión completa): 10.128 series, 34.023 sintéticas con `no_rate`, $21,2M/$173,3M bajo suelo (88% nunca necesitó reparación), contrafactual $166.370, escalera: 1 peldaño (band_level_2) basta para el 100%, waterfall → $0, φ mediana 2,76, 1.176 pools estacionales. **Fase 2: rango de uplift [0,04, 466,33] — el 466× es un artefacto de datos pendiente de investigar** (`SELECT TOP 20 * FROM sff_uplift_chain WHERE uplift > 5 ORDER BY uplift DESC`). Fase 3 falló con NaN por el bug de parseo posicional (corregido, ver asunción 19); **la ejecución quedó por completar desde fase 3**.

### 4.8 Bugs cazados (todos documentados en ASUNCIONES)
- `region="NA"` leído como NaN por `read_csv` (Norteamérica) → `keep_default_na=False`.
- Columnas duplicadas en el puente (mandatory en grano_uplift y sueltas) → `uplift_cell_key` no casaba.
- Parseo posicional `str[0]` de la celda mandatory (funcionaba con 1 dim) → `smoke_multidim.py`.
- Mes en curso contaminando la selección de técnicas.
- Sintéticas con tasa 0% (→ `gap_rate_policy`).
- `truncate` que hacía DELETE.

---

## 5 · Reglas de trabajo vigentes

- **Idioma**: conversación en español; código, docstrings, comentarios y consola en inglés; columnas y valores persistidos en español (contrato).
- **Lenguaje técnico directo** en las explicaciones (petición explícita del usuario, 12-sep). Las metáforas (la moneda, bailar, el polvo, la vara, hablar solas, pool) solo si están acordadas y se usan consistentemente. Pendiente: glosario único metáfora ↔ término técnico.
- **Vocabulario prohibido**: covariables (→ extra_renovacion/extra_revalorizacion), corrida (→ ejecución), insumo, masa.
- **Respuestas por partes** cuando el usuario revisa; el usuario valida cada parte.
- **Puerta de equivalencia obligatoria** tras cualquier cambio de código; el golden se regenera solo con divergencia intencionada declarada en ASUNCIONES.
- **El usuario quiere cerrar una iteración completa** antes de seguir mejorando: «si no, estaremos siempre analizando sin saber cuánto mejoramos».
- El usuario ha señalado que el proyecto **acumula demasiado**: priorizar consolidación sobre nuevas piezas.
- Nunca decir que se hizo algo sin haberlo verificado; un turno anterior salió vacío una vez y el usuario lo notó.

---

## 6 · Pendiente, por prioridad

1. **Completar la vuelta en Kamelot** desde fase 3 con el `fase3_assembly.py` corregido; leer el panel de validación; leer `horizon_report_total`.
2. **Investigar el uplift 466×** (artefacto de datos: unidades de pipeline ~0 o migraciones de producto con precio de llegada no comparable). Posible guardarraíl: `uplift_cap` configurable + check en validación (ya existe «uplift en rango plausible»).
3. **Optimizar `key_bridge`** (103s para 647k filas; sospechoso: merges/drop_duplicates sobre strings). Palanca: `category` en dimensiones.
4. **Glosario único** de metáforas acordadas ↔ términos técnicos.
5. **Sellar Anexo G** (explicación motivacional de Simpson nivel bachillerato) y continuar la serie de "lecturas" por fase (FASE1_LECTURA...).
6. Buscar escaparate Simpson con `net_new` / `tr_product_level_1`; o montar la slide de la trampa del snapshot con la curva de maduración.
7. Backlog de diseño: `staging_swap` como patrón de carga con BI vivo; φ como palanca (banda × √φ); test estacional con varios años (cota/√años); Wilson/Clopper-Pearson para n minúsculo; fases 5-8 (adquisición, proyección año siguiente); pasar el catálogo de técnicas a `tecnicas.py` cuando crezca.
8. Refactors SFF del backlog del usuario: output contracts, density_money canónica, aggregation_cost a Power BI.

---

## 7 · Cómo arrancar la nueva conversación

Sugerencia de primer mensaje: *«Adjunto HANDOVER.md, DISENO_V2.md y sff_v2.zip. Léelos. Estamos cerrando la primera iteración completa contra Kamelot: la ejecución falló en fase 3 (ya corregido) y quiero completarla, leer la validación y el informe de horizonte, e investigar el uplift de 466×. Lenguaje técnico directo, sin metáforas no acordadas. Puerta de equivalencia tras cada cambio.»*
