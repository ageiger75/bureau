"""Le type d'avertissement partagé par tout le domaine.

Extrait de `claims.py` en tranche 2 : quatre modules produisent désormais des
avertissements (affirmations, maturité du dossier, engagements, revues), et le type
n'appartient à aucun d'eux en particulier.

Ces avertissements sont la matière première du produit. Le brief §4 interdit de les
agréger en un score : ils s'affichent nommés, un par un, avec le geste qui les lève.
"""

from __future__ import annotations

from dataclasses import dataclass

# Sévérités. « serious » remonte sur l'écran d'accueil ; « minor » reste local au dossier.
SERIOUS = "serious"
MINOR = "minor"


@dataclass(frozen=True)
class QualityWarning:
    """Un défaut nommé, avec le geste concret qui le lève.

    `fix` n'est pas facultatif par convention : un avertissement sans correctif proposé est
    un reproche, pas un mode d'emploi. Un test vérifie que tous en portent un.
    """

    code: str
    severity: str
    message: str
    fix: str

    @property
    def is_serious(self) -> bool:
        return self.severity == SERIOUS


def blocker(code: str, message: str, fix: str) -> QualityWarning:
    """Un bloquant est toujours sérieux : il empêche une transition d'état."""
    return QualityWarning(code=code, severity=SERIOUS, message=message, fix=fix)


def warning(
    code: str, message: str, fix: str, severity: str = SERIOUS
) -> QualityWarning:
    return QualityWarning(code=code, severity=severity, message=message, fix=fix)
