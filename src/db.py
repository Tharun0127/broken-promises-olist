"""DuckDB connection helpers and the SQL runner."""
from pathlib import Path

import duckdb

from src import config

LAYERS = ["staging", "intermediate", "marts"]


def connect(path=None):
    """Open the project warehouse (or an in-memory db when path=':memory:')."""
    target = str(path or config.DB_PATH)
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(target)


def register_raw(con, raw_dir=None):
    """Expose each raw CSV as a view. All type casting happens in staging."""
    raw_dir = Path(raw_dir or config.RAW_DIR)
    missing = [f for f in config.RAW_FILES.values() if not (raw_dir / f).exists()]
    if missing:
        raise FileNotFoundError(f"Missing raw files in {raw_dir}: {missing}")
    for view, fname in config.RAW_FILES.items():
        path = (raw_dir / fname).as_posix()
        # all_varchar keeps raw text untouched; staging decides every type.
        con.execute(
            f"create or replace view {view} as "
            f"select * from read_csv('{path}', header=true, all_varchar=true)"
        )


def write_params(con):
    """Store analysis parameters in a table so SQL never hardcodes them."""
    con.execute("create or replace table params as select "
                f"{config.REPEAT_WINDOW_DAYS} as repeat_window_days, "
                f"{config.SELLER_ACTIVE_DAYS} as seller_active_days, "
                f"date '{config.COHORT_START}' as cohort_start")


def run_layer(con, layer):
    """Run every .sql file in a layer folder in file-name order."""
    for sql_file in sorted((config.SQL_DIR / layer).glob("*.sql")):
        con.execute(sql_file.read_text(encoding="utf-8"))


def build(con, layers=LAYERS):
    write_params(con)
    for layer in layers:
        run_layer(con, layer)
