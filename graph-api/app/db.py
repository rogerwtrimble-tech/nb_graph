"""PostgreSQL access and installing the graph schema (nbgraph.*) into NetBox's database."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .settings import get_settings

log = logging.getLogger('nbgraph.db')
_pool: ConnectionPool | None = None

REQUIRED_TABLES = ('dcim_site', 'dcim_cablepath', 'circuits_virtualcircuit', 'netbox_numbers_telephonenumber')


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = ConnectionPool(s.database_url, min_size=1, max_size=10, kwargs={'row_factory': dict_row},
                               open=True)
    return _pool


def query(sql: str, params: tuple | dict | None = None) -> list[dict]:
    with pool().connection() as conn:
        return conn.execute(sql, params).fetchall()


def query_one(sql: str, params: tuple | dict | None = None) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def netbox_schema_ready() -> bool:
    row = query_one("SELECT count(*) AS n FROM information_schema.tables WHERE table_schema = 'public' "
                    "AND table_name = ANY(%s)", (list(REQUIRED_TABLES),))
    return bool(row and row['n'] == len(REQUIRED_TABLES))


def install_graph_schema(wait_seconds: int = 900) -> list[str]:
    """Apply db/graph/*.sql in order. Idempotent: everything is CREATE OR REPLACE / IF NOT EXISTS."""
    sql_dir = Path(get_settings().graph_sql_dir)
    deadline = time.time() + wait_seconds
    while True:
        try:
            if netbox_schema_ready():
                break
            log.info('waiting for NetBox migrations (tables %s)', ', '.join(REQUIRED_TABLES))
        except Exception as exc:  # noqa: BLE001  database not up yet
            log.info('waiting for database: %s', exc.__class__.__name__)
        if time.time() > deadline:
            raise RuntimeError('NetBox schema never became ready')
        time.sleep(5)

    applied = []
    files = sorted(p for p in sql_dir.glob('*.sql') if not p.name.startswith('09'))  # 09x = future/optional
    with pool().connection() as conn:
        with conn.transaction():
            conn.execute('SELECT pg_advisory_xact_lock(424242)')
            for f in files:
                conn.execute(f.read_text())
                applied.append(f.name)
    log.info('graph schema installed: %s', ', '.join(applied))
    return applied


def server_version() -> str:
    row = query_one('SELECT version() AS v, current_setting(\'server_version\') AS sv')
    return row['sv'] if row else 'unknown'
