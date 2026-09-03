"""Les deux gestes humains sur un sujet de management.

Le registre sait déjà tout retenir ; ce qui manquait, c'est de pouvoir arbitrer sans passer
par un terminal. Le lecteur de ce cockpit n'écrit pas de code, et lui demander de composer
une ligne de commande pour dire « j'accepte cet écart » revient à ne pas lui offrir le
geste du tout.

Deux gestes seulement, et ce sont exactement ceux que la doctrine réserve à un humain.

**Accepter un écart** est une décision de ne rien faire, et elle doit se voir : sans elle,
le sujet reviendrait chaque lundi, le lecteur le réarbitrerait, et il cesserait de lire.
Le sujet dort ensuite jusqu'à un fait postérieur à la décision ou jusqu'à sa date de
réexamen — jamais avant, jamais sur une preuve antérieure, qui est ce sur quoi la décision
a été prise.

**Clore** n'est jamais prononcé par la machine (§C9). Elle sait constater qu'un chiffre est
revenu dans sa zone, ce qui est réversible et s'appelle une normalisation. Elle ne sait pas
dire qu'une cause est comprise et qu'une action a produit un résultat.

Ce que ce module n'offre pas, délibérément : rouvrir. Un sujet clos qui reçoit un fait
nouveau ouvre un **autre** sujet, qui déclare celui qu'il suit. Offrir un bouton
« rouvrir » effacerait la clôture, son motif et sa dernière preuve — et surtout ferait
d'une rechute une découverte, alors que la répétition est précisément ce que ce registre
existe pour rendre calculable.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain import issues as domain
from ..forms import parse_closure, parse_variance
from ..perf import memory
from ..web import flash, redirect

router = APIRouter()


def _named(register, reference: str):
    """Le sujet visé, par sa référence ou par une clé d'observation qu'il couvre.

    Les deux formes, comme en ligne de commande et pour la même raison : une référence est
    attribuée par machine et ne désigne pas le même sujet sur deux postes, une clé désigne
    la même chose partout.
    """
    found = register.of(reference)
    if found is not None:
        return found
    kind, separator, scope = reference.partition(":")
    if not separator:
        return None
    return register.holding((kind.strip(), scope.strip()))


@router.post("/issues/{reference}/accept")
async def accept_variance(
    request: Request,
    reference: str,
    session: Session = Depends(get_session),
):
    register = memory.load(session)
    issue = _named(register, reference)
    if issue is None:
        flash(request, "Aucun sujet %s." % reference, "error")
        return redirect("/")

    result = parse_variance(await request.form())
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect("/")

    try:
        issue.accept_variance(domain.Arbitration(
            decided_by=result.values["decided_by"],
            at=result.values["at"] or date.today().isoformat(),
            reason=result.values["reason"],
            review_on=result.values["review_on"],
        ))
    except (ValueError, domain.TransitionRefused) as refused:
        flash(request, str(refused), "error")
        return redirect("/")

    memory.save(session, register)
    session.commit()
    review = result.values["review_on"]
    flash(request, "%s dort : il ne remontera que sur un fait nouveau%s."
          % (issue.issue_id, " ou le %s" % review if review else ""), "success")
    return redirect("/")


@router.post("/issues/{reference}/close")
async def close_issue(
    request: Request,
    reference: str,
    session: Session = Depends(get_session),
):
    register = memory.load(session)
    issue = _named(register, reference)
    if issue is None:
        flash(request, "Aucun sujet %s." % reference, "error")
        return redirect("/")

    result = parse_closure(await request.form())
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect("/")

    try:
        issue.close(by=result.values["closed_by"], reason=result.values["reason"])
    except (domain.ClosureRefused, domain.TransitionRefused) as refused:
        flash(request, str(refused), "error")
        return redirect("/")

    memory.save(session, register)
    session.commit()
    flash(request, "%s est clos. Un fait nouveau ouvrira un autre sujet, qui déclarera "
                   "celui-ci." % issue.issue_id, "success")
    return redirect("/")
