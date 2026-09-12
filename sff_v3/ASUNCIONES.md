# ASUNCIONES de la implementación (revisión pendiente del usuario)
1. **Mini-evals por bloque**: sustituidos en esta pasada por asserts integrados (conservación, columnas exhaustivas, guardarraíles) + la ejecución end-to-end como smoke. El harness de 3 casos/bloque queda pendiente de la sesión de obra formal.
2. **L2 con hermanas singleton**: L2 junta hermanas pequeñas entre sí; si tras anular la dim muda la hermana queda sola (p. ej. tele: el web grande conserva su id por tener soporte), el nivel no gana n — lo resuelve la credibilidad (etapa 3), visible en support_chain. Coherente con P5/P6.
3. **Contrafactual Simpson**: walk-forward sobre los últimos 6 meses con verdad (train+test), método segmentado = tasas por serie ≤t−1 × pesos reales de t. El mes en curso no se excluye aquí por ser diagnóstico (sí se excluiría del backtest de selección real).
4. **k de credibilidad**: fijadas pragmáticas (tasa k=60, uplift k=24) — calibración varianza-dentro/entre pendiente con datos reales.
5. **Backtest**: 1 origen por horizonte (h=1..4) por presupuesto; el diseño real usa múltiples orígenes. Series elegibles: ≥10 meses y n≥suelo/2 al grano L2.
6. **Uplift**: definido como AUV_renovado/AUV_pipeline por fila; vara s/√meses. Intervalos de descuento: el sintético ya trae niveles (d0/d40); el mapeo continuo→intervalos queda como config futura.
7. **Padres de tasa**: la credibilidad encoge hacia la celda mandatory (no hacia la cadena completa de padres por levels) — suficiente para la demo; la jerarquía multinivel queda para la obra.
8. **SQL**: main corre sobre sintético; config_sqlserver de la cantera se enchufa sobrescribiendo Config.write (una clase).

9. **Obra (refactor profesional)**: identificadores de código renombrados a inglés
   autoexplicativo; los NOMBRES DE COLUMNA persistidos se conservan tal cual (celda,
   gu, tasa, ruta...) porque son el contrato del golden y de cualquier BI ya conectado —
   renombrarlos exigiría nueva golden y migración de consumidores (decisión aparte).
   Puerta de equivalencia 16/16 tras el refactor: el estilo cambió; los números, no.
10. **phi (2026-08-15)**: `diagnostico_dinamica` adds sd_obs_pp / sd_binom_pp / phi
    (overdispersion vs own-coin variance; doctrine in DISENO_V2 Anexo F). Measured,
    NOT yet applied to bands (calibrated band = z·se·sqrt(phi) belongs to the bands
    monograph). Golden gate unaffected: new columns only — the gate compares the
    golden's column set, and every pre-existing number is untouched (16/16 PASS).

10. **Doctrina del mes en curso (2026-08-16, cambio de contrato sellado por el usuario)**:
    el mes en curso pasa a rol PROJECTION en fase 0 (es el primer mes a proyectar,
    nunca test), y projection se limpia de resultados tempranos (renovaciones y
    readquisiciones → NaN) con resumen impreso de lo eliminado. Motivación: pipeline
    conocido + resultado incompleto = futuro, no pasado; evaluar contra él contamina
    (ya se excluía del backtest; ahora la exclusión es estructural). El golden se
    REGENERÓ con esta doctrina — divergencia intencionada, declarada aquí.

## Versión completa (2026-08-16) — lo implementado en esta pasada

11. **Catálogo de técnicas completo (15)**: añadidas T3 (medias móviles 3/6), T5 (drift
    saturado), T6 (promedio mismo-mes), T9 (SES con alpha ajustada in-sample), T10 (Holt
    amortiguado), T11 (Holt-Winters aditivo — reporta nivel/tendencia/estación), T13
    (Croston para series intermitentes). Elegibilidad por historia mínima; guardarraíl de
    techo en todas las que extrapolan. Constantes: DAMPING_PHI=0.90, CROSTON_ZERO_SHARE=0.30.
