# SFF v3 — Stratified Forecast Framework · README

Forecast de renovaciones de suscripciones por unidades de forecast (serie × mes), con
soporte prestado por una escalera de parientes, técnica por serie elegida en backtest,
bandas asimétricas calibradas, uplift por celda, y horizonte extendido con pipeline
simulada. Todo en un directorio plano; nada del legacy.

Lee primero `GUION_MARCO.md` (de qué va, en el orden en que se piensa), `PREGUNTAS_NEGOCIO.md` (las diez preguntas que responde y en qué tabla), `ESTRATEGIA_POR_REGION.md` (cómo organizarse con el resultado), `POR_QUE_ESTE_FORECAST.md` (por qué así) y `GUION_V3.md` (qué hace cada
pieza); `GLOSARIO.md` para los términos; `COTA_BINOMIAL.md` para se_pp_max / moe / el dial 30-271-752 y por qué importa; `METODOS.md` para cada técnica estadística explicada con números (cuadratura, credibilidad, η², Kitagawa, φ, logit, bandas); `PARAMETROS.md` para cada parámetro y su valor
por defecto justificado; `AUDITORIA.md` para auditar una serie (Power BI y notebook);
`ANALYSIS_POINTS.md` para qué mirar cuando corra sobre datos reales; `PENSAR_JUNTOS.md`
para las preguntas abiertas de ajuste; `USO_NOTEBOOK.md` para trabajar desde un notebook.

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
- La estacionalidad de la tasa se decide UNA vez, en el benchmark de las series grandes
  neutras (fase 2): amplitud en pp, consistencia entre años y una prueba predictiva contra
  el nivel reciente. Sin estación material, la tasa se predice desde su nivel; con ella,
  efectos de mes solo en esas series. Ninguna técnica "encuentra" estación por su cuenta.
- El calendario se decide desde el mes en curso: proyección (mes en curso y después),
  mes pendiente de cierre (ni verdad ni entrenamiento; se predice), 6 meses de examen, resto
  entrenamiento. El forecast aprende de todos los meses cerrados; las técnicas y sus bandas se
  deciden sin los meses de examen.
- Un juez con dos baterías sobre los últimos 6 meses cerrados: h=1 (el mes siguiente con
  datos hasta el anterior) y h=6 (con datos hasta seis meses antes); más allá de 6 se usa la
  de 6 y se actualiza mes a mes. Retador T3_ma3; margen 0,10 cerca y 0 lejos; dentro del
  margen gana la técnica con más memoria.
- La banda del total = idiosincrática (pools independientes, cuadratura) ⊕ común (el error
  de toda la cartera por horizonte, sumado linealmente entre meses).
- Bandas: cuantiles p5/p95 del error normalizado por (id, h), propias o de familia, monótonas
  en h, × el error binomial del pool en el momento de predecir, ⊕ el muestreo de la fila.
  Agregación: suma lineal dentro de (id, mes), cuadratura entre.
- La composición se cuenta, no se busca: Kitagawa (comportamiento vs composición) y el
  coste en dólares de la vista solo-mandatory (walk-forward). Nada decide con ello.
- Horizonte extendido: `pipeline(m) = renovados(m − plazo) × factor_adquisicion`, filas
  `simulada = 1`, factor estimado del histórico (o de config). Es la asunción declarada.

## Módulos (directorio plano)

