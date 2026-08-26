"""Who owns which market.

This does not exist in the warehouse, and should not: it is organisational knowledge, not
a measurement. It changes when people change roles, which no data pipeline will tell you.

Ten lines of maintenance buys the difference between "Japan E-commerce is €1.2m below
plan" and "ask Naoki about Japan this week" — which is the whole point of the screen.

A market absent from this table still appears everywhere else. It is simply left out of
"People to push", and the screen says how many were left out rather than inventing a name.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from .model import Owner

#: market -> (name, role). Edit freely; nothing else needs to change.
OWNERS: Dict[str, Tuple[str, str]] = {
    # "Japan": ("Naoki", "Managing Director"),
    # "France": ("...", "Regional Director"),
    # "United States": ("...", "Managing Director"),
}


def owner_for(market: str) -> Owner:
    """The named owner of a market, or an unnamed placeholder.

    Never guesses. An owner invented from a region or a job title would put a real person
    in front of a question they do not own.
    """
    name, role = OWNERS.get(market, ("", ""))
    return Owner(name=name, role=role, market=market)


def is_named(owner: Optional[Owner]) -> bool:
    return bool(owner and owner.name.strip())


def unnamed_markets(markets) -> list:
    return sorted({market for market in markets if market not in OWNERS})
