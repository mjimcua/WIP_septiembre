# DISEÑO SPLIT — separación RUN / ANALYSIS y estructura del repositorio

*SFF v2 · 12-sep-2026 · Complementa a DISENO_V2.md (doctrina). Este documento fija QUÉ código se delega y QUÉ código se retiene, cómo se comunican, y cómo se organiza el repositorio. Pendiente de sellar por el usuario: las decisiones marcadas [SELLAR].*

---

## 1 · Principio de separación

**RUN** = lo imprescindible para producir cada mes `forecast_detail` y sus bandas **sin tomar ninguna decisión**. Lee datos, aplica reglas ya decididas, escribe tablas, se audita. Es el código que se delega a otro equipo técnico.

**ANALYSIS** = lo que decide *cómo* se hace el forecast y mide *si* lo hace bien: diagnósticos, contrafactual Simpson, η², backtest, selección de técnica, distribución de errores, herramientas de obra y didácticas. Es el código que se retiene durante el periodo de evaluación.

Regla de trazado: una función va a ANALYSIS si su salida se usa para **elegir** (grano, técnica, orden de colapso, banda) o para **explicar** (Simpson, φ, gates). Va a RUN si su salida es una tabla que el forecast **consume** o el usuario de BI **reporta** cada mes.

## 2 · Mapa función → carpeta (estado actual → destino)

| Fichero actual | Función | Destino | Motivo |
|---|---|---|---|
| config.py | todo | RUN | contrato; también lo importa ANALYSIS |
| fase0.py | f0_load_and_validate, f0_split_and_key, f0_universe_routes, f0_fu_summary | RUN | referencia inmutable; se reporta cada mes |
| fase1.py | f1_series_and_gaps | RUN | series y huecos son parte del forecast |
| fase1.py | f1_diagnose_round1 (foto binomial, contrafactual Simpson, η², pares) | ANALYSIS | produce evidencia y `decision_eta2` |
| fase1.py | f1_improve_support (L1/L2/L3, parent_ladder) | RUN | estimación de la tasa. **Hoy recibe `eta2_by_dim` en memoria → pasa a leer `decision_eta2`** |
| fase1.py | construcción de `support_chain_rows` (dentro de f1_improve_support) | ANALYSIS | es explicación, no estimación. Hay que **extraer** la construcción de la cadena a una función propia |
| fase1.py | f1_support_chain, f1_diagnose_round2 (gates, φ) | ANALYSIS | waterfall y censo de comportamientos |
| fase2.py | f2_uplift_fine | RUN | estimación del uplift |
| fase2.py | f2_diagnose (η² uplift) | ANALYSIS | produce `decision_eta2` (rama uplift) |
| fase2.py | f2_improve (+ uplift_chain) | RUN (estimación) / ANALYSIS (cadena) | misma extracción que en fase 1. **Hoy recibe η² en memoria → `decision_eta2`** |
| fase3_assembly.py | f3_build_key_bridge, f3_ensamblaje | RUN | el forecast |
| fase4_backtest.py | f4_backtest, f4_rolling_next_month | ANALYSIS | el juez; producen `decision_technique` y `decision_error_bands` |
| fase4_backtest.py | f4_forecast_bands, f4_tablas_fu, f4_horizon_report | RUN | salida mensual. **Hoy reciben `technique_selection` y `rolling_table` en memoria → leen tablas de decisión** |
| validation.py | run_validation | RUN | audita cada ejecución; los checks que dependen de artefactos de ANALYSIS se marcan `n/a` si no existen |
| fase_pre.py | buscador de escaparates Simpson | ANALYSIS | didáctico |
| synthetic.py, eval_harness.py, equivalence_gate.py, smoke_multidim.py | — | TESTS | herramientas de obra |
| generate_model.py, render_model.py, modelo/ | — | DOCS | ERD |

## 3 · Contrato ANALYSIS → RUN: las tablas de decisión

RUN no calcula decisiones: las **lee** de tablas persistidas que ANALYSIS escribe. Cada tabla lleva `execution_id` del análisis que la produjo y `decision_date`. Son tres:

| Tabla | Grano | Columnas | La consume |
|---|---|---|---|
| `decision_eta2` | rama × dimensión | `rama` (tasa/uplift), `dimension`, `eta2`, `decision_date`, `execution_id` | f1_improve_support (dim anulable en L2, orden de colapso de la escalera), f2_improve (ejes mudos) |
| `decision_technique` | pool L2 | `fs_id_L2`, `tecnica_elegida`, `err_bt`, `decision_date`, `execution_id` | f4_forecast_bands, f4_horizon_report (hoy `forecast_seleccion`, que se renombra) |
| `decision_error_bands` | técnica × horizonte | `tecnica_id`, `h`, `p90_abs_err_pp`, `n_medido`, `decision_date`, `execution_id` | f4_forecast_bands (sustituye al cálculo in-memory sobre `rolling_table`) |

**Comportamiento de RUN cuando falta una decisión** (declarado, nunca silencioso):
- Pool sin técnica → `T2_promedio` con `tecnica_origen = "default"` en la salida; la validación cuenta cuántos pools y cuánto $ van por default.
- Par (técnica, h) sin banda medida → cota binomial con `banda_fallback = 1` (ya existe).
- Dimensión sin η² → error bloqueante en fase 1 (sin η² no hay orden de colapso; es una decisión que no puede faltar).
- Tablas de decisión con antigüedad > `decision_max_age_months` (config) → WARN en validación: «análisis caducado».

