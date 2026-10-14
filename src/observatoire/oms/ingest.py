"""Ingestion OMS : une exécution = une transaction (écriture des DON, présence, journal).

Déroulement d'une exécution :
1. lecture complète de l'API en mémoire (aucune écriture en base) ;
2. validation de chaque enregistrement (les rejets sont journalisés, le reste continue) ;
3. une transaction unique : ouverture de la ligne `ingestion_runs`, archivage des bruts, upsert
   de `reports`, versions, suivi des DON absents, fermeture de la ligne ;
4. en cas d'échec à n'importe quelle étape : ROLLBACK, puis le run est enregistré `echec`.

Règles d'état (docs/01-invariants.md) : I8 (`Id` distincts), I9 (écart 0 sur les présents),
I10 (retrait à la 3e exécution complète sans le DON), I11 (compteurs), I13, I42, I43, I51, I52.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import ValidationError

from observatoire.db import to_utc_z, transaction, utc_now
from observatoire.oms.client import Fetched, WhoClient
from observatoire.oms.errors import ErrorKind, IngestionError
from observatoire.oms.normalize import Prepared, prepare_record

logger = logging.getLogger(__name__)

SOURCE = "oms_don"
COMPLETE = ("succes", "inchange")  # exécutions « complètes » : seules à compter pour un retrait
REMOVAL_AFTER = 3  # D24 : retiré à la 3e exécution complète sans le DON
MAX_DROP = 0.01  # architecture §7 : baisse de plus de 1 % du total = incohérence
MAX_REJECTS_IN_MESSAGE = 10
MAX_MESSAGE = 2000

Status = Literal["succes", "inchange", "partiel", "echec"]


@dataclass(frozen=True)
class Rejection:
    """Enregistrement reçu mais rejeté à la validation."""

    position: int
    don_id: str | None
    reason: str

    def __str__(self) -> str:
        return f"#{self.position} (Id={self.don_id}) : {self.reason}"


@dataclass
class Batch:
    """Enregistrements reçus, triés en valides, rejetés et doublons d'`Id`."""

    received: int
    prepared: list[Prepared] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    fingerprint: str = ""


@dataclass(frozen=True)
class RunSummary:
    """Ce qui est journalisé dans `ingestion_runs` pour l'exécution."""

    run_id: int
    status: Status
    expected_count: int | None
    seen_count: int | None
    inserted_count: int
    updated_count: int
    absent_count: int | None
    removed_count: int | None
    reappeared_count: int | None
    rejected_count: int
    http_requests: int
    http_retries: int
    error_kind: ErrorKind | None
    error_message: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _Counts:
    inserted: int = 0
    updated: int = 0
    reappeared: int = 0


@dataclass(frozen=True)
class _Known:
    """Un DON déjà en base, avec l'empreinte de son contenu courant (I52)."""

    id: int
    last_seen_run_id: int
    sha256: str
    version: int


# --- Validation du lot reçu -------------------------------------------------------------------


def _reason(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'enregistrement'} : {e['msg']}"
            for e in exc.errors()
        )
    return str(exc)


def _fingerprint(records: list[Any]) -> str:
    """sha256 de la liste triée des champs reçus (union sur tous les enregistrements)."""
    names = sorted({key for r in records if isinstance(r, dict) for key in r})
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


def prepare_batch(fetched: Fetched) -> Batch:
    """Valide chaque enregistrement. Un rejet n'arrête pas le lot ; un `Id` en double est écarté (I8)."""
    batch = Batch(received=len(fetched.records),
                  fingerprint=_fingerprint([r.raw for r in fetched.records]))
    seen: set[str] = set()
    for position, item in enumerate(fetched.records):
        try:
            prepared = prepare_record(item.raw, item.request_url)
        except ValueError as exc:  # ValidationError en est une sous-classe (pydantic v2)
            raw_id = item.raw.get("Id") if isinstance(item.raw, dict) else None
            rejection = Rejection(position, raw_id if isinstance(raw_id, str) else None, _reason(exc))
            logger.warning("enregistrement rejeté %s", rejection)
            batch.rejected.append(rejection)
            continue
        if prepared.row.external_id in seen:
            logger.warning("Id reçu en double : %s", prepared.row.external_id)
            batch.duplicate_ids.append(prepared.row.external_id)
            continue
        seen.add(prepared.row.external_id)
        batch.prepared.append(prepared)
    return batch


