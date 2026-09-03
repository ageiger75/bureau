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

from .domain.enums import (
    CaseStatus,
    ChallengeKind,
    ChallengeStatus,
    ChallengeVoice,
    ClaimCategory,
    CommitmentStatus,
    Confidentiality,
    Materiality,
    Reversibility,
    ReviewStatus,
    Severity,
    UserRole,
)
from .util import new_id, now_iso


class Base(DeclarativeBase):
    pass


def _id_column() -> Mapped[str]:
    return mapped_column(String(32), primary_key=True, default=new_id)


class User(Base):
    """Identité. En tranche 1 les utilisateurs viennent du seed ; Entra ID arrive en tranche 5,
    et `entra_oid` est déjà là pour recevoir l'identifiant d'objet sans migration de données."""

    __tablename__ = "users"

    id: Mapped[str] = _id_column()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(
        String(40), nullable=False, default=UserRole.CEO.value
    )
    entra_oid: Mapped[Optional[str]] = mapped_column(String(64), unique=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)

    owned_cases: Mapped[List["DecisionCase"]] = relationship(
        back_populates="owner", foreign_keys="DecisionCase.owner_id"
    )

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return "<User %s %s>" % (self.role, self.email)


class DecisionCase(Base):
    """Le dossier de décision : l'unité de travail du produit (brief §1)."""

    __tablename__ = "decision_cases"

    id: Mapped[str] = _id_column()
    # Référence lisible par un humain, citable en réunion : DR-2026-004.
    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=CaseStatus.DRAFT.value, index=True
    )
    deadline: Mapped[Optional[str]] = mapped_column(String(10), default=None, index=True)
    confidentiality: Mapped[str] = mapped_column(
        String(30), nullable=False, default=Confidentiality.CONFIDENTIAL.value
    )

    # Cadrage : ce que l'outil reformule, distinct de la question posée au départ (brief §6).
    real_decision: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope_out: Mapped[str] = mapped_column(Text, nullable=False, default="")
    constraints: Mapped[str] = mapped_column(Text, nullable=False, default="")
    blind_spot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    owner_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id"), nullable=False
    )
    created_by_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)
    updated_at: Mapped[str] = mapped_column(
        String(32), nullable=False, default=now_iso, onupdate=now_iso
    )

    owner: Mapped["User"] = relationship(
        back_populates="owned_cases", foreign_keys=[owner_id]
    )
    claims: Mapped[List["Claim"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="Claim.created_at",
    )
    options: Mapped[List["Option"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="Option.ordinal",
    )
    recommendation: Mapped[Optional["Recommendation"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    challenges: Mapped[List["Challenge"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="Challenge.created_at",
    )
    decision: Mapped[Optional["DecisionRecord"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    commitments: Mapped[List["Commitment"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="Commitment.created_at",
    )
    reviews: Mapped[List["Review"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="Review.planned_date",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return "<DecisionCase %s %s>" % (self.reference, self.status)


class Claim(Base):
    """Une affirmation qualifiée : fait sourcé, hypothèse, opinion ou élément à vérifier.

    `source_ref` est du texte libre en tranche 1 (« Board pack juillet, p. 12 »). En tranche 3
    l'import de documents le remplacera par une clé étrangère vers un passage indexé, ce qui
    rendra le lien cliquable jusqu'au passage — exigence du brief §15.
    """

    __tablename__ = "claims"

    id: Mapped[str] = _id_column()
    case_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("decision_cases.id"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ClaimCategory.ASSUMPTION.value
    )
    source_ref: Mapped[str] = mapped_column(Text, nullable=False, default="")
    quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    as_of_date: Mapped[Optional[str]] = mapped_column(String(10), default=None)
    materiality: Mapped[str] = mapped_column(
        String(20), nullable=False, default=Materiality.MEDIUM.value
    )
    # Pourquoi cette hypothèse est tenue pour vraie, et par qui.
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Le test le moins coûteux qui lèverait l'inconnue (brief §10, « Incertitude »).
    best_test: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)
    updated_at: Mapped[str] = mapped_column(
        String(32), nullable=False, default=now_iso, onupdate=now_iso
    )

    case: Mapped["DecisionCase"] = relationship(back_populates="claims")

    @property
    def is_unsourced_fact(self) -> bool:
        return (
            self.category == ClaimCategory.SOURCED_FACT.value
            and not self.source_ref.strip()
        )

    def __repr__(self) -> str:  # pragma: no cover
        return "<Claim %s %s>" % (self.category, self.text[:40])


class Option(Base):
    """Une option comparable. Deux ou trois par dossier, statu quo compris (brief §4)."""

    __tablename__ = "options"

    id: Mapped[str] = _id_column()
    case_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("decision_cases.id"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_status_quo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assumptions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    benefits: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risks: Mapped[str] = mapped_column(Text, nullable=False, default="")
    success_conditions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reversibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default=Reversibility.COSTLY.value
    )
    reversibility_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    time_to_effect: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)
    updated_at: Mapped[str] = mapped_column(
        String(32), nullable=False, default=now_iso, onupdate=now_iso
    )

    case: Mapped["DecisionCase"] = relationship(back_populates="options")

    def __repr__(self) -> str:  # pragma: no cover
        return "<Option %s>" % self.name[:40]


class Recommendation(Base):
    """La position de l'outil, distincte de la décision de l'humain.

    Un seul enregistrement par dossier en tranche 1 : l'historique des positions
    successives arrive avec la traçabilité des exécutions IA (tranche 4).
    """

    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("case_id", name="uq_recommendation_case"),)

    id: Mapped[str] = _id_column()
    case_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("decision_cases.id"), nullable=False, index=True
    )
    option_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("options.id"), default=None
    )
    # « Voilà ce que je ferais » : la position nette exigée par le brief §4.
    position: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reasons: Mapped[str] = mapped_column(Text, nullable=False, default="")
    success_conditions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Ce qui invaliderait la recommandation. Champ obligatoire pour passer « Prêt à décider ».
    would_change_if: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Désaccords non résolus : jamais masqués (brief §9, Chief of Staff Composer).
    open_disagreements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)
    updated_at: Mapped[str] = mapped_column(
        String(32), nullable=False, default=now_iso, onupdate=now_iso
    )

    case: Mapped["DecisionCase"] = relationship(back_populates="recommendation")
    option: Mapped[Optional["Option"]] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return "<Recommendation case=%s>" % self.case_id


# ---------------------------------------------------------------------------
# Tranche 2 — challenge, décision, engagements, revue
# ---------------------------------------------------------------------------


class Challenge(Base):
    """Une objection concrète portée par une voix (brief §7 FR-07, §9).

    « Ne critique pas pour le spectacle ; chaque objection doit être concrète » : c'est
    pourquoi `evidence` existe et pourquoi une objection sans preuve est signalée.
    """

    __tablename__ = "challenges"

    id: Mapped[str] = _id_column()
    case_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("decision_cases.id"), nullable=False, index=True
    )
    # Null = l'objection porte sur le cadrage lui-même, pas sur une option en particulier.
    option_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("options.id"), default=None
    )
    voice: Mapped[str] = mapped_column(
        String(40), nullable=False, default=ChallengeVoice.DEVILS_ADVOCATE.value
    )
    kind: Mapped[str] = mapped_column(
        String(40), nullable=False, default=ChallengeKind.PREMISE.value
    )
    objection: Mapped[str] = mapped_column(Text, nullable=False)
    # Sur quoi l'objection s'appuie. Vide = objection en l'air, signalée comme telle.
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default=Severity.SERIOUS.value
    )
    response: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ChallengeStatus.OPEN.value
    )
    answered_by: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    answered_at: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)
    updated_at: Mapped[str] = mapped_column(
        String(32), nullable=False, default=now_iso, onupdate=now_iso
    )

    case: Mapped["DecisionCase"] = relationship(back_populates="challenges")
    option: Mapped[Optional["Option"]] = relationship()

    @property
    def is_unanswered(self) -> bool:
        return self.status == ChallengeStatus.OPEN.value

    def __repr__(self) -> str:  # pragma: no cover
        return "<Challenge %s %s>" % (self.voice, self.severity)


