"""The only module that knows where performance numbers come from.

Brief §35 Phase 6 asks for a clean seam between the data source and everything above it,
so that a warehouse can replace mock data without rewriting the application. That seam is
this file: the analytics engine, the routes and the templates never import `mock`.

When real data arrives, add a source that returns the same normalised `Dataset` and change
`current_source()`. Nothing above this line should need to move.
"""

from __future__ import annotations

from typing import List

from . import mock
from .model import Dataset


class MockSource:
    """Invented data, clearly labelled as such everywhere it is shown."""

    name = "mock"
    label = "Mock data"
    #: Shown in the interface. A cockpit that looks authoritative while running on
    #: invented numbers is worse than no cockpit at all.
    caveat = (
        "Every figure on this screen is invented for demonstration. No real market, "
        "person or product appears here."
    )

    def dataset(self) -> Dataset:
        return mock.dataset()

    def commitments(self) -> List["mock.MockCommitment"]:
        return mock.commitments()


def current_source() -> MockSource:
    """The active source. One line to change when the warehouse is connected."""
    return MockSource()
