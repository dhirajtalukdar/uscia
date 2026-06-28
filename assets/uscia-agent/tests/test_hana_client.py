"""Unit tests for HANA client stub (IBD_TESTING=true mode)."""
import os
import pytest

# IBD_TESTING is set to "1" by conftest.py at the root level
# so hana_client will run in stub mode


def test_hana_client_stub_execute():
    """In IBD_TESTING mode, execute() must not raise."""
    from db.hana_client import execute
    execute("INSERT INTO test VALUES (?)", ("value",))


def test_hana_client_stub_fetchall_returns_list():
    """In IBD_TESTING mode, fetchall() must return a list."""
    from db.hana_client import fetchall
    result = fetchall("SELECT * FROM test WHERE id = ?", ("id_value",))
    assert isinstance(result, list)


def test_hana_client_stub_fetchall_empty():
    """In IBD_TESTING mode, fetchall() returns empty list."""
    from db.hana_client import fetchall
    result = fetchall("SELECT * FROM SomeTable", ())
    assert result == []


def test_hana_client_execute_update():
    from db.hana_client import execute
    # Should not raise
    execute("UPDATE RemediationRecord SET outcome = ? WHERE action_id = ?", ("Resolved", "a1"))


def test_hana_client_execute_no_params():
    from db.hana_client import execute
    execute("DELETE FROM test")
