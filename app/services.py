"""Pont entre les objets persistés et les règles du domaine.

Les routes ne doivent pas construire elles-mêmes les vues du domaine : sans ce point de
passage unique, deux écrans finiraient par juger différemment la maturité d'un même dossier.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import challenge as challenge_rules
from .domain import commitments as commitment_rules
from .domain import reviews as review_rules
from .domain.cases import (
    DECIDED_STATUSES,
    CaseSnapshot,
    Readiness,
    TransitionContext,
    assess_readiness,
    urgency,
)
from .domain.claims import (
    ClaimInput,
    check_claim,
    count_by_category,
    source_coverage,
)
from .domain.enums import CaseStatus, ChallengeVoice, ClaimCategory, ReviewStatus, UserRole
from .domain.warnings import QualityWarning
from .models import (
    Challenge,
    Claim,
    Commitment,
    DecisionCase,
    DecisionRecord,
    Option,
    Recommendation,
    Review,
    User,
)
from .util import days_until, today


# --------------------------------------------------------------------------- identités


def resolve_current_user(session: Session) -> User:
    """Utilisateur courant.

    Tranche 1 : identité locale unique, prise dans le seed. Aucune authentification, donc
    aucune illusion d'authentification — le bandeau de l'interface le dit explicitement.
    Entra ID (tranche 5) remplacera cette fonction sans toucher aux routes.
    """
    user = session.scalars(
        select(User).where(User.role == UserRole.CEO.value, User.is_active.is_(True))
    ).first()
    if user is not None:
        return user
    user = session.scalars(select(User).where(User.is_active.is_(True))).first()
    if user is not None:
        return user
    raise LookupError(
        "Aucun utilisateur en base. Lancer `python -m app.cli seed` avant de démarrer."
    )


# --------------------------------------------------------------------------- références


def next_reference(session: Session, year: Optional[int] = None) -> str:
    """Référence lisible et citable : DR-2026-004.

    Le numéro est déduit du plus grand existant sur l'année, et non d'un compteur : un
    dossier supprimé ne doit pas faire réapparaître une référence déjà prononcée en réunion.
    """
    year = year or today().year
    prefix = "DR-%d-" % year
    existing = session.scalars(
        select(DecisionCase.reference).where(DecisionCase.reference.like(prefix + "%"))
    ).all()
    highest = 0
    for reference in existing:
        suffix = reference[len(prefix) :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return "%s%03d" % (prefix, highest + 1)


# --------------------------------------------------------------------------- domaine


def to_claim_input(claim: Claim) -> ClaimInput:
    return ClaimInput(
        text=claim.text,
        category=claim.category,
        source_ref=claim.source_ref,
        quote=claim.quote,
        rationale=claim.rationale,
        best_test=claim.best_test,
        materiality=claim.materiality,
    )


def to_challenge_input(item: Challenge) -> challenge_rules.ChallengeInput:
    return challenge_rules.ChallengeInput(
        objection=item.objection,
        voice=item.voice,
        kind=item.kind,
        evidence=item.evidence,
        severity=item.severity,
        status=item.status,
        response=item.response,
    )


def to_commitment_input(item: Commitment) -> commitment_rules.CommitmentInput:
    return commitment_rules.CommitmentInput(
        action=item.action,
        owner_name=item.owner_name,
        due_date=item.due_date,
        status=item.status,
        is_critical=item.is_critical,
        evidence=item.evidence,
    )


def to_review_input(item: Review) -> review_rules.ReviewInput:
    return review_rules.ReviewInput(
        planned_date=item.planned_date,
        status=item.status,
        observed_results=item.observed_results,
        gaps=item.gaps,
        invalidated_assumptions=item.invalidated_assumptions,
        lessons=item.lessons,
        next_step=item.next_step,
        next_step_note=item.next_step_note,
    )


def snapshot_of(case: DecisionCase) -> CaseSnapshot:
    claims = [to_claim_input(c) for c in case.claims]
    counts = count_by_category(claims)
    recommendation = case.recommendation
    challenge_summary = challenge_rules.summarize(
        to_challenge_input(c) for c in case.challenges
    )
    return CaseSnapshot(
        question=case.question,
        real_decision=case.real_decision,
        option_count=len(case.options),
        status_quo_present=any(o.is_status_quo for o in case.options),
        sourced_fact_count=counts[ClaimCategory.SOURCED_FACT.value],
        assumption_count=counts[ClaimCategory.ASSUMPTION.value],
        missing_verification_count=counts[ClaimCategory.MISSING_VERIFICATION.value],
        unsourced_fact_count=sum(1 for c in case.claims if c.is_unsourced_fact),
        has_recommendation=recommendation is not None
        and bool(recommendation.position.strip()),
        recommendation_has_change_conditions=recommendation is not None
        and bool(recommendation.would_change_if.strip()),
        challenge_count=challenge_summary.total,
        unanswered_blocking_challenges=challenge_summary.unanswered_blocking,
        premise_tested=challenge_summary.premise_tested,
        challenges_without_evidence=challenge_summary.without_evidence,
        missing_voice_labels=tuple(challenge_summary.missing_voice_labels),
    )


def diagnose(case: DecisionCase) -> Readiness:
    return assess_readiness(snapshot_of(case))


def transition_context(case: DecisionCase) -> TransitionContext:
    """Rassemble les conditions d'entrée dans chaque état. Un seul constructeur, pour
    qu'aucune route ne puisse en oublier une."""
    return TransitionContext(
        readiness=diagnose(case),
        has_decision=case.decision is not None,
        commitment_count=len(case.commitments),
        has_planned_review=any(not r.is_completed for r in case.reviews),
        review_completed=any(r.is_completed for r in case.reviews),
    )


