"""DuckDB access layer.

Includes a quote-aware SQL splitter. The previous revision stripped ``--``
anywhere in a line, which silently corrupts any statement containing ``--``
inside a string literal; this one tracks quoting state properly.
"""
from __future__ import annotations

from contextlib import contextmanager

import duckdb
import pandas as pd

from .config import load_settings
from .errors import WarehouseError
from .logging_conf import get_logger

log = get_logger(__name__)


def split_sql(script: str) -> list[str]:
    """Split a SQL script into statements, respecting quotes and comments."""
    statements, buf = [], []
    i, n = 0, len(script)
    in_single = in_double = in_line_comment = in_block_comment = False
    while i < n:
        ch = script[i]
        nxt = script[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                buf.append(ch)
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if not in_single and not in_double:
            if ch == "-" and nxt == "-":
                in_line_comment = True
                i += 2
                continue
            if ch == "/" and nxt == "*":
                in_block_comment = True
                i += 2
                continue
            if ch == ";":
                statements.append("".join(buf))
                buf = []
                i += 1
                continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        buf.append(ch)
        i += 1
    statements.append("".join(buf))
    return [s.strip() for s in statements if s.strip()]


@contextmanager
def connect(read_only: bool = False):
    s = load_settings()
    s.db_path.parent.mkdir(parents=True, exist_ok=True)
    if read_only and not s.db_path.exists():
        raise WarehouseError(f"Warehouse not found at {s.db_path}. Run 'ingomob warehouse' first.")
    try:
        con = duckdb.connect(str(s.db_path), read_only=read_only)
    except duckdb.Error as exc:
        raise WarehouseError(f"Could not open DuckDB at {s.db_path}: {exc}") from exc
    try:
        yield con
    finally:
        con.close()


def run_script(con, sql_text: str, label: str = "script") -> int:
    """Execute a multi-statement SQL script; returns the statement count."""
    stmts = split_sql(sql_text)
    for idx, stmt in enumerate(stmts, start=1):
        try:
            con.execute(stmt)
        except duckdb.Error as exc:
            head = " ".join(stmt.split())[:120]
            raise WarehouseError(
                f"{label}: statement {idx}/{len(stmts)} failed ({head}...): {exc}") from exc
    log.debug("%s: executed %d statements", label, len(stmts))
    return len(stmts)


def query_df(sql: str, params: list | None = None) -> pd.DataFrame:
    with connect(read_only=True) as con:
        try:
            return con.execute(sql, params or []).df()
        except duckdb.Error as exc:
            raise WarehouseError(f"Query failed: {exc}\nSQL: {sql[:200]}") from exc


def table_exists(name: str) -> bool:
    with connect(read_only=True) as con:
        r = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [name]
        ).fetchone()
    return bool(r and r[0])
