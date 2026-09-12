"""main.py — SFF v3 · production entry point.

Three things, nothing else: a Config whose `read_raw` returns the extract, the engine
the tables go to, and one of the two runners. No parameters, no files.

    python main.py             # the monthly RUN (reads the decisions of the last analysis)
    python main.py analysis    # the ANALYSIS (decides, writes decision_*, produces the forecast)

The raw comes from your own query; write it in `KamelotConfig.read_raw` below. The
framework assumes only that the method returns a DataFrame with every column of the
extract: the column contract (phase 0) checks the rest.

The test entry point is `test_pipeline.py`: the same lines with `read_raw` returning
the synthetic dataset and a throw-away sqlite engine.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import sys

import pandas as pd

# every module lives in this folder; make sure it is importable.
PROJECT_FOLDER = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, PROJECT_FOLDER)

from config import Config                       # noqa: E402
from pipeline import run_analysis, run_pipeline  # noqa: E402


# ─── named constants ─────────────────────────────────────────────────────────────
# Fill in with the query that produces the raw extract (every declared column).
RAW_EXTRACT_QUERY = "SELECT * FROM ..."
ANALYSIS_KEYWORD = "analysis"


class KamelotConfig(Config):
    """Production Config: `Config()` defaults (the production taxonomy) + the raw query."""

    def read_raw(self) -> pd.DataFrame:
        """The raw extract, read with the configured engine."""
        return pd.read_sql(RAW_EXTRACT_QUERY, self.engine)


if __name__ == "__main__":
    configuration = KamelotConfig(sql_server="...", sql_database="Kamelot",
                                  backtest_test_start="2026-01",       # the 2026 months already happened
                                  extended_horizon_end="2027-12")      # simulate the pipeline into 2027
    if ANALYSIS_KEYWORD in sys.argv[1:]:
        run_analysis(configuration)
    else:
        run_pipeline(configuration)