| Módulo | Etapa | Qué hace |
|---|---|---|
| `config.py` | ambos | dataclass Config (contrato de columnas, taxonomía, parámetros), registro de tablas, `write` |
| `binomial_reference.py` | ambos | se binomial, Wilson, el dial, logit, φ, cuantiles |
| `analysis_data_profile.py` | ANALYSIS | niveles 0 y 1: perfil del raw (calendario, dominios y su estabilidad, coherencia de medidas, plazo) y de las unidades (completitud, dial, combinaciones, meses extremos) |
| `raw_data_validation.py` | RUN | fase 0: contrato, doctrina mes en curso, tabla fina, forecast units, claves, universos/rutas |
| `support_reference.py` | ANALYSIS | fu_summary: la foto del soporte |
| `run_rate_series.py` | RUN | 1.1 series, huecos (tasa NaN), tasa por fila, resumen con signo |
| `analysis_dimensions.py` | ANALYSIS | 1.2 η² individual / contribución única / ω² / pares → `decision_eta2`; contrafactual y Kitagawa; calibración timevarying |
| `run_support_ladder.py` | RUN | 1.3 parientes, pools, subida, credibilidad, niveles de riesgo, ficha, cadena, informe nivel × $ |
| `analysis_seasonality_benchmark.py` | ANALYSIS | 2 el benchmark de estacionalidad sobre las series grandes neutras: una decisión para toda la cartera → `decision_estacionalidad`, `bench_panel`, `bench_flags` |
| `techniques.py` | ambos | catálogo REDUCIDO: 7 técnicas de nivel + T15 (nivel reciente + efecto de mes, solo donde el benchmark lo declaró); `predict` |
| `analysis_backtest.py` | ANALYSIS | serie mensual por pool y `pool_reference`; 3 dos baterías (h=1, h=6) sobre los últimos 6 meses cerrados, decisión sin el examen, campeón por tramo con retador ma3 → `decision_technique`; bandas propias/familia + banda común → `decision_error_bands`, `decision_agg_bands`; hold-out por pool y del total |
| `run_uplift.py` | RUN | 4 ratio de sumas por celda, padre por punto de partida, bootstrap → `decision_uplift` |
| `run_forecast_assembly.py` | RUN | 5 horizonte extendido, ensamblaje con orígenes, bandas, agregación, informes |
| `analysis_baseline.py` | ANALYSIS | la previsión de Excel (tasa en $ de los últimos meses por grano agregado × pipeline) frente al framework, con su propio walk-forward |
| `run_validation.py` | ambos | panel INTEGRITY / DOCTRINE / QUALITY |
| `sheet.py` | ambos | `sheet(key, configuration)`: la ficha de lo que señale cualquier clave (fs_key, estimacion_key, celda_key, uplift_cell_key, fu_key, fu_comb_key, o un fs_id): tablas filtradas + resumen en palabras + figura |
| `diagnostics_plots.py` | análisis | `run_series_diagnostics(configuration, top=10, by="usd")`: 4 figuras compactas de las top series (tasa, pipeline, perfil estacional, hold-out) con sus diagnósticos, para revisar a ojo |
| `audit_series.py` | ambos | `audit_series(fs_id, configuration)`: la explicación completa de una serie desde las tablas (AUDITORIA.md) |
| `pipeline.py` | — | `run_analysis`, `run_pipeline`, `key_bridge`, horizontes |
| `main.py` | — | entrada de producción (`python main.py` / `python main.py analysis`) |
| `synthetic_v3.py` | test | dataset sintético con un escenario por feature |
| `checks.py`, `test_fixtures.py`, `test_*.py`, `run_all_tests.py` | test | ocho baterías: config, fase 0, fase 1, fases 2-3, fases 4-5, pipeline, ingeniería (determinismo, integridad, contratos, robustez, rendimiento) y estadística (coberturas, credibilidad, cuadratura, fuga, potencia del benchmark, identidades) |

## Tablas (47, prefijo `sff_`)

Fase 0: `fact_fu`, `fact_fine`, `fact_fu_gaps`, `lookup_fu`, `lookup_comb`, `fu_summary`, `raw_profile`, `dim_domains`, `fu_profile`, `dial_buckets`.
Fase 1: `fs_summary`, `series_card`, `risk_levels`, `parent_ladder`, `support_chain`,
`decision_support`, `decision_eta2`, `decision_eta2_pairs`, `mandatory_only_cost`,
`mix_shift`, `tv_calibration`. Fase 2: `decision_estacionalidad`, `bench_panel`, `bench_flags`, `pool_reference`. Fase 3: `dim_tecnica`,
`backtest_pred`, `backtest_holdout`, `backtest_holdout_agg`, `backtest_agg_error`, `decision_agg_bands`, `decision_technique`, `decision_error_bands`.
Fase 4: `uplift_chain`, `decision_uplift`. Fase 5: `key_bridge`, `fu_extended`,
`forecast_detail`, `forecast_bands`, `horizon_report_total`, `forecast_by_level`,
`pipeline_summary`, `business_summary`, `forecast_by_region`, `baseline_forecast`, `baseline_summary`, `validation_report`.

Ids y claves: `fu_id`/`fu_key` (unidad), `comb_id`/`comb_key` (combinación de extras de
revalorización), `fu_comb_key` (fila del raw), `fs_id`/`fs_key` (serie), `id_estimacion`/
`estimacion_key` (patrón del pariente elegido: `EU|SIG=neg|A|*`), `uplift_cell_id`/`uplift_cell_key`,
`celda_id`/`celda_key` (celda mandatory). Las claves se estampan al escribir en toda tabla
que lleve el id (`Config.stamp_derived_keys`); `key_bridge` une todos por fila del raw.

## Niveles de riesgo

A propio (n ≥ 271, ≥ 12 meses: sola) · A2 propio corto (n ≥ 271, < 12 meses) · A3 propio reforzado (30 ≤ n < 271: su tasa completada con su primer pariente con soporte) · B prestado (peldaño 1-2: pariente que comparte todas las mandatory) · C lejano (peldaño ≥ 3: celda o mandatory colapsada) · S señal bajo suelo (con flag, celda × signo sin llegar al suelo: mejor tasa de su signo, ruidosa) · M signo mixto · D sin historia · N sin impacto · T universo ts. La consola imprime la leyenda completa tras la tabla de dinero (`LEVEL_DEFINITIONS`).

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
