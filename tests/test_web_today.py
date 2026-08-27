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


# --------------------------------------------------------------- customer KPIs


def test_customer_kpis_are_on_the_screen(client):
    """Recruitment and active customers lead the sales figures by months."""
    page = page_text(client.get("/"))

    assert "Customers" in page
    assert "New customers" in page
    assert "ARC — active customers" in page


def test_a_lower_is_better_kpi_is_marked_as_such(client):
    """Retail turnover above its ceiling is bad news, and the screen must not leave the
    reader to work out the direction."""
    page = page_text(client.get("/"))

    assert "lower is better" in page


def test_a_kpi_whose_definition_is_unsettled_is_shown_but_not_challenged(client):
    page = page_text(client.get("/"))

    assert "No challenge raised" in page
    assert "not yet aligned with the one used in China" in page


def test_a_quarterly_kpi_is_not_reported_missing_between_readings(client):
    """The US NPS has a Q1 figure and no August one. That is the calendar, not a gap."""
    page = page_text(client.get("/"))

    assert "not reported" in page          # the genuinely late one is named
    assert "CLV — top customers" in page
    # and the rule is stated, so the absence of other flags is understood
    assert "would teach you to ignore the flag" in page


def test_customer_signals_are_attached_to_the_market_that_is_on_fire(client):
    """A conversion gap with recruitment holding up is a different conversation from one
    where both are falling."""
    page = page_text(client.get("/"))

    assert "Customer signals" in page


# ------------------------------------------------ saying which figures are not settled


def test_the_screen_lists_what_is_not_settled():
    """A register nobody renders is a register that protects nobody."""
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        page = page_text(client.get("/"))

    assert "Not settled yet" in page
    assert "Sell-in" in page


def test_each_unsettled_line_carries_the_question_that_would_close_it():
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        page = page_text(client.get("/"))

    assert "To confirm" in page


def test_the_headline_figure_is_flagged_while_anything_is_unsettled():
    """The number that gets quoted in a meeting is the one that most needs the mark."""
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        body = client.get("/").text

    assert "badge-beta" in body


# ------------------------------------------------------- saying what is on the screen


def test_the_banner_does_not_deny_real_data_when_there_is_some(monkeypatch):
    """The banner said "no real data expected" unconditionally. The moment the warehouse
    was connected that became false — and a banner telling a passing reader that the
    Maison's own figures are invented is worse than no banner at all."""
    from starlette.testclient import TestClient

    from app.main import app
    from app.web import templates

    monkeypatch.setitem(templates.env.globals, "reads_warehouse", True)

    with TestClient(app) as client:
        page = page_text(client.get("/"))

    assert "no real data expected" not in page
    assert "Confidential" in page


def test_the_prototype_banner_still_appears_on_invented_data():
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        page = page_text(client.get("/"))

    assert "no real data expected" in page


def test_a_missing_forecast_is_a_dash_not_a_zero(monkeypatch):
    """A forecast of exactly zero is not a forecast of nothing: it is the absence of one.
    Printing €0 puts a number where nobody has made a commitment."""
    from starlette.testclient import TestClient

    import app.routes.today as today_route
    from app.main import app
    from app.perf import mock
    from app.perf.model import Dataset

    original = mock.dataset

    def without_forecast():
        built = original()
        for item in built.units:
            item.forecast_sales = 0.0
        return built

    monkeypatch.setattr(mock, "dataset", without_forecast)
    today_route.current_source().dataset()

    with TestClient(app) as client:
        page = page_text(client.get("/"))

    assert "no forecast reported" in page


def test_a_name_and_a_role_do_not_run_together_when_copied():
    """The layout separates them with a flex gap, which exists only on screen. This page
    gets copied into mails and notes, where a gap is not a character and the reader
    receives "YAMAMOTOBU Leader Japan"."""
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        page = page_text(client.get("/"))

    # The mock owner's name and role, adjacent in the markup.
    assert "Naoki" in page
    assert "NaokiManaging" not in page and "NaokiGeneral" not in page


def test_the_confidence_and_the_owner_do_not_glue_together_when_copied():
    """The same defect as the name and the role, in a second place: flex layout drops
    whitespace-only nodes between its items, so "Confidence HIGHNaoki YAMAMOTO" is what a
    copied screen hands to the reader."""
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        page = page_text(client.get("/"))

    assert "HIGHNaoki" not in page
    assert "MEDIUMNaoki" not in page


def test_the_reason_a_gap_cannot_be_explained_is_given_once():
    """It was printed twice in a row, in near-identical words. A screen that repeats
    itself reads as a screen that is padding."""
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        page = page_text(client.get("/"))

    assert page.count("its cause is not measured") <= page.count("below plan")
    assert "The gap is real and visible" not in page
