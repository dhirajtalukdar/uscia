"""
Thin HANA Cloud client wrapper.
Reads HANA_HOST, HANA_PORT, HANA_USER, HANA_PASSWORD from environment.
Falls back to a no-op stub when running in IBD_TESTING mode or when
hdbcli is not installed.
"""
from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)

_conn = None


def _get_connection():
    global _conn
    if os.getenv("IBD_TESTING") == "true":
        return None
    if _conn is not None:
        try:
            _conn.isconnected()
            return _conn
        except Exception:
            _conn = None
    try:
        from hdbcli import dbapi  # noqa: F401
        hana_host = os.environ.get("HANA_HOST", "")
        hana_port = int(os.environ.get("HANA_PORT", "443"))
        hana_user = os.environ.get("HANA_USER", "")
        hana_pwd = os.environ.get("HANA_PASSWORD", "")
        _conn = dbapi.connect(
            address=hana_host,
            port=hana_port,
            user=hana_user,
            password=hana_pwd,
            encrypt=True,
            sslValidateCertificate=False,
        )
        return _conn
    except ImportError:
        logger.warning("hdbcli not installed — HANA persistence disabled")
        return None
    except Exception as exc:
        logger.error("HANA connection failed: %s", exc)
        return None


def execute(sql: str, params: tuple = ()) -> None:
    """Execute a DML statement (INSERT / UPDATE / DELETE). No-op in test mode."""
    conn = _get_connection()
    if conn is None:
        logger.debug("[HANA STUB] execute: %s", sql[:80])
        return
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()
    cursor.close()


def fetchall(sql: str, params: tuple = ()) -> list:
    """Execute a SELECT and return all rows. Returns [] in test mode."""
    conn = _get_connection()
    if conn is None:
        logger.debug("[HANA STUB] fetchall: %s", sql[:80])
        return []
    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    return rows
