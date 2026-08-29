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

    assert "This week's conversations" in page
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


def test_managed_kpis_are_grouped_by_the_pillar_the_tracker_files_them_under(client):
    """The domain comes from the tracker, never from the query that produced the figure.

    Grouping by the query is what put customer recruitment, an advocacy score and a
    supply metric under one heading called "Customers" — three pillars, one label, and a
    reader who would have taken the lot for a picture of the customer base.
    """
    page = page_text(client.get("/"))

    assert "Managed KPIs" in page
    assert "Client Acquisition" in page
    assert "Brand Elevation" in page
    assert "3P People" in page
    assert "New customers" in page
    assert "ARC — active customers" in page
    # And the claim nothing here has demonstrated is no longer made.
    assert "lead the sales figures above by months" not in page


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

    assert "CLV — top customers" in page   # the genuinely late one is named
    assert "Reading overdue" in page
    # and the rule is stated, so the absence of other flags is understood
    assert "would teach you to ignore the flag" in page


def test_a_kpi_off_on_both_axes_is_listed_once(client):
    """CLV is short of target and its reading is stale. It used to be listed once for
    each — the same line under two headings of the same panel, reading as two problems.

    Counted inside the customer panel and not across the page: the same KPI appearing
    beside a market's card is a cross-reference, which is the opposite of a duplicate —
    it is what makes the card worth more than the number alone.
    """
    page = page_text(client.get("/"))
    panel = page.split("Managed KPIs")[-1].split("Commitments")[0]

    assert panel.count("CLV — top customers") == 1
    assert "Reading overdue" in panel
    assert "Awaiting a reading" not in page


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
        page = page_text(client.get("/system"))

    assert "Not settled yet" in page
    assert "Sell-in" in page


def test_each_unsettled_line_carries_the_question_that_would_close_it():
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        page = page_text(client.get("/system"))

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

    assert "No real data" not in page
    assert "Internal · read only" in page
    # And the two facts that survived the trim are both there: real figures, nothing
    # written back. The database path and the loopback address moved to System status.
    assert "Real company figures" in page
    assert "nothing is written back" in page
    assert "sqlite" not in page.lower()


def test_the_prototype_banner_still_appears_on_invented_data():
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        page = page_text(client.get("/"))

    assert "Prototype · read only" in page
    assert "No real data" in page


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


# ------------------------------------------------ the screen must not contradict itself
#
# The demonstration screen showed it first: ten open commitments listed in one panel, and
# "no commitment source is connected" in the panel below. Two halves of one screen
# disagreeing costs more than either half is worth — a reader who catches it once stops
# believing the careful half too.


def test_a_panel_that_shows_data_is_not_listed_as_unmeasured():
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        page = page_text(client.get("/"))

    # Mock data provides both, so neither may appear among the things nothing measures.
    assert "No source connected" not in page
    assert "Neither is wired" not in page


def test_a_panel_with_no_source_is_still_listed(monkeypatch):
    """The fix must not silence the register: a measure that genuinely has no source has
    to keep saying so."""
    from starlette.testclient import TestClient

    import app.routes.today as today_route
    from app.main import app
    from app.perf.source import MockSource

    def refuse(self):
        raise NotImplementedError("no commitment source")

    monkeypatch.setattr(
        today_route, "current_source", lambda: type("S", (MockSource,), {"commitments": refuse})()
    )

    with TestClient(app) as client:
        page = page_text(client.get("/system"))

    assert "No source connected" in page


# ------------------------------------------------------------ the year behind the month


def test_the_year_to_date_is_on_the_screen(client):
    """A month is the loudest figure here and the least reliable: a shipment that slips
    across a month end shows as a collapse and a rebound, and neither happened. The year
    to date is the same business read without that noise."""
    page = page_text(client.get("/"))

    assert "FY27 to date" in page
    assert "sold since April" in page


def test_the_year_to_date_says_what_it_could_not_compare(client):
    """The reason the figure is trustworthy is the reason it looks small. On the real
    warehouse the actual with no plan against it is large enough to turn a year behind
    budget into a year ahead of it, so it is named rather than absorbed."""
    page = page_text(client.get("/"))

    assert "carrying no plan" in page
    assert "no sales recorded against it" in page
    # And the basis of the total, said in the same breath as the figure. Two bases are
    # added together here — shoppers at the till, partners at the invoice — which is how
    # the accounts recognise revenue and why it must never be swapped for a sell-through
    # figure without saying so.
    assert "Sold and shipped together" in page
    # A fragment that survives the template's own line wrapping: asserting a phrase
    # that spans two source lines tests the indentation, not the sentence.
    assert "Hospitality and corporate gifts" in page


