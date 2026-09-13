# Ejecutar el pipeline desde un notebook

Todo el código nuevo está en una sola carpeta (`sff_v3/`). El legacy sigue en `sff_v2/`,
un nivel por encima; el pipeline lo encuentra solo.

## 1 · Que la carpeta sea importable

Si el notebook está dentro de `sff_v3/`, no hace falta nada. Si está en otro sitio:

```python
import sys
sys.path.insert(0, "ruta/al/repo/sff_v3")
```

## 2 · Ejecutar

```python
import pandas as pd
from config import Config
from pipeline import run_analysis, run_pipeline   # v3: análisis (decide) / run mensual (lee decisiones)

class MiConfig(Config):
    def read_raw(self):
        return pd.read_sql("SELECT * FROM ...", self.engine)   # tu query

cfg = MiConfig(sql_server="...", sql_database="Kamelot")
resultados = run_pipeline(cfg)
```

## 3 · Recargar cambios en los .py sin reiniciar el kernel

### Recomendado: autoreload

Una vez, al principio:

```python
%load_ext autoreload
%autoreload 2
```

Editas un .py, ejecutas la celda que lo usa, coge el cambio. Punto ciego: no siempre
re-ejecuta constantes a nivel de módulo (`PHYSICAL_TABLE_NAMES`, etc.); para eso, el helper.

### Respaldo: reload_project()

```python
import sys, importlib

def reload_project():
    """Olvida los módulos del proyecto; el siguiente import los relee del disco."""
    for module_name in ["config", "raw_data_validation", "support_reference", "pipeline"]:
        sys.modules.pop(module_name, None)
    importlib.invalidate_caches()
```

Tras editar: `reload_project()` y rehaces los `from ... import`.

## Dos avisos (valen para ambos métodos)

1. **Los objetos ya creados NO se actualizan.** Si tenías `cfg = MiConfig(...)` y
   recargas, ese `cfg` es de la clase vieja. Recréalo.
2. **`MiConfig` la defines en el notebook heredando de `Config`.** Al recargar,
   sigue heredando de la `Config` vieja. Re-ejecuta también su celda.


## v3: los dos runners

- `results = run_analysis(configuration)` — el análisis: escribe `decision_*`, produce el forecast y devuelve un dict con todo (`series_card`, `decisions`, `backtest`, `forecast`, `validation`...).
- `results = run_pipeline(configuration)` — el run mensual: lee `decision_*` de la base y produce el forecast. Sin análisis previo se niega a correr.

Módulos `run_*.py` = RUN, `analysis_*.py` = ANALYSIS, `techniques.py` y `binomial_reference.py` compartidos. `reload_project()` debe incluirlos todos.


## Auditar una serie

```python
from audit_series import audit_series
audit = audit_series("EU|0|0|0|0|A|tele", configuration)   # lee las tablas sff_*; ver AUDITORIA.md
```

## Si aparece `AttributeError: 'SFFConfig' object has no attribute ...`

Tu `config.py` es de una entrega anterior: sustitúyelo por el de esta y reinicia el kernel (`pipeline` lo comprueba al arrancar y lo dice en claro). Tu subclase con `read_raw` no cambia.


## Ver las series a ojo

```python
from diagnostics_plots import run_series_diagnostics
run_series_diagnostics(configuration, top=10, by="usd")        # o by="history"; figuras en <outdir>/diagnostics/
```

Cuatro PNG: tasas de las top series en un eje, pipeline (log), perfil estacional, hold-out real vs predicho. Mándame los cuatro.


## La ficha de una serie (o de lo que señale una clave)

```python
from sheet import sheet
s = sheet("Europe|North Europe|...|1 device", configuration)   # por fs_id
s = sheet(233977162747724, configuration)                    # por cualquier clave bigint (fs_key, estimacion_key, celda_key, uplift_cell_key, fu_key, fu_comb_key)
s["summary"]; s["tables"]["parent_ladder"]; s["figure"]      # resumen · tablas filtradas · PNG
```

Y los tres casos de muestra con `from diagnostics_plots import showcase_sheets; showcase_sheets(configuration)` (estacional, tendencia, cambio de nivel, mix-shift), y el juego «tú frente a la máquina» con `guess_game(fs_id, 6, configuration)`.

**Hasta dónde ejecutar para ver las figuras**: `run_series_diagnostics` y `sheet` necesitan `series_card` (fase 1.3) y `decision_dynamics` (fase 2); la figura de hold-out y la técnica necesitan la fase 3. Con `run_analysis` completo todo está.
