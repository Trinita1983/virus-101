"""Modèle pydantic d'un enregistrement de l'API OMS.

Seuls les champs que la normalisation utilise sont typés. Les autres champs de l'API
(`Response`, `Advice`, `Epidemiology`...) sont acceptés tels quels et archivés dans le
JSON brut : la phase 0 a observé `Epidemiology` à `null` sur les enregistrements anciens,
et rien ne justifie de rejeter un DON pour un champ que la phase 2 ne lit pas.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from observatoire.db import to_utc_z


class DonRecord(BaseModel):
    """Un enregistrement de `diseaseoutbreaknews`. Typage strict : aucune conversion implicite."""

    model_config = ConfigDict(extra="allow", strict=True, frozen=True)

    Id: str = Field(min_length=1)
    UrlName: str = Field(min_length=1)
    Title: str
    UseOverrideTitle: bool
    PublicationDateAndTime: str
    LastModified: str
    OverrideTitle: str | None = None
    DonId: str | None = None  # absent ou vide selon les années (docs/00-sources.md §2.4)
    Summary: str | None = None

    @field_validator("PublicationDateAndTime", "LastModified")
    @classmethod
    def _horodatage_utc(cls, value: str) -> str:
        """Refuse une date illisible ou sans fuseau, et la ramène à la forme UTC du schéma (I2)."""
        return to_utc_z(value)