def _find_problems(
    batch: Batch, expected: int, previous_seen: int | None
) -> list[tuple[ErrorKind, str]]:
    """Incohérences qui rendent l'exécution `partiel` (elle ne compte plus pour un retrait)."""
    problems: list[tuple[ErrorKind, str]] = []
    if batch.rejected:
        shown = "; ".join(str(r) for r in batch.rejected[:MAX_REJECTS_IN_MESSAGE])
        more = len(batch.rejected) - MAX_REJECTS_IN_MESSAGE
        suffix = f" (+{more} autres)" if more > 0 else ""
        problems.append(("validation", f"{len(batch.rejected)} enregistrement(s) rejeté(s) : {shown}{suffix}"))
    if batch.duplicate_ids:
        problems.append(("controle", f"{len(batch.duplicate_ids)} Id reçu(s) en double "
                                     f"(ex. {batch.duplicate_ids[0]})"))
    if batch.received != expected:
        problems.append(("controle", f"seen_count {batch.received} ≠ expected_count {expected}"))
    if previous_seen and expected < previous_seen * (1 - MAX_DROP):
        problems.append(("controle", f"total en baisse de plus de 1 % : {previous_seen} -> {expected}"))
    return problems


# --- Écriture ---------------------------------------------------------------------------------


def _load_known(conn: sqlite3.Connection) -> dict[str, _Known]:
    rows = conn.execute(
        """SELECT r.external_id, r.id, r.last_seen_run_id, p.sha256,
                  COALESCE((SELECT max(v.version) FROM report_versions AS v
                            WHERE v.report_id = r.id), 0) AS version
           FROM reports AS r JOIN raw_payloads AS p ON p.id = r.raw_payload_id
           WHERE r.source_code = ?""", (SOURCE,)).fetchall()
    return {r["external_id"]: _Known(r["id"], r["last_seen_run_id"], r["sha256"], r["version"])
            for r in rows}


def _complete_run_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM ingestion_runs WHERE source_code = ? AND status IN ('succes', 'inchange') "
        "ORDER BY id", (SOURCE,)).fetchall()
    return [r["id"] for r in rows]


def _previous(conn: sqlite3.Connection, column: str) -> Any:
    """Valeur de `column` pour la dernière exécution complète (NULL s'il n'y en a pas)."""
    row = conn.execute(
        f"SELECT {column} FROM ingestion_runs WHERE source_code = ? "  # noqa: S608 (nom interne)
        "AND status IN ('succes', 'inchange') ORDER BY id DESC LIMIT 1", (SOURCE,)).fetchone()
    return row[0] if row else None


def _open_run(conn: sqlite3.Connection, started_at: str, expected: int, triggered_by: str,
              code_version: str, ci_run_url: str | None) -> int:
    cur = conn.execute(
        """INSERT INTO ingestion_runs (source_code, started_at, status, triggered_by,
                                       code_version, ci_run_url, expected_count)
           VALUES (?, ?, 'en_cours', ?, ?, ?, ?) RETURNING id""",
        (SOURCE, started_at, triggered_by, code_version, ci_run_url, expected))
    return int(cur.fetchone()[0])


def _store_raw(conn: sqlite3.Connection, run_id: int, retrieved_at: str, rec: Prepared) -> int:
    """Archive le JSON brut ; un contenu déjà archivé n'est pas réinséré (I42). Renvoie son id."""
    row = conn.execute(
        """INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256,
                                     byte_size, body_text, source_modified_at, first_run_id,
                                     retrieved_at)
           VALUES (?, ?, ?, 'application/json', ?, ?, ?, ?, ?, ?)
           ON CONFLICT (source_code, resource_key, sha256) DO NOTHING RETURNING id""",
        (SOURCE, rec.row.external_id, rec.request_url, rec.sha256, rec.byte_size, rec.body,
         rec.row.source_modified_at, run_id, retrieved_at)).fetchone()
    if row:
        return int(row[0])
    existing = conn.execute(
        "SELECT id FROM raw_payloads WHERE source_code = ? AND resource_key = ? AND sha256 = ?",
        (SOURCE, rec.row.external_id, rec.sha256)).fetchone()
    return int(existing[0])


def _insert_report(conn: sqlite3.Connection, run_id: int, rec: Prepared, raw_id: int) -> int:
    """Nouveau DON. Classification et chiffres sont laissés à la phase 3 (statut `non_classe`)."""
    r = rec.row
    cur = conn.execute(
        """INSERT INTO reports (source_code, external_id, external_ref, slug, url, title, summary,
                                published_at, date_quality, geo_scope, classification_status,
                                raw_payload_id, first_seen_run_id, last_seen_run_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'inconnu', 'non_classe', ?, ?, ?) RETURNING id""",
        (SOURCE, r.external_id, r.external_ref, r.slug, r.url, r.title, r.summary,
         r.published_at, r.date_quality, raw_id, run_id, run_id))
    return int(cur.fetchone()[0])


