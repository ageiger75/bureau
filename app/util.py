"""Utilitaires transverses : identifiants, horloge, nettoyage des saisies."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional


def new_id() -> str:
    """Identifiant opaque. UUID plutôt qu'un entier auto-incrémenté, pour deux raisons :
    portabilité PostgreSQL et absence de fuite d'information par énumération d'URL."""
    return uuid.uuid4().hex


def now_iso() -> str:
    """Horodatage UTC ISO-8601 à la seconde. Même format en base et dans les journaux."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> date:
    return datetime.now(timezone.utc).date()


def today_iso() -> str:
    return today().isoformat()


def parse_date(value: Optional[str]) -> Optional[date]:
    """Lit une date ISO. Retourne None sur valeur vide ou invalide, sans lever :
    l'appelant décide s'il s'agit d'une erreur de formulaire."""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def days_until(value: Optional[str]) -> Optional[int]:
    """Nombre de jours avant une échéance ISO. Négatif si l'échéance est dépassée."""
    parsed = parse_date(value)
    if parsed is None:
        return None
    return (parsed - today()).days


_WHITESPACE = re.compile(r"[ \t]+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: Optional[str], max_length: int = 20000) -> str:
    """Normalise une saisie utilisateur.

    Les caractères de contrôle sont retirés : ils servent à dissimuler du contenu
    dans un texte d'apparence anodine. L'échappement HTML n'est pas fait ici mais par
    Jinja2 à l'affichage — échapper deux fois produirait des `&amp;amp;`.
    """
    if not value:
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    lines = [_WHITESPACE.sub(" ", line).rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()[:max_length]


def clean_line(value: Optional[str], max_length: int = 500) -> str:
    """Comme clean_text, mais réduit à une seule ligne (titres, noms, références)."""
    return clean_text(value, max_length).replace("\n", " ").strip()
