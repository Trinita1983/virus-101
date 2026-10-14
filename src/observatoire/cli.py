"""Points d'entrée en ligne de commande : `observatoire ingest-oms`, `db-check` et `gold-sample`.

Codes de sortie : 0 succès (`succes` ou `inchange`), 1 échec, 2 erreur d'usage ou de
configuration, 3 exécution `partiel` (rejets ou incohérence de comptage : écart non nul).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx

from observatoire import __version__
from observatoire.config import MAX_PAGE_SIZE, WHO_API_URL, Settings, detect_code_version
from observatoire.db import SQL_DIR, connect, init_db
from observatoire.gold_sample import (
    DEFAULT_RANDOM, DEFAULT_SEED, DEFAULT_SIZE, fixture_ids, load_candidates, select, summary, write_sample,
)
from observatoire.oms.client import WhoClient
from observatoire.oms.ingest import run_oms_ingestion

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_PARTIAL = 0, 1, 2, 3
_EXIT_BY_STATUS = {"succes": EXIT_OK, "inchange": EXIT_OK, "partiel": EXIT_PARTIAL,
                   "echec": EXIT_FAILED}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="observatoire", description=__doc__.split("\n")[0])
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    db_default = os.environ.get("OBSERVATOIRE_DB", "data/observatoire.sqlite")
    ingest = sub.add_parser("ingest-oms", help="ingère les Disease Outbreak News de l'OMS")
    ingest.add_argument("--db", default=db_default, help="fichier SQLite (créé s'il n'existe pas)")
    ingest.add_argument("--contact", default=os.environ.get("OBSERVATOIRE_CONTACT"),
                        help="adresse de contact du User-Agent (ou OBSERVATOIRE_CONTACT)")
    ingest.add_argument("--timeout", type=float,
                        default=float(os.environ.get("OBSERVATOIRE_TIMEOUT", "30")),
                        help="délai HTTP en secondes (défaut 30)")
    ingest.add_argument("--page-size", type=int, default=MAX_PAGE_SIZE,
                        help=f"taille de page `$top`, au plus {MAX_PAGE_SIZE}")
    ingest.add_argument("--max-retries", type=int, default=3,
                        help="nouvelles tentatives sur erreur réseau ou 5xx (défaut 3)")
    ingest.add_argument("--order-by", default="PublicationDate desc",
                        help="`$orderby` OData (défaut : le tri vérifié en phase 0)")
    ingest.add_argument("--base-url", default=WHO_API_URL, help=argparse.SUPPRESS)
    ingest.add_argument("--triggered-by", choices=("planifie", "manuel", "reprise"),
                        default="manuel")
    ingest.add_argument("--ci-run-url", default=os.environ.get("OBSERVATOIRE_CI_RUN_URL"))

    gold = sub.add_parser("gold-sample", help="propose des DON à étiqueter (jeu de référence, phase 3)")
    gold.add_argument("--db", default=db_default)
    gold.add_argument("--out", default="tests/gold/a_etiqueter.csv")
    gold.add_argument("--texts-dir", default="tests/gold/textes")
    gold.add_argument("--n", type=int, default=DEFAULT_SIZE)
    gold.add_argument("--n-random", type=int, default=DEFAULT_RANDOM,
                      help="dont ce nombre de DON tirés au hasard, sans strates (défaut 10)")
    gold.add_argument("--seed", type=int, default=DEFAULT_SEED)
    gold.add_argument("--force", action="store_true", help="écrase un a_etiqueter.csv existant")
    gold.add_argument("--keep-fixture-dons", action="store_true",
                      help="ne pas exclure les 5 DON de fixtures/who_don_sample.json")

    check = sub.add_parser("db-check", help="contrôle d'intégrité et dénombrement des DON en base")
    check.add_argument("--db", default=db_default)
    return parser


def _ingest(args: argparse.Namespace, transport: httpx.BaseTransport | None) -> int:
    if not args.contact:
        print("erreur : --contact (ou OBSERVATOIRE_CONTACT) est obligatoire", file=sys.stderr)
        return EXIT_USAGE
    try:
        settings = Settings(
            db_path=Path(args.db), contact=args.contact, base_url=args.base_url,
            timeout=args.timeout, page_size=args.page_size, max_retries=args.max_retries,
            order_by=args.order_by, code_version=detect_code_version())
    except ValueError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return EXIT_USAGE
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path)
    client = WhoClient(settings, transport=transport)
    try:
        init_db(conn)
        summary = run_oms_ingestion(conn, client, triggered_by=args.triggered_by,
                                    ci_run_url=args.ci_run_url)
    finally:
        client.close()
        conn.close()
    print(json.dumps(summary.as_dict(), ensure_ascii=False, indent=2))
    return _EXIT_BY_STATUS[summary.status]


def _db_check(args: argparse.Namespace) -> int:
    path = Path(args.db)
    if not path.exists():
        print(f"erreur : base introuvable : {path}", file=sys.stderr)
        return EXIT_USAGE
    conn = connect(path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        violations = [dict(r) for r in conn.execute("SELECT * FROM controle_invariants")]
        presence = {r["presence"]: r["n"] for r in conn.execute(
            "SELECT presence, count(*) AS n FROM reports_presence GROUP BY presence")}
        report = {
            "integrity_check": integrity,
            "foreign_key_violations": fk_violations,
            "controle_invariants": violations,
            "reports_total": conn.execute("SELECT count(*) FROM reports").fetchone()[0],
            "reports_distinct_external_id": conn.execute(
                "SELECT count(DISTINCT external_id) FROM reports").fetchone()[0],
            "reports_active": conn.execute("SELECT count(*) FROM reports_active").fetchone()[0],
            "presence": {k: presence.get(k, 0) for k in ("present", "absent", "retire")},
            "last_run": next((dict(r) for r in conn.execute(
                """SELECT id, status, expected_count, seen_count, inserted_count, updated_count,
                          absent_count, removed_count, reappeared_count, error_kind
                   FROM ingestion_runs WHERE source_code = 'oms_don' ORDER BY id DESC LIMIT 1""")),
                None),
        }
    finally:
        conn.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    healthy = integrity == "ok" and fk_violations == 0 and not violations
    return EXIT_OK if healthy else EXIT_FAILED


def _gold_sample(args: argparse.Namespace) -> int:
    path, out = Path(args.db), Path(args.out)
    if not path.exists():
        print(f"erreur : base introuvable : {path}", file=sys.stderr)
        return EXIT_USAGE
    if out.exists() and not args.force:
        print(f"erreur : {out} existe déjà (--force pour l'écraser)", file=sys.stderr)
        return EXIT_USAGE
    exclude = set() if args.keep_fixture_dons else fixture_ids(SQL_DIR.parent / "fixtures" / "who_don_sample.json")
    conn = connect(path)
    try:
        candidates = load_candidates(conn, exclude)
    finally:
        conn.close()
    if not candidates:
        print("erreur : aucun DON éligible dans la base", file=sys.stderr)
        return EXIT_USAGE
    if not 0 <= args.n_random <= args.n:
        print("erreur : --n-random doit être compris entre 0 et --n", file=sys.stderr)
        return EXIT_USAGE
    selection = select(candidates, args.n, args.seed, args.n_random)
    write_sample(selection, out, Path(args.texts_dir))
    print(json.dumps(summary(selection, len(candidates)), ensure_ascii=False, indent=2))
    return EXIT_OK


def main(argv: Sequence[str] | None = None, *,
         transport: httpx.BaseTransport | None = None) -> int:
    """Point d'entrée. `transport` ne sert qu'aux tests (transport HTTP simulé)."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    if args.command == "ingest-oms":
        return _ingest(args, transport)
    if args.command == "gold-sample":
        return _gold_sample(args)
    return _db_check(args)


if __name__ == "__main__":
    sys.exit(main())
