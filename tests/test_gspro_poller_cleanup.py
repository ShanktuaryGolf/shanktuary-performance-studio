"""Read-only GSPro fallback owns its connection and temporary files together."""

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gspro import poller  # noqa: E402


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "live database" / "GSPro.db"
    path.parent.mkdir()
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE DrivingRangeShot (ID INTEGER, DateCreated TEXT, ShotData TEXT)")
    conn.execute("INSERT INTO DrivingRangeShot VALUES (1, 'today', '{}')")
    conn.commit()
    conn.close()
    return str(path)


@pytest.fixture
def fallback(monkeypatch, tmp_path):
    """Force only the live open to fail; use real SQLite for the copied DB."""
    real_connect = sqlite3.connect
    directories, connections, calls = [], [], []

    def temporary_directory(**kwargs):
        directory = tempfile.TemporaryDirectory(dir=tmp_path, **kwargs)
        directories.append(directory.name)
        return directory

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise sqlite3.OperationalError("live database locked")
        conn = real_connect(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(poller, "TemporaryDirectory", temporary_directory)
    monkeypatch.setattr(poller.sqlite3, "connect", connect)
    return directories, connections, calls


def assert_cleaned(directories, connections):
    assert len(directories) == 1
    assert not os.path.exists(directories[0])
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")


def test_fallback_reads_rows_and_cleans_up(database, fallback):
    directories, connections, calls = fallback
    assert poller.read_latest(database) == [
        {"id": 1, "date_created": "today", "shot_data": "{}"}
    ]
    assert len(calls) == 2
    assert calls[1][1] == {"uri": True, "timeout": 1.0}
    assert calls[1][0][0].endswith("?mode=ro")
    assert_cleaned(directories, connections)


def test_fallback_keeps_copy_alive_until_connection_closes(database, fallback):
    directories, connections, _ = fallback
    with poller._connect_readonly(database) as conn:
        assert os.path.isdir(directories[0])
        assert conn.execute("SELECT COUNT(*) FROM DrivingRangeShot").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM DrivingRangeShot")
    assert_cleaned(directories, connections)


@pytest.mark.parametrize("failure", ["query", "validation"])
def test_fallback_cleans_up_when_read_fails(database, monkeypatch, failure):
    conn = sqlite3.connect(database)
    if failure == "query":
        conn.execute("DROP TABLE DrivingRangeShot")
    else:
        conn.execute("UPDATE DrivingRangeShot SET ShotData = NULL")
    conn.commit()
    conn.close()
    # Install the fallback only after preparing the live database.
    real_connect = sqlite3.connect
    directories, connections = [], []

    def connect(database_uri, **kwargs):
        if not directories:
            raise sqlite3.OperationalError("live database locked")
        conn = real_connect(database_uri, **kwargs)
        connections.append(conn)
        return conn

    def temporary_directory(**kwargs):
        directory = tempfile.TemporaryDirectory(**kwargs)
        directories.append(directory.name)
        return directory

    monkeypatch.setattr(poller.sqlite3, "connect", connect)
    monkeypatch.setattr(poller, "TemporaryDirectory", temporary_directory)
    with pytest.raises(sqlite3.OperationalError if failure == "query" else ValueError):
        poller.read_latest(database)
    assert_cleaned(directories, connections)


def test_fallback_cleans_up_partial_copy_failure(database, fallback, monkeypatch):
    directories, connections, calls = fallback

    def fail_copy(db_path, directory):
        with open(os.path.join(directory, "partial.db"), "w") as stream:
            stream.write("partial")
        raise OSError("copy failed")

    monkeypatch.setattr(poller, "_copy_with_wal", fail_copy)
    with pytest.raises(OSError, match="copy failed"):
        poller.read_latest(database)
    assert len(calls) == 1
    assert_cleaned(directories, connections)


def test_fallback_cleans_up_when_copied_database_cannot_open(database, fallback, monkeypatch):
    directories, connections, _ = fallback

    def fail_connect(*args, **kwargs):
        raise sqlite3.OperationalError("cannot open database")

    monkeypatch.setattr(poller.sqlite3, "connect", fail_connect)
    with pytest.raises(sqlite3.OperationalError, match="cannot open database"):
        poller.read_latest(database)
    assert_cleaned(directories, connections)


def test_direct_read_closes_connection_without_creating_copy(database, monkeypatch):
    real_connect = sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        connections.append(conn)
        return conn

    def unexpected_copy(**kwargs):
        pytest.fail("direct reads must not create a temporary directory")

    monkeypatch.setattr(poller.sqlite3, "connect", connect)
    monkeypatch.setattr(poller, "TemporaryDirectory", unexpected_copy)
    assert poller.read_latest(database)[0]["id"] == 1
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")
