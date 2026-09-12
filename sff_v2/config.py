"""config.py — SFF v2. Exhaustive config (P3), 4-group taxonomy (§3), hash keys (P7), write with process_date+execution_id.
CONTRACT: every raw column must be declared or the program stops. Derivable grains:
grano_tasa = mandatory + timevarying + extra_renovacion · grano_uplift = mandatory + extra_revalorizacion."""
from dataclasses import dataclass, field
import hashlib, os, datetime, uuid
import pandas as pd

def join_columns(frame, columns):
    """GOAL: build a '|'-joined id from several columns, VECTORIZED.
    Why not `frame[cols].astype(str).agg("|".join, axis=1)`: that runs row by row —
    measured at 600k×10 it takes ~46s versus ~3s here (x16). At production scale the
    difference is minutes per run, and this function is called on every phase."""
    # works on arrays, never on Series: adding Series aligns by index, and a frame
    # coming out of a merge can carry duplicate labels (it would raise or misalign)
    joined = frame[columns[0]].astype(str).to_numpy(dtype=object)
    for column_name in columns[1:]:
        joined = joined + "|" + frame[column_name].astype(str).to_numpy(dtype=object)
    return pd.Series(joined, index=frame.index)


def hash_key(s):  # deterministic int64 hash key of the id (P7)
    return int(hashlib.md5(str(s).encode()).hexdigest()[:12], 16)

