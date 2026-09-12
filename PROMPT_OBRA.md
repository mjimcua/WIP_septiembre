# PROMPT DE OBRA — implementación limpia SFF v2 (fases 0–2)

*Copiar todo lo que sigue como primer mensaje de una sesión nueva, adjuntando: (1) DISENO_V2.md [obligatorio], (2) sff_v4_steps_hito1.zip [opcional: la cantera].*

---

Eres el implementador de la versión 2 del framework de forecast de renovaciones SFF. Vas a construir, **de golpe y en limpio**, las fases 0, 1 y 2 descritas en el documento adjunto `DISENO_V2.md`, que es tu **única fuente de diseño**: contiene el problema, los 10 principios, la taxonomía de variables, la cadena de identificadores, el detalle de cada fase, la cantera de código reutilizable, las 18 decisiones selladas y lo que queda fuera de alcance. Léelo entero antes de escribir una línea. No hay más contexto que ese documento y este prompt; si algo no está en ellos, no existe.

## Qué construyes

Un pipeline que parte de un dataset de renovaciones (en producción se lee de SQL Server; en desarrollo, de un dataset sintético que también construirás) y produce:

- **Fase 0**: config exhaustivo validado, las dos tablas (vista-tasa y tabla fina), claves hash + lookups, etiquetas de universo/cobertura/ruta, y `forecast_units_raw_summary` — la referencia inmutable.
- **Fase 1 (rama renovación, error binomial)**: series con huecos rellenos y su summary; diagnóstico tanda 1 (foto binomial, Simpson medido —descomposición + contrafactual en $—, ANOVA sin timevarying, combinaciones de variables); las tres mejoras de soporte (L1 por signo a través de columnas, L2 por asterisco, credibilidad z=n/(n+k)); `support_chain` con la ganancia por etapa; diagnóstico tanda 2 (historia y dinámica con saturación) sobre la base consolidada.
- **Fase 2 (rama revalorización, error s/√n̄)**: uplift fino sobre renovadores; su diagnóstico (n, s medida, vara, ANOVA-uplift, combinaciones); sus mejoras (ejes mudos, intervalos, credibilidad al mismo punto de partida); `uplift_chain`.

Todas las tablas nombradas en el documento se **persisten** vía `config.write` (con `process_date` y `execution_id` automáticos), joinables por sus keys.

## Estructura de ficheros — OBLIGATORIA

Nada agolpado. Reparto exacto:

```
sff_v2/
├── config.py            # Config exhaustivo: taxonomía de 4 grupos, validación-o-excepción,
│                        #   read()/write() con process_date + execution_id
├── config_sqlserver.py  # Subclase de escritura SQL Server (adaptada de la cantera)
├── synthetic.py         # Generador del dataset sintético v2 (ver sección siguiente)
├── eval_harness.py      # Andamiaje común de mini-evals (config de juguete, encadenadores, asserts)
├── fase0.py             # Bloques 0.1–0.4 como funciones
├── fase1.py             # Bloques 1.1–1.5 como funciones
├── fase2.py             # Bloques 2.1–2.4 como funciones
└── main.py              # Punto de entrada: construye config, lee (SQL o sintético),
                         #   ejecuta fases en orden, imprime el resumen de cadenas de ganancia
```

Cada función de fase lleva su **prompt-contrato** como docstring con las cinco secciones del documento (ENTRADA · SALIDA · REGLAS numeradas · BORDES · REGISTRO), escrito para poder regenerar la función sin ver el código. Cada `faseN.py` ejecuta bajo `__main__` los mini-evals de sus bloques (tres casos por bloque: control / edge / frontera) apoyándose en `eval_harness.py` — unas ~15 líneas por bloque, no más.

## El dataset sintético v2 — primero

Antes de las fases, construye `synthetic.py`: un generador cuyo propósito es **ejercitar todas las features del framework**. Incluye en su docstring una **matriz de cobertura** feature → escenario que la provoca. Como mínimo:

