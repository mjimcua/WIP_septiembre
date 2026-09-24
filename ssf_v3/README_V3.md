# SFF v3 — Stratified Forecast Framework · el forecast de renovaciones, explicado

**Qué es.** Un framework que predice cuánto dinero de renovaciones entrará cada mes,
con una banda de confianza defendible, y que cuenta por qué. Parte de la pipeline (qué
contratos vencen cuándo), aprende del pasado —sobre todo del reciente—, y produce tres
respuestas: cómo acaba este año, cuál es la pipeline del que viene y cómo acaba, más las
acciones que el resultado sugiere, por región.

**Cómo se lee este repositorio, según quién eres:**

| Lector | Empieza por | Después |
|---|---|---|
| Negocio / dirección | el **informe** que genera cada análisis (`<outdir>/informe/informe.md`) | `PREGUNTAS_NEGOCIO.md`, `ESTRATEGIA_POR_REGION.md` |
| Analista que va a usar el framework | `USO_NOTEBOOK.md` (el bloque de configuración y cómo ejecutar) | `INFORME.md` (qué cuenta cada capítulo), `ANALYSIS_POINTS.md` (qué tabla mirar para qué), `RECORRIDO_DE_UNA_SERIE.md` |
| Quien quiere entender el método | `GUION_MARCO.md` (de qué va, en el orden en que se piensa) | `COTA_BINOMIAL.md`, `METODOS.md` (la matemática con números), `ETAPA_MADURACION_SENALES.md` |
| Quien va a tocar el código | `FLUJO.md` (función a función, con entradas, salidas y tablas) | `PARAMETROS.md`, `vocabulario.py`, los tests |
| Quien monta Power BI | `AUDITORIA.md` (claves, relaciones, tablas `bi`) | `config.TABLE_KIND` |

## Cómo se ejecuta

```python
from config import Config
from pipeline import run_analysis

class SFFConfig(Config):
    def read_raw(self):
        return pd.read_sql(RAW_EXTRACT_QUERY, self.engine)

configuration = SFFConfig(sql_server="...", sql_database="Kamelot", extended_horizon_end="2027-12",
                          term_column="term_level_2", term_months_by_value={"1 year": 12, "2 year": 24, "3 year": 36},
                          extension_row_filter={"term_level_2": ["1 year"]},
                          uplift_mandatory_dims=["regional_level_1", "product_level_1", "purchase_type", "term_level_2"],
                          benchmark_group_dims=["regional_level_1", "product_level_1"])
results = run_analysis(configuration)      # tablas en SQL (prefijo sff_), fichas y el informe en <outdir>/
```

`run_analysis` hace todo: perfila el raw, construye las series, decide la escalera, la
estacionalidad y las técnicas, ensambla el forecast, lo examina, responde a negocio,
dibuja las fichas de las cinco series mayores y escribe el informe. `run_pipeline` es la
versión mensual que solo aplica las decisiones ya tomadas.

## El flujo, en una línea por fase

0 raw y calendario desde el mes en curso · 1.1 series y ruido binomial · 1.2 qué
dimensiones separan comportamiento · 1.3 escalera con credibilidad y niveles de riesgo ·
1.4 composición (contada, no buscada) y señales · 1.5 descuento y churn · 2 benchmark de estacionalidad (una
decisión para toda la cartera) · 3 backtest con dos baterías (un mes y seis meses vista),
sin fuga, con bandas idiosincrática y común · 4 revalorización · 5 ensamblaje, maduración
de señales, respuestas, región, top movers, baseline · fichas · informe · validación.

`FLUJO.md` tiene cada paso con su función, sus entradas, sus reglas y su tabla.

## Los módulos

| Módulo | Fase | Qué hace |
|---|---|---|
| `vocabulario.py` | — | los valores persistidos (roles, signos, tratamientos, orígenes, niveles), en español, en un solo sitio |
| `config.py` | — | contrato de columnas, taxonomía, parámetros por fase, registro de tablas y su tipo, `write` con trazabilidad, claves para BI |
| `binomial_reference.py` | — | error binomial, Wilson, soporte para un margen dado, logit |
| `raw_data_validation.py` | 0 | contrato del raw, calendario desde el mes en curso, tablas fina y de unidades, universos y tratamientos |
| `support_reference.py` | 0 | las tres cotas por unidad (se_pp_max, moe_pp_max, moe_usd_max) en `fact_fu` |
| `analysis_data_profile.py` | 0-1 | perfil del raw y de las unidades: calendario, dominios, medidas, el dial |
| `run_rate_series.py` | 1.1 | series, huecos, tasas, signo, resumen por serie |
| `analysis_dimensions.py` | 1.2 / 1.4 | η² y orden de colapso; composición (Kitagawa) y coste de la vista solo-mandatory; calibración de señales |
| `run_support_ladder.py` | 1.3 | parientes por signo, pools, subida, credibilidad, estimación, niveles de riesgo |
| `analysis_discount_churn.py` | 1.5 | ¿el descuento es un driver de churn? tasa por tramo estandarizada por celda, dentro de cada estado de señal, efectos ajustados, importancia relativa, precio vs tasa |
| `analysis_seasonality_benchmark.py` | 2 | el benchmark de estacionalidad sobre las series grandes neutras: una decisión |
| `techniques.py` | 3 / 5 | 10 técnicas (nivel, Theta, Holt amortiguado; efectos de mes solo con veredicto) |
| `analysis_backtest.py` | 2-3 | serie mensual por pool, referencia de pools, backtest sin fuga, campeón por visión, bandas, examen, error común |
| `run_uplift.py` | 4 | revalorización: la vía de contrato (descuento conocido → regla, validada con el ratio de realización) y la estadística por celda (padre y celda bajo el suelo, bootstrap, tope) |
| `run_forecast_assembly.py` | 5 | reentradas (proyectada / simulada), tasa por fila (forma del pool + nivel propio), bandas, agregación |
| `answers.py` | 5 | resumen de la pipeline, respuestas de negocio, región, forecast ajustado |
| `analysis_signal_maturation.py` | 5 | composición por celda, foto mensual, maduración pendiente, ajuste, alertas |
| `analysis_top_movers.py` | 5 | deterioro / mejora, señal negativa, banda ancha, sesgo del examen, precio |
| `analysis_baseline.py` | 5 | la previsión de hoja de cálculo, con su propio walk-forward |
| `run_validation.py` | 5 | panel INTEGRITY / DOCTRINE / QUALITY |
| `informe.py` | 5 | el informe: portada, siete capítulos, leyenda, anexo |
| `sheet.py`, `audit_series.py`, `diagnostics_plots.py` | — | la ficha de cualquier clave, la auditoría en consola, las figuras |
| `pipeline.py` | — | `run_analysis`, `run_pipeline`, el puente de claves, las fichas |
| `main.py`, `synthetic_v3.py` | — | la configuración de producción; el dataset sintético de pruebas |

