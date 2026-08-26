"""Commitment intelligence for the cockpit (brief §18).

The alert levels, the overdue rule and the summary come from `app/domain/commitments.py`,
written for Decision Room and reused unchanged: an engagement without an owner or a date
is the same management failure whichever screen records it.

What is added here is what the cockpit needs and Decision Room never had — the comparison
between the impact an action was expected to produce and the one it actually produced.
"""

from __future__ import annotations

from typing import List, Sequence

from ..domain import commitments as rules


class CommitmentBoard:
    """Everything the Today screen and the Commitments screen read."""

    __slots__ = ("items", "summary", "at_risk")

    def __init__(self, items: Sequence) -> None:
        self.items = list(items)
        self.summary = rules.summarize(
            [(item.as_input(), item.days_left) for item in self.items]
        )
        # "At risk" is not a stored status: it is a reading of the situation — blocked, or
        # falling due within the week and not yet done.
        self.at_risk = [
            item
            for item in self.items
            if not rules.is_closed(item.status)
            and (
                item.status == "blocked"
                or rules.alert_level(item.status, item.days_left) == rules.DUE_SOON
            )
        ]

    @property
    def open_count(self) -> int:
        return self.summary.open_count

    @property
    def overdue(self) -> List:
        return [
            item
            for item in self.items
            if rules.alert_level(item.status, item.days_left) == rules.OVERDUE
        ]

    @property
    def repeatedly_delayed(self) -> List:
        """Postponed more than once. The second delay is the signal, not the first."""
        return [item for item in self.items if item.postponements >= 2]

    @property
    def without_expected_impact(self) -> List:
        """An action nobody sized cannot be judged, only remembered."""
        return [
            item
            for item in self.items
            if not rules.is_closed(item.status) and not item.expected_impact.strip()
        ]

    @property
    def done_without_result(self) -> List:
        """Delivered, and it did not work.

        The most easily lost fact in any management loop: the action was completed, the
        box was ticked, and the problem is still there.
        """
        return [
            item
            for item in self.items
            if item.status == "done"
            and item.expected_impact.strip()
            and _looks_negative(item.actual_impact)
        ]

    @property
    def delivered_results(self) -> List:
        """Delivered, and it worked. Worth as much as the failures, for the opposite reason."""
        return [
            item
            for item in self.items
            if item.status == "done"
            and item.expected_impact.strip()
            and item.actual_impact.strip()
            and not _looks_negative(item.actual_impact)
        ]


def _looks_negative(actual_impact: str) -> bool:
    """Whether a stated outcome reports an absence of result.

    Deliberately literal. V1 stores the observed impact as text, so the honest test is
    whether someone wrote that nothing happened — not an inference dressed up as one.
    """
    text = actual_impact.strip().lower()
    if not text:
        return False
    return any(
        marker in text
        for marker in ("no measurable", "no uplift", "no change", "unchanged", "none")
    )


def board(items: Sequence) -> CommitmentBoard:
    return CommitmentBoard(items)
