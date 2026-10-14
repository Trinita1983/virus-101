"""Erreur d'ingestion qualifiée par le `error_kind` du schéma."""

from __future__ import annotations

from typing import Literal

ErrorKind = Literal["reseau", "http", "quota", "format", "validation", "controle", "autre"]


class IngestionError(Exception):
    """Échec d'une exécution. `kind` est une valeur de `ingestion_runs.error_kind`."""

    def __init__(self, kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind: ErrorKind = kind
