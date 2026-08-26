"""Screen 1 — TODAY (brief §7 to §12, §34).

The success criterion of V1 is not that the page renders: it is that a CEO can answer
eight questions from it in about two minutes. These tests check that each of those answers
is actually on the screen, and that the things the brief forbids are not.
"""

from __future__ import annotations

from tests.conftest import page_text


def test_today_is_the_home_page(client):
    """The pivot in one assertion: opening the product lands on performance."""
    response = client.get("/")

    assert response.status_code == 200
    assert "Sales MTD" in page_text(response)


def test_decision_room_is_still_reachable(client):
    """Nothing was deleted. Decision Room simply no longer owns the front door."""
    assert client.get("/decisions").status_code == 200


# ------------------------------------------------------- the eight questions of §34


def test_where_the_business_is_underperforming(client):
    page = page_text(client.get("/"))

    assert "Where to push" in page
    assert "Japan E-commerce" in page


def test_why_it_is_underperforming(client):
    """A diagnosis, not a description (brief §3.2)."""
    page = page_text(client.get("/"))

    assert "of the gap comes from conversion" in page


def test_how_much_money_is_involved(client):
    page = page_text(client.get("/"))

    assert "-€1.2m" in page


def test_where_the_upside_is(client):
    page = page_text(client.get("/"))

    assert "Opportunities" in page
    assert "Assumes conversion returns to last year" in page


def test_who_to_challenge(client):
    page = page_text(client.get("/"))

    assert "People to push" in page
    assert "Naoki" in page


def test_what_to_ask_them(client):
    """The question is the product. Without it the screen is a report."""
    page = page_text(client.get("/"))

    assert "Why is the plan focused on sessions" in page


def test_what_people_committed_to(client):
    page = page_text(client.get("/"))

    assert "Ship the mobile checkout recovery plan" in page


def test_whether_those_actions_worked(client):
    """Brief §18: delivered, and it did not work — the most easily lost fact in the loop."""
    page = page_text(client.get("/"))

    assert "Done, no result" in page
    assert "Worked" in page


# --------------------------------------------------------------- honesty guarantees


def test_management_explanation_is_challenged_not_repeated(client):
    """Brief §3.5 and §20: quantify what the stated cause leaves unexplained."""
    page = page_text(client.get("/"))

    assert "Sales are down because the market is difficult." in page
    assert "remains unexplained" in page


def test_estimates_are_labelled_as_estimates(client):
    """Brief §3.3 and §32: never present an inferred relationship as a proven fact."""
    page = page_text(client.get("/"))

    assert "estimates" in page
    assert "not" in page and "measured causes" in page


def test_the_ranking_can_be_inspected(client):
    """Brief §31: opaque ranking costs the trust the whole product depends on."""
    page = page_text(client.get("/"))

    assert "Why am I seeing this?" in page
    assert "consecutive months below plan" in page
    assert "priority = € gap × persistence" in page


def test_confidence_is_shown_on_every_diagnosis(client):
    assert "Confidence HIGH" in page_text(client.get("/"))


def test_the_screen_says_the_data_is_invented(client):
    """A cockpit that looks authoritative on mock numbers is worse than none."""
    page = page_text(client.get("/"))

    assert "invented for demonstration" in page


def test_the_unbuilt_assistant_is_announced_not_faked(client):
    """A text box that appears to work and does not would cost more than an empty section."""
    page = page_text(client.get("/"))

    assert "Ask Performance CoS" in page
    assert "Not built yet" in page


def test_immaterial_markets_stay_off_the_screen(client):
    """Italy is in the dataset and below plan, and deliberately too small to be shown."""
    assert "Italy Retail" not in page_text(client.get("/"))


def test_aggregates_are_never_presented_as_something_to_push(client):
    page = page_text(client.get("/"))

    assert "Rest of World" not in page


def test_no_outbound_call_is_made_to_render_the_cockpit(client):
    """Brief §32 and the standing rule of this repository: no network client anywhere."""
    import pathlib

    perf = pathlib.Path(__file__).resolve().parent.parent / "app" / "perf"
    offenders = []
    for path in perf.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in ("import httpx", "import requests", "urllib.request", "smtplib"):
            if needle in text:
                offenders.append("%s : %s" % (path.name, needle))

    assert offenders == []
