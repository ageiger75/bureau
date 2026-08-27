"""Screen 1 — TODAY.

The primary screen. A CEO should understand the state of the business in about two
minutes (brief §7), which is a constraint on what may appear here, not a wish.

The route computes nothing itself: it asks the analytics engine and hands the result to
the template. Any arithmetic written here would eventually disagree with the same
arithmetic on the Investigate screen.
"""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Request

from ..perf import analytics
from ..perf import kpi as kpi_rules
from ..perf import provenance
from ..perf.commitments import board
from ..perf.source import current_source
from ..web import render

router = APIRouter()


def _commitments_by_market(items) -> Dict[str, List]:
    grouped: Dict[str, List] = {}
    for item in items:
        grouped.setdefault(item.market, []).append(item)
    return grouped


def settled_now() -> List[str]:
    """Measures this instance has actually resolved, whatever the register says.

    The register describes the design. Whether the directory file is on this machine is a
    fact about this machine, and the screen should not ask the CEO to chase something he
    has already provided.
    """
    from ..perf import owners

    return ["owners"] if len(owners.current()) else []


@router.get("/")
def today(request: Request):
    source = current_source()
    # `?refresh=1` forces a fresh read. Not a button, deliberately: a CEO who can make the
    # screen wait three minutes with one click will do it by reflex and learn that the
    # cockpit is slow. Whoever needs it knows to type it.
    refresh = request.query_params.get("refresh") in ("1", "true", "yes")
    try:
        dataset = source.dataset(refresh=refresh)
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

    fires = analytics.fires(dataset)
    suspects = analytics.suspects(dataset)
    by_market = _commitments_by_market(commitments.items)

    # A fire is worth more with two things attached: the promise already made about it,
    # and what the customer base is doing. A conversion gap with recruitment holding up is
    # a different conversation from one where both are falling.
    linked = []
    for fire in fires:
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
        linked.append((fire, open_items[0] if open_items else None, signals))

    return render(
        request,
        "today.html",
        {
            "user": None,
            "source": source,
            "dataset": dataset,
            "header": {
                "actual": dataset.sales_actual,
                "budget": dataset.sales_budget,
                "last_year": dataset.sales_last_year,
                "forecast": dataset.sales_forecast,
                "vs_budget": analytics.variance(dataset.sales_actual, dataset.sales_budget),
                "vs_last_year": analytics.variance(
                    dataset.sales_actual, dataset.sales_last_year
                ),
            },
            "fires": linked,
            "opportunities": analytics.opportunities(dataset),
            "people": analytics.people_to_push(fires),
            "wins": analytics.wins(dataset),
            "commitments": commitments,
            "kpis": kpi_rules.needing_attention(kpis),
            "kpis_awaiting": kpi_rules.awaiting(kpis),
            "kpis_provisional": kpi_rules.provisional(kpis),
            "suspects": suspects,
            "suspect_patterns": analytics.patterns(suspects),
            "kpi_rules": kpi_rules,
            "unavailable": unavailable,
            "unsettled": provenance.unsettled(settled=settled_now()),
            "perimeter_note": getattr(source, "perimeter_note", ""),
            "conflicts": getattr(source, "conflicts", []),
            "markets_without_owner": getattr(source, "markets_without_owner", []),
        },
    )
