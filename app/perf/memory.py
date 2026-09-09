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

**Ce qui n'a pas changé n'est pas réécrit, et ce qui est réécrit l'est par sujet.** La
première version réécrivait les preuves et les lectures de chaque sujet à chaque écriture,
en supprimant les anciennes lignes par leur identifiant. Deux requêtes qui se chevauchent —
l'écran du jour et sa vérification de fraîcheur, un onglet rouvert avant que le premier ait
fini — écrivaient donc chacune leur copie : la seconde ne trouvait plus les lignes qu'elle
voulait supprimer (l'entrepôt de la première les avait déjà remplacées) et insérait quand
même les siennes. Les preuves doublaient à chaque chevauchement ; en quelques semaines, un
registre de trois cents lignes en portait cent vingt-huit mille, chaque écran les relisait,
et « ce qui a changé » citait vingt fois la même lecture. Trois gardes maintenant : une
écriture ne touche pas un sujet dont les preuves et les lectures sont déjà celles de la
base ; quand elle le touche, elle supprime les lignes **du sujet** et non des identifiants
lus plus tôt, de sorte que deux écritures concurrentes laissent une copie et non deux ; et
la lecture écarte les doublons qu'une base déjà abîmée porterait encore, puis les efface.
"""

from __future__ import annotations

import threading
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from ..domain import issues as domain
from ..models import IssueEvidence, IssueReading, ManagementIssue

#: Le séparateur des clés dans `covers`. Le saut de ligne plutôt que la virgule : un
#: périmètre peut porter une virgule dans son nom, et une clé coupée en deux rattacherait
#: des preuves à un sujet qui ne les attend pas.
SEPARATOR = "\n"
#: Ce qui sépare le type du périmètre à l'intérieur d'une clé. Le caractère est choisi pour
#: n'apparaître dans aucun libellé de marché ni dans aucun code d'entité.
JOIN = ""


#: Une seule écriture du registre à la fois dans un processus. Le serveur sert ses
#: requêtes depuis un pool de fils, et deux écrans ouverts à une seconde d'écart écrivaient
#: le même registre en même temps. Le verrou ne protège pas de deux processus ; la
#: suppression par sujet (voir `save`) s'en charge.
_WRITE = threading.Lock()

#: Par lots : SQLite borne le nombre de paramètres d'une requête, et une base abîmée peut
#: avoir des dizaines de milliers de lignes à effacer.
_BATCH = 500


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


def _evidence_key(item) -> tuple:
    """Ce qui rend deux lignes de preuve identiques : tout ce qu'elles portent.

    Ce n'est **pas** une clé naturelle au sens du domaine — deux mesures du même jour sur
    le même périmètre restent deux preuves si leur phrase ou leur montant diffère. Seule
    la ligne recopiée à l'identique est un doublon.
    """
    return (item.kind, item.scope, item.seen_at, item.statement, item.amount,
            item.basis, item.confidence, item.measure)


def _reading_key(item) -> tuple:
    return (item.conclusion, item.at, item.because)


def _unique(rows: Iterable, key) -> Tuple[list, list]:
    """Les lignes sans doublon dans l'ordre lu, et les identifiants des doublons."""
    kept, seen, extra = [], set(), []
    for item in rows:
        mark = key(item)
        if mark in seen:
            extra.append(item.id)
            continue
        seen.add(mark)
        kept.append(item)
    return kept, extra


def to_domain(row: "ManagementIssue") -> "domain.Issue":
    """Une ligne et ses enfants, rendus comme le sujet que le domaine manipule.

    Les lignes recopiées à l'identique sont lues une fois. Voir `load` pour ce qu'il
    advient des copies.
    """
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
        opened_at=row.created_at or "",
        updated_at=row.updated_at or "",
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
        for item in _unique(row.evidence, _evidence_key)[0]
    ]
    issue.readings = [
        domain.Reading(conclusion=item.conclusion, at=item.at, because=item.because)
        for item in _unique(row.readings, _reading_key)[0]
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

    Les preuves et les lectures viennent avec leurs sujets en deux requêtes, pas en deux
    par sujet : cent sujets valaient deux cents allers-retours à chaque écran.

    Une base qui porte encore des copies (voir l'en-tête du module) est réparée au
    passage : les doublons sont écartés de la lecture et effacés, et la transaction que
    l'appelant referme les emporte. Une lecture qui répare n'est pas une lecture qui
    décide — rien du domaine n'est écrit ici, seules des lignes identiques à celles
    qu'on garde disparaissent.
    """
    rows = session.scalars(
        select(ManagementIssue)
        .options(selectinload(ManagementIssue.evidence),
                 selectinload(ManagementIssue.readings))
        .order_by(ManagementIssue.reference)
    ).all()
    register = domain.Register([to_domain(row) for row in rows])
    mend(session, rows)
    return register


def duplicates(rows: Sequence["ManagementIssue"]) -> Tuple[List[str], List[str]]:
    """Les identifiants des preuves et des lectures recopiées à l'identique."""
    evidence: List[str] = []
    readings: List[str] = []
    for row in rows:
        evidence.extend(_unique(row.evidence, _evidence_key)[1])
        readings.extend(_unique(row.readings, _reading_key)[1])
    return evidence, readings


def _erase(session: Session, model, ids: Sequence[str]) -> None:
    for start in range(0, len(ids), _BATCH):
        session.execute(
            delete(model).where(model.id.in_(ids[start:start + _BATCH]))
            .execution_options(synchronize_session="fetch"))


def mend(session: Session, rows: Optional[Sequence["ManagementIssue"]] = None) -> int:
    """Effacer les copies. Rend le nombre de lignes effacées ; zéro sur une base saine."""
    if rows is None:
        rows = session.scalars(
            select(ManagementIssue)
            .options(selectinload(ManagementIssue.evidence),
                     selectinload(ManagementIssue.readings))
        ).all()
    evidence, readings = duplicates(rows)
    if not evidence and not readings:
        return 0
    _erase(session, IssueEvidence, evidence)
    _erase(session, IssueReading, readings)
    for row in rows:
        session.expire(row, ["evidence", "readings"])
    session.flush()
    return len(evidence) + len(readings)


def _wanted_evidence(issue) -> List[tuple]:
    return [(item.kind, item.scope, item.seen_at, item.statement,
             "" if item.amount is None else repr(item.amount),
             item.basis, item.confidence, item.measure)
            for item in issue.evidence]


def _wanted_readings(issue) -> List[tuple]:
    return [(item.conclusion, item.at, item.because) for item in issue.readings]


def save(session: Session, register: "domain.Register") -> int:
    """Écrire le registre. Les sujets connus sont repris, les nouveaux insérés.

    Les preuves et les lectures d'un sujet sont réécrites en entier — mais seulement quand
    elles diffèrent de ce que la base porte, et en effaçant celles **du sujet** plutôt que
    des lignes lues plus tôt. Un rapprochement fin coûterait une clé naturelle sur chaque
    preuve — donc une décision sur ce qui rend deux preuves identiques — pour économiser
    quelques écritures. La clé naturelle serait le vrai risque : deux mesures du même jour
    sur le même périmètre existent, et l'une écraserait l'autre.

    Rend le nombre de sujets écrits.
    """
    with _WRITE:
        return _save(session, register)


def _save(session: Session, register: "domain.Register") -> int:
    known: Dict[str, ManagementIssue] = {
        row.reference: row
        for row in session.scalars(
            select(ManagementIssue)
            .options(selectinload(ManagementIssue.evidence),
                     selectinload(ManagementIssue.readings))
        ).all()
    }

    rewrite = []
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

        evidence = _wanted_evidence(issue)
        readings = _wanted_readings(issue)
        if [_evidence_key(item) for item in row.evidence] != evidence:
            rewrite.append((row, IssueEvidence, "evidence", evidence))
        if [_reading_key(item) for item in row.readings] != readings:
            rewrite.append((row, IssueReading, "readings", readings))

    # Les sujets neufs reçoivent leur identifiant à cette écriture ; les enfants en ont
    # besoin, et l'effacement par sujet aussi.
    session.flush()

    for row, model, name, wanted in rewrite:
        session.execute(
            delete(model).where(model.issue_id == row.id)
            .execution_options(synchronize_session="fetch"))
        session.expire(row, [name])
        if model is IssueEvidence:
            session.add_all([
                IssueEvidence(
                    issue_id=row.id, position=index, kind=kind, scope=scope,
                    seen_at=seen_at, statement=statement, amount=amount, basis=basis,
                    confidence=confidence, measure=measure)
                for index, (kind, scope, seen_at, statement, amount, basis, confidence,
                            measure) in enumerate(wanted)
            ])
        else:
            session.add_all([
                IssueReading(issue_id=row.id, position=index, conclusion=conclusion,
                             at=at, because=because)
                for index, (conclusion, at, because) in enumerate(wanted)
            ])

    session.flush()
    for row, _model, name, _wanted in rewrite:
        session.expire(row, [name])
    return len(register.issues)