class DecisionRecord(Base):
    """L'arbitrage assumé par l'humain, distinct de la recommandation de l'outil.

    Un seul enregistrement par dossier : ré-arbitrer passe par une revue puis une
    réouverture explicite, ce qui laisse une trace au lieu d'écraser l'historique.
    """

    __tablename__ = "decision_records"
    __table_args__ = (UniqueConstraint("case_id", name="uq_decision_case"),)

    id: Mapped[str] = _id_column()
    case_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("decision_cases.id"), nullable=False, index=True
    )
    option_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("options.id"), nullable=False
    )
    reasons: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Réserves assumées : ce que le CEO sait ne pas avoir résolu en décidant.
    reservations: Mapped[str] = mapped_column(Text, nullable=False, default="")
    success_criteria: Mapped[str] = mapped_column(Text, nullable=False, default="")
    change_conditions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Écart avec la recommandation de l'outil. Enregistré, jamais reproché : c'est une
    # information précieuse lors de la revue.
    diverges_from_recommendation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    divergence_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    review_date: Mapped[str] = mapped_column(String(10), nullable=False)
    decided_by_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id"), nullable=False
    )
    decided_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)

    case: Mapped["DecisionCase"] = relationship(back_populates="decision")
    option: Mapped["Option"] = relationship()
    decided_by: Mapped["User"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return "<DecisionRecord case=%s>" % self.case_id


class Commitment(Base):
    """Un engagement suivi **à l'intérieur du produit**.

    `owner_name` est du texte libre et non une clé étrangère vers `users` : rattacher un
    engagement à un compte suggérerait une notification, ce que le brief §14 interdit
    explicitement. Le suivi est manuel et assumé comme tel.
    """

    __tablename__ = "commitments"

    id: Mapped[str] = _id_column()
    case_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("decision_cases.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    owner_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    due_date: Mapped[Optional[str]] = mapped_column(String(10), default=None, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=CommitmentStatus.OPEN.value
    )
    # « Critique » = son échec remet la décision en cause (brief §3).
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)
    updated_at: Mapped[str] = mapped_column(
        String(32), nullable=False, default=now_iso, onupdate=now_iso
    )

    case: Mapped["DecisionCase"] = relationship(back_populates="commitments")

    def __repr__(self) -> str:  # pragma: no cover
        return "<Commitment %s %s>" % (self.status, self.action[:30])


