"""Modèles SQLAlchemy 2.0 — tranches 1 et 2.

Conventions, toutes destinées à la portabilité PostgreSQL (brief §12) :
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

from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .util import new_id, now_iso


class Base(DeclarativeBase):
    pass


def _id_column() -> Mapped[str]:
    return mapped_column(String(32), primary_key=True, default=new_id)


class ManagementIssue(Base):
    """Un sujet qui traverse les lectures, plutôt qu'une alerte qui renaît chaque lundi.

    Distinct de `DecisionCase` et pas une variante de lui : un dossier de décision est
    ouvert par quelqu'un qui veut trancher, un sujet de management est trouvé par la
    mesure. Le premier commence par une question, le second par un fait. Les fondre en une
    seule table aurait donné un objet dont la moitié des colonnes sont vides selon la
    porte par laquelle il est entré, et deux cycles de vie superposés dans une colonne
    `status`.

    Le champ qui fait tout le travail est `covers` : les clés d'observation que ce sujet
    porte, séparées par des sauts de ligne. C'est ce que le registre interroge pour savoir
    si une preuve nouvelle appartient à un sujet connu. Écrit comme du texte et non comme
    une table fille, parce qu'il se lit toujours en entier avec son sujet et jamais seul —
    et parce que le brief interdit le JSON natif, qui aurait été la tentation.
    """

    __tablename__ = "management_issues"

    id: Mapped[str] = _id_column()
    #: L'identifiant lisible et cité dans les comptes rendus. Jamais réattribué.
    reference: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    covers: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="detected")
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="MONITOR")
    #: Le responsable du sujet. Texte libre comme `Commitment.owner_name`, et pour la même
    #: raison : une clé étrangère vers un compte suggérerait une notification.
    accountable: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: Le rôle a-t-il été posé ? Sans ce drapeau, « MONITOR » ne se distingue pas de « pas
    #: encore qualifié », et une règle requalifierait chaque semaine un sujet tranché.
    role_set: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Les trois dimensions du §C2. Trois colonnes et non une : dès qu'elles tiennent dans
    #: un seul champ, quelqu'un l'affiche seul.
    trend: Mapped[str] = mapped_column(String(20), nullable=False, default="stable")
    progress: Mapped[str] = mapped_column(String(20), nullable=False, default="on_track")
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="established")

    #: Le sujet clos dont celui-ci est la réapparition. Vide sinon.
    follows: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    #: Le sujet dans lequel celui-ci a été versé. Distinct de `follows`, qui regarde le
    #: passé : les confondre ferait compter un doublon réparé comme un problème répété.
    merged_into: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    closed_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    #: L'arbitrage « on ne fait rien », tracé comme une décision (§C1).
    arbitrated_by: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    arbitrated_at: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    arbitration_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    review_on: Mapped[Optional[str]] = mapped_column(String(10), default=None, index=True)

    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)
    updated_at: Mapped[str] = mapped_column(
        String(32), nullable=False, default=now_iso, onupdate=now_iso
    )

    evidence: Mapped[List["IssueEvidence"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan",
        order_by="IssueEvidence.position",
    )
    readings: Mapped[List["IssueReading"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan",
        order_by="IssueReading.position",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return "<ManagementIssue %s %s>" % (self.reference, self.status)


class IssueEvidence(Base):
    """Un fait mesuré, rattaché au sujet qu'il concerne.

    `position` garde l'ordre de lecture. Trier sur `seen_at` aurait suffi tant que les
    preuves arrivent dans l'ordre du temps ; une fusion les mêle, et deux preuves du même
    jour se seraient réordonnées à chaque chargement — une histoire qui change de forme
    sans que rien n'ait changé.
    """

    __tablename__ = "issue_evidence"

    id: Mapped[str] = _id_column()
    issue_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("management_issues.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    scope: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    seen_at: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    statement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: `Float` est refusé partout dans ce dépôt pour un montant : la chaîne garde ce que la
    #: source a écrit, et le domaine convertit. Un arrondi binaire sur un écart au plan est
    #: invisible et faux.
    amount: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    #: Ce que le montant mesure — « stake » ou « flow ». Vide quand la source ne l'a pas
    #: dit : un montant sans sens déclaré n'ordonne rien, il ne se lit pas comme un enjeu.
    basis: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="established")
    #: La clé du registre de provenance, pour remonter d'un fait à sa source.
    measure: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)

    issue: Mapped["ManagementIssue"] = relationship(back_populates="evidence")

    def __repr__(self) -> str:  # pragma: no cover
        return "<IssueEvidence %s/%s %s>" % (self.kind, self.scope, self.seen_at)


class IssueReading(Base):
    """Une conclusion portée sur un sujet, et ce qui l'a fait changer.

    La mémoire d'interprétation du §C1. Les conclusions s'empilent au lieu de se
    remplacer : « une correction de mapping n'efface pas le diagnostic opérationnel
    antérieur ». Sans la précédente et son motif, le lecteur ne peut pas distinguer une
    erreur de donnée d'un retournement du métier — deux nouvelles opposées.
    """

    __tablename__ = "issue_readings"

    id: Mapped[str] = _id_column()
    issue_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("management_issues.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    #: Vide pour la première lecture, exigé ensuite — la règle vit dans le domaine.
    because: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)

    issue: Mapped["ManagementIssue"] = relationship(back_populates="readings")

    def __repr__(self) -> str:  # pragma: no cover
        return "<IssueReading %s>" % self.conclusion[:40]