def claim_warnings(claims: Iterable[Claim]) -> Dict[str, List[QualityWarning]]:
    """Avertissements par affirmation, indexés par identifiant pour l'affichage."""
    result: Dict[str, List[QualityWarning]] = {}
    for claim in claims:
        warnings = check_claim(to_claim_input(claim))
        if warnings:
            result[claim.id] = warnings
    return result


def claims_by_category(case: DecisionCase) -> Dict[str, List[Claim]]:
    """Affirmations regroupées, les déterminantes en tête de chaque groupe."""
    grouped: Dict[str, List[Claim]] = {member.value: [] for member in ClaimCategory}
    for claim in case.claims:
        grouped.setdefault(claim.category, []).append(claim)
    weight = {"high": 0, "medium": 1, "low": 2}
    for items in grouped.values():
        items.sort(key=lambda c: (weight.get(c.materiality, 1), c.created_at))
    return grouped


def coverage_label(case: DecisionCase) -> str:
    """Couverture des sources, en texte.

    Aucune valeur n'est affichée s'il n'y a aucun fait : un « 100 % » sur un ensemble vide
    est exactement la fausse précision que le brief §10 interdit.
    """
    ratio = source_coverage([to_claim_input(c) for c in case.claims])
    if ratio is None:
        return "Aucun fait déclaré"
    return "%d %% des faits sont sourcés" % round(ratio * 100)


# ------------------------------------------------------- challenge, suivi, revue


def challenge_summary(case: DecisionCase) -> challenge_rules.ChallengeSummary:
    return challenge_rules.summarize(to_challenge_input(c) for c in case.challenges)


def challenge_warnings(case: DecisionCase) -> Dict[str, List[QualityWarning]]:
    result: Dict[str, List[QualityWarning]] = {}
    for item in case.challenges:
        warnings = challenge_rules.check_challenge(to_challenge_input(item))
        if warnings:
            result[item.id] = warnings
    return result


def challenges_by_voice(case: DecisionCase) -> Dict[str, List[Challenge]]:
    """Objections regroupées par voix, les plus graves d'abord dans chaque groupe."""
    grouped: Dict[str, List[Challenge]] = {
        member.value: [] for member in ChallengeVoice
    }
    for item in case.challenges:
        grouped.setdefault(item.voice, []).append(item)
    weight = {"blocking": 0, "serious": 1, "minor": 2}
    for items in grouped.values():
        items.sort(key=lambda c: (weight.get(c.severity, 1), c.created_at))
    return grouped


def commitment_days_left(item: Commitment) -> Optional[int]:
    return days_until(item.due_date)


def commitment_alerts(case: DecisionCase) -> Dict[str, str]:
    """Niveau d'alerte par engagement, indexé par identifiant."""
    return {
        item.id: commitment_rules.alert_level(item.status, commitment_days_left(item))
        for item in case.commitments
    }


def commitment_warnings(case: DecisionCase) -> Dict[str, List[QualityWarning]]:
    result: Dict[str, List[QualityWarning]] = {}
    for item in case.commitments:
        warnings = commitment_rules.check_commitment(
            to_commitment_input(item), commitment_days_left(item)
        )
        if warnings:
            result[item.id] = warnings
    return result


def commitment_summary(case: DecisionCase) -> commitment_rules.CommitmentSummary:
    return commitment_rules.summarize(
        (to_commitment_input(item), commitment_days_left(item))
        for item in case.commitments
    )


