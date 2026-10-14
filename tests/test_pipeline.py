"""Atomicité d'une exécution : un échec ne laisse aucune écriture partielle et le run est journalisé."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from conftest import TABLES, assert_base_coherente, snapshot
from fake_who import FakeWHO, make_record, make_records
from observatoire.oms import ingest as ingest_module
from observatoire.oms.ingest import RunSummary

Ingest = Callable[[FakeWHO], RunSummary]


def unchanged_except_runs(before: dict[str, list[tuple[Any, ...]]],
                          after: dict[str, list[tuple[Any, ...]]]) -> bool:
    return all(before[t] == after[t] for t in TABLES if t != "ingestion_runs")


def test_echec_reseau_a_la_page_3_sur_5_base_inchangee(
    conn: sqlite3.Connection, ingest: Ingest, sleeps: list[float]
) -> None:
    """Test 5 : panne à la page 3 sur 5 -> base inchangée, run enregistré comme échoué avec sa cause."""
    fake = FakeWHO(make_records(50))  # 5 pages de 10
    assert ingest(fake).status == "succes"
    for record in fake.records[::7]:  # des modifications qui seraient écrites si le run aboutissait
        record["Title"] = "modifié"
    fake.records.extend(make_records(3, start=500))  # et de nouveaux DON
    fake.calls.clear()
    fake.fault(httpx.ConnectError("connexion coupée"), skip=20)  # page 3
    before = snapshot(conn)

    summary = ingest(fake)

    after = snapshot(conn)
    assert summary.status == "echec" and summary.error_kind == "reseau"
    assert unchanged_except_runs(before, after)  # aucune écriture partielle
    assert after["ingestion_runs"][:-1] == before["ingestion_runs"]
    assert len(after["ingestion_runs"]) == len(before["ingestion_runs"]) + 1
    run = conn.execute("SELECT * FROM ingestion_runs WHERE id = ?", (summary.run_id,)).fetchone()
    assert (run["status"], run["error_kind"], run["http_retries"]) == ("echec", "reseau", 3)
    assert "ConnectError" in run["error_message"] and "connexion coupée" in run["error_message"]
    assert run["finished_at"] is not None and run["seen_count"] is None
    assert run["inserted_count"] == run["updated_count"] == 0
    assert fake.page_skips == [0, 10, 20, 20, 20, 20]  # pages 1 et 2 lues, puis 4 essais sur la 3
    assert sleeps == [2.0, 8.0, 30.0]
    assert_base_coherente(conn)

    fake.clear_faults()  # le run suivant, lui, aboutit et applique tout
    retry = ingest(fake)
    assert retry.status == "succes" and retry.inserted_count == 3 and retry.updated_count == 8
    assert_base_coherente(conn)


def test_echec_de_source_ferme_l_execution(conn: sqlite3.Connection, ingest: Ingest) -> None:
    """I6 : après un échec, aucune exécution ne reste « en_cours » (et l'index I5 ne bloque pas la suite)."""
    fake = FakeWHO(make_records(30))
    fake.fault(503, skip=10)
    summary = ingest(fake)
    assert summary.status == "echec" and summary.error_kind == "http"
    assert conn.execute("SELECT count(*) FROM ingestion_runs WHERE status = 'en_cours'"
                        ).fetchone()[0] == 0
    assert [r for r in conn.execute("SELECT * FROM controle_invariants WHERE invariant = 'I6'")] == []
    run = conn.execute("SELECT * FROM ingestion_runs").fetchone()
    assert run["finished_at"] is not None and run["error_message"]
    fake.clear_faults()
    assert ingest(fake).status == "succes"
    assert_base_coherente(conn)


def test_echec_sur_le_decompte_est_journalise(conn: sqlite3.Connection, ingest: Ingest) -> None:
    fake = FakeWHO(make_records(30))
    fake.fault(404, skip=None)
    summary = ingest(fake)
    assert (summary.status, summary.error_kind, summary.expected_count) == ("echec", "http", None)
    assert fake.calls and len(fake.calls) == 1  # 4xx : pas de retry
    assert summary.http_requests == 1 and summary.http_retries == 0


def test_conflit_de_slug_annule_toute_l_ecriture(conn: sqlite3.Connection, ingest: Ingest) -> None:
    """Une contrainte SQL violée en fin de lot annule aussi les DON écrits avant (R7)."""
    fake = FakeWHO(make_records(20))
    ingest(fake)
    clash = make_record(900)
    clash["UrlName"] = fake.records[3]["UrlName"]  # UrlName déjà pris par un autre `Id`
    fake.records[0]["Title"] = "modifié avant le conflit"
    fake.records.extend(make_records(5, start=800) + [clash])
    before = snapshot(conn)

    summary = ingest(fake)

    assert summary.status == "echec" and summary.error_kind == "format"
    assert "UNIQUE" in (summary.error_message or "")
    assert unchanged_except_runs(before, snapshot(conn))
    assert_base_coherente(conn)


def test_exception_inattendue_en_cours_d_ecriture_annule_tout(
    conn: sqlite3.Connection, ingest: Ingest, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeWHO(make_records(30))
    before = snapshot(conn)
    real = ingest_module._store_raw  # noqa: SLF001
    calls = {"n": 0}

    def flaky(*args: Any, **kwargs: Any) -> int:
        calls["n"] += 1
        if calls["n"] == 17:
            raise RuntimeError("disque plein")
        return real(*args, **kwargs)

    monkeypatch.setattr(ingest_module, "_store_raw", flaky)

    summary = ingest(fake)

    assert calls["n"] == 17
    assert (summary.status, summary.error_kind) == ("echec", "autre")
    assert "disque plein" in (summary.error_message or "")
    assert unchanged_except_runs(before, snapshot(conn))
    assert conn.execute("SELECT count(*) FROM ingestion_runs").fetchone()[0] == 1
    assert_base_coherente(conn)


def test_run_reussi_ecrit_un_journal_complet(conn: sqlite3.Connection, ingest: Ingest) -> None:
    fake = FakeWHO(make_records(25))
    summary = ingest(fake)
    run = conn.execute("SELECT * FROM ingestion_runs WHERE id = ?", (summary.run_id,)).fetchone()
    assert (run["source_code"], run["status"], run["triggered_by"]) == ("oms_don", "succes", "manuel")
    assert (run["expected_count"], run["seen_count"], run["inserted_count"]) == (25, 25, 25)
    assert run["http_requests"] == 4 and run["http_retries"] == 0  # décompte + 3 pages
    assert run["code_version"] == "test" and run["error_kind"] is None
    assert run["started_at"] < run["finished_at"] and run["field_fingerprint"]
    assert (run["absent_count"], run["removed_count"], run["reappeared_count"]) == (0, 0, 0)