def _update_content(conn: sqlite3.Connection, report_id: int, rec: Prepared, raw_id: int) -> None:
    r = rec.row
    conn.execute(
        """UPDATE reports SET external_ref = ?, slug = ?, url = ?, title = ?, summary = ?,
                  published_at = ?, date_quality = ?, raw_payload_id = ? WHERE id = ?""",
        (r.external_ref, r.slug, r.url, r.title, r.summary, r.published_at, r.date_quality,
         raw_id, report_id))


def _insert_version(conn: sqlite3.Connection, report_id: int, version: int, rec: Prepared,
                    raw_id: int, run_id: int) -> None:
    """Une ligne de `report_versions` à chaque changement du contenu courant (D26, I51)."""
    conn.execute(
        """INSERT INTO report_versions (report_id, version, source_code, external_id,
                                        raw_payload_id, run_id) VALUES (?, ?, ?, ?, ?, ?)""",
        (report_id, version, SOURCE, rec.row.external_id, raw_id, run_id))


def _write_record(conn: sqlite3.Connection, run_id: int, retrieved_at: str, rec: Prepared,
                  known: dict[str, _Known], previous_complete: int | None,
                  counts: _Counts) -> None:
    """Insère un DON nouveau, ou met à jour un DON connu (contenu et présence)."""
    raw_id = _store_raw(conn, run_id, retrieved_at, rec)
    current = known.get(rec.row.external_id)
    if current is None:
        report_id = _insert_report(conn, run_id, rec, raw_id)
        _insert_version(conn, report_id, 1, rec, raw_id, run_id)
        counts.inserted += 1
        return
    if previous_complete is not None and current.last_seen_run_id < previous_complete:
        counts.reappeared += 1  # absent ou retiré à l'exécution complète précédente
    if rec.sha256 != current.sha256:  # contenu courant différent (I52), même pour un retour à A
        _update_content(conn, current.id, rec, raw_id)
        _insert_version(conn, current.id, current.version + 1, rec, raw_id, run_id)
        counts.updated += 1
    # removed_run_id repasse à NULL dans la même instruction : CHECK removed_run_id > last_seen.
    conn.execute("UPDATE reports SET last_seen_run_id = ?, removed_run_id = NULL WHERE id = ?",
                 (run_id, current.id))


def _apply_presence(conn: sqlite3.Connection, complete_ids: list[int],
                    run_id: int) -> tuple[int, int]:
    """Met `removed_run_id` d'accord avec I10. Renvoie (absents, retirés par cette exécution).

    `complete_ids` : exécutions complètes triées, y compris la courante si elle l'est. Un DON
    est « absent » après 1 ou 2 exécutions complètes sans lui, retiré à la 3e (D24).
    """
    absent = removed_now = 0
    rows = conn.execute("SELECT id, last_seen_run_id, removed_run_id FROM reports "
                        "WHERE source_code = ?", (SOURCE,)).fetchall()
    for r in rows:
        after = bisect_right(complete_ids, r["last_seen_run_id"])
        missing = len(complete_ids) - after
        expected_removed = complete_ids[after + REMOVAL_AFTER - 1] if missing >= REMOVAL_AFTER else None
        if r["removed_run_id"] != expected_removed:
            conn.execute("UPDATE reports SET removed_run_id = ? WHERE id = ?",
                         (expected_removed, r["id"]))
        if expected_removed == run_id:
            removed_now += 1
        elif expected_removed is None and missing > 0:
            absent += 1
    return absent, removed_now


def _close_run(conn: sqlite3.Connection, run_id: int, finished_at: str, batch: Batch,
               summary: RunSummary) -> None:
    conn.execute(
        """UPDATE ingestion_runs SET finished_at = ?, status = ?, seen_count = ?,
                  inserted_count = ?, updated_count = ?, absent_count = ?, removed_count = ?,
                  reappeared_count = ?, http_requests = ?, http_retries = ?, field_fingerprint = ?,
                  error_kind = ?, error_message = ? WHERE id = ?""",
        (finished_at, summary.status, summary.seen_count, summary.inserted_count,
         summary.updated_count, summary.absent_count, summary.removed_count,
         summary.reappeared_count, summary.http_requests, summary.http_retries,
         batch.fingerprint, summary.error_kind, summary.error_message, run_id))


