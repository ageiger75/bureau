"""Challenge : contester le dossier avant de décider (brief §7 FR-07, §9).

Deux règles du brief structurent ce module.

« Ne cherche pas à plaire au CEO. » Un dossier qui n'a jamais été contesté ne peut pas
passer en « Prêt à décider » : c'est le seul moyen d'empêcher l'outil de devenir une machine
à confirmer l'intuition initiale.

« Ne critique pas pour le spectacle ; chaque objection doit être concrète. » Une objection
sans preuve est enregistrée mais signalée — même politique que pour un fait sans source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence, Tuple

from .enums import (
    CHALLENGE_VOICE_LABELS,
    CHALLENGE_VOICE_ORDER,
    ChallengeKind,
    ChallengeStatus,
    ChallengeVoice,
    Severity,
)
from .warnings import MINOR, QualityWarning, warning

# Voix dont l'absence est signalée avant de décider. L'avocat du diable en fait partie :
# c'est lui qui teste les prémisses, donc son silence est le plus coûteux.
EXPECTED_VOICES: Tuple[str, ...] = (
    ChallengeVoice.DEVILS_ADVOCATE.value,
    ChallengeVoice.FINANCE.value,
    ChallengeVoice.BRAND.value,
    ChallengeVoice.CLIENT.value,
    ChallengeVoice.LONG_TERM.value,
)


@dataclass(frozen=True)
class ChallengeInput:
    """Vue minimale d'une objection, indépendante de l'ORM."""

    objection: str
    voice: str
    kind: str = ChallengeKind.PREMISE.value
    evidence: str = ""
    severity: str = Severity.SERIOUS.value
    status: str = ChallengeStatus.OPEN.value
    response: str = ""


def check_challenge(item: ChallengeInput) -> List[QualityWarning]:
    """Avertissements portés par une objection prise isolément."""
    warnings: List[QualityWarning] = []

    if not item.evidence.strip():
        warnings.append(
            warning(
                "objection_without_evidence",
                "Objection sans élément concret à l'appui.",
                "Citer le fait, le chiffre ou le signal qui la fonde — sinon c'est une "
                "impression, pas une objection.",
            )
        )

    if item.status != ChallengeStatus.OPEN.value and not item.response.strip():
        warnings.append(
            warning(
                "closed_without_response",
                "Objection classée sans réponse écrite.",
                "Écrire ce qui a été répondu : c'est ce qu'on relira à la revue.",
            )
        )

    if (
        item.severity == Severity.BLOCKING.value
        and item.status == ChallengeStatus.OPEN.value
    ):
        warnings.append(
            warning(
                "blocking_unanswered",
                "Objection bloquante sans réponse : elle empêche de déclarer le dossier prêt.",
                "Y répondre, l'accepter comme réserve, ou l'écarter en expliquant pourquoi.",
            )
        )

    if item.status == ChallengeStatus.REJECTED.value and not item.response.strip():
        warnings.append(
            warning(
                "rejected_without_reason",
                "Objection écartée sans motif.",
                "Écarter une objection sans dire pourquoi revient à ne pas l'avoir entendue.",
                severity=MINOR,
            )
        )

    return warnings


@dataclass
class ChallengeSummary:
    """État du challenge sur un dossier."""

    total: int = 0
    unanswered_blocking: int = 0
    unanswered: int = 0
    without_evidence: int = 0
    premise_tested: bool = False
    voices_present: List[str] = field(default_factory=list)

    @property
    def missing_voices(self) -> List[str]:
        return [v for v in EXPECTED_VOICES if v not in self.voices_present]

    @property
    def missing_voice_labels(self) -> List[str]:
        return [CHALLENGE_VOICE_LABELS.get(v, v) for v in self.missing_voices]


def summarize(challenges: Iterable[ChallengeInput]) -> ChallengeSummary:
    items = list(challenges)
    voices: List[str] = []
    for item in items:
        if item.voice not in voices:
            voices.append(item.voice)

    return ChallengeSummary(
        total=len(items),
        unanswered_blocking=sum(
            1
            for i in items
            if i.severity == Severity.BLOCKING.value
            and i.status == ChallengeStatus.OPEN.value
        ),
        unanswered=sum(1 for i in items if i.status == ChallengeStatus.OPEN.value),
        without_evidence=sum(1 for i in items if not i.evidence.strip()),
        # « Au moins une prémisse importante est testée » (brief §15). Testée veut dire
        # qu'on y a répondu, pas seulement qu'on l'a écrite.
        premise_tested=any(
            i.kind == ChallengeKind.PREMISE.value
            and i.status != ChallengeStatus.OPEN.value
            and i.response.strip()
            for i in items
        ),
        voices_present=voices,
    )


def group_by_voice(
    challenges: Sequence[ChallengeInput],
) -> Dict[str, List[ChallengeInput]]:
    """Objections regroupées par voix, dans l'ordre d'affichage du domaine."""
    grouped: Dict[str, List[ChallengeInput]] = {v: [] for v in CHALLENGE_VOICE_ORDER}
    for item in challenges:
        grouped.setdefault(item.voice, []).append(item)
    return grouped
