"""
Flask DB connection pool.

Separate pool from the poller — Flask and poller run in different
containers and must not share connections.

Pattern:
  - Pool initialised once at app startup in main.py
  - get_connection() called at start of each request
  - release_connection() called in teardown_appcontext
  - Never hold a connection across the full app lifetime
"""

import os
import time

import psycopg2
from psycopg2 import pool

from flask import g

import logging
logger = logging.getLogger("app.db")

_connection_pool = None

_STARTUP_RETRIES   = 10
_STARTUP_RETRY_DELAY = 3


def init_pool() -> None:
    """
    Initialise the connection pool.
    Called once at app startup.
    Retries on startup to handle RDS not being immediately reachable.
    """
    global _connection_pool

    db_config = {
        "host":     os.environ["DB_HOST"],
        "port":     int(os.environ.get("DB_PORT", 5432)),
        "dbname":   os.environ["DB_NAME"],
        "user":     os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }

    for attempt in range(1, _STARTUP_RETRIES + 1):
        try:
            _connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                **db_config,
            )
            logger.info("Flask DB connection pool initialised")
            return
        except psycopg2.OperationalError as e:
            logger.warning(
                f"DB connection attempt {attempt}/{_STARTUP_RETRIES} failed: {e}"
            )
            if attempt < _STARTUP_RETRIES:
                time.sleep(_STARTUP_RETRY_DELAY)
            else:
                raise


def get_connection():
    """
    Get a connection from the pool.
    Stores it in Flask's g object so it is released at end of request.
    """
    if "db_conn" not in g:
        if _connection_pool is None:
            raise RuntimeError("DB pool not initialised")
        g.db_conn = _connection_pool.getconn()
    return g.db_conn


def release_connection(exception=None):
    """
    Return the connection to the pool.
    Registered as teardown_appcontext handler in main.py.
    Called automatically at end of every request.
    """
    conn = g.pop("db_conn", None)
    if conn is not None and _connection_pool is not None:
        if exception:
            conn.rollback()
        _connection_pool.putconn(conn)


def close_pool() -> None:
    """Close all connections. Called on app shutdown."""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None