def _write_run(conn: sqlite3.Connection, client: WhoClient, batch: Batch, expected: int,
               started_at: str, clock: Callable[[], datetime], triggered_by: str,
               ci_run_url: str | None) -> RunSummary:
    """Corps de la transaction : tout ce qui touche la base pour une exécution réussie ou partielle."""
    complete_ids = _complete_run_ids(conn)
    known = _load_known(conn)
    problems = _find_problems(batch, expected, _previous(conn, "seen_count"))
    previous_fingerprint = _previous(conn, "field_fingerprint")
    if previous_fingerprint and previous_fingerprint != batch.fingerprint:
        logger.warning("la liste des champs de l'API a changé depuis la dernière exécution complète")

    run_id = _open_run(conn, started_at, expected, triggered_by,
                       client.settings.code_version, ci_run_url)
    counts = _Counts()
    previous_complete = complete_ids[-1] if complete_ids else None
    for rec in batch.prepared:
        _write_record(conn, run_id, started_at, rec, known, previous_complete, counts)

    if not problems:
        complete_ids.append(run_id)
    absent, removed = _apply_presence(conn, complete_ids, run_id)

    changed = counts.inserted or counts.updated or removed or counts.reappeared
    status: Status = "partiel" if problems else ("succes" if changed else "inchange")
    summary = RunSummary(
        run_id=run_id, status=status, expected_count=expected, seen_count=batch.received,
        inserted_count=counts.inserted, updated_count=counts.updated, absent_count=absent,
        removed_count=removed, reappeared_count=counts.reappeared,
        rejected_count=len(batch.rejected), http_requests=client.requests,
        http_retries=client.retries,
        error_kind=problems[0][0] if problems else None,
        error_message=" | ".join(m for _, m in problems)[:MAX_MESSAGE] if problems else None)
    _close_run(conn, run_id, to_utc_z(clock()), batch, summary)
    return summary


# --- Échec ------------------------------------------------------------------------------------


def _classify(exc: Exception) -> tuple[ErrorKind, str]:
    if isinstance(exc, IngestionError):
        return exc.kind, str(exc)
    if isinstance(exc, sqlite3.IntegrityError):  # ex. UrlName en double (R7) : échec visible voulu
        return "format", f"contrainte de la base violée : {exc}"
    return "autre", f"{type(exc).__name__} : {exc}"


def _record_failure(conn: sqlite3.Connection, client: WhoClient, started_at: str,
                    finished_at: str, expected: int | None, triggered_by: str,
                    ci_run_url: str | None, exc: Exception) -> RunSummary:
    """Enregistre le run `echec` après le ROLLBACK : c'est la seule écriture d'un run échoué."""
    kind, message = _classify(exc)
    message = message[:MAX_MESSAGE]
    with transaction(conn):
        run_id = int(conn.execute(
            """INSERT INTO ingestion_runs (source_code, started_at, finished_at, status,
                      triggered_by, code_version, ci_run_url, expected_count, http_requests,
                      http_retries, error_kind, error_message)
               VALUES (?, ?, ?, 'echec', ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (SOURCE, started_at, finished_at, triggered_by, client.settings.code_version,
             ci_run_url, expected, client.requests, client.retries, kind, message)).fetchone()[0])
    return RunSummary(
        run_id=run_id, status="echec", expected_count=expected, seen_count=None,
        inserted_count=0, updated_count=0, absent_count=None, removed_count=None,
        reappeared_count=None, rejected_count=0, http_requests=client.requests,
        http_retries=client.retries, error_kind=kind, error_message=message)


def run_oms_ingestion(
    conn: sqlite3.Connection,
    client: WhoClient,
    *,
    clock: Callable[[], datetime] = utc_now,
    triggered_by: str = "manuel",
    ci_run_url: str | None = None,
) -> RunSummary:
    """Exécute une ingestion complète de l'API OMS et renvoie le résumé du run.

    Ne lève pas d'exception pour un échec d'ingestion : le run est enregistré `echec` et le
    résumé le dit. Utiliser un client neuf par exécution (ses compteurs sont cumulatifs).
    """
    started_at = to_utc_z(clock())
    expected: int | None = None
    try:
        fetched = client.fetch_all()
        expected = fetched.expected_count
        batch = prepare_batch(fetched)
        with transaction(conn):
            return _write_run(conn, client, batch, expected, started_at, clock, triggered_by,
                              ci_run_url)
    except Exception as exc:
        logger.error("ingestion OMS en échec : %s", exc, exc_info=not isinstance(exc, IngestionError))
        return _record_failure(conn, client, started_at, to_utc_z(clock()), expected, triggered_by,
                               ci_run_url, exc)