12. **Escalera de padres multinivel**: el orden de colapso se deriva de los sufijos
    `_level_N` (dentro de familia cae primero el nivel MÁS FINO) y del η² (entre familias,
    colapsa antes la que menos separa). La credibilidad encoge hacia el PRIMER padre que
    alcanza el suelo, no hacia la celda mandatory completa. Nueva tabla `parent_ladder`
    (serie × peldaño: padre, n, tasa, elegido). Resuelve el pendiente medido de los $5,5M.
13. **Política de huecos (`gap_rate_policy`, default "no_rate")**: un mes sin vencimientos
    tiene tasa INDEFINIDA (0/0), no 0%. La fila sintética se conserva para continuidad y
    conteo, pero su tasa es NaN y las técnicas no la ven. "zero_rate" restaura lo anterior.
14. **Backtest multi-origen** (BACKTEST_ORIGINS=3): tres orígenes por horizonte en vez de
    uno — un origen suelto es un mes con suerte, no evidencia. Columnas `origen` y
    `mes_objetivo` en `backtest_predictions`.
15. **Bandas empíricas del forecast** (`forecast_bands`, peldaño 4 de la escalera de
    bandas): banda = percentil 90 del |error| MEDIDO por (técnica, horizonte) en el
    rolling; si ese par nunca se midió, cota binomial marcada con `banda_fallback=1`
    (nunca silenciosa). Banda de cartera en CUADRATURA.
16. **Informe de validación** (`validation_report` + panel en consola): 17 checks en tres
    familias — INTEGRITY (conservación, unicidad, cobertura del puente), DOCTRINE
    (projection limpio, mes en curso en projection, techo, uplift>0, mandatory intactas en
    L1/L2) y QUALITY (dinero reparado, cobertura de técnica y de banda medida, calibración,
    estacionalidad solo con ciclo completo, uplift plausible). No detiene la ejecución:
    la audita. Golden regenerado (23 tablas) con todo lo anterior.
17. **Informe de horizonte** (`horizon_report_series` + `horizon_report_total`): degradación
    mes a mes usando el error de la técnica REALMENTE elegida por cada pool (no la media
    de todas). Por serie: error medio, p90, cobertura de cota y degradación vs h=1. Total:
    $ esperado y banda en cuadratura por mes proyectado, error ponderado por dinero y
    % de filas con banda medida. Series sin historia propia toman como referencia el mes
    más reciente con verdad de la ejecución (su horizonte es real, nunca 1 por defecto).
18. **Vectorización de ids + bug latente del puente (2026-08-16)**: los ids se construían
    con `frame[cols].astype(str).agg("|".join, axis=1)` — fila a fila: medido a escala de
    producción (600k×10), 45,7s por llamada frente a 2,9s vectorizado (x16), y hay varias
    llamadas por ejecución. Nuevo helper `join_columns` en config, sobre arrays (inmune a
    índices duplicados tras merge). Al vectorizar afloró un BUG LATENTE: `key_bridge`
    seleccionaba columnas DUPLICADAS (las mandatory viven en `grano_uplift` y otra vez
    sueltas), de modo que su `uplift_cell_key` no casaba con el de fase 2. Corregido con
    dedupe de columnas; golden regenerado (la puerta cazó la divergencia y la declaramos).
19. **Bug de lookup por parseo posicional (2026-08-17, cazado en Kamelot)**: el fallback de
    tasa derivaba la celda mandatory con `fs_id.str.split("|").str[0]` — solo el PRIMER
    campo. Con una dimensión obligatoria (el sintético) funcionaba por casualidad; con las
    diez de producción no casaba nunca → tasa NaN → `esperado_usd` NaN → assert. Corregido
    tomando los `len(business_mandatory_dims)` primeros campos. Añadido: cascada de fallback
    con trazabilidad (`tasa_origen` = serie/celda/global) impresa por consola, guardarraíles
    con diagnóstico (filas, dinero afectado, ejemplo y lookup culpable) en vez de asserts
    mudos, dos checks nuevos en validación, y `smoke_multidim.py` — prueba con VARIAS dims
    obligatorias, verificada capaz de cazar este mismo bug si se reintroduce.