@dataclass
class Config:
    # ── raw column names (defaults = production, from the user's notebook) ──
    verbosity: str = "execution"
    period_col: str = "period"; dataset_role_col: str = "dataset_role"
    pipeline_units_col: str = "total_tr_units"
    pipeline_usd_col: str = "total_tr_usd"
    renewed_units_col: str = "total_renewed_units"
    renewed_usd_col: str = "total_renewed_usd"
    reacq_units_col: str = "total_reacquired_units"      # outside the renewal study; declared anyway
    reacq_usd_col: str = "total_reacquired_usd"
    auv_pipeline_col: str = "TR_AUV"                     # if present in the raw, declared as measures
    auv_renewed_col: str = "REN_AUV"
    auv_reacq_col: str = "ReAC_AUV"
    current_month_col: str = "is_current_month"
    flag_time_series_col: str = "flag_time_series"
    ts_revenue_col: str = "total_renewed_usd"     # revenue del universo time_series
    raw_data_path: str = None                     # compatibilidad con el notebook v4
    business_mandatory_dims: list = field(default_factory=lambda: [
        "tr_regional_level_1", "tr_regional_level_2", "tr_regional_level_3",
        "tr_product_level_1", "tr_product_level_2", "tr_origin_type_SKU_based",
        "tr_term_level_1", "tr_term_level_2", "tr_band_level_1", "tr_band_level_2"])
    structural_timevarying_dims: dict = field(default_factory=lambda: {"softcancel": "negative"})
    timevarying_positive_values: list = field(default_factory=lambda: [1, "1", True])
    extra_renovacion: list = field(default_factory=list)
    # former pricing covariate_cols → their new home in the taxonomy:
    extra_revalorizacion: list = field(default_factory=lambda: [
        "price_cap", "msrp_increased", "discount_interval", "prev_OperationGroup"])
    ignore_cols: list = field(default_factory=lambda: ["dummy_field", "row_id", "_filter"])
    # a missing month means "no contracts were due": the rate is undefined (0/0), NOT 0%.
    # "no_rate" keeps the row for continuity but leaves its rate NaN so techniques never
    # see a false 0% month. "zero_rate" restores the legacy behaviour.
    gap_rate_policy: str = "no_rate"
    support_floor: float = 30.0; z: float = 1.645            # 90%
    rate_cap: float = 0.95; k_cred: float = 60.0; k_uplift: float = 24.0
    semantic_labels: list = field(default_factory=list)       # [(col, valor, etiqueta)]
    outdir: str = "./salida"
    # ── SQL persistence (SQLAlchemy; adapted from the quarry) ──
    sql_server: str = None; sql_database: str = None
    sql_driver: str = "ODBC Driver 17 for SQL Server"
    sql_username: str = None; sql_password: str = None; sql_trusted: bool = True
    sql_schema: str = "dbo"                     # the schema is a config datum
    sql_write_mode: str = "replace"             # replace (DROP+CREATE) | truncate (keeps table definition)
    sql_chunksize: int = 50_000
    sql_engine: object = None                           # or inject an already-built engine
    sql_table_prefix: str = "sff_"
    sql_table_names: dict = field(default_factory=dict)   # overrides logical_name→physical table
    def __post_init__(self):
        for d, s in self.structural_timevarying_dims.items():
            if s not in ("negative", "positive"):
                raise ValueError(f"timevarying['{d}']='{s}': debe ser 'negative' o 'positive'")
        m = set(self.business_mandatory_dims)
        if m & set(self.structural_timevarying_dims) or m & set(self.extra_renovacion) or m & set(self.extra_revalorizacion):
            raise ValueError("mandatory es excluyente con timevarying y extras")
        if set(self.structural_timevarying_dims) & (set(self.extra_renovacion) | set(self.extra_revalorizacion)):
            raise ValueError("timevarying es excluyente con los grupos extra")
        self.execution_id = uuid.uuid4().hex[:10]; os.makedirs(self.outdir, exist_ok=True)
    @property
    def grano_tasa(self): return self.business_mandatory_dims + list(self.structural_timevarying_dims) + self.extra_renovacion
    @property
    def grano_uplift(self): return self.business_mandatory_dims + self.extra_revalorizacion
    @property
    def medidas(self):  # núcleo de cálculo
        return [self.pipeline_units_col, self.pipeline_usd_col,
                self.renewed_units_col, self.renewed_usd_col]
    @property
    def medidas_declaradas(self):  # medidas del raw fuera del cálculo (reacq, AUVs)
        return [c for c in (self.reacq_units_col, self.reacq_usd_col, self.auv_pipeline_col,
                            self.auv_renewed_col, self.auv_reacq_col) if c]
    def validar_columnas(self, df):
        """GOAL: the exhaustive contract (P3) — every raw column declared in exactly
        one role, or an exception listing the orphans. The first validation of all."""
        rol = set([self.period_col, self.dataset_role_col, self.current_month_col, self.flag_time_series_col] + self.medidas
                  + self.medidas_declaradas + self.grano_tasa + self.extra_revalorizacion
                  + self.ignore_cols)
        huerfanas = [c for c in df.columns if c not in rol]
        if huerfanas:
            raise ValueError(f"columns with no role in config: {huerfanas} — declare their group or add to ignore_cols")
    # ── nombres físicos predefinidos (editables vía sql_table_names) ──
    _NOMBRES = {"forecast_units_raw_summary": "fu_summary", "forecast_series_raw_summary": "fs_summary",
        "lookup_fu": "lookup_fu", "lookup_comb": "lookup_comb", "fact_fu": "fact_fu",
        "fact_fine": "fact_fine", "simpson_contrafactual": "simpson_contrafactual",
        "support_chain": "support_chain", "diagnostico_dinamica": "diag_dinamica",
        "uplift_chain": "uplift_chain", "forecast_detail": "forecast_detail",
        "backtest_predictions": "backtest_pred", "backtest_predictions_fu": "backtest_pred_fu",
        "forecast_predictions_fu": "forecast_pred_fu", "dim_tecnica": "dim_tecnica", "simpson_showcase": "simpson_showcase", "key_bridge": "key_bridge", "fact_fu_gaps": "fact_fu_gaps", "parent_ladder": "parent_ladder", "forecast_bands": "forecast_bands", "validation_report": "validation_report", "horizon_report_series": "horizon_report_series",
        "horizon_report_total": "horizon_report_total",
        "simpson_showcase_series": "simpson_showcase_series", "rolling_next_month": "rolling_next_month",
        "rolling_next_month_resumen": "rolling_nm_resumen",
        "forecast_final_seleccion": "forecast_seleccion"}
    def _asegurar_fast_executemany(self, eng):
        """fast_executemany is an attribute of the pyodbc CURSOR: forced via event on
        every executemany, whatever the engine's origin (built here or injected)."""
        if getattr(eng, "_sff_fast", False) or not str(eng.url).startswith("mssql"):
            return eng
        from sqlalchemy import event
        @event.listens_for(eng, "before_cursor_execute")
        def _f(conn, cursor, stmt, params, ctx, executemany):
            if executemany:
                cursor.fast_executemany = True
        eng._sff_fast = True
        return eng

    @property
    def engine(self):
        if self.sql_engine is not None:
            return self._asegurar_fast_executemany(self.sql_engine)
        if self.sql_engine is None and self.sql_server:
            import urllib.parse
            from sqlalchemy import create_engine
            auth = ("Trusted_Connection=yes;" if self.sql_trusted
                    else f"UID={self.sql_username};PWD={self.sql_password};")
            odbc = (f"DRIVER={{{self.sql_driver}}};SERVER={self.sql_server};"
                    f"DATABASE={self.sql_database};{auth}")
            self.sql_engine = create_engine(
                "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(odbc),
                fast_executemany=True)
        return self.sql_engine
    @staticmethod
    def _sanitize(df):
        out = df.copy()
        for c in list(out.columns):
            dt = out[c].dtype
            if isinstance(dt, pd.PeriodDtype):
                if f"{c}_date" not in out.columns:
                    out[f"{c}_date"] = out[c].dt.to_timestamp()
                out[c] = out[c].astype(str)
            elif isinstance(dt, pd.IntervalDtype):
                out[c] = out[c].astype(str)
            else:
                ej = out[c].dropna().head(1)
                if len(ej) and isinstance(ej.iloc[0], pd.Period):
                    out[c] = out[c].astype(str)
                elif len(ej) and isinstance(ej.iloc[0], (pd.DataFrame, pd.Series, list, dict, set)):
                    raise ValueError(f"write: column '{c}' holds nested objects — not writable")
        return out
    def _dtypes(self, out):
        from sqlalchemy.types import NVARCHAR
        m = {}
        for c in out.columns:
            if str(out[c].dtype) in ("object", "str", "string"):
                s = out[c].dropna().astype(str)
                n = int(s.str.len().max()) if len(s) else 1
                m[c] = NVARCHAR(min(max(int(n * 1.3) + 4, 8), 4000))
        return m
    def write(self, df, logical_table_name):
        """GOAL: persist one star-schema table with automatic traceability.
        INPUT:  df + LOGICAL name (the _NOMBRES registry maps it to physical).
        OUTPUT: the table in SQL (or CSV without an engine), with process_date and execution_id.
        STEPS: [1] sanitize (Period→str+_date; nested objects = named error) ·
        [2] stamp traceability · [3] resolve physical name and schema ·
        [4] write: truncate (real TRUNCATE, DELETE as last resort) or replace ·
        [5] stopwatch: rows/second on the console."""
        out = self._sanitize(df)
        out["process_date"] = datetime.datetime.now().isoformat(timespec="seconds")
        out["execution_id"] = self.execution_id
        physical_table_name = self.sql_table_names.get(logical_table_name, self.sql_table_prefix + self._NOMBRES.get(logical_table_name, logical_table_name))
        import time
        write_start_time = time.time()
        if self.engine is not None:
            qualified_table_name = f"[{self.sql_schema}].[{physical_table_name}]" if self.sql_schema else f"[{physical_table_name}]"
            effective_write_mode = self.sql_write_mode
            if effective_write_mode == "truncate":
                from sqlalchemy import inspect, text
                if inspect(self.engine).has_table(physical_table_name, schema=self.sql_schema):
                    with self.engine.begin() as con:
                        try:
                            # TRUNCATE: minimally logged and instantaneous (600k rows of
                            # DELETE = lock escalation + hundreds of MB of log)
                            con.execute(text(f"TRUNCATE TABLE {qualified_table_name}"))
                        except Exception:
                            # no permission or referencing FKs: DELETE as last resort
                            con.execute(text(f"DELETE FROM {qualified_table_name}"))
                    out.to_sql(physical_table_name, self.engine, schema=self.sql_schema, if_exists="append",
                               index=False, chunksize=self.sql_chunksize, dtype=self._dtypes(out))
                    dt = time.time() - write_start_time; print(f"[write] {len(out):,} rows → {qualified_table_name} (truncate, {dt:.1f}s, {len(out)/max(dt,.01):,.0f} rows/s)"); return out
                effective_write_mode = "replace"
            out.to_sql(physical_table_name, self.engine, schema=self.sql_schema, if_exists="replace",
                       index=False, chunksize=self.sql_chunksize, dtype=self._dtypes(out))
            dt = time.time() - write_start_time; print(f"[write] {len(out):,} rows → {qualified_table_name} (SQL {effective_write_mode}, {dt:.1f}s, {len(out)/max(dt,.01):,.0f} rows/s)")
        else:
            out.to_csv(os.path.join(self.outdir, f"{physical_table_name}.csv"), index=False)
            print(f"[write] {len(out):,} rows → {physical_table_name}.csv (sin engine: CSV)")
        return out
