"""Échantillon de DON à étiqueter à la main pour le jeu de référence de la phase 3.

ATTENTION : les heuristiques de ce module (« sans chiffre apparent », « approximation »,
« cumulé », « multi-pays »...) ne servent QU'À CHOISIR quels DON proposer à l'étiquetage, de
façon à couvrir des cas variés. Elles ne sont pas des règles d'extraction, ne doivent jamais
être importées ailleurs ni recopiées dans l'extracteur (un test le vérifie). Aucune étiquette
n'est écrite : l'étiquetage est fait par une personne.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from observatoire.oms.text import report_text

# Colonnes du jeu de référence, alignées sur report_figures (docs/01b-arbitrage.md, point D).
GOLD_COLUMNS = ("don_id", "split", "pays", "maladie", "type", "valeur", "qualificatif",
                "precision", "cumule_ou_nouveau", "date_reference", "citation")
SAMPLE_COLUMNS = ("don_id", "split", "titre", "url", "chemin_texte", "origine")
PRECISIONS = ("exact", "environ", "au_moins", "au_plus", "fourchette_basse", "fourchette_haute")
DEFAULT_SEED = 20261014
DEFAULT_SIZE = 40
DEFAULT_RANDOM = 10  # DON tirés au hasard, sans stratification
def split_for(don_id: str) -> str:
    """Split 50/50 déterministe : parité du sha256 de l'identifiant (`Id` de l'API)."""
    return "dev" if int(hashlib.sha256(don_id.encode("utf-8")).hexdigest(), 16) % 2 == 0 else "holdout"


# --- Heuristiques d'échantillonnage (jamais des règles d'extraction) ----------------------------

_WORDS = "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|zero|no"
_NUM = rf"(?:\d[\d,  ]*\d|\d|{_WORDS})"
_KEY = r"(?:cases?|deaths?|died|fatal\w*)"
_HAS_FIGURE = re.compile(rf"\b{_NUM}\b.{{0,40}}\b{_KEY}\b|\b{_KEY}\b.{{0,40}}\b{_NUM}\b", re.I | re.S)
_APPROX = re.compile(rf"\b(about|approximately|around|nearly|almost|at least|more than|over|up to|"
                     rf"estimated)\s+{_NUM}\b", re.I)
_CUMUL = re.compile(r"\b(cumulative\w*|to date|total of|since the (start|beginning))\b", re.I)
_NEW = re.compile(rf"\b(new(ly)?|additional|in the past|last week|since the last)\b.{{0,40}}\b{_KEY}\b",
                  re.I | re.S)
_MULTI_TITLE = re.compile(r"multi-?country|region|global|countries|worldwide|international|"
                          r"\band\b|,", re.I)
_TITLE_SPLIT = re.compile(r"\s+[–-]\s+")


@dataclass(frozen=True)
class Candidate:
    don_id: str
    title: str
    url: str
    published_at: str
    text: str
    disease: str
    flags: frozenset[str] = field(default_factory=frozenset)


def year_bin(published_at: str) -> str:
    year = int(published_at[:4])
    return "ancien" if year < 2015 else ("recent" if year >= 2022 else "intermediaire")


def disease_key(title: str) -> str:
    """Partie « maladie » du titre (avant le premier tiret), en minuscules, sans « update N »."""
    head = _TITLE_SPLIT.split(title.strip(), maxsplit=1)[0]
    return re.sub(r"[\s\-–]*update\s*\d*$", "", head.strip().lower()).strip() or title.lower()


def strata_flags(title: str, published_at: str, text: str) -> frozenset[str]:
    """Strates d'un DON, pour l'échantillonnage seulement."""
    flags = {year_bin(published_at)}
    if not _HAS_FIGURE.search(text):
        flags.add("sans_chiffre")
    if _APPROX.search(text):
        flags.add("approx")
    if _CUMUL.search(text):
        flags.add("cumule")
    if _NEW.search(text):
        flags.add("nouveau")
    if _MULTI_TITLE.search(title):
        flags.add("multi_pays")
    return frozenset(flags)


# Effectif visé par strate (les strates se recouvrent : un DON compte dans chacune des siennes).
QUOTAS = {"sans_chiffre": 6, "multi_pays": 8, "cumule": 8, "nouveau": 8, "approx": 8,
          "ancien": 10, "recent": 10}
MAX_PER_DISEASE = 2


@dataclass(frozen=True)
class Selection:
    chosen: list[Candidate]
    random_ids: frozenset[str]  # DON tirés au hasard ; les autres viennent des strates
    available: dict[str, int]
    reached: dict[str, int]
    shortfalls: dict[str, int]


def select(candidates: Iterable[Candidate], n: int = DEFAULT_SIZE, seed: int = DEFAULT_SEED,
           n_random: int = DEFAULT_RANDOM) -> Selection:
    """Choix reproductible : même base, même graine, mêmes tailles -> même échantillon.

    `n_random` DON sont d'abord tirés au hasard (sans strates) parmi tous les candidats, avec la
    même graine ; les `n - n_random` autres sont choisis par strates parmi le reste. Les
    effectifs atteints par strate ne comptent que la partie stratifiée. Les strates sont remplies de la plus rare à la plus fréquente, en préférant les maladies
    encore peu représentées (au plus `MAX_PER_DISEASE` par maladie tant que c'est possible),
    puis l'échantillon est complété par les maladies les moins représentées.
    """
    if not 0 <= n_random <= n:
        raise ValueError("n_random doit être compris entre 0 et n")
    pool = sorted(candidates, key=lambda c: c.don_id)
    drawn = list(pool)
    random.Random(seed).shuffle(drawn)
    random_part = drawn[:n_random]
    random_ids = frozenset(c.don_id for c in random_part)
    pool = [c for c in pool if c.don_id not in random_ids]
    n_strata = n - len(random_part)
    random.Random(seed).shuffle(pool)
    rank = {c.don_id: i for i, c in enumerate(pool)}
    available = {k: sum(1 for c in pool if k in c.flags) for k in QUOTAS}
    chosen: list[Candidate] = []
    per_disease: Counter[str] = Counter()

    def take(options: list[Candidate], cap: int | None) -> bool:
        options = [c for c in options if c not in chosen
                   and (cap is None or per_disease[c.disease] < cap)]
        if not options or len(chosen) >= n_strata:
            return False
        best = min(options, key=lambda c: (per_disease[c.disease], rank[c.don_id]))
        chosen.append(best)
        per_disease[best.disease] += 1
        return True

    for key in sorted(QUOTAS, key=lambda k: (available[k], k)):
        while sum(1 for c in chosen if key in c.flags) < QUOTAS[key]:
            if not (take([c for c in pool if key in c.flags], MAX_PER_DISEASE)
                    or take([c for c in pool if key in c.flags], None)):
                break
    while len(chosen) < n_strata and (take(pool, MAX_PER_DISEASE) or take(pool, None)):
        pass
    reached = {k: sum(1 for c in chosen if k in c.flags) for k in QUOTAS}
    shortfalls = {k: QUOTAS[k] - v for k, v in reached.items() if v < QUOTAS[k]}
    everything = sorted([*random_part, *chosen], key=lambda c: c.don_id)
    return Selection(everything, random_ids, available, reached, shortfalls)


# --- Base, fichiers ----------------------------------------------------------------------------


def fixture_ids(fixture: Path) -> set[str]:
    """`Id` des DON de la fixture, exclus du jeu de référence."""
    if not fixture.exists():
        return set()
    return {r["Id"] for r in json.loads(fixture.read_text(encoding="utf-8"))["value"]}


def load_candidates(conn: sqlite3.Connection, exclude: set[str]) -> list[Candidate]:
    """DON actifs de la base, avec leur texte tiré du JSON brut courant."""
    rows = conn.execute(
        """SELECT r.external_id, r.title, r.url, r.published_at, p.body_text
           FROM reports_active AS r JOIN raw_payloads AS p ON p.id = r.raw_payload_id
           WHERE r.source_code = 'oms_don' ORDER BY r.external_id""").fetchall()
    out = []
    for r in rows:
        if r["external_id"] in exclude:
            continue
        text = report_text(r["title"], r["url"], r["published_at"], json.loads(r["body_text"]))
        out.append(Candidate(r["external_id"], r["title"], r["url"], r["published_at"], text,
                             disease_key(r["title"]),
                             strata_flags(r["title"], r["published_at"], text)))
    return out


def write_sample(selection: Selection, out_csv: Path, texts_dir: Path,
                 path_of: Callable[[Candidate], str] | None = None) -> None:
    """Écrit les textes puis `a_etiqueter.csv` (aucune colonne d'étiquette)."""
    texts_dir.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(SAMPLE_COLUMNS)
        for c in selection.chosen:
            file = texts_dir / f"{c.don_id}.txt"
            file.write_text(c.text, encoding="utf-8")
            writer.writerow([c.don_id, split_for(c.don_id), c.title, c.url,
                             path_of(c) if path_of else file.as_posix(),
                             "aleatoire" if c.don_id in selection.random_ids else "strate"])


def summary(selection: Selection, eligible: int) -> dict[str, Any]:
    splits = Counter(split_for(c.don_id) for c in selection.chosen)
    return {"eligible": eligible, "selected": len(selection.chosen),
            "aleatoire": len(selection.random_ids),
            "dev": splits["dev"], "holdout": splits["holdout"],
            "strata": {k: {"quota": QUOTAS[k], "available": selection.available[k],
                           "reached": selection.reached[k]} for k in QUOTAS},
            "shortfalls": selection.shortfalls}