class Review(Base):
    """La confrontation des hypothèses d'origine aux résultats observés (brief §7 FR-14).

    C'est l'étape qui transforme une décision en apprentissage réutilisable. Elle est créée
    automatiquement au moment de la décision, à la date de revue choisie : une revue qu'il
    faut penser à créer soi-même n'a jamais lieu.
    """

    __tablename__ = "reviews"

    id: Mapped[str] = _id_column()
    case_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("decision_cases.id"), nullable=False, index=True
    )
    planned_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    held_date: Mapped[Optional[str]] = mapped_column(String(10), default=None)
    # Recopié depuis la décision à la création : la revue doit comparer aux attentes
    # d'origine, pas à celles réécrites entre-temps.
    initial_expectations: Mapped[str] = mapped_column(Text, nullable=False, default="")
    observed_results: Mapped[str] = mapped_column(Text, nullable=False, default="")
    gaps: Mapped[str] = mapped_column(Text, nullable=False, default="")
    invalidated_assumptions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lessons: Mapped[str] = mapped_column(Text, nullable=False, default="")
    next_step: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    next_step_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReviewStatus.PLANNED.value
    )
    completed_by_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("users.id"), default=None
    )
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=now_iso)
    updated_at: Mapped[str] = mapped_column(
        String(32), nullable=False, default=now_iso, onupdate=now_iso
    )

    case: Mapped["DecisionCase"] = relationship(back_populates="reviews")
    completed_by: Mapped[Optional["User"]] = relationship()

    @property
    def is_completed(self) -> bool:
        return self.status == ReviewStatus.COMPLETED.value

    def __repr__(self) -> str:  # pragma: no cover
        return "<Review %s %s>" % (self.planned_date, self.status)


# ---------------------------------------------------------------------------
# Tranche 3 — mémoire des sujets de management (brief V6.1 §C1)
# ---------------------------------------------------------------------------


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
