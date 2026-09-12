"""config.py — SFF v2 · RUN · the configuration contract.

This module is the single place where the framework learns four things:

  1. TAXONOMY AND VALIDATION   which raw column plays which role (DISENO_V2 §3):
                               mandatory · timevarying (with sign) · extra_renovacion ·
                               extra_revalorizacion · measures · ignore. Every raw
                               column must be declared in exactly one role, or the
                               program stops (principle P3, the exhaustive contract).
  2. SERIES AND CELL COLUMNS   which columns define a rate series and an uplift cell.
                               DERIVED from the taxonomy, never typed:
                               rate_series_columns = mandatory + timevarying + extra_renovacion
                               uplift_cell_columns = mandatory + extra_revalorizacion
  3. KEYS AND IDS              how a row becomes an id ('|'-joined fields) and how an
                               id becomes a deterministic int64 key (P7).
  4. SQL PERSISTENCE           how a star-schema table is written back: physical name
                               registry with the `sff_` prefix, process_date and
                               execution_id stamped on every row, TRUNCATE/replace
                               semantics, fast_executemany on the pyodbc cursor.

  RAW SOURCE                   `read_raw()` returns the raw DataFrame and MUST be
                               overridden by the caller's main (production: its own
                               query; tests: the synthetic dataset). Nothing in `run/`
                               reads a file or a query.

Numerical contract: this file is a verbose rewrite of legacy `config.py`. The style
changed; the numbers did not. Any change in a key, an id, a column list or a written table
must be caught by `tests/test_pipeline.py` against the reference output.

Vocabulary: `extra_renovacion` / `extra_revalorizacion` are the doctrine names of the
two extra groups (the word "covariates" is forbidden). Persisted column names and
values stay in Spanish because they are the contract of the reference output and of the BI.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import datetime
import hashlib
import os
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.types import NVARCHAR


# ─── named constants ─────────────────────────────────────────────────────────────
# Accepted signs for a timevarying dimension: "negative" rotates towards churn (e.g.
# softcancel), "positive" rotates towards renewal (e.g. autorenew).
VALID_TIMEVARYING_SIGNS = ("negative", "positive")

# Separator between the fields of an id. Ids are '|'-joined in the order
# `mandatory | timevarying | extra_renovacion | month` for a forecast unit.
ID_FIELD_SEPARATOR = "|"

# Separator between fu_id and comb_id when they are fused into one single-column key
# (`fu_comb_key`), so the BI can join the raw anchor to the key bridge with ONE
# relationship.
COMBINED_ID_SEPARATOR = "||"

# The key of an id is the first 12 hex digits of its MD5, read as an integer: it fits
# a SQL bigint and is reproducible across runs, machines and languages (P7).
HASH_HEX_DIGITS = 12

# Length of the execution identifier stamped on every persisted row.
EXECUTION_ID_LENGTH = 10

# Sizing rule for NVARCHAR columns on SQL Server: observed max length × 1.3 + 4,
# never below 8 and never above the NVARCHAR(4000) ceiling.
NVARCHAR_GROWTH_FACTOR = 1.3
NVARCHAR_GROWTH_PADDING = 4
NVARCHAR_MIN_LENGTH = 8
NVARCHAR_MAX_LENGTH = 4000

# Floor of the write stopwatch so rows/second never divides by zero.
MIN_ELAPSED_SECONDS = 0.01

# Logical table name → physical suffix. The physical table is `sql_table_prefix` +
# suffix (e.g. `sff_fu_summary`), unless `sql_table_names` overrides the logical name.
# This registry is a datum of the contract: the reference output and the BI expect these names.
PHYSICAL_TABLE_NAMES = {
    "forecast_units_raw_summary": "fu_summary",
    "forecast_series_raw_summary": "fs_summary",
    "lookup_fu": "lookup_fu",
    "lookup_comb": "lookup_comb",
    "fact_fu": "fact_fu",
    "fact_fine": "fact_fine",
    "fact_fu_gaps": "fact_fu_gaps",
    "key_bridge": "key_bridge",
    "simpson_contrafactual": "simpson_contrafactual",
    "simpson_showcase": "simpson_showcase",
    "simpson_showcase_series": "simpson_showcase_series",
    "support_chain": "support_chain",
    "parent_ladder": "parent_ladder",
    "diagnostico_dinamica": "diag_dinamica",
    "uplift_chain": "uplift_chain",
    "forecast_detail": "forecast_detail",
    "forecast_bands": "forecast_bands",
    "backtest_predictions": "backtest_pred",
    "backtest_predictions_fu": "backtest_pred_fu",
    "forecast_predictions_fu": "forecast_pred_fu",
    "forecast_final_seleccion": "forecast_seleccion",
    "dim_tecnica": "dim_tecnica",
    "rolling_next_month": "rolling_next_month",
    "rolling_next_month_resumen": "rolling_nm_resumen",
    "horizon_report_series": "horizon_report_series",
    "horizon_report_total": "horizon_report_total",
    "validation_report": "validation_report",
}


# ═══════════════════════════════════════════════════════════════════════════════════
# BLOCK 3 · KEYS AND IDS
# (module-level functions: every phase imports them; they do not depend on Config)
# ═══════════════════════════════════════════════════════════════════════════════════

def join_columns(frame: pd.DataFrame, columns: list) -> pd.Series:
    """Build the '|'-joined id of every row from several columns, vectorized.

    INPUT:   frame — any DataFrame · columns — ordered list of column names to join.
    OUTPUT:  Series of str, one id per row, indexed like `frame`.
    RULES:   fields are joined in the order given, cast with `astype(str)`, with
             ID_FIELD_SEPARATOR between them. The ORDER is contractual: the same
             columns in another order produce a different id and a different key.
    EDGE CASES: `columns` must be non-empty. Works on NumPy arrays, never on Series:
             adding Series aligns by index, and a frame coming out of a merge can carry
             duplicate index labels (it would raise or silently misalign). Measured at
             600k×10 rows: ~3 s here versus ~46 s with the row-by-row
             `frame[cols].astype(str).agg("|".join, axis=1)` (x16).
    CONSOLE: nothing.
    STEPS:
      [1] Start from the first column as an object array of strings.
      [2] Append every remaining column with the separator in front.
      [3] Return a Series aligned to the frame's index.
    """
    # [1] first field: the seed of the id, as a plain object array
    joined_ids = frame[columns[0]].astype(str).to_numpy(dtype=object)

    # [2] every further field is glued after a separator, still on arrays
    for column_name in columns[1:]:
        next_field = frame[column_name].astype(str).to_numpy(dtype=object)
        joined_ids = joined_ids + ID_FIELD_SEPARATOR + next_field

    # [3] back to a Series that carries the caller's index
    return pd.Series(joined_ids, index=frame.index)


def hash_key(identifier) -> int:
    """Deterministic int64 key of an id (P7: keys are derived, never assigned).

    INPUT:   identifier — anything; it is cast with `str()` first.
    OUTPUT:  int, the first HASH_HEX_DIGITS (12) hex digits of MD5(str(identifier)),
             read as a base-16 integer.
    RULES:   the same id always yields the same key, on any machine and in any run.
             12 hex digits = 48 bits, so the key fits a SQL bigint.
    EDGE CASES: collisions are possible in theory (48 bits) and have never been observed;
             fu_id uniqueness is asserted in phase 0 on the id, not on the key.
    CONSOLE: nothing.
    STEPS:
      [1] Cast to str and encode as UTF-8 bytes.
      [2] MD5 hex digest, keep the first 12 hex digits.
      [3] Parse them as an integer.
    """
    # [1] canonical text form of the id
    identifier_bytes = str(identifier).encode()

    # [2] first 12 hex digits of the MD5 digest
    digest_prefix = hashlib.md5(identifier_bytes).hexdigest()[:HASH_HEX_DIGITS]

    # [3] the key is that prefix read in base 16
    return int(digest_prefix, 16)


# ═══════════════════════════════════════════════════════════════════════════════════
# THE CONFIG
# ═══════════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    """The single declaration of what the raw data IS and where the results GO.

    PURPOSE. Every phase of the framework needs to answer the same four questions, and
    none of them should answer any of them on its own: which column plays which role,
    which columns define a series and a cell in each branch, how a row becomes an id and a key, and under
    what name a result table is persisted. `Config` is the one place where those
    answers live, so that a change of taxonomy, of series definition or of destination is a change
    in ONE file and not a search across five phases.

    WHAT IT GUARANTEES.
      · Exhaustiveness (P3): a raw column with no declared role stops the run. There is
        no "unknown column" path, and therefore no column silently ignored.
      · Consistency of the taxonomy (DISENO_V2 §3): the exclusion rules are checked at
        construction, so a misdeclared Config never reaches a phase.
      · Derived definitions: the columns of a rate series and of an uplift cell are
        computed from the taxonomy by formula, never typed by hand; they cannot drift
        apart from it.
      · Reproducible identity: the same row yields the same id and the same key in any
        run, on any machine — the keys in SQL survive a re-execution.
      · Traceable persistence: every written row carries `process_date` and
        `execution_id`, and every table lands under the physical name of the registry.

    WHAT IT DOES NOT DO. It does not know where the raw comes from (`read_raw` is
    overridden by the caller's main), does not compute
    any forecast quantity, and does not decide anything measured: η², chosen technique
    and error bands are decisions of ANALYSIS, persisted in the decision tables
    (DISENO_SPLIT §3). Only the versioned business parameters live here
    (`support_floor`, `z`, `rate_cap`, `k_cred`, `k_uplift`, `gap_rate_policy`):
    they are decisions of the repository, not measurements of a run.

    USAGE. Subclass it in your main and override `read_raw()`; `Config()` fields with
    no arguments are production. Tests pass a smaller taxonomy and inject a sqlite
    engine. Field names are the public contract used by every phase, by the runners and
    by the regeneration prompts; they do not change.
    """

    # ─── raw column names (defaults = production, from the user's notebook) ─────────
    period_col: str = "period"
    dataset_role_col: str = "dataset_role"
    pipeline_units_col: str = "total_tr_units"
    pipeline_usd_col: str = "total_tr_usd"
    renewed_units_col: str = "total_renewed_units"
    renewed_usd_col: str = "total_renewed_usd"
    # reacquisitions are outside the renewal study but present in the raw: declared
    reacq_units_col: str = "total_reacquired_units"
    reacq_usd_col: str = "total_reacquired_usd"
    # AUV columns, if present in the raw, are declared as measures (never computed from)
    auv_pipeline_col: str = "TR_AUV"
    auv_renewed_col: str = "REN_AUV"
    auv_reacq_col: str = "ReAC_AUV"
    current_month_col: str = "is_current_month"
    flag_time_series_col: str = "flag_time_series"
    # revenue column of the time_series universe; declared for the universe contract,
    # not read by any phase yet (reserved for the time_series treatment)
    ts_revenue_col: str = "total_renewed_usd"

    # ─── taxonomy (DISENO_V2 §3) ────────────────────────────────────────────────────
    # mandatory: opens both the rate series and the uplift cell; never collapsed in pools;
    # exclusive with every other group
    business_mandatory_dims: list = field(default_factory=lambda: [
        "tr_regional_level_1", "tr_regional_level_2", "tr_regional_level_3",
        "tr_product_level_1", "tr_product_level_2", "tr_origin_type_SKU_based",
        "tr_term_level_1", "tr_term_level_2", "tr_band_level_1", "tr_band_level_2"])
    # timevarying: dichotomous columns that rotate with the calendar; each carries its
    # sign; handled in L1; exclusive with mandatory and with both extra groups
    structural_timevarying_dims: dict = field(default_factory=lambda: {"softcancel": "negative"})
    # which raw values mean "flag is on" for a timevarying column
    timevarying_positive_values: list = field(default_factory=lambda: [1, "1", True])
    # extra_renovacion: enters the rate series only; may overlap extra_revalorizacion
    extra_renovacion: list = field(default_factory=list)
    # extra_revalorizacion: enters the uplift cell only (former pricing columns)
    extra_revalorizacion: list = field(default_factory=lambda: [
        "price_cap", "msrp_increased", "discount_interval", "prev_OperationGroup"])
    # ignore: present in the raw, read by nobody
    ignore_cols: list = field(default_factory=lambda: ["dummy_field", "row_id", "_filter"])
    # optional semantic labels (column, value, label); empty on purpose in production
    semantic_labels: list = field(default_factory=list)

    # ─── business parameters (versioned decisions; DISENO_SPLIT §3) ────────────────
    # A missing month means "no contracts were due": the rate is undefined (0/0), NOT 0%.
    # "no_rate" keeps the gap row for continuity but leaves its rate NaN, so no
    # technique ever sees a false 0% month. "zero_rate" restores the legacy behaviour.
    gap_rate_policy: str = "no_rate"
    support_floor: float = 30.0
    z: float = 1.645          # 90% two-sided
    rate_cap: float = 0.95
    k_cred: float = 60.0
    k_uplift: float = 24.0

    # ─── output ─────────────────────────────────────────────────────────────────────
    outdir: str = "./salida"

    # ─── SQL persistence (SQLAlchemy) ───────────────────────────────────────────────
    sql_server: Optional[str] = None
    sql_database: Optional[str] = None
    sql_driver: str = "ODBC Driver 17 for SQL Server"
    sql_username: Optional[str] = None
    sql_password: Optional[str] = None
    sql_trusted: bool = True
    sql_schema: Optional[str] = "dbo"        # the schema is a config datum
    sql_write_mode: str = "replace"          # replace (DROP+CREATE) | truncate (keeps DDL)
    sql_chunksize: int = 50_000
    sql_engine: object = None                # or inject an already-built engine
    sql_table_prefix: str = "sff_"
    sql_table_names: dict = field(default_factory=dict)   # logical name → physical override

    # ═══════════════════════════════════════════════════════════════════════════════
    # RAW SOURCE (override in your own main; run/ never reads a file or a query)
    # ═══════════════════════════════════════════════════════════════════════════════

    def read_raw(self) -> pd.DataFrame:
        """Return the raw extract as a DataFrame. MUST be overridden by the caller.

        INPUT:   none (the subclass decides: a SQL query, a file, a generator).
        OUTPUT:  a DataFrame with every column of the extract; the pipeline validates
                 it against the column contract before computing anything.
        RULES:   the framework assumes nothing about where the raw comes from. The
                 production main subclasses Config and reads its query; the test main
                 subclasses Config and builds the synthetic dataset. `run/` contains no
                 loading code of any kind.
        EDGE CASES: the base implementation raises NotImplementedError with the
                 instruction, so a Config used without an override fails at the first
                 step with a sentence, not a downstream AttributeError.
        CONSOLE: nothing.
        STEPS:
          [1] Refuse: this method only exists to be overridden.
        """
        # [1] there is no default source, on purpose
        raise NotImplementedError(
            "Config.read_raw() must be overridden: subclass Config in your main and "
            "return the raw DataFrame from your own query or dataset")

    # ═══════════════════════════════════════════════════════════════════════════════
    # BLOCK 1 · TAXONOMY AND VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════════

    def __post_init__(self) -> None:
        """Validate the taxonomy and prepare the execution context.

        INPUT:   the dataclass fields as given by the caller.
        OUTPUT:  none; sets `execution_id` and creates `outdir`.
        RULES:   the exclusion rules of DISENO_V2 §3 are checked here, once, at
                 construction: a misdeclared taxonomy never reaches a phase.
        EDGE CASES: an invalid sign or an overlap raises ValueError naming the culprit.
        CONSOLE: nothing.
        STEPS:
          [1] Check the taxonomy (signs and exclusions).
          [2] Mint the execution identifier stamped on every persisted row.
          [3] Make sure the output folder exists.
        """
        # [1] taxonomy first: everything downstream assumes it is consistent
        self._validate_taxonomy()

        # [2] one short random id per execution, shared by all the tables it writes
        self.execution_id = uuid.uuid4().hex[:EXECUTION_ID_LENGTH]

        # [3] the CSV fallback of `write` needs the folder
        os.makedirs(self.outdir, exist_ok=True)

    def _validate_taxonomy(self) -> None:
        """Enforce the exclusion rules of the 4-group taxonomy (DISENO_V2 §3).

        INPUT:   the taxonomy fields of this Config.
        OUTPUT:  none.
        RULES:   every timevarying sign is "negative" or "positive" · mandatory is
                 exclusive with timevarying and with both extra groups · timevarying is
                 exclusive with both extra groups · the two extra groups MAY overlap.
        EDGE CASES: raises ValueError with the offending column names.
        CONSOLE: nothing.
        STEPS:
          [1] Every timevarying dimension carries a valid sign.
          [2] Mandatory does not overlap timevarying, extra_renovacion or
              extra_revalorizacion.
          [3] Timevarying does not overlap the extra groups.
        """
        # [1] a timevarying without a valid sign cannot be grouped in L1
        for dimension_name, sign in self.structural_timevarying_dims.items():
            if sign not in VALID_TIMEVARYING_SIGNS:
                raise ValueError(
                    f"timevarying['{dimension_name}']='{sign}': "
                    f"the sign must be one of {VALID_TIMEVARYING_SIGNS}")

        # [2] mandatory is exclusive with every other dimension group
        mandatory_set = set(self.business_mandatory_dims)
        timevarying_set = set(self.structural_timevarying_dims)
        extra_renovacion_set = set(self.extra_renovacion)
        extra_revalorizacion_set = set(self.extra_revalorizacion)
        mandatory_overlap = (mandatory_set & timevarying_set
                             | mandatory_set & extra_renovacion_set
                             | mandatory_set & extra_revalorizacion_set)
        if mandatory_overlap:
            raise ValueError(
                f"mandatory is exclusive with timevarying and with the extra groups; "
                f"overlapping columns: {sorted(mandatory_overlap)}")

        # [3] timevarying is exclusive with the extra groups (the extras may overlap
        #     each other: a column can serve both the rate and the uplift)
        timevarying_overlap = timevarying_set & (extra_renovacion_set | extra_revalorizacion_set)
        if timevarying_overlap:
            raise ValueError(
                f"timevarying is exclusive with the extra groups; "
                f"overlapping columns: {sorted(timevarying_overlap)}")

    def validate_column_contract(self, frame: pd.DataFrame) -> None:
        """The exhaustive contract (P3): every raw column has exactly one role.

        INPUT:   frame — the raw extract as loaded.
        OUTPUT:  none.
        RULES:   the set of declared columns is: period, role, current-month flag,
                 time-series flag, the four core measures, the declared measures, the
                 rate series columns, extra_revalorizacion and ignore_cols. Any raw column outside
                 that set is an orphan and stops the run. Declared columns MISSING from
                 the raw are not checked here: the phases fail on first access.
        EDGE CASES: raises ValueError listing every orphan column at once.
        CONSOLE: nothing.
        STEPS:
          [1] Assemble the set of columns that have a role.
          [2] List the raw columns outside that set.
          [3] Stop if there is any orphan.
        """
        # [1] every column the taxonomy knows about
        context_columns = [self.period_col, self.dataset_role_col,
                           self.current_month_col, self.flag_time_series_col]
        declared_columns = set(context_columns
                               + self.core_measures
                               + self.declared_measures
                               + self.rate_series_columns
                               + self.extra_revalorizacion
                               + self.ignore_cols)

        # [2] the orphans: present in the raw, declared nowhere
        orphan_columns = [column_name for column_name in frame.columns
                          if column_name not in declared_columns]

        # [3] an orphan is a contract violation, not a warning
        if orphan_columns:
            raise ValueError(
                f"columns with no role in config: {orphan_columns} — "
                f"declare their group or add them to ignore_cols")

    # ═══════════════════════════════════════════════════════════════════════════════
    # BLOCK 2 · SERIES AND CELL COLUMNS (derived from the taxonomy, never typed)
    # ═══════════════════════════════════════════════════════════════════════════════

    @property
    def rate_series_columns(self) -> list:
        """The columns that define ONE renewal-rate series (a forecast series, `fs_id`).

        = mandatory + timevarying + extra_renovacion. Every distinct combination of these
        columns is one series; with the month appended it is one forecast unit (`fu_id`).
        The order is contractual: it is the field order of `fu_id` and `fs_id`.
        """
        return (self.business_mandatory_dims
                + list(self.structural_timevarying_dims)
                + self.extra_renovacion)

    @property
    def uplift_cell_columns(self) -> list:
        """The columns that define ONE uplift cell (`gu` / `uplift_cell_key`).

        = mandatory + extra_revalorizacion. The uplift has no time axis: it is estimated
        over every month at once, so its unit is a static cell, not a series.
        """
        return self.business_mandatory_dims + self.extra_revalorizacion

    @property
    def core_measures(self) -> list:
        """The four measures the forecast computes with: pipeline and renewed, units and USD."""
        return [self.pipeline_units_col, self.pipeline_usd_col,
                self.renewed_units_col, self.renewed_usd_col]

    @property
    def declared_measures(self) -> list:
        """Measures of the raw outside the computation (reacquisitions, AUVs).

        They are declared so the contract accepts them; nobody computes from them.
        A column configured as None or "" is simply not expected in the raw.
        """
        candidate_columns = (self.reacq_units_col, self.reacq_usd_col,
                             self.auv_pipeline_col, self.auv_renewed_col, self.auv_reacq_col)
        present_columns = [column_name for column_name in candidate_columns if column_name]
        return present_columns

    # ─── legacy aliases (Spanish names used by phases 1-4 until their own rewrite) ──
    # Removed in chat 6, when no legacy module imports them any more.

    @property
    def grano_tasa(self) -> list:
        """Legacy alias of `rate_series_columns`."""
        return self.rate_series_columns

    @property
    def grano_uplift(self) -> list:
        """Legacy alias of `uplift_cell_columns`."""
        return self.uplift_cell_columns

    @property
    def medidas(self) -> list:
        """Legacy alias of `core_measures`."""
        return self.core_measures

    @property
    def medidas_declaradas(self) -> list:
        """Legacy alias of `declared_measures`."""
        return self.declared_measures

    def validar_columnas(self, frame: pd.DataFrame) -> None:
        """Legacy alias of `validate_column_contract`."""
        self.validate_column_contract(frame)

    # ═══════════════════════════════════════════════════════════════════════════════
    # BLOCK 4 · SQL PERSISTENCE
    # ═══════════════════════════════════════════════════════════════════════════════

    @property
    def engine(self):
        """The SQLAlchemy engine, built lazily from the SQL fields or injected.

        INPUT:   sql_engine (injected) or sql_server + sql_database + auth fields.
        OUTPUT:  an Engine with fast_executemany guaranteed on mssql, or None when no
                 engine is injected and no server is configured (CSV fallback).
        RULES:   an injected engine wins; a built engine is cached in `sql_engine`.
        EDGE CASES: trusted connection when `sql_trusted`, else UID/PWD.
        CONSOLE: nothing.
        STEPS:
          [1] Injected engine: reuse it, only making sure fast_executemany is on.
          [2] No engine but a server: build the mssql+pyodbc engine once and cache it.
          [3] Neither: None (the writer falls back to CSV).
        """
        # [1] an injected engine (tests use sqlite, production may inject mssql)
        if self.sql_engine is not None:
            return self._ensure_fast_executemany(self.sql_engine)

        # [2] build from the connection fields, once
        if self.sql_server:
            if self.sql_trusted:
                auth_fragment = "Trusted_Connection=yes;"
            else:
                auth_fragment = f"UID={self.sql_username};PWD={self.sql_password};"
            odbc_connection_string = (f"DRIVER={{{self.sql_driver}}};SERVER={self.sql_server};"
                                      f"DATABASE={self.sql_database};{auth_fragment}")
            sqlalchemy_url = ("mssql+pyodbc:///?odbc_connect="
                              + urllib.parse.quote_plus(odbc_connection_string))
            self.sql_engine = create_engine(sqlalchemy_url, fast_executemany=True)

        # [3] None when nothing is configured
        return self.sql_engine

    @staticmethod
    def _ensure_fast_executemany(sqlalchemy_engine):
        """Force `fast_executemany` on every executemany of an mssql engine.

        INPUT:   sqlalchemy_engine — built here or injected by the caller.
        OUTPUT:  the same engine, with the cursor event registered at most once.
        RULES:   fast_executemany is an attribute of the pyodbc CURSOR, not of the
                 engine; the only way to guarantee it for an injected engine is a
                 `before_cursor_execute` listener. Non-mssql engines are returned as is.
        EDGE CASES: idempotent: a private flag on the engine prevents double registration.
        CONSOLE: nothing.
        STEPS:
          [1] Skip if already done or if the dialect is not mssql.
          [2] Register the listener that flips the cursor flag on executemany.
          [3] Mark the engine as done.
        """
        # [1] nothing to do for sqlite or for an engine already patched
        already_patched = getattr(sqlalchemy_engine, "_sff_fast", False)
        is_mssql = str(sqlalchemy_engine.url).startswith("mssql")
        if already_patched or not is_mssql:
            return sqlalchemy_engine

        # [2] the listener runs before every statement; only executemany is affected
        @event.listens_for(sqlalchemy_engine, "before_cursor_execute")
        def enable_fast_executemany(connection, cursor, statement, parameters,
                                    context, executemany):
            if executemany:
                cursor.fast_executemany = True

        # [3] remember it, so a second call is a no-op
        sqlalchemy_engine._sff_fast = True
        return sqlalchemy_engine

    @staticmethod
    def _sanitize_for_persistence(frame: pd.DataFrame) -> pd.DataFrame:
        """Make a frame writable by pandas `to_sql` / `to_csv` without losing information.

        INPUT:   frame — any table produced by a phase.
        OUTPUT:  a copy where Period columns become str (plus a `<col>_date` timestamp
                 column, if not already present) and Interval columns become str.
        RULES:   the original frame is never modified. A `<col>_date` companion is
                 added ONLY for columns with a PeriodDtype; a column of Period objects
                 in an object column is cast to str without a companion (legacy
                 behaviour, kept for equivalence).
        EDGE CASES: a column holding nested objects (DataFrame, Series, list, dict, set)
                 raises a named error instead of a cryptic driver failure.
        CONSOLE: nothing.
        STEPS:
          [1] Copy the frame.
          [2] Period dtype → str + `<col>_date`; Interval dtype → str.
          [3] Object columns: Period objects → str; nested objects → error.
        """
        # [1] never touch the phase's frame
        sanitized_frame = frame.copy()

        for column_name in list(sanitized_frame.columns):
            column_dtype = sanitized_frame[column_name].dtype

            # [2] typed Period / Interval columns
            if isinstance(column_dtype, pd.PeriodDtype):
                companion_column = f"{column_name}_date"
                if companion_column not in sanitized_frame.columns:
                    sanitized_frame[companion_column] = sanitized_frame[column_name].dt.to_timestamp()
                sanitized_frame[column_name] = sanitized_frame[column_name].astype(str)
                continue
            if isinstance(column_dtype, pd.IntervalDtype):
                sanitized_frame[column_name] = sanitized_frame[column_name].astype(str)
                continue

            # [3] object columns: inspect the first non-null value
            first_non_null = sanitized_frame[column_name].dropna().head(1)
            if len(first_non_null) == 0:
                continue
            sample_value = first_non_null.iloc[0]
            if isinstance(sample_value, pd.Period):
                sanitized_frame[column_name] = sanitized_frame[column_name].astype(str)
            elif isinstance(sample_value, (pd.DataFrame, pd.Series, list, dict, set)):
                raise ValueError(
                    f"write: column '{column_name}' holds nested objects — not writable")

        return sanitized_frame

    @staticmethod
    def _nvarchar_dtypes(frame: pd.DataFrame) -> dict:
        """Size every text column as NVARCHAR(n) for SQL Server.

        INPUT:   frame — already sanitized.
        OUTPUT:  dict column → NVARCHAR(length) for object/str/string columns only.
        RULES:   length = max observed × NVARCHAR_GROWTH_FACTOR + NVARCHAR_GROWTH_PADDING,
                 clamped to [NVARCHAR_MIN_LENGTH, NVARCHAR_MAX_LENGTH]. An all-null
                 text column gets the minimum.
        EDGE CASES: numeric and datetime columns are left to pandas' default mapping.
        CONSOLE: nothing.
        STEPS:
          [1] For every text column, measure the longest value.
          [2] Apply the growth rule and the clamp.
        """
        dtype_by_column = {}
        for column_name in frame.columns:
            is_text_column = str(frame[column_name].dtype) in ("object", "str", "string")
            if not is_text_column:
                continue

            # [1] longest observed text (1 when the column is entirely null)
            non_null_text = frame[column_name].dropna().astype(str)
            if len(non_null_text) > 0:
                longest_observed = int(non_null_text.str.len().max())
            else:
                longest_observed = 1

            # [2] leave headroom for future values, within SQL Server's limits
            grown_length = int(longest_observed * NVARCHAR_GROWTH_FACTOR) + NVARCHAR_GROWTH_PADDING
            clamped_length = min(max(grown_length, NVARCHAR_MIN_LENGTH), NVARCHAR_MAX_LENGTH)
            dtype_by_column[column_name] = NVARCHAR(clamped_length)
        return dtype_by_column

    def _resolve_physical_table_name(self, logical_table_name: str) -> str:
        """Map a logical table name to its physical name.

        INPUT:   logical_table_name — as used by the phases ("fact_fu", ...).
        OUTPUT:  the physical table name.
        RULES:   an explicit override in `sql_table_names` wins; otherwise prefix +
                 registry suffix; a logical name absent from the registry keeps its
                 own name (prefixed).
        EDGE CASES: none.
        CONSOLE: nothing.
        STEPS:
          [1] Override, if configured.
          [2] Prefix + registry suffix (or the logical name itself).
        """
        # [1] the caller may pin any physical name
        if logical_table_name in self.sql_table_names:
            return self.sql_table_names[logical_table_name]

        # [2] the registry, with the logical name as fallback suffix
        registry_suffix = PHYSICAL_TABLE_NAMES.get(logical_table_name, logical_table_name)
        return self.sql_table_prefix + registry_suffix

    def _qualified_table_name(self, physical_table_name: str) -> str:
        """`[schema].[table]` when a schema is configured, else `[table]` (sqlite)."""
        if self.sql_schema:
            return f"[{self.sql_schema}].[{physical_table_name}]"
        return f"[{physical_table_name}]"

    def _empty_table_keeping_definition(self, qualified_table_name: str) -> None:
        """Empty an existing table with TRUNCATE, falling back to DELETE.

        INPUT:   qualified_table_name — `[schema].[table]`.
        OUTPUT:  none; the table is empty and its DDL untouched.
        RULES:   TRUNCATE is minimally logged and instantaneous; 600k rows of DELETE
                 mean lock escalation and hundreds of MB of log. DELETE is the LAST
                 resort, used only when TRUNCATE fails (no permission, referencing FKs).
        EDGE CASES: any exception from TRUNCATE triggers the DELETE path.
        CONSOLE: nothing.
        STEPS:
          [1] Try TRUNCATE inside a transaction.
          [2] On failure, DELETE inside the same transaction.
        """
        with self.engine.begin() as connection:
            try:
                # [1] the cheap path
                connection.execute(text(f"TRUNCATE TABLE {qualified_table_name}"))
            except Exception:
                # [2] the expensive but always-allowed path
                connection.execute(text(f"DELETE FROM {qualified_table_name}"))

    def _write_to_sql(self, sanitized_frame: pd.DataFrame, physical_table_name: str) -> str:
        """Write one table to the engine honouring `sql_write_mode`.

        INPUT:   sanitized_frame (traceability columns already stamped) ·
                 physical_table_name.
        OUTPUT:  the effective write mode used ("truncate" or "replace").
        RULES:   "truncate" keeps the table definition when the table exists (empty +
                 append); when it does not exist yet, the first write is a "replace".
                 "replace" drops and recreates. Text columns are sized with
                 `_nvarchar_dtypes`; rows go in chunks of `sql_chunksize`.
        EDGE CASES: a "truncate" on a missing table silently becomes "replace".
        CONSOLE: nothing (the caller prints the stopwatch line).
        STEPS:
          [1] Truncate mode on an existing table: empty it, then append.
          [2] Otherwise: replace.
        """
        effective_write_mode = self.sql_write_mode
        qualified_table_name = self._qualified_table_name(physical_table_name)
        text_column_types = self._nvarchar_dtypes(sanitized_frame)

        # [1] keep the DDL (indexes, permissions, BI bindings): empty and append
        if effective_write_mode == "truncate":
            table_exists = inspect(self.engine).has_table(physical_table_name, schema=self.sql_schema)
            if table_exists:
                self._empty_table_keeping_definition(qualified_table_name)
                sanitized_frame.to_sql(physical_table_name, self.engine, schema=self.sql_schema,
                                       if_exists="append", index=False,
                                       chunksize=self.sql_chunksize, dtype=text_column_types)
                return "truncate"
            effective_write_mode = "replace"

        # [2] drop and recreate
        sanitized_frame.to_sql(physical_table_name, self.engine, schema=self.sql_schema,
                               if_exists="replace", index=False,
                               chunksize=self.sql_chunksize, dtype=text_column_types)
        return effective_write_mode

    def write(self, frame: pd.DataFrame, logical_table_name: str) -> pd.DataFrame:
        """Persist one star-schema table with automatic traceability.

        INPUT:   frame — the table as produced by a phase · logical_table_name — the
                 LOGICAL name (PHYSICAL_TABLE_NAMES maps it to the physical one).
        OUTPUT:  the sanitized frame that was written (with process_date and
                 execution_id), so callers can keep using it.
        RULES:   every row is stamped with `process_date` (ISO, seconds) and
                 `execution_id`; with an engine the table goes to SQL, without one it
                 goes to `<outdir>/<physical>.csv`. Period columns become str with a
                 `<col>_date` companion (see `_sanitize_for_persistence`).
        EDGE CASES: nested objects in a column stop the write with a named error.
        CONSOLE: one line per table: rows, destination, mode, seconds and rows/second.
        STEPS:
          [1] Sanitize the frame for the driver.
          [2] Stamp traceability.
          [3] Resolve the physical name.
          [4] Write to SQL (truncate/replace) or to CSV, timing it.
          [5] Report rows, destination and throughput.
        """
        # [1] Period/Interval → str, nested objects → error
        sanitized_frame = self._sanitize_for_persistence(frame)

        # [2] every persisted row knows when and by which execution it was written
        sanitized_frame["process_date"] = datetime.datetime.now().isoformat(timespec="seconds")
        sanitized_frame["execution_id"] = self.execution_id

        # [3] logical → physical
        physical_table_name = self._resolve_physical_table_name(logical_table_name)
        row_count = len(sanitized_frame)

        # [4] SQL when there is an engine, CSV otherwise
        write_start_time = time.time()
        if self.engine is not None:
            effective_write_mode = self._write_to_sql(sanitized_frame, physical_table_name)
            destination = self._qualified_table_name(physical_table_name)
            mode_label = "truncate" if effective_write_mode == "truncate" else f"SQL {effective_write_mode}"
        else:
            csv_path = os.path.join(self.outdir, f"{physical_table_name}.csv")
            sanitized_frame.to_csv(csv_path, index=False)
            destination = f"{physical_table_name}.csv"
            mode_label = "no engine: CSV"

        # [5] the stopwatch line: what was written, where, and how fast
        elapsed_seconds = time.time() - write_start_time
        rows_per_second = row_count / max(elapsed_seconds, MIN_ELAPSED_SECONDS)
        print(f"[write] {row_count:,} rows → {destination} "
              f"({mode_label}, {elapsed_seconds:.1f}s, {rows_per_second:,.0f} rows/s)")
        return sanitized_frame