def sorted_commitments(case: DecisionCase) -> List[Commitment]:
    """Les engagements en retard d'abord, puis par échéance. Sans date en dernier :
    un engagement sans échéance ne peut pas prétendre à l'attention."""
    alerts = commitment_alerts(case)
    rank = {
        commitment_rules.OVERDUE: 0,
        commitment_rules.DUE_SOON: 1,
        commitment_rules.ON_TRACK: 2,
        commitment_rules.NO_DATE: 3,
        commitment_rules.CLOSED: 4,
    }
    return sorted(
        case.commitments,
        key=lambda c: (
            rank.get(alerts.get(c.id, ""), 9),
            c.due_date or "9999-12-31",
            c.created_at,
        ),
    )


def active_review(case: DecisionCase) -> Optional[Review]:
    """La revue en cours : la première non terminée, sinon la dernière terminée."""
    pending = [r for r in case.reviews if not r.is_completed]
    if pending:
        return sorted(pending, key=lambda r: r.planned_date)[0]
    if case.reviews:
        return sorted(case.reviews, key=lambda r: r.planned_date)[-1]
    return None


def review_days_left(review: Review) -> Optional[int]:
    return days_until(review.planned_date)


# --------------------------------------------------------------------------- accueil


class CaseRow:
    """Ligne d'accueil : le dossier plus ce qu'il faut savoir sans l'ouvrir."""

    __slots__ = (
        "case",
        "days_left",
        "urgency",
        "readiness",
        "claim_count",
        "option_count",
        "commitments",
        "review",
        "review_days_left",
    )

    def __init__(self, case: DecisionCase) -> None:
        self.case = case
        self.days_left = days_until(case.deadline)
        self.urgency = urgency(self.days_left)
        self.readiness = diagnose(case)
        self.claim_count = len(case.claims)
        self.option_count = len(case.options)
        self.commitments = commitment_summary(case)
        self.review = active_review(case)
        self.review_days_left = (
            review_days_left(self.review) if self.review is not None else None
        )

    @property
    def review_is_due(self) -> bool:
        if self.review is None:
            return False
        return review_rules.is_due(self.review.status, self.review_days_left)

    @property
    def review_is_upcoming(self) -> bool:
        if self.review is None:
            return False
        return review_rules.is_upcoming(self.review.status, self.review_days_left)

    @property
    def is_decided(self) -> bool:
        return self.case.status in DECIDED_STATUSES

    @property
    def decision_deadline_matters(self) -> bool:
        """L'échéance de décision ne concerne que les dossiers pas encore arbitrés.

        Sans ce filtre, un dossier décidé en avril resterait signalé « échéance dépassée »
        pour toujours — et noierait les vrais signaux de l'exécution.
        """
        return not self.is_decided

    @property
    def needs_attention(self) -> bool:
        if self.is_decided:
            # Un dossier décidé se juge sur son exécution, pas sur sa maturité.
            return self.commitments.overdue > 0 or self.review_is_due
        return (
            self.urgency in ("overdue", "critical")
            or self.readiness.serious_warning_count > 0
        )

    @property
    def attention_reasons(self) -> List[str]:
        """Pourquoi ce dossier demande attention, en clair.

        Une liste de raisons nommées plutôt qu'un pictogramme : le brief §4 exige de montrer
        ce qui soutient l'analyse, pas de résumer par un symbole.
        """
        reasons: List[str] = []
        if self.decision_deadline_matters:
            if self.urgency == "overdue":
                reasons.append("échéance de décision dépassée")
            elif self.urgency == "critical":
                reasons.append("échéance sous 3 jours")
        if self.commitments.critical_overdue > 0:
            reasons.append(
                "%d engagement%s critique%s en retard"
                % (
                    self.commitments.critical_overdue,
                    "s" if self.commitments.critical_overdue > 1 else "",
                    "s" if self.commitments.critical_overdue > 1 else "",
                )
            )
        elif self.commitments.overdue > 0:
            reasons.append(
                "%d engagement%s en retard"
                % (
                    self.commitments.overdue,
                    "s" if self.commitments.overdue > 1 else "",
                )
            )
        if self.commitments.rearbitration_needed > 0:
            reasons.append("ré-arbitrage demandé")
        if self.review_is_due:
            reasons.append("revue échue")
        # Le diagnostic de maturité ne dit plus rien d'utile sur un dossier déjà arbitré.
        count = 0 if self.is_decided else self.readiness.serious_warning_count
        if count > 0:
            reasons.append(
                "%d signalement%s sérieux" % (count, "s" if count > 1 else "")
            )
        return reasons


