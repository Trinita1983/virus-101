"""Texte d'un DON tel que lu par l'étiquetage et par l'extracteur de chiffres (phase 3).

Fonction unique : le fichier `tests/gold/textes/<Id>.txt` proposé à l'étiquetage et le texte
sur lequel l'extracteur travaillera sont produits par `report_text`, donc les citations et
les positions du jeu de référence s'appliquent au même texte. Toute modification de cette
fonction invalide les textes déjà étiquetés.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

# Champs texte de l'API OMS, dans l'ordre de lecture (docs/00-sources.md §2.2).
TEXT_FIELDS = ("Summary", "Overview", "Epidemiology", "Assessment", "Advice", "Response",
               "FurtherInformation")


_BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str | None) -> str:
    """Texte brut d'un fragment HTML : un paragraphe ou un élément de liste par ligne, sans ligne vide."""
    if not html:
        return ""
    parser = _Text()
    parser.feed(html)
    parser.close()
    lines = [" ".join(line.replace("\xa0", " ").split()) for line in "".join(parser.parts).split("\n")]
    return "\n".join(line for line in lines if line)


def report_text(title: str, url: str, published_at: str, raw: dict[str, Any]) -> str:
    """Texte d'un DON : en-tête puis les champs texte non vides, chacun sous `## Champ`.

    Les citations du jeu de référence doivent être des sous-chaînes de ce fichier.
    """
    parts = [f"TITRE : {title}", f"PUBLIÉ : {published_at}", f"URL : {url}"]
    for name in TEXT_FIELDS:
        body = html_to_text(raw.get(name)) if isinstance(raw.get(name), str) else ""
        if body:
            parts.append(f"\n## {name}\n{body}")
    return "\n".join(parts) + "\n"
