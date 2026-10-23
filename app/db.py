import json
from decimal import Decimal

from fastapi import Request
from psycopg.rows import dict_row
from psycopg.types.json import set_json_loads
from psycopg_pool import ConnectionPool


def configure_connection(conn):
    # Preserve precision also inside JSON returned by PostgreSQL functions.
    set_json_loads(lambda value: json.loads(value, parse_float=Decimal), conn)


def create_pool(database_url: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo=database_url,
        min_size=0,
        max_size=5,
        timeout=5,
        open=False,
        check=ConnectionPool.check_connection,
        configure=configure_connection,
        kwargs={
            "row_factory": dict_row,
            "connect_timeout": 5,
            "options": "-c default_transaction_read_only=on -c statement_timeout=10000",
        },
    )


def get_connection(request: Request):
    with request.app.state.pool.connection() as conn:
        yield conn