def test_a_plan_the_record_does_not_support_is_questioned_on_the_screen(client):
    """Two kinds of question about a plan, and both belong on the screen. One asks where
    the plan aims; this one asks whether it was ever reachable. It is answerable today
    where the twelve-month verdict is not: the sales record is two years deep and
    trusted, while the workbook covers the current year only."""
    page = page_text(client.get("/"))

    assert "above every reading of the record" in page
    assert "Was this plan ever reachable" in page
    # And the other one is still there. Neither hides the other.
    assert "Why is the plan focused on sessions" in page


def test_the_plan_finding_carries_its_euros(client):
    """A percentage says how far the plan is from the record; the euros say whether it is
    worth an hour. The screen ranks everything else by money and this must not be the
    exception."""
    page = page_text(client.get("/"))

    assert "across the year's plan" in page


def test_the_page_can_tell_when_a_fresher_read_has_landed(client):
    """The screen opens on the last read and a fresh one lands behind it minutes later.
    The only sign of that used to be a line in the server window, so the instruction was
    "watch the log and reload" — a developer's habit handed to a reader, and not followed
    because it should not have to be."""
    page = page_text(client.get("/"))

    assert "data-read-at=" in page

    stamp = client.get("/freshness")
    assert stamp.status_code == 200
    assert "as_of" in stamp.json()


def test_the_freshness_check_can_never_cause_a_warehouse_read(monkeypatch):
    """A check that could trigger a three-minute query would be a worse problem than the
    one it solves. It reports what the cache holds and nothing else."""
    from app.perf import source

    source.cache_clear()

    assert source.last_read() == ""


def test_the_plumbing_is_one_click_away_and_not_on_the_decision_screen(client):
    """None of it is deleted, because all of it is true and someone eventually asks. It
    simply is not a decision: the person deciding what to do about Japan this week does
    not need the SQLite path, the loopback address or the autonomy level, and every line
    of that kind is a line taken from the five that matter.
    """
    today = page_text(client.get("/"))

    assert "127.0.0.1" not in today
    assert "autonomy level" not in today.lower()
    assert "System status" in today          # named, so nothing looks hidden

    status = page_text(client.get("/system"))

    assert "PREPARE" in status
    assert "loopback" in status
    assert "writes nothing back" in status


def test_the_register_lives_on_one_page_only(client):
    """It was on both: moved to System status, and left where it was. Two copies of a
    register are two registers, and the day they disagree the reader believes neither."""
    assert "Not settled yet" not in page_text(client.get("/"))
    assert "Not settled yet" in page_text(client.get("/system"))


def test_a_repeated_paragraph_becomes_a_badge_and_a_note(client):
    """The rule V3 sets: a fact that changes the action is a badge, a fact that explains
    how the number was made is a footnote. "Shipped, not sold" was printed on every channel
    of every market — eight prints of one fact on a screen meant to be read in two minutes.
    """
    page = page_text(client.get("/"))

    # Gone from the cards.
    assert "Shipped, not sold (June): invoiced to a partner" not in page
    assert "No commitment recorded against this gap" not in page
    # And said once, where a reader who wants it can find it.
    assert "How to read this screen" in page
    assert page.count("Invoiced to a partner, which is when the accounts recognise it") == 1


def test_the_screen_says_what_each_channel_actually_is(client):
    """"China E-retailers" and "China E-commerce" look like two shades of online selling.
    They are a partner who buys our stock and our own site, recognised at different
    moments and answered by different people — and the platform most readers picture for
    China sits under a third name again."""
    page = page_text(client.get("/"))

    assert "The channels on this screen" in page
    assert "brand.com" in page          # what "E-commerce" is
    assert "Sold when the shopper pays" in page

    # Only the channels actually on the screen: a glossary of everything the taxonomy
    # knows would be a page of definitions for figures nobody is looking at.
    assert "Tmall or JD flagship" not in page   # no marketplace line in this dataset