Los parámetros de negocio (`support_floor`, `z`, `rate_cap`, `k_cred`, `k_uplift`) siguen en `config.py`: son decisiones versionadas en el repositorio, no tablas.

**[SELLAR] Alternativa descartada**: que RUN recalcule el backtest cada mes. Más caro, sin punto de control, y mezcla juez y ejecutor. Se descarta salvo que el usuario diga lo contrario.

## 4 · Periodo de evaluación

Durante N meses coexisten dos ejecuciones sobre el mismo extracto:
1. El usuario ejecuta `analyze.py` (ANALYSIS completo: diagnósticos, backtest, escribe tablas de decisión) y después `run_forecast.py`.
2. El equipo receptor ejecuta solo `run_forecast.py` contra las tablas de decisión vigentes.

Criterio de cierre del periodo: `validation_report` y `horizon_report_total` estables durante N meses, y las tablas de decisión con cadencia de refresco acordada (propuesta: trimestral, o cuando `validation` marque «análisis caducado»). Después de eso el usuario conserva ANALYSIS y la propiedad de las tablas de decisión; RUN pasa íntegro al equipo receptor como business requirement (ver /areas/pipeline-handover).

## 5 · Puerta de equivalencia tras el split

La puerta no cambia de naturaleza: `tests/eval_harness.py` ejecuta `analyze.py` + `run_forecast.py` sobre `raw_golden.csv` y compara contra el golden. Consecuencias:
- Las 25 tablas actuales deben salir **idénticas** (filas, sumas, claves). El split no puede cambiar un número.
- Se añaden las 3 tablas de decisión al golden (divergencia intencionada, declarada en ASUNCIONES): 28 tablas.
- `forecast_seleccion` se renombra a `decision_technique`: se declara en ASUNCIONES y se regenera el golden. Ningún otro nombre de tabla ni de columna cambia (contrato del BI).
- `smoke_multidim.py` se ejecuta contra las dos carpetas.

## 6 · Estructura del repositorio (público)

```
sff/
├── README.md                 # qué es, cómo ejecutar RUN, cómo ejecutar ANALYSIS, cómo pasar la puerta
├── HANDOVER.md               # estado vigente; se reescribe al cierre de cada chat de obra
├── ASUNCIONES.md             # divergencias intencionadas, numeradas
├── run/                      # DELEGABLE · ejecución mensual
│   ├── config.py
│   ├── phase0_contract_and_reference.py
│   ├── phase1_series_and_support.py
│   ├── phase2_uplift.py
│   ├── phase3_assembly.py
│   ├── phase4_forecast_and_bands.py
│   ├── validation.py
│   └── run_forecast.py       # runner mensual
├── analysis/                 # RETENIDO · decide y explica
│   ├── phase1_diagnostics.py         # foto binomial, contrafactual, η², pares, support_chain, gates, φ
│   ├── phase2_diagnostics.py         # η² uplift, uplift_chain
│   ├── phase4_backtest.py            # 15 técnicas, campeón por pool
│   ├── phase4_rolling.py             # rolling h=1..3, cobertura de cota
│   ├── decision_tables.py            # escribe decision_eta2 / decision_technique / decision_error_bands
│   ├── simpson_showcase.py           # fase_pre actual
│   └── analyze.py                    # runner de análisis
├── tests/
│   ├── synthetic.py
│   ├── eval_harness.py
│   ├── equivalence_gate.py
│   ├── smoke_multidim.py
│   └── golden/  raw_golden.csv · sff_v2_golden.db
├── prompts/                  # regeneración con LLM interno
│   ├── PROMPT_PHASE_0.md … PROMPT_PHASE_4.md
│   └── PROMPT_COMMON.md      # contrato de config, claves, ids, criterio de aceptación
└── docs/
    ├── doctrine/  DISENO_V2.md · DISENO_SPLIT.md · PROMPT_OBRA.md
    ├── catalogs/  CATALOGO_TECNICAS.md · CATALOGO_TABLAS.md · FASE0_LECTURA.md
    ├── model/     ERD (dbml/mmd/sql/png/svg) + generate_model.py + render_model.py
    └── didactic/  gráficos y scripts didácticos + SQL de Simpson
```

**[SELLAR] Nombres de fichero en inglés** (`phase0_…`), coherentes con la regla «todo el texto del código en inglés». Los nombres de tablas y columnas persistidas NO cambian.

**Primer commit**: el `sff_v2.zip` actual tal cual, en una carpeta `legacy/` o como tag `v2-golden-baseline`. Es la cantera del refactor y la referencia de la puerta; nunca se edita.

## 7 · Orden de obra (un chat por fila)

| Chat | Entrega | Puerta |
|---|---|---|
| 1 (este) | DISENO_SPLIT, PROMPT_OBRA v3, esqueleto del repo | — |
| 2 | `run/config.py` + `run/phase0_…` verbose · `prompts/PROMPT_COMMON.md` + `PROMPT_PHASE_0.md` | 25/25 |
| 3 | fase 1 separada en `run/phase1_…` + `analysis/phase1_diagnostics.py` · `decision_eta2` · prompt | 25/25 + decision_eta2 |
| 4 | fase 2 y fase 3 · prompt | ídem |
| 5 | fase 4 separada · `decision_technique`, `decision_error_bands` · runners · prompt | 28/28 |
| 6 | validation, smoke sobre dos carpetas, README, HANDOVER final | 28/28 |
| 7+ | manual RUN (inglés, business requirement), manual ANALYSIS, presentación | — |

La vuelta en Kamelot se lanza al cierre del chat 6, con el código ya separado.