| Feature | Escenario sintético |
|---|---|
| Config exhaustivo | una columna extra opcional para probar la excepción |
| Conservación del split | extras de revalorización con varias combinaciones por FU |
| Universos y rutas | series normal y time_series; full / train_only / projection_only |
| Huecos | series con meses ausentes dentro de su historia |
| L1 por signo | ≥2 columnas timevarying negativas binarias (dormant, softcancel) con series pequeñas que SOLO cruzan el suelo al unirse por signo; alguna positiva minoritaria |
| L2 por asterisco | una extra_renovacion con η² alto y otra muda; hermanas pequeñas |
| Credibilidad | series ínfimas con padre gordo del mismo régimen |
| Simpson / contrafactual | una celda mandatory cuyo mix cambia en el tiempo (segmentos estables, pesos que rotan) |
| Combinaciones | dos extras cuyo efecto conjunto supere la suma de individuales |
| Uplift / punto de partida | clientes nuevos con descuento de captación (aterrizaje: uplift alto) vs veteranos planos; descuento con niveles para probar intervalos |
| Dinámica | una serie con estacionalidad clara y otra con tendencia que debe saturar contra el techo |
| Mes en curso y roles | flag de mes en curso etiquetado test |

Parámetros con semilla; tamaño pequeño por defecto (rápido para evals) y modo `grande` para pruebas de volumen.

## Reglas de trabajo

0. **Estilo de código (contractual)**: identificadores —variables, funciones, columnas internas— en **inglés**, profesionales y autoexplicativos (`series_summary`, `eta2_by_dim`, `uplift_cells`; prohibidos `g`, `v`, `e2`, `cf` y abreviaturas crípticas); **prohibidos también los nombres genéricos que describen la forma y no el papel**: no `nombre`/`name`, `modo`/`mode`, `fisico`, `qual`, `data`, `df2`, `tmp`, `aux`, `result` — sí `logical_table_name`, `physical_table_name`, `write_mode`, `qualified_table_name`, `renewal_rate_series`. Prueba del algodón: leído fuera de contexto, el nombre debe decir qué contiene y para qué sirve. Docstrings, comentarios y mensajes de consola en **inglés** (decisión [U] posterior: todo el texto del código en inglés); banners de sección (`# ─── NOMBRE ───`) organizando cada módulo; una sentencia por línea; números mágicos como constantes con nombre o parámetros de config; type hints en toda función pública; docstring-contrato de cinco secciones en cada bloque. El código se escribe para el mantenedor de dentro de un año, no para el que lo genera hoy.
1. **Vocabulario**: jamás «covariables» (usa `extra_renovacion` / `extra_revalorizacion`); jamás «corrida» (usa «ejecución»); jamás «insumo» o «masa» (usa «pipeline» / «valor conservado»). `gate` se queda en inglés.
2. **Cantera**: si se adjunta el zip anterior, las piezas marcadas «copiar-adaptar» en §9 del documento se copian y adaptan al diseño nuevo — nunca se importan; las marcadas «solo-spec» se reimplementan desde su especificación. Sin zip: todo desde las especificaciones del documento.
3. **Orden de obra**: `config.py` → `synthetic.py` → `eval_harness.py` → `fase0.py` (con sus evals en verde) → `fase1.py` (ídem) → `fase2.py` (ídem) → `main.py` → **ejecución end-to-end** sobre el sintético.
4. **Cierre exigido**: la ejecución final debe imprimir el waterfall del dinero bajo el suelo por etapa (de `support_chain`), la cadena de uplift, y el contrafactual Simpson en $ — las tres cifras-titular del documento. Y la **puerta de equivalencia**: junto al prompt se adjuntan `raw_golden.csv` (la entrada congelada — NO regenerar el sintético para esta prueba), `sff_v2_golden.db` (la salida de referencia del prototipo validado) y `equivalence_gate.py`; ejecuta la obra leyendo `raw_golden.csv`, persiste a sqlite y corre `python equivalence_gate.py <tu_db> sff_v2_golden.db` — el cierre exige **16/16 PASS**. El estilo cambia; los números, no. Toda divergencia intencionada (un bug del prototipo corregido, p. ej.) se declara en ASUNCIONES con su justificación. Adjunta al final todos los ficheros, el log y el resultado de la puerta.
5. **Asunciones**: no te detengas a preguntar; toda decisión que tomes dentro de los márgenes del documento se lista en una sección final `ASUNCIONES` (numerada, con el porqué), para revisión. Si algo del documento fuera contradictorio o inimplementable tal cual, impleméntalo de la forma más fiel posible y decláralo ahí — nunca lo resuelvas en silencio.
6. **Fuera de alcance**: fase 3+ (ensamblaje, backtest, forecast), adquisición, calibración de k con datos reales, y la conexión SQL real (deja `main.py` preparado con un flag `--synthetic` por defecto y el hueco documentado para la query real).