## Las tablas (60, prefijo `sff_`)

Clasificadas en `config.TABLE_KIND`:

- **producto** (las que lee el informe y negocio): `pipeline_summary`, `business_summary`,
  `forecast_by_region`, `forecast_by_level`, `horizon_report_total`, `top_movers`,
  `risk_levels`, `decision_estacionalidad`, `baseline_summary`, `signal_adjustment`,
  `signal_alerts`, `validation_report`, `dial_buckets`, `metric_legend`, `discount_churn_*` (5).
- **bi** (dimensiones y hechos para Power BI): `fact_fu`, `fact_fine`, `lookup_fu`,
  `lookup_comb`, `key_bridge`, `forecast_detail`, `forecast_bands`, `series_card`,
  `fu_extended`, `signal_snapshot`, `mix_shift`.
- **intermedia** (decisiones y trazas que el framework lee): el resto.

Toda tabla lleva `process_date`, `execution_id` y las claves derivadas (`fs_key`,
`estimacion_key`, `uplift_cell_key`, `celda_key`) para relacionarse en BI.

## Las decisiones de diseño (las finales)

- El ruido binomial √(p(1−p)/n) es el suelo de todo: el dial (30 / 271 / 752 contratos
  ↔ ±15 / ±5 / ±3 pp), los niveles de riesgo, el error normalizado del backtest.
- Segmentar para ganar homogeneidad, agrupar para recuperar soporte: la escalera con dos
  suelos (30 para prestar, 271 para ir sola) y credibilidad en medio; los signos nunca se
  mezclan.
- El calendario se decide desde el mes en curso: proyección, mes pendiente de cierre,
  seis meses de examen, entrenamiento. El forecast aprende de todos los meses cerrados;
  técnicas y bandas se deciden sin los de examen.
- La composición se cuenta (Kitagawa, coste de la vista solo-mandatory), no se persigue.
- La estacionalidad de la tasa se decide una vez, en las series grandes neutras, con
  amplitud, consistencia y una prueba predictiva; ninguna técnica la encuentra por su cuenta.
- Dos baterías de backtest (un mes y seis meses vista) sobre los últimos seis meses
  cerrados; retador el último trimestre; margen 0,10 cerca y 0 lejos, donde gana la memoria.
- La banda del total = idiosincrática (cuadratura) ⊕ común (el error del total, lineal
  entre meses). El error del total se examina aparte.
- La pipeline futura se etiqueta real / proyectada / simulada; la adquisición se simula,
  la renovación se proyecta; ninguna lleva banda de volumen.
- Las señales maduran: la maduración pendiente se valora y se presenta como forecast
  ajustado, acompañante hasta que las fotos mensuales midan la curva.
- Ninguna cifra sin unidad, referencia y lectura: la leyenda de métricas se imprime la
  primera vez que cada una aparece.

## Tests

`python run_all_tests.py`: ocho baterías (config, fase 0, fase 1, fases 2-3, fases 4-5,
pipeline, ingeniería, estadística). Las dos últimas comprueban propiedades con verdad
conocida: cobertura de Wilson, credibilidad, cuadratura medida, ausencia de fuga,
potencia y falsos positivos del benchmark, identidad de Kitagawa, uplift insesgado,
calibración de bandas.

## Documentación vigente

`GUION_MARCO.md` · `INFORME.md` · `PREGUNTAS_NEGOCIO.md` · `ESTRATEGIA_POR_REGION.md` ·
`USO_NOTEBOOK.md` · `FLUJO.md` · `METODOS.md` · `COTA_BINOMIAL.md` ·
`RECORRIDO_DE_UNA_SERIE.md` · `ETAPA_MADURACION_SENALES.md` · `ANALYSIS_POINTS.md` ·
`PARAMETROS.md` · `GLOSARIO.md` · `AUDITORIA.md` (Power BI) · `AUDITORIA_PROFUNDA.md`
(la auditoría que motivó esta versión). Los documentos de diseño previos están en
`historico/` y no describen el código actual.
