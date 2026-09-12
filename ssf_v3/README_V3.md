# SFF v3 — Stratified Forecast Framework · README

Forecast de renovaciones de suscripciones por unidades de forecast (serie × mes), con
soporte prestado por una escalera de parientes, técnica por serie elegida en backtest,
bandas asimétricas calibradas, uplift por celda, y horizonte extendido con pipeline
simulada. Todo en un directorio plano; nada del legacy.

Lee primero `POR_QUE_ESTE_FORECAST.md` (por qué así) y `GUION_V3.md` (qué hace cada
pieza); `GLOSARIO.md` para los términos; `ANALYSIS_POINTS.md` para qué mirar cuando
corra sobre datos reales; `USO_NOTEBOOK.md` para trabajar desde un notebook.

## Ejecutar

```python
from config import Config
from pipeline import run_analysis, run_pipeline
import pandas as pd

class MiConfig(Config):
    def read_raw(self):
        return pd.read_sql("SELECT ... ", self.engine)     # tu query; todas las columnas declaradas

configuration = MiConfig(sql_server="...", sql_database="Kamelot",
                         backtest_test_start="2026-01",       # los meses de 2026 ya ocurridos = hold-out
                         extended_horizon_end="2027-12")      # simular la pipeline hasta aquí

results = run_analysis(configuration)     # ANALYSIS: decide, escribe decision_*, produce el forecast
results = run_pipeline(configuration)     # RUN mensual: lee decision_*, produce el forecast
```

`read_raw` DEBE sobreescribirse. `run_analysis` se ejecuta en el periodo de evaluación (lo
retiene el analista); `run_pipeline` cada mes (delegable). Tests: `python run_all_tests.py`.

## Doctrina (sellada)

- **Aprendemos del pasado, confirmamos en el presente, proyectamos el futuro — para cambiarlo.**
- La referencia binomial √(p(1−p)/n) mide todo: suelo de soporte, normalización de errores,
  tests de estacionalidad/tendencia, φ (varianza observada / binomial) que dice dónde hay motor.
- Predecir ≠ reportar: dos errores por serie, `se_estimacion_pp` (lo que sabemos de la tasa)
  y `se_prediccion_pp` (lo que pasará en un mes con ese n; nunca encoge).
- Una escalera, un bucle: cada serie toma soporte del pariente más cercano que lo tiene, y
  se lo cree en proporción a lo poco que tiene ella (credibilidad z = n/(n+k), Bühlmann-Straub).
- **El signo nunca se pierde.** Timevarying = banderas binarias por motivo con signo; la serie
  se resume en su signo (neutral/neg/pos/mixed). Positivos y negativos nunca se juntan; los
  neutros solo con neutros; una serie mixta se queda sola y se cuenta. Para las series con
  signo la escalera **termina en la celda mandatory × signo**: más arriba es fabricar Simpson.
  Si sigue bajo el suelo se queda con lo mejor de su signo, sin credibilidad (`S_signo_bajo_suelo`).
- Los pools se calculan con TODAS las series que casan el patrón (hermanas grandes incluidas):
  el patrón decide quién calcula el número; la escalera decide quién lo recibe.
- Un juez: backtest rolling-origin con todos los orígenes, error con signo normalizado por
  el error binomial del mes objetivo. Retador T2_mean con margen; entre técnicas dentro del
  margen gana la familia más rica (series temporales). Elegibilidad por historia y etiquetas.
- Entrenar con todo el histórico, testear con los meses de 2026 ya ocurridos (`backtest_test_start`).
- Bandas: cuantiles p5/p95 del error normalizado por (id, h), propias o de familia, monótonas
  en h, × el error binomial del pool en el momento de predecir, ⊕ el muestreo de la fila.
  Agregación: suma lineal dentro de (id, mes), cuadratura entre.
- Simpson no se busca: se explica (Kitagawa: comportamiento vs composición) y se cuantifica
  (contrafactual walk-forward plano vs segmentado en dinero).
- Horizonte extendido: `pipeline(m) = renovados(m − plazo) × factor_adquisicion`, filas
  `simulada = 1`, factor estimado del histórico (o de config). Es la asunción declarada.

## Módulos (directorio plano)

