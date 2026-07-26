"""Build the star-schema warehouse from the ordered SQL layers."""
from __future__ import annotations

from .config import load_settings
from .errors import SourceError
from .ingest import load_staging
from .logging_conf import get_logger
from .warehouse import connect, run_script

log = get_logger(__name__)
SQL_LAYERS = ("01_dimensions.sql", "02_facts.sql", "03_marts.sql")


def build_warehouse() -> dict:
    s = load_settings()
    missing = [f for f in SQL_LAYERS if not (s.sql_dir / f).exists()]
    if missing:
        raise SourceError(f"SQL layer file(s) not found in {s.sql_dir}: {missing}")
    with connect() as con:
        staging = load_staging(con, s)
        for layer in SQL_LAYERS:
            run_script(con, (s.sql_dir / layer).read_text(encoding="utf-8"), label=layer)
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main' "
            "ORDER BY table_name").df()["table_name"].tolist()
        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}
    log.info("warehouse built: %d objects", len(counts))
    return {"staging": staging, "objects": counts}
