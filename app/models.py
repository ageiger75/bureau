"""Modèles SQLAlchemy 2.0.

Aucune table aujourd'hui. Le registre des sujets et les engagements, dernières tables du
dépôt, sont partis le 13 novembre 2026 avec le suivi, que le cabinet du lecteur tient hors
d'ici. `Base` reste pour `create_all` et pour la prochaine table, s'il en vient une, avec
les conventions qui la rendront portable sur PostgreSQL (brief §12) :
  * identifiants : `String(32)` contenant un UUID hexadécimal, jamais un entier
    auto-incrémenté — pas de dépendance à SERIAL/AUTOINCREMENT, et pas d'URL énumérable ;
  * dates : `String(10)` au format ISO `AAAA-MM-JJ` ;
  * horodatages : `String(32)` ISO-8601 UTC ;
  * booléens : `Boolean` (SQLAlchemy le traduit en INTEGER sur SQLite) ;
  * aucune valeur par défaut calculée côté serveur : tout est explicite en Python,
    donc identique sur les deux moteurs.

Python 3.9 : annotations `Optional[...]`, jamais `X | None`.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
