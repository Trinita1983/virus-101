"""Fixtures communes : base temporaire créée depuis le vrai schéma, client simulé, horloge."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from observatoire.config import Settings
from observatoire.db import connect, init_db
from observatoire.oms.client import WhoClient
from observatoire.oms.ingest import RunSummary, run_oms_ingestion

from fake_who import FakeWHO

TABLES = ("reports", "raw_payloads", "report_versions", "ingestion_runs")


class FakeClock:
    """Horloge déterministe : chaque appel avance d'une seconde (chaque run a son horodatage)."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 14, 6, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(db_path=tmp_path / "obs.sqlite", contact="contact@example.org",
                    page_size=10, code_version="test")


@pytest.fixture
def conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = connect(settings.db_path)
    init_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def sleeps() -> list[float]:
    """Durées d'attente demandées par le client (aucune attente réelle)."""
    return []


@pytest.fixture
def make_client(settings: Settings, sleeps: list[float]) -> Callable[[FakeWHO], WhoClient]:
    def factory(fake: FakeWHO) -> WhoClient:
        return WhoClient(settings, transport=httpx.MockTransport(fake), sleep=sleeps.append,
                         jitter=lambda delay: 0.0)
    return factory


@pytest.fixture
def ingest(conn: sqlite3.Connection, make_client: Callable[[FakeWHO], WhoClient]
           ) -> Callable[[FakeWHO], RunSummary]:
    """Lance une exécution complète contre le faux serveur, avec un client neuf."""
    clock = FakeClock()

    def run(fake: FakeWHO) -> RunSummary:
        client = make_client(fake)
        try:
            return run_oms_ingestion(conn, client, clock=clock)
        finally:
            client.close()
    return run


def snapshot(conn: sqlite3.Connection) -> dict[str, list[tuple[Any, ...]]]:
    """Contenu complet des tables écrites par le pipeline, pour comparer avant / après."""
    return {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1")] for t in TABLES}


def row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}


def assert_base_coherente(conn: sqlite3.Connection) -> None:
    """La base serait publiable : intégrité, clés étrangères et vue de contrôle vides (D25)."""
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert [tuple(r) for r in conn.execute("SELECT * FROM controle_invariants")] == []