# Ordre de tri de l'accueil : d'abord ce qui presse, ensuite ce qui est fragile.
_URGENCY_RANK = {"overdue": 0, "critical": 1, "soon": 2, "later": 3, "none": 4}
_STATUS_RANK = {
    CaseStatus.READY.value: 0,
    CaseStatus.ANALYSIS.value: 1,
    CaseStatus.DRAFT.value: 2,
    CaseStatus.DECIDED.value: 3,
    CaseStatus.EXECUTING.value: 4,
    CaseStatus.TO_REVIEW.value: 5,
    CaseStatus.CLOSED.value: 6,
}


def list_case_rows(session: Session, include_closed: bool = False) -> List[CaseRow]:
    statement = select(DecisionCase)
    if not include_closed:
        statement = statement.where(DecisionCase.status != CaseStatus.CLOSED.value)
    cases = session.scalars(statement).all()
    rows = [CaseRow(case) for case in cases]
    rows.sort(
        key=lambda row: (
            _URGENCY_RANK.get(row.urgency, 9),
            _STATUS_RANK.get(row.case.status, 9),
            row.case.reference,
        )
    )
    return rows


class ArchivedRow:
    """Ligne d'archive : ce qu'on relit d'un dossier clos, six mois plus tard.

    Pas le raisonnement complet — ce qui a été décidé, ce qui s'est réellement passé, et
    la leçon. Le dossier entier reste à un clic.
    """

    __slots__ = ("case", "decision", "review")

    def __init__(self, case: DecisionCase) -> None:
        self.case = case
        self.decision = case.decision
        self.review = active_review(case)

    @property
    def lessons(self) -> str:
        return self.review.lessons if self.review is not None else ""

    @property
    def closed_on(self) -> str:
        """Date de clôture : celle où la revue s'est tenue, à défaut la dernière écriture.

        `held_date` et non `planned_date` : ce qui compte à la relecture est le jour où
        les hypothèses ont été confrontées aux résultats, pas celui où on avait prévu
        de le faire.
        """
        if self.review is not None and self.review.held_date:
            return self.review.held_date
        return (self.case.updated_at or "")[:10]

    @property
    def diverged(self) -> bool:
        return (
            self.decision is not None
            and self.decision.diverges_from_recommendation
        )


def list_archived_rows(session: Session) -> List[ArchivedRow]:
    """Dossiers clos, du plus récemment clos au plus ancien.

    Le brief §6 demande un dossier « archivé et retrouvable ». Retrouvable veut dire
    atteignable depuis l'interface : un dossier qui n'existe plus qu'au bout d'une adresse
    conservée ailleurs n'est pas archivé, il est perdu proprement — et la leçon de sa
    revue, seul produit réutilisable d'une décision passée, l'est avec lui.
    """
    cases = session.scalars(
        select(DecisionCase).where(DecisionCase.status == CaseStatus.CLOSED.value)
    ).all()
    rows = [ArchivedRow(case) for case in cases]
    rows.sort(key=lambda row: (row.closed_on, row.case.reference), reverse=True)
    return rows


# --------------------------------------------------------------------------- écritures


def next_option_ordinal(case: DecisionCase) -> int:
    return max([o.ordinal for o in case.options], default=-1) + 1


def get_or_create_recommendation(session: Session, case: DecisionCase) -> Recommendation:
    if case.recommendation is not None:
        return case.recommendation
    recommendation = Recommendation()
    case.recommendation = recommendation  # l'ORM renseigne case_id
    session.flush()
    return recommendation


def find_case(session: Session, case_id: str) -> Optional[DecisionCase]:
    return session.get(DecisionCase, case_id)


def find_claim(session: Session, case_id: str, claim_id: str) -> Optional[Claim]:
    """Recherche portée par le dossier : un identifiant d'affirmation seul ne doit jamais
    suffire à atteindre le contenu d'un autre dossier."""
    claim = session.get(Claim, claim_id)
    if claim is None or claim.case_id != case_id:
        return None
    return claim


def find_challenge(session: Session, case_id: str, item_id: str) -> Optional[Challenge]:
    item = session.get(Challenge, item_id)
    if item is None or item.case_id != case_id:
        return None
    return item


def find_commitment(session: Session, case_id: str, item_id: str) -> Optional[Commitment]:
    item = session.get(Commitment, item_id)
    if item is None or item.case_id != case_id:
        return None
    return item


