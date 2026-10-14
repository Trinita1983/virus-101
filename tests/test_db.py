"""Socle base de données : connexion (I1), horodatages UTC (I2), aucun DELETE (I3), création."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from fake_who import FakeWHO, fixture_records, make_records
from observatoire.db import SCHEMA_VERSION, connect, init_db, to_utc_z, transaction
from observatoire.oms.ingest import RunSummary

SRC = Path(__file__).resolve().parents[1] / "src"


def test_connexion_active_les_cles_etrangeres(conn: sqlite3.Connection) -> None:
    """I1 : la fabrique de connexion active les clés étrangères, qui refusent alors une source inconnue."""
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute("INSERT INTO ingestion_runs (source_code, started_at, status, triggered_by, "
                     "code_version) VALUES ('inconnue', '2026-10-14T06:00:00Z', 'en_cours', "
                     "'manuel', 'x')")
    memory = connect(":memory:")
    assert memory.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    memory.close()


@pytest.mark.parametrize("given, expected", [
    ("2026-10-10T15:53:19Z", "2026-10-10T15:53:19Z"),
    ("2026-10-10T17:53:19+02:00", "2026-10-10T15:53:19Z"),
    ("2026-10-10T10:53:19-05:00", "2026-10-10T15:53:19Z"),
    ("2026-10-10T15:53:19.987654Z", "2026-10-10T15:53:19Z"),
    ("2008-01-21T00:00:00Z", "2008-01-21T00:00:00Z"),
    (datetime(2026, 10, 10, 17, 53, 19, tzinfo=timezone(timedelta(hours=2))), "2026-10-10T15:53:19Z"),
    (datetime(2026, 10, 10, 15, 53, 19, tzinfo=UTC), "2026-10-10T15:53:19Z"),
])
def test_horodatage_converti_en_utc(given: str | datetime, expected: str) -> None:
    """I2 : une seule fonction convertit en UTC, forme exacte `YYYY-MM-DDTHH:MM:SSZ`."""
    assert to_utc_z(given) == expected


@pytest.mark.parametrize("bad", ["2026-10-10T15:53:19", "2026-10-10", "pas une date",
                                 "2026-99-99T00:00:00Z", ""])
def test_horodatage_invalide_ou_sans_fuseau_refuse(bad: str) -> None:
    with pytest.raises(ValueError):
        to_utc_z(bad)


def test_aucun_delete_hors_purge(
    conn: sqlite3.Connection, ingest: Callable[[FakeWHO], RunSummary]
) -> None:
    """I3 : le code ne contient aucune requête DELETE, et un run complet n'en émet aucune."""
    pattern = re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE)
    offenders = [str(p) for p in SRC.rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []

    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    fake = FakeWHO(make_records(300) + fixture_records())
    ingest(fake)
    removed = fake.records.pop(0)
    for _ in range(4):  # absence, puis retrait à la 3e exécution complète
        ingest(fake)
    fake.records.append(removed)
    ingest(fake)
    conn.set_trace_callback(None)
    assert len(statements) > 100
    assert [s for s in statements if pattern.search(s) or s.lstrip().upper().startswith("DROP")] == []


def test_init_db_cree_une_fois_et_verifie_la_version(tmp_path: Path) -> None:
    connection = connect(tmp_path / "x.sqlite")
    assert init_db(connection) is True
    assert init_db(connection) is False
    assert connection.execute("SELECT count(*) FROM sources WHERE code = 'oms_don'").fetchone()[0] == 1
    assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    connection.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError, match="version de schéma"):
        init_db(connection)
    connection.close()


def test_transaction_annule_tout_en_cas_d_exception(conn: sqlite3.Connection) -> None:
    before = conn.execute("SELECT count(*) FROM diseases").fetchone()[0]
    with pytest.raises(RuntimeError), transaction(conn):
        conn.execute("INSERT INTO diseases (code, label_fr) VALUES ('x', 'X')")
        raise RuntimeError("panne")
    assert conn.in_transaction is False
    assert conn.execute("SELECT count(*) FROM diseases").fetchone()[0] == before
