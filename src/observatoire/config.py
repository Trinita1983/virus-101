"""Réglages du pipeline d'ingestion, avec les bornes vérifiées en phase 0."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from observatoire import __version__

WHO_API_URL = "https://www.who.int/api/news/diseaseoutbreaknews"

# `$top=100` est accepté par l'API, `$top=500` donne HTTP 400 (docs/00-sources.md §2.3).
# Le maximum exact entre 100 et 499 n'a pas été cherché : on reste à 100.
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class Settings:
    """Réglages d'une exécution. `contact` est obligatoire : il figure dans le User-Agent."""

    db_path: Path
    contact: str
    base_url: str = WHO_API_URL
    timeout: float = 30.0
    page_size: int = MAX_PAGE_SIZE
    max_retries: int = 3
    backoff_base: float = 2.0
    backoff_factor: float = 4.0
    backoff_max: float = 30.0
    order_by: str = "PublicationDate desc"
    code_version: str = "inconnue"

    def __post_init__(self) -> None:
        if not self.contact.strip():
            raise ValueError("une adresse de contact est obligatoire (User-Agent)")
        if not 1 <= self.page_size <= MAX_PAGE_SIZE:
            raise ValueError(f"page_size doit être compris entre 1 et {MAX_PAGE_SIZE}")
        if self.timeout <= 0:
            raise ValueError("timeout doit être strictement positif")
        if self.max_retries < 0:
            raise ValueError("max_retries ne peut pas être négatif")

    @property
    def user_agent(self) -> str:
        """User-Agent explicite, avec l'adresse de contact configurée."""
        return f"ObservatoireMaladies/{__version__} (contact: {self.contact})"


def detect_code_version() -> str:
    """SHA git du code exécuté : variable d'environnement, sinon `git rev-parse`, sinon « inconnue »."""
    for name in ("OBSERVATOIRE_CODE_VERSION", "GITHUB_SHA"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.SubprocessError):
        return "inconnue"
    return result.stdout.strip() or "inconnue"
