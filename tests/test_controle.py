"""Vue `controle_invariants` : vide sur une base cohérente, et pas vide quand une règle est violée."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from conftest import assert_base_coherente
from fake_who import FakeWHO, fixture_records, make_record, make_records
from observatoire.oms.ingest import RunSummary

Ingest = Callable[[FakeWHO], RunSummary]


def test_vue_controle_vide_sur_base_coherente(conn: sqlite3.Connection, ingest: Ingest) -> None:
    """Méta-test : après tout le cycle de vie, la vue est vide (sinon chaque envoi serait bloqué)."""
    assert_base_coherente(conn)  # base vide
    fake = FakeWHO(make_records(300) + fixture_records())
    ingest(fake)
    assert_base_coherente(conn)
    fake.records[0]["Title"] = "révisé"
    removed = fake.records.pop(10)
    broken = make_record(998)
    broken["Id"] = ""
    fake.records.append(broken)
    ingest(fake)  # partiel
    fake.records.pop()
    fake.fault(500, skip=0)
    ingest(fake)  # échec
    fake.clear_faults()
    for _ in range(3):  # absent, absent, retiré
        ingest(fake)
        assert_base_coherente(conn)
    fake.records.append(removed)
    ingest(fake)  # réapparition
    fake.records[0]["Title"] = "titre d'origine"
    ingest(fake)
    assert_base_coherente(conn)
    assert conn.execute("SELECT count(*) FROM ingestion_runs WHERE status = 'en_cours'"
                        ).fetchone()[0] == 0


def test_la_vue_signale_un_retrait_prematuré(conn: sqlite3.Connection, ingest: Ingest) -> None:
    """La vue n'est pas vide par construction : un `removed_run_id` trop tôt est signalé (I10)."""
    fake = FakeWHO(make_records(300))
    ingest(fake)
    fake.records.pop(0)
    second = ingest(fake)
    conn.execute("UPDATE reports SET removed_run_id = ? WHERE slug = '2030-DON0'", (second.run_id,))
    rows = [tuple(r) for r in conn.execute("SELECT invariant FROM controle_invariants")]
    assert rows == [("I10",)]
