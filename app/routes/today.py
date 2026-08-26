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
from ..perf.commitments import board
from ..perf.source import current_source
from ..web import render

router = APIRouter()


def _commitments_by_market(items) -> Dict[str, List]:
    grouped: Dict[str, List] = {}
    for item in items:
        grouped.setdefault(item.market, []).append(item)
    return grouped


@router.get("/")
def today(request: Request):
    source = current_source()
    dataset = source.dataset()
    commitments = board(source.commitments())

    fires = analytics.fires(dataset)
    by_market = _commitments_by_market(commitments.items)

    # A fire is worth more with the promise already made about it attached: the CEO then
    # asks about the plan rather than about the problem.
    linked = []
    for fire in fires:
        open_items = [
            item
            for item in by_market.get(fire.unit.market, [])
            if item.status not in ("done", "cancelled")
        ]
        linked.append((fire, open_items[0] if open_items else None))

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
        },
    )
