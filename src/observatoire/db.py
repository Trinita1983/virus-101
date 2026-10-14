"""Accès à la base SQLite : connexion, création du schéma, transactions, horodatages UTC."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

# db/schema.sql et db/seed.sql sont à la racine du dépôt (src/observatoire/db.py -> racine).
SQL_DIR = Path(__file__).resolve().parents[2] / "db"
SCHEMA_VERSION = 1
MIN_SQLITE = (3, 39, 0)  # R12 : STRICT (3.37) et IS DISTINCT FROM dans les vues (3.39)
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> datetime:
    """Instant courant en UTC, à la seconde."""
    return datetime.now(UTC).replace(microsecond=0)


def to_utc_z(value: str | datetime) -> str:
    """Convertit un horodatage en `YYYY-MM-DDTHH:MM:SSZ` (UTC). Seule fonction de conversion (I2).

    Une chaîne est lue au format ISO 8601. Un horodatage sans fuseau est refusé (`ValueError`) :
    on ne devine pas son fuseau. Les fractions de seconde sont tronquées.
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        raise ValueError(f"horodatage sans fuseau : {value.isoformat()}")
    return value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def connect(path: Path | str, *, timeout: float = 30.0) -> sqlite3.Connection:
    """Fabrique de connexion unique (I1) : clés étrangères actives, mode autocommit.

    Le mode autocommit (`isolation_level=None`) laisse le code ouvrir les transactions
    explicitement avec `transaction()`.
    """
    if sqlite3.sqlite_version_info < MIN_SQLITE:
        raise RuntimeError(f"SQLite {sqlite3.sqlite_version} < 3.39 : schéma non supporté")
    conn = sqlite3.connect(str(path), timeout=timeout, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        conn.close()
        raise RuntimeError("SQLite n'a pas activé les clés étrangères (I1)")
    return conn


def init_db(conn: sqlite3.Connection) -> bool:
    """Crée la base depuis `db/schema.sql` et `db/seed.sql` si elle est vide.

    Renvoie True si la base a été créée, False si elle existait déjà. Une base existante
    dont la version de schéma diffère est refusée plutôt que modifiée.
    """
    existing = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sources'"
    ).fetchone()
    if existing:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise RuntimeError(f"version de schéma {version}, attendue {SCHEMA_VERSION}")
        return False
    schema = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
    seed = (SQL_DIR / "seed.sql").read_text(encoding="utf-8")
    conn.executescript(f"BEGIN;\n{schema}\n{seed}\nCOMMIT;")
    return True


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Transaction unique : `BEGIN IMMEDIATE`, puis COMMIT, ou ROLLBACK si une exception sort."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
