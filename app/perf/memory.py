"""Ce qui fait survivre un sujet d'une lecture à l'autre.

Le registre de `app.domain.issues` tient les règles ; il vit en mémoire, et un processus
qui s'arrête les emporte avec lui. Ce module est la seule chose qui sépare « le cockpit
sait qu'il connaît déjà ce marché » de « le cockpit le redécouvre chaque lundi ». Le brief
V6.1 appelle la seconde une amnésie hebdomadaire, et c'est le mot juste : sans persistance,
tout le travail d'identité produit une mémoire qui dure le temps d'une commande.

Deux choix méritent d'être dits, parce que l'inverse était plus court.

**Les règles ne descendent pas ici.** Le domaine décide ce qui rejoint un sujet et ce qui
en ouvre un ; ce module traduit, et rien de plus. On aurait pu interroger la base pour
trouver le sujet qui porte une clé — une requête au lieu d'une boucle. Mais la règle aurait
alors existé à deux endroits, en SQL et en Python, et le jour où l'une change sans l'autre,
c'est le doublon qui revient sans qu'aucun test ne tombe.

**Ce qui est écrit remplace, ce qui n'est pas écrit n'est pas touché.** `save` reprend les
sujets connus par leur référence plutôt que de vider la table : une référence citée dans un
compte rendu doit désigner le même sujet la semaine suivante, et un identifiant réattribué
transforme une trace en énigme.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import issues as domain
from ..models import IssueEvidence, IssueReading, ManagementIssue

#: Le séparateur des clés dans `covers`. Le saut de ligne plutôt que la virgule : un
#: périmètre peut porter une virgule dans son nom, et une clé coupée en deux rattacherait
#: des preuves à un sujet qui ne les attend pas.
SEPARATOR = "\n"
#: Ce qui sépare le type du périmètre à l'intérieur d'une clé. Le caractère est choisi pour
#: n'apparaître dans aucun libellé de marché ni dans aucun code d'entité.
JOIN = ""


def _pack(covers: Sequence) -> str:
    return SEPARATOR.join(JOIN.join((kind, scope)) for kind, scope in covers)


def _unpack(text: str) -> List:
    keys = []
    for line in (text or "").split(SEPARATOR):
        if not line:
            continue
        kind, _sep, scope = line.partition(JOIN)
        keys.append((kind, scope))
    return keys


def _amount(text: str) -> Optional[float]:
    """Le montant tel que la base le garde — une chaîne — rendu au domaine.

    Illisible vaut absent, jamais zéro : un montant qu'on ne sait pas lire compté pour rien
    ferait d'un sujet matériel un sujet sans enjeu, ce qui le sortirait de toute sélection
    sans que rien ne le dise.
    """
    value = (text or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def to_domain(row: "ManagementIssue") -> "domain.Issue":
    """Une ligne et ses enfants, rendus comme le sujet que le domaine manipule."""
    issue = domain.Issue(
        issue_id=row.reference,
        title=row.title,
        covers=_unpack(row.covers),
        status=row.status,
        role=row.role,
        role_set=row.role_set,
        accountable=row.accountable,
        trend=row.trend,
        progress=row.progress,
        confidence=row.confidence,
        follows=row.follows,
        merged_into=row.merged_into,
        closed_reason=row.closed_reason,
    )
    issue.evidence = [
        domain.Observation(
            kind=item.kind, scope=item.scope, seen_at=item.seen_at,
            statement=item.statement, amount=_amount(item.amount),
            basis=item.basis, confidence=item.confidence, measure=item.measure,
        )
        for item in row.evidence
    ]
    issue.readings = [
        domain.Reading(conclusion=item.conclusion, at=item.at, because=item.because)
        for item in row.readings
    ]
    if row.arbitrated_by:
        issue.arbitration = domain.Arbitration(
            decided_by=row.arbitrated_by, at=row.arbitrated_at,
            reason=row.arbitration_reason, review_on=row.review_on,
        )
    return issue


def load(session: Session) -> "domain.Register":
    """Tous les sujets connus, dans l'ordre où ils ont été ouverts.

    L'ordre compte : `Register` attribue la référence suivante à partir de la plus grande
    déjà émise, et une liste mélangée donnerait le même résultat mais rendrait toute
    lecture d'écran instable d'un chargement à l'autre.
    """
    rows = session.scalars(
        select(ManagementIssue).order_by(ManagementIssue.reference)
    ).all()
    return domain.Register([to_domain(row) for row in rows])


def save(session: Session, register: "domain.Register") -> int:
    """Écrire le registre. Les sujets connus sont repris, les nouveaux insérés.

    Les preuves et les lectures sont réécrites en entier plutôt que rapprochées une à une.
    Ce sont des collections en ajout seul, courtes, et toujours lues avec leur sujet : un
    rapprochement fin coûterait une clé naturelle sur chaque preuve — donc une décision sur
    ce qui rend deux preuves identiques — pour économiser quelques écritures. La clé
    naturelle serait le vrai risque : deux mesures du même jour sur le même périmètre
    existent, et l'une écraserait l'autre.

    Rend le nombre de sujets écrits.
    """
    known: Dict[str, ManagementIssue] = {
        row.reference: row
        for row in session.scalars(select(ManagementIssue)).all()
    }

    for issue in register.issues:
        row = known.get(issue.issue_id)
        if row is None:
            row = ManagementIssue(reference=issue.issue_id)
            session.add(row)
        row.title = issue.title
        row.covers = _pack(issue.covers)
        row.status = issue.status
        row.role = issue.role
        row.role_set = issue.role_set
        row.accountable = issue.accountable
        row.trend = issue.trend
        row.progress = issue.progress
        row.confidence = issue.confidence
        row.follows = issue.follows
        row.merged_into = issue.merged_into
        row.closed_reason = issue.closed_reason

        arbitration = issue.arbitration
        row.arbitrated_by = arbitration.decided_by if arbitration else ""
        row.arbitrated_at = arbitration.at if arbitration else ""
        row.arbitration_reason = arbitration.reason if arbitration else ""
        row.review_on = arbitration.review_on if arbitration else None

        row.evidence[:] = [
            IssueEvidence(
                position=index, kind=item.kind, scope=item.scope, seen_at=item.seen_at,
                statement=item.statement,
                amount="" if item.amount is None else repr(item.amount),
                basis=item.basis, confidence=item.confidence, measure=item.measure,
            )
            for index, item in enumerate(issue.evidence)
        ]
        row.readings[:] = [
            IssueReading(position=index, conclusion=item.conclusion, at=item.at,
                         because=item.because)
            for index, item in enumerate(issue.readings)
        ]

    session.flush()
    return len(register.issues)