| Módulo | Etapa | Qué hace |
|---|---|---|
| `config.py` | ambos | dataclass Config (contrato de columnas, taxonomía, parámetros), registro de tablas, `write` |
| `binomial_reference.py` | ambos | se binomial, Wilson, el dial, logit, φ, cuantiles |
| `raw_data_validation.py` | RUN | fase 0: contrato, doctrina mes en curso, tabla fina, forecast units, claves, universos/rutas |
| `support_reference.py` | ANALYSIS | fu_summary: la foto del soporte |
| `run_rate_series.py` | RUN | 1.1 series, huecos (tasa NaN), tasa por fila, resumen con signo |
| `analysis_dimensions.py` | ANALYSIS | 1.2 η² individual / contribución única / ω² / pares → `decision_eta2`; contrafactual y Kitagawa; calibración timevarying |
| `run_support_ladder.py` | RUN | 1.3 parientes, pools, subida, credibilidad, niveles de riesgo, ficha, cadena, informe nivel × $ |
| `analysis_dynamics.py` | ANALYSIS | 2 serie mensual por id de estimación, φ, gate, perfil estacional (sin tendencia), tendencia → `decision_dynamics` |
| `techniques.py` | ambos | catálogo de 15 técnicas en logit con elegibilidad; `predict` |
| `analysis_backtest.py` | ANALYSIS | 3 rolling-origin, selección con retador → `decision_technique`; bandas → `decision_error_bands`; hold-out |
| `run_uplift.py` | RUN | 4 ratio de sumas por celda, padre por punto de partida, bootstrap → `decision_uplift` |
| `run_forecast_assembly.py` | RUN | 5 horizonte extendido, ensamblaje con orígenes, bandas, agregación, informes |
| `run_validation.py` | ambos | panel INTEGRITY / DOCTRINE / QUALITY |
| `pipeline.py` | — | `run_analysis`, `run_pipeline`, `key_bridge`, horizontes |
| `main.py` | — | entrada de producción (`python main.py` / `python main.py analysis`) |
| `synthetic_v3.py` | test | dataset sintético con un escenario por feature |
| `checks.py`, `test_fixtures.py`, `test_*.py`, `run_all_tests.py` | test | 310 checks de lógica |

## Tablas (32, prefijo `sff_`)

Fase 0: `fact_fu`, `fact_fine`, `fact_fu_gaps`, `lookup_fu`, `lookup_comb`, `fu_summary`.
Fase 1: `fs_summary`, `series_card`, `risk_levels`, `parent_ladder`, `support_chain`,
`decision_support`, `decision_eta2`, `decision_eta2_pairs`, `simpson_contrafactual`,
`mix_shift`, `tv_calibration`. Fase 2: `decision_dynamics`. Fase 3: `dim_tecnica`,
`backtest_pred`, `backtest_holdout`, `decision_technique`, `decision_error_bands`.
Fase 4: `uplift_chain`, `decision_uplift`. Fase 5: `key_bridge`, `fu_extended`,
`forecast_detail`, `forecast_bands`, `horizon_report_total`, `forecast_by_level`,
`validation_report`.

Ids y claves: `fu_id`/`fu_key` (unidad), `comb_id`/`comb_key` (combinación de extras de
revalorización), `fu_comb_key` (fila del raw), `fs_id`/`fs_key` (serie), `id_estimacion`
(patrón del pariente elegido: `EU|SIG=neg|A|*`), `uplift_cell_id`/`uplift_cell_key`,
`celda_id` (celda mandatory). `key_bridge` une todos por fila del raw.

## Niveles de riesgo

A propio · B prestado (peldaño ≤ 2) · C lejano (peldaño ≥ 3 o neutra bajo suelo) ·
D sin historia · S con signo bajo suelo · M signo mixto · N sin impacto · T universo ts.

## Divergencias declaradas respecto a DISENO_SPLIT / DISENO_V2

- `fu_summary` se escribe en ANALYSIS (`support_reference.py`), no en RUN.
- EDGE CASES en inglés en los docstrings; nombres de columnas y valores persistidos en español.
- `verbosity` y `raw_data_path` eliminados; `ts_revenue_col` conservado (uso futuro).
- Sin `simpson_showcase*`: se sustituye por Kitagawa + contrafactual.
- Sin comparación con referencia numérica: los tests son de lógica sobre escenarios diseñados.
- La credibilidad del uplift (v2, no-op) se elimina; el soporte del uplift se repara por padre/celda.
- El universo `time_series` solo se etiqueta (nivel T); su forecast usa la cascada celda/global.

## Pendiente / abiertos

- SARIMA / ETS auto como técnicas enchufables (statsmodels no disponible en este entorno).
- Uplift: credibilidad / η² aplazados; investigar celdas con `recortado = 1` en datos reales.
- `key_bridge` y `backtest_pred` pueden ser grandes en Kamelot: medir tiempos.
- φ como palanca de banda (hoy solo informativo).
- Test estacional multi-año con cambio de amplitud.
