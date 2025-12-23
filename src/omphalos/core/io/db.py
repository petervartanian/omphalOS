from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def connect_sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=FULL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def create_table(conn: sqlite3.Connection, name: str, columns: Sequence[str]) -> None:
    cols = ", ".join(columns)
    conn.execute(f"CREATE TABLE IF NOT EXISTS {name} ({cols});")


def insert_many(conn: sqlite3.Connection, name: str, rows: Iterable[Mapping[str, object]]) -> int:
    rows_list = list(rows)
    if not rows_list:
        return 0
    keys = list(rows_list[0].keys())
    placeholders = ",".join(["?"] * len(keys))
    sql = f"INSERT INTO {name} ({','.join(keys)}) VALUES ({placeholders});"
    conn.executemany(sql, [[r[k] for k in keys] for r in rows_list])
    return len(rows_list)
