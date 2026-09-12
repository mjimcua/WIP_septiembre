"""main.py — SFF v2 · production run.

Three things, nothing else: a Config whose `read_raw` returns the extract, the engine
the tables go to, and `run_pipeline`. No parameters, no files.

    python main.py

The raw comes from your own query; write it in `KamelotConfig.read_raw` below. The
framework assumes only that the method returns a DataFrame with every column of the
extract: the column contract (phase 0) checks the rest.

The test main is `tests/test_pipeline.py`: the same three lines with `read_raw`
returning the synthetic dataset and a throw-away sqlite engine.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import sys

import pandas as pd

REPOSITORY_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(REPOSITORY_ROOT, "run"))

from config import Config          # noqa: E402
from pipeline import run_pipeline  # noqa: E402


# ─── named constants ─────────────────────────────────────────────────────────────
# Fill in with the query that produces the raw extract (every declared column).
RAW_EXTRACT_QUERY = "SELECT * FROM ..."


class KamelotConfig(Config):
    """Production Config: `Config()` defaults (the production taxonomy) + the raw query."""

    def read_raw(self) -> pd.DataFrame:
        """The raw extract, read with the configured engine."""
        return pd.read_sql(RAW_EXTRACT_QUERY, self.engine)


if __name__ == "__main__":
    configuration = KamelotConfig(sql_server="...", sql_database="Kamelot")
    run_pipeline(configuration)
