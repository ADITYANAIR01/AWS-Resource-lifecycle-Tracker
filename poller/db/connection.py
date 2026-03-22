import os
import time

import psycopg2
from psycopg2 import pool

from utils.logger import get_logger

logger = get_logger("poller.db")

_connection_pool = None

_STARTUP_RETRIES = 10
_STARTUP_RETRY_DELAY = 3


def init_pool() -> None:
    global _connection_pool

    db_config = {
        "host": os.environ["DB_HOST"],
        "port": int(os.environ.get("DB_PORT", 5432)),
        "dbname": os.environ["DB_NAME"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }

    for attempt in range(1, _STARTUP_RETRIES + 1):
        try:
            _connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=5,
                **db_config,
            )
            logger.info("Database connection pool initialised successfully")
            return
        except psycopg2.OperationalError as e:
            logger.warning(
                f"DB connection attempt {attempt}/{_STARTUP_RETRIES} failed: {e}"
            )
            if attempt < _STARTUP_RETRIES:
                logger.info(f"Retrying in {_STARTUP_RETRY_DELAY}s...")
                time.sleep(_STARTUP_RETRY_DELAY)
            else:
                logger.error("Could not connect to database after all retries")
                raise


def get_connection():
    if _connection_pool is None:
        raise RuntimeError("Connection pool not initialised — call init_pool() first")
    return _connection_pool.getconn()


def release_connection(conn) -> None:
    if _connection_pool and conn:
        _connection_pool.putconn(conn)


def close_pool() -> None:
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("Database connection pool closed")