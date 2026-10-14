"""Archivage du JSON brut : empreinte sur le contenu non compressé (I43), unicité (I42)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable

import pytest

from fake_who import FakeWHO, fixture_records
from observatoire.oms.ingest import RunSummary


def test_empreinte_sur_contenu_non_compresse(
    conn: sqlite3.Connection, ingest: Callable[[FakeWHO], RunSummary]
) -> None:
    """I43 : `sha256` et `byte_size` portent sur les octets UTF-8 du contenu en clair."""
    ingest(FakeWHO(fixture_records()))
    rows = conn.execute("SELECT * FROM raw_payloads ORDER BY id").fetchall()
    assert len(rows) == 5
    for row in rows:
        encoded = row["body_text"].encode("utf-8")
        assert row["sha256"] == hashlib.sha256(encoded).hexdigest()
        assert row["byte_size"] == len(encoded)
        assert row["body_gzip"] is None and row["purged_at"] is None
        assert row["content_type"] == "application/json"
    mpox = conn.execute("SELECT * FROM raw_payloads WHERE resource_key = ?",
                        (fixture_records()[1]["Id"],)).fetchone()
    assert mpox["byte_size"] > len(mpox["body_text"])  # tiret cadratin : plusieurs octets par caractère


def test_json_brut_archive_identique_a_l_enregistrement_recu(
    conn: sqlite3.Connection, ingest: Callable[[FakeWHO], RunSummary]
) -> None:
    records = fixture_records()
    ingest(FakeWHO(records))
    for record in records:
        row = conn.execute("SELECT * FROM raw_payloads WHERE resource_key = ?",
                           (record["Id"],)).fetchone()
        assert json.loads(row["body_text"]) == record  # aucune transformation
        assert row["source_modified_at"] == record["LastModified"]
        assert "$top=10" in row["request_url"] and "$skip=0" in row["request_url"]
        assert row["retrieved_at"].endswith("Z")


def test_meme_contenu_pas_reinsere(
    conn: sqlite3.Connection, ingest: Callable[[FakeWHO], RunSummary]
) -> None:
    """I42 : (source, ressource, sha256) unique ; un second run n'ajoute aucun brut."""
    fake = FakeWHO(fixture_records())
    ingest(fake)
    ingest(fake)
    assert conn.execute("SELECT count(*) FROM raw_payloads").fetchone()[0] == 5
    row = conn.execute("SELECT * FROM raw_payloads LIMIT 1").fetchone()
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        conn.execute(
            """INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type,
                      sha256, byte_size, body_text, first_run_id, retrieved_at)
               VALUES (?, ?, 'u', 'application/json', ?, 1, 'x', ?, '2026-10-14T06:00:00Z')""",
            (row["source_code"], row["resource_key"], row["sha256"], row["first_run_id"]))
