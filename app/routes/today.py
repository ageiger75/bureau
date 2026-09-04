"""Screen 1 — TODAY.

The primary screen. A CEO should understand the state of the business in about two
minutes (brief §7), which is a constraint on what may appear here, not a wish.

The route computes nothing itself: it asks the analytics engine and hands the result to
the template. Any arithmetic written here would eventually disagree with the same
arithmetic on the Investigate screen.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..perf import analytics, routing
from ..perf import kpi as kpi_rules
from ..perf import provenance
from ..perf import week as week_of
from ..perf.commitments import board
from ..perf.source import current_source
from ..web import render

router = APIRouter()


def _channels_shown(dataset) -> List:
    """One entry per channel present, name and meaning, in alphabetical order."""
    seen = {}
    for unit in dataset.units:
        if unit.channel_meaning:
            seen[unit.channel_label] = unit.channel_meaning
    return sorted(seen.items())


def _commitments_by_market(items) -> Dict[str, List]:
    grouped: Dict[str, List] = {}
    for item in items:
        grouped.setdefault(item.market, []).append(item)
    return grouped


def settled_now(unavailable: Sequence[str] = ()) -> List[str]:
    """Measures this instance has actually resolved, whatever the register says.

    The register describes the design; what this machine has in hand is a different
    question, and the screen must not ask the CEO to chase something already in front of
    him. It did: the commitments panel listed ten open items while the panel below it
    announced that no commitment source was connected. Two halves of one screen
    contradicting each other costs more than either half is worth.
    """
    from ..perf import owners

    settled = []
    if len(owners.current()):
        settled.append("owners")
    if "commitments" not in unavailable:
        settled.append("commitments")
    if "kpis" not in unavailable:
        settled.append("client_kpis")
    return settled


def _month_review(source):
    """Où en est le mois, ou pourquoi on ne peut pas le dire.

    Jamais une page qui tombe : sans requête écrite ou sans plan, le panneau dit ce qui
    manque. Et jamais une page qui attend — la lecture est bornée au mois, la forme des
    mois et l'organigramme sont des fichiers locaux.
    """
    from ..config import settings
    from ..perf import month as month_module
    from ..perf import pace as pace_module
    from ..perf import perimeter as perimeter_module

    try:
        rows = source.month_to_date()
    except NotImplementedError as why:
        return month_module.Review("", 0, "", [], [], [str(why)])
    except Exception as why:  # pragma: no cover — l'entrepôt, pas le code
        return month_module.Review("", 0, "", [], [],
                                   ["lecture du mois en cours impossible : %s" % why])
    days = sorted(str(row.get("read_through") or "")[:7] for row in rows)
    period = days[-1] if days and days[-1] else ""
    try:
        targets = source.month_targets(period) if period else {}
    except NotImplementedError as why:
        targets = {}
    phasing = pace_module.current() if settings.has_phasing_file else None
    org = perimeter_module.current() if settings.has_org_file else None
    return month_module.build(rows, targets, phasing, org)


@router.get("/freshness")
def freshness():
    """When the figures in memory were read. Polled by the page, never by a person.

    The screen opens on the last read and a fresh one lands behind it minutes later. Until
    now the only sign of that was a line in the server window, so the instruction was
    "watch the log and reload" — which is a developer's habit handed to a reader, and it
    was not followed because it should not have to be. The page now watches for itself.
    """
    from ..perf import source

    return {"as_of": source.last_read()}


@router.get("/")
def today(request: Request, session: Session = Depends(get_session)):
    source = current_source()
    # `?refresh=1` forces a fresh read. Not a button, deliberately: a CEO who can make the
    # screen wait three minutes with one click will do it by reflex and learn that the
    # cockpit is slow. Whoever needs it knows to type it.
    refresh = request.query_params.get("refresh") in ("1", "true", "yes")
    try:
        # Nobody waits three minutes for a screen. Without an explicit refresh the page
        # serves what is on disk, however old, and says how old — the age is printed
        # beside the figures, so a stale reading is a stated one rather than a hidden one.
        dataset = source.dataset(refresh=refresh, wait_for_warehouse=refresh)
    except NotImplementedError as incomplete:
        # Pointing at a warehouse whose queries are not written yet is a normal state
        # during connection, not a crash. Say what is missing and how to get back to
        # mock data — a stack trace would say neither.
        from ..perf import queries

        return render(
            request,
            "source_incomplete.html",
            {
                "user": None,
                "source": source,
                "detail": str(incomplete),
                "missing": queries.missing(),
            },
            status_code=503,
        )

    # Performance is the screen. Commitments and customer KPIs enrich it, and they connect
    # on their own schedule — so a missing one dims its own panel instead of taking the
    # page down. What it must not do is render an empty board: "no overdue commitments"
    # and "not connected to commitments" look the same and mean opposite things.
    unavailable = []
    try:
        commitments = board(source.commitments())
    except NotImplementedError:
        commitments = board([])
        unavailable.append("commitments")
    try:
        kpis = source.client_kpis()
    except NotImplementedError:
        kpis = []
        unavailable.append("kpis")
    # Not in `unavailable`: nothing here dims when it is empty. Empty means the two bases
    # agree everywhere, which is a good state and not a missing panel.
    bulk_findings = getattr(source, "bulk_findings", list)()
    month = _month_review(source)

    fires = analytics.fires(dataset)
    # The subjects, which is what the reader ends up with: a market losing ground in two
    # channels is one conversation with one person, and the screen used to make it two.
    issues = analytics.issues(dataset)
    # Routed out of the week's five, not out of the screen. Each is real money whose
    # question belongs to consolidation, to finance or to the data team — and a reader who
    # simply stopped seeing them would have no way to tell a routed item from a lost one.
    elsewhere = analytics.routed_elsewhere(dataset)
    # Two lists, never one. A plan above everything the record shows will be missed every
    # month and the misses are not news; a plan below what the business is already doing
    # is a forecast to redo. Mixed, they cancel out — fourteen lines and no way to tell
    # which half is which.
    plans_above = routing.plan_reviews(dataset, above=True)
    plans_below = routing.plan_reviews(dataset, above=False)
    suspects = analytics.suspects(dataset)
    by_market = _commitments_by_market(commitments.items)

    # A fire is worth more with two things attached: the promise already made about it,
    # and what the customer base is doing. A conversion gap with recruitment holding up is
    # a different conversation from one where both are falling.
    def attach(fire):
        open_items = [
            item
            for item in by_market.get(fire.unit.market, [])
            if item.status not in ("done", "cancelled")
        ]
        signals = [
            item
            for item in kpi_rules.by_scope(kpis, fire.unit.market)
            if item.status in (kpi_rules.WATCH, kpi_rules.ALERT)
        ]
        return (fire, open_items[0] if open_items else None, signals)

    for issue in issues:
        issue.has_commitment = any(
            item.status not in ("done", "cancelled")
            for item in by_market.get(issue.market, [])
        )
    linked = [(issue, [attach(fire) for fire in issue.fires]) for issue in issues]

    # The register, which is the only thing on this page that remembers. Everything above
    # is recomputed from the current reading and would present the same three markets as
    # discoveries every Monday — the weekly amnesia the doctrine forbids. The subjects
    # below carry their own identity, their arbitrations and the readings already made of
    # them, and they are ranked by an engine with hard caps rather than by size.
    #
    # The dataset is handed over rather than re-read: a second read would cost another
    # warehouse query and, worse, could land on a different hour and therefore different
    # figures than the ones printed above it.
    # `placing` : un sujet rendu dans un créneau d'attention **est** en attention, et son
    # état doit le dire — sinon il reste « détecté » à vie et le lecteur ne peut plus le
    # clore. C'est cet écran qui place, parce que c'est lui qui montre vraiment la semaine ;
    # une inspection en terminal ne déplace rien.
    week, scan = week_of.read(session, dataset=dataset, placing=True)
    # La transaction se referme ici et pas dans le module de lecture : la politique de
    # validation appartient à la surface, pas au domaine. Sans ce commit, la session ouverte
    # par la dépendance se ferme sans écrire, et le registre paraissait sans mémoire alors
    # qu'il l'avait — un état porté redevenait « détecté » au rechargement suivant.
    session.commit()

    return render(
        request,
        "today.html",
        {
            "user": None,
            "source": source,
            "dataset": dataset,
            # Handed to the page so it can tell a fresh read from the one it is showing.
            "read_at": getattr(dataset, "as_of", ""),
            # The top figure comes from the published file whole where there is one, and
            # from the readable units otherwise. The cards below are unchanged: the gap
            # comes from the consolidation, the explanation from the warehouse.
            "header": {
                "actual": dataset.headline_actual,
                "budget": dataset.headline_budget,
                "last_year": dataset.headline_last_year,
                "forecast": dataset.sales_forecast,
                "published": dataset.headline_is_published,
                "vs_budget": analytics.variance(
                    dataset.headline_actual, dataset.headline_budget
                ),
                "vs_last_year": analytics.variance(
                    dataset.headline_actual, dataset.headline_last_year
                ),
            },
            "issues": linked,
            # Three slots, five under watch, and the rest counted in an annex. The caps
            # are hard on both sides: a screen that renders everything it found hands the
            # selection back to the reader, which is the work they came for.
            "week": week,
            "month": month,
            "week_sources": scan.sources,
            # The channels actually on this screen, each with what it is. A reader who
            # has to guess whether "E-retailers" means Tmall or Amazon cannot judge the
            # number under it — and the guess is usually wrong, since the platform most
            # people picture sits under a third name again.
            "channels_shown": _channels_shown(dataset),
            "fires": [attach(fire) for fire in fires],
            "opportunities": analytics.opportunities(dataset),
            "reallocations": analytics.reallocations(dataset),
            # Fed from the subjects: the top of each one, so a market that lost ground
            # in two channels puts its lead on this list once, for the larger of the two,
            # rather than competing with itself for a place.
            "people": analytics.people_to_push([issue.fires[0] for issue in issues]),
            "wins": analytics.wins(dataset),
            "commitments": commitments,
            # One list, one line per KPI. Off target, overdue, or both — the card carries
            # whichever apply, instead of the KPI appearing here for one and again below
            # for the other, as if it were two problems.
            "kpis": kpi_rules.worth_showing(kpis),
            # Grouped under the pillar the tracker files them under. The domain comes from
            # the tracker and nowhere else — never from the query that produced the figure,
            # which is what put recruitment, an advocacy score and a refill rate under one
            # heading called "Customers".
            "kpis_by_pillar": kpi_rules.by_pillar(kpi_rules.worth_showing(kpis)),
            #: The denominator. "Three KPIs are off target" and "three of seventeen" are
            #: different facts, and the panel shows only the three — so without this the
            #: reader cannot tell a business mostly holding from one mostly failing.
            # Recounted from the cards actually printed, never from the list they were
            # drawn out of. The two drifted apart the moment "shown" stopped meaning "off
            # target": a KPI held back for an unsettled definition is neither holding nor
            # failing, and counting it as holding while printing it as a problem is a
            # summary that contradicts the list beneath it.
            "kpis_total": len(kpis),
            "kpis_holding": len(kpis) - len(kpi_rules.worth_showing(kpis)),
            "kpis_provisional": kpi_rules.provisional(kpis),
            # Only the markets where taking the bulk out changes the verdict. Bulk is
            # real turnover and it belongs in the accounts; it answers a different
            # question from the one this screen asks, and in two markets it is large
            # enough to answer it wrongly — a sixth of Hong Kong moves in orders, not in
            # shoppers. Where the two bases agree, nothing appears.
            "bulk_findings": bulk_findings,
            "reclassifications": analytics.reclassification_checks(dataset),
            "elsewhere": elsewhere,
            "plans_above": plans_above,
            "plans_below": plans_below,
            # One incident, one diagnosis. The panel used to state the shape and then
            # list markets underneath, each repeating a fix for the same fault — two
            # accounts of one fact, and the second undoes the first.
            "incidents": analytics.incidents(suspects),
            "kpi_rules": kpi_rules,
            "unavailable": unavailable,
            "unsettled": provenance.unsettled(settled=settled_now(unavailable)),
            "perimeter_note": getattr(source, "perimeter_note", ""),
            "markets_without_own_site": dataset.markets_without_own_site,
            "conflicts": getattr(source, "conflicts", []),
            "markets_without_owner": getattr(source, "markets_without_owner", []),
        },
    )