def find_review(session: Session, case_id: str, item_id: str) -> Optional[Review]:
    item = session.get(Review, item_id)
    if item is None or item.case_id != case_id:
        return None
    return item


def find_option(session: Session, case_id: str, option_id: str) -> Optional[Option]:
    option = session.get(Option, option_id)
    if option is None or option.case_id != case_id:
        return None
    return option


def option_choices(case: DecisionCase) -> Sequence[Option]:
    return sorted(case.options, key=lambda o: o.ordinal)


# ------------------------------------------------- enregistrement d'une décision


def record_decision(
    session: Session,
    case: DecisionCase,
    user: User,
    values: Dict[str, object],
) -> DecisionRecord:
    """Enregistre l'arbitrage et **crée la revue** à la date choisie.

    La revue est créée ici, et non par un geste séparé : une revue qu'il faut penser à
    planifier soi-même n'a jamais lieu, et le brief §3 en fait un objectif mesurable.

    Les attentes initiales sont recopiées dans la revue au moment de la décision. La revue
    doit comparer aux attentes d'origine, pas à celles réécrites entre-temps.
    """
    decision = case.decision
    if decision is None:
        decision = DecisionRecord(
            option_id=str(values["option_id"]),
            decided_by_id=user.id,
            review_date=str(values["review_date"]),
        )
        case.decision = decision  # l'ORM renseigne case_id

    for name in (
        "option_id",
        "reasons",
        "reservations",
        "success_criteria",
        "change_conditions",
        "diverges_from_recommendation",
        "divergence_reason",
        "review_date",
    ):
        setattr(decision, name, values[name])
    decision.decided_by_id = user.id
    session.flush()

    expectations = "\n".join(
        part
        for part in (str(values["success_criteria"]), str(values["change_conditions"]))
        if part.strip()
    )
    pending = [r for r in case.reviews if not r.is_completed]
    if pending:
        # Ré-arbitrage : on déplace la revue existante au lieu d'en empiler une seconde.
        review = sorted(pending, key=lambda r: r.planned_date)[0]
        review.planned_date = str(values["review_date"])
        review.initial_expectations = expectations
    else:
        case.reviews.append(
            Review(
                planned_date=str(values["review_date"]),
                initial_expectations=expectations,
            )
        )
    session.flush()
    return decision


def recommendation_option_id(case: DecisionCase) -> Optional[str]:
    """Option recommandée par l'outil, pour détecter une divergence assumée."""
    if case.recommendation is None:
        return None
    return case.recommendation.option_id


# --------------------------------------------------- agrégats pour l'accueil


class CommitmentLine:
    """Un engagement en retard, avec le dossier dont il vient."""

    __slots__ = ("commitment", "case", "days_left")

    def __init__(self, commitment: Commitment, days_left: Optional[int]) -> None:
        self.commitment = commitment
        self.case = commitment.case
        self.days_left = days_left

    @property
    def days_late(self) -> int:
        return -(self.days_left or 0)


class ReviewLine:
    """Une revue échue ou à venir, avec le dossier dont elle vient."""

    __slots__ = ("review", "case", "days_left")

    def __init__(self, review: Review, days_left: Optional[int]) -> None:
        self.review = review
        self.case = review.case
        self.days_left = days_left

    @property
    def is_due(self) -> bool:
        return review_rules.is_due(self.review.status, self.days_left)


def overdue_commitments(session: Session) -> List[CommitmentLine]:
    """Engagements en retard, tous dossiers confondus (brief §8, écran Accueil).

    Les critiques d'abord : leur retard remet la décision en cause, pas seulement le
    calendrier.
    """
    lines: List[CommitmentLine] = []
    for item in session.scalars(select(Commitment)).all():
        days_left = commitment_days_left(item)
        if commitment_rules.alert_level(item.status, days_left) == commitment_rules.OVERDUE:
            lines.append(CommitmentLine(item, days_left))
    lines.sort(key=lambda line: (not line.commitment.is_critical, line.days_left or 0))
    return lines


def due_and_upcoming_reviews(session: Session) -> List[ReviewLine]:
    """Revues échues ou proches, tous dossiers confondus."""
    lines: List[ReviewLine] = []
    for review in session.scalars(
        select(Review).where(Review.status != ReviewStatus.COMPLETED.value)
    ).all():
        days_left = review_days_left(review)
        if review_rules.is_due(review.status, days_left) or review_rules.is_upcoming(
            review.status, days_left
        ):
            lines.append(ReviewLine(review, days_left))
    lines.sort(key=lambda line: line.days_left if line.days_left is not None else 9999)
    return lines
