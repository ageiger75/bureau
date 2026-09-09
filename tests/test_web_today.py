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
    assert "Qu'est-ce que je décide cette semaine" in page_text(response)


def test_decision_room_is_gone(client):
    """Retiré le 7 septembre 2026 : une seule porte, et elle donne sur le cockpit."""
    assert client.get("/decisions").status_code == 404


# ------------------------------------------------------- the eight questions of §34


def test_where_the_business_is_underperforming(client):
    page = page_text(client.get("/analyses"))

    assert "Où pousser" in page
    assert "Japan E-commerce" in page


def test_why_it_is_underperforming(client):
    """A diagnosis, not a description (brief §3.2)."""
    page = page_text(client.get("/"))

    assert "de l'écart vient de la conversion" in page


def test_how_much_money_is_involved(client):
    page = page_text(client.get("/"))

    assert "-1.2 M€" in page


def test_where_the_upside_is(client):
    page = page_text(client.get("/analyses"))

    assert "Opportunités" in page
    assert "Suppose que la conversion revient à" in page


def test_who_to_challenge(client):
    page = page_text(client.get("/"))

    # Une seule liste de conversations, celle du registre : l'ancienne, recalculée à chaque
    # lecture par l'analytique, faisait du même marché deux entrées sur le même écran.
    assert "Les conversations de la semaine" not in page
    assert "Qu'est-ce que je décide cette semaine" in page
    assert "Naoki" in page_text(client.get("/analyses"))


def test_what_to_ask_them(client):
    """The question is the product. Without it the screen is a report."""
    page = page_text(client.get("/analyses"))

    assert "Pourquoi le plan vise-t-il les sessions" in page


def test_what_people_committed_to(client):
    page = page_text(client.get("/"))

    assert "Ship the mobile checkout recovery plan" in page


def test_whether_those_actions_worked(client):
    """Brief §18: delivered, and it did not work — the most easily lost fact in the loop."""
    page = page_text(client.get("/"))

    assert "Fait, sans résultat" in page
    assert "A marché" in page


# --------------------------------------------------------------- honesty guarantees


def test_management_explanation_is_challenged_not_repeated(client):
    """Brief §3.5 and §20: quantify what the stated cause leaves unexplained."""
    page = page_text(client.get("/analyses"))

    assert "Sales are down because the market is difficult." in page
    assert "restent inexpliqués" in page


def test_estimates_are_labelled_as_estimates(client):
    """Brief §3.3 and §32: never present an inferred relationship as a proven fact."""
    page = page_text(client.get("/analyses"))

    assert "estimations" in page
    assert "pas des causes mesurées" in page


def test_the_ranking_can_be_inspected(client):
    """Brief §31: opaque ranking costs the trust the whole product depends on."""
    page = page_text(client.get("/analyses"))

    assert "Pourquoi je vois ça ?" in page
    assert "mois consécutifs sous le plan" in page
    assert "priorité = écart € × persistance" in page


def test_confidence_is_shown_on_every_diagnosis(client):
    assert "Confiance haute" in page_text(client.get("/analyses"))


def test_the_screen_says_the_data_is_invented(client):
    """A cockpit that looks authoritative on mock numbers is worse than none."""
    page = page_text(client.get("/"))

    assert "inventé pour la démonstration" in page


def test_the_unbuilt_assistant_is_not_on_the_screen(client):
    """Une section qui annonce ce qui n'existe pas est du bruit sur l'écran d'un CEO. Elle
    reviendra le jour où elle répond."""
    page = page_text(client.get("/"))

    assert "Ask Performance CoS" not in page
    assert "Not built yet" not in page


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
    page = page_text(client.get("/analyses"))

    assert "KPI suivis" in page
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
    page = page_text(client.get("/analyses"))

    assert "plus bas est mieux" in page


def test_a_kpi_whose_definition_is_unsettled_is_shown_but_not_challenged(client):
    page = page_text(client.get("/analyses"))

    assert "Pas de question posée" in page
    assert "not yet aligned with the one used in China" in page


def test_a_quarterly_kpi_is_not_reported_missing_between_readings(client):
    """The US NPS has a Q1 figure and no August one. That is the calendar, not a gap."""
    page = page_text(client.get("/analyses"))

    assert "CLV — top customers" in page   # the genuinely late one is named
    assert "Lecture en retard" in page
    # and the rule is stated, so the absence of other flags is understood
    assert "apprendrait à ignorer le signal" in page


def test_a_kpi_off_on_both_axes_is_listed_once(client):
    """CLV is short of target and its reading is stale. It used to be listed once for
    each — the same line under two headings of the same panel, reading as two problems.

    Counted inside the customer panel and not across the page: the same KPI appearing
    beside a market's card is a cross-reference, which is the opposite of a duplicate —
    it is what makes the card worth more than the number alone.
    """
    page = page_text(client.get("/analyses"))
    panel = page.split("KPI suivis")[-1].split("La donnée à vérifier")[0]

    assert panel.count("CLV — top customers") == 1
    assert "Lecture en retard" in panel
    assert "Awaiting a reading" not in page


def test_customer_signals_are_attached_to_the_market_that_is_on_fire(client):
    """A conversion gap with recruitment holding up is a different conversation from one
    where both are falling."""
    page = page_text(client.get("/analyses"))

    assert "Signaux clients" in page


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

    assert "Aucune donnée réelle" not in page
    assert "Interne · lecture seule" in page
    # And the two facts that survived the trim are both there: real figures, nothing
    # written back. The database path and the loopback address moved to System status.
    assert "Chiffres réels de l'entreprise" in page
    assert "rien n'est réécrit" in page
    assert "sqlite" not in page.lower()


def test_the_prototype_banner_still_appears_on_invented_data():
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        page = page_text(client.get("/"))

    assert "Prototype · lecture seule" in page
    assert "Aucune donnée réelle" in page


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

    assert "Aucune prévision remontée" in page


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


def test_the_year_leads_and_the_month_follows(client):
    """A month is the loudest figure here and the least reliable: a shipment that slips
    across a month end shows as a collapse and a rebound, and neither happened. The year
    to date is the same business read without that noise.

    The screen used to open on the month anyway, and it cost something concrete — a month
    at −1.6% sat above a year at −0.2%, and the reader spent three blocks worried about a
    year that was being held. The house judges the exercise; the screen now opens on it,
    and the month reads second, for pace and for what moved.
    """
    page = page_text(client.get("/"))
    body = page[page.index("cockpit-header"):]

    assert "Exercice à date" in body
    assert "Dernier mois clos" in body
    # Order, not merely presence: the year's figure has to come first on the page.
    assert body.index("Exercice à date") < body.index("Dernier mois clos")


def test_the_year_to_date_says_what_it_could_not_compare(client):
    """The reason the figure is trustworthy is the reason it looks small. On the real
    warehouse the actual with no plan against it is large enough to turn a year behind
    budget into a year ahead of it, so it is named rather than absorbed."""
    page = page_text(client.get("/"))
    how_to_read = page_text(client.get("/analyses"))

    assert "sans plan, hors des comparaisons" in page
    assert "sans vente lue" in page
    page = how_to_read
    # And the basis of the total, said in the same breath as the figure. Two bases are
    # added together here — shoppers at the till, partners at the invoice — which is how
    # the accounts recognise revenue and why it must never be swapped for a sell-through
    # figure without saying so.
    assert "Vendu et expédié ensemble" in page
    # A fragment that survives the template's own line wrapping: asserting a phrase
    # that spans two source lines tests the indentation, not the sentence.
    assert "Hospitality et cadeaux d'entreprise" in page


def test_a_plan_the_record_does_not_support_is_questioned_on_the_screen(client):
    """Two kinds of question about a plan, and both belong on the screen. One asks where
    the plan aims; this one asks whether it was ever reachable. It is answerable today
    where the twelve-month verdict is not: the sales record is two years deep and
    trusted, while the workbook covers the current year only."""
    page = page_text(client.get("/analyses"))

    assert "au-dessus de chaque lecture du réalisé" in page
    assert "Ce plan a-t-il jamais été atteignable" in page
    # And the other one is still there. Neither hides the other.
    assert "Pourquoi le plan vise-t-il les sessions" in page


def test_the_plan_finding_carries_its_euros(client):
    """A percentage says how far the plan is from the record; the euros say whether it is
    worth an hour. The screen ranks everything else by money and this must not be the
    exception."""
    page = page_text(client.get("/analyses"))

    assert "embarqués sur l'année" in page


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
    assert "État du système" in today          # named, so nothing looks hidden

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
    page = page_text(client.get("/analyses"))

    # Gone from the cards.
    assert "Expédié, pas vendu (juin) : facturé à un partenaire" not in page
    assert "No commitment recorded against this gap" not in page
    # And said once, where a reader who wants it can find it.
    assert "Comment lire cet écran" in page
    assert page.count("Facturé à un partenaire, moment où les comptes le reconnaissent") == 1


def test_the_screen_says_what_each_channel_actually_is(client):
    """"China E-retailers" and "China E-commerce" look like two shades of online selling.
    They are a partner who buys our stock and our own site, recognised at different
    moments and answered by different people — and the platform most readers picture for
    China sits under a third name again."""
    page = page_text(client.get("/analyses"))

    assert "Les canaux de cet écran" in page
    assert "brand.com" in page          # what "E-commerce" is
    assert "Vendu quand le client paie" in page

    # Only the channels actually on the screen: a glossary of everything the taxonomy
    # knows would be a page of definitions for figures nobody is looking at.
    assert "marketplace flagship" not in page   # no marketplace line in this dataset


# ------------------------------------------- the second base, where it changes the verdict


def test_a_market_whose_bulk_hides_its_shoppers_says_so_on_both_bases(client):
    """Hong Kong grows on the total and falls on the shoppers. Both figures, or neither.

    One of them alone is a wrong answer to the question this screen asks, and which one is
    wrong depends on the market — so the card carries the pair and names the difference.
    """
    page = page_text(client.get("/analyses"))

    assert "Là où le vrac répond à la place des clients" in page
    assert "Hong Kong" in page
    assert "hors vrac" in page


def test_markets_whose_two_bases_agree_stay_off_the_screen(client):
    """The panel exists for the disagreement, not for the bulk.

    Listing every market that carries some bulk would put the reader back to scanning for
    the one line that matters, which is the habit this screen is built against.
    """
    from app.perf import mock

    shown = [item.scope for item in mock.bulk_findings()]
    assert all(item.changes_the_verdict for item in mock.bulk_findings())
    assert "Japan" not in shown


def test_a_kpi_green_at_group_level_names_the_markets_it_hides(client):
    """Le chiffre groupe passe la cible et la moitié des marchés est en dessous.

    Le montrer et s'arrêter revient à afficher la seule chose qui ne demande aucune
    action — l'inverse exact de ce que cet écran est censé faire.
    """
    page = page_text(client.get("/analyses"))

    assert "Units per transaction" in page
    assert "sont sous cette cible" in page
    assert "Finland" in page


def test_the_screen_shows_the_register_and_not_a_fresh_recount(client, db_session):
    """Le défaut que la doctrine appelle amnésie hebdomadaire : l'écran recalculait ses
    sujets à chaque lecture et présentait chaque lundi les mêmes marchés comme des
    découvertes. Une référence affichée doit désigner le même sujet d'une lecture à
    l'autre — c'est la seule preuve que la page se souvient."""
    from app.domain import issues as I
    from app.perf import memory

    register = I.Register()
    issue = register.observe(I.Observation(
        kind="gap_to_plan", scope="Northland", seen_at="2026-08-01",
        statement="Un écart qui ne se referme pas", amount=-900_000.0,
        basis=I.STAKE))
    issue.accountable = "Une dirigeante"
    memory.save(db_session, register)
    db_session.commit()

    first = client.get("/").text
    second = client.get("/").text

    assert issue.issue_id in first
    assert "Un écart qui ne se referme pas" in first
    assert issue.issue_id in second


def test_a_source_the_reading_did_not_open_is_named_on_the_screen(client):
    """« Rien à signaler » et « je n'ai pas regardé » ne s'écrivent jamais pareil. Le
    défaut serait invisible : un écran muet sur une source absente se lit comme un écran
    qui a tout vu."""
    page = client.get("/").text

    # Assertion portée sur ce qui distingue, pas sur la formule : l'écran a été raccourci
    # une fois et ce test est tombé sans qu'aucun comportement ait changé.
    assert "je n'ai pas regardé" in page


def test_the_screen_never_prints_the_score_that_orders_the_subjects(client, db_session):
    """§C6. Un nombre affiché à côté d'un marché invite à discuter le nombre, alors que ce
    qui se discute est la matérialité, l'urgence et la fiabilité. Ce qui est vérifié ici
    est la valeur elle-même, pas le mot : un test sur le mot tomberait sur la phrase qui
    explique justement qu'on ne l'affiche pas."""
    from app.domain import issues as I
    from app.perf import memory, selection

    register = I.Register()
    register.observe(I.Observation(kind="gap_to_plan", scope="Northland",
                                   seen_at="2026-08-01", statement="Un écart",
                                   amount=-900_000.0, basis=I.STAKE))
    memory.save(db_session, register)
    db_session.commit()

    row = selection.rank(register, "2026-09-01").attention[0]
    response = client.get("/")
    page = page_text(response)

    assert row.why in page
    for rendered in (repr(row._score), "%.2f" % row._score, "%d" % int(row._score)):
        assert rendered not in page


def test_the_month_in_progress_is_on_the_screen_with_two_rates_per_market(client):
    """B3, tel que le lecteur l'a dit : « savoir où j'en suis dans le mois, pas seulement
    à la fin ». Le panneau existe, il nomme le sell-in pour ce qu'il est, et il porte des
    marchés — ou dit ce qui manque pour les lire."""
    page = page_text(client.get("/"))

    assert "à date" in page
    assert "une facture tombe quand elle tombe" in page_text(client.get("/analyses"))

def test_the_mix_is_on_the_screen_as_a_calculation_never_as_a_result(client):
    """B5, première pièce : le mix par canal contre le plan se lit sans aucun taux, le
    taux marginal est dit absent, et rien ne s'appelle EBITDA ni résultat."""
    page = page_text(client.get("/analyses"))

    assert "L'euro gagné est-il le bon euro" in page
    assert "Part au plan" in page
    assert "Taux marginal : absent" in page
    assert "Aucun canal n'est classé sur son taux moyen" in page
    # Le panneau du mix ne nomme jamais l'EBITDA : le plan EBITDA par BU, lui, a sa place
    # en haut de l'écran, comme un plan et jamais comme un résultat du mix.
    mix_panel = page.split("L'euro gagné est-il le bon euro")[1].split("La part loyer")[0]
    assert "EBITDA" not in mix_panel


def test_the_rent_share_panel_is_on_the_screen_or_says_what_it_waits_for(client):
    """B5, deuxième pièce : la part loyer se lit boutique par boutique, et sans fichier le
    panneau nomme ce qu'il attend au lieu de rendre un zéro."""
    page = page_text(client.get("/analyses"))

    assert "La part loyer du prochain euro" in page
    assert "stores-sales.xlsx" in page


def test_the_screen_answers_whether_we_are_in_line_with_the_plan(client):
    """La question que le lecteur pose en ouvrant l'écran, avec un mot par période et la
    base à côté — ou ce qui manque pour répondre."""
    page = page_text(client.get("/"))

    assert "Exercice à date" in page
    assert "Mois en cours" in page or "à date, jour" in page
    assert "Atterrissage" in page


def test_the_perimeter_pages_exist_and_an_unknown_one_is_refused(client):
    """B1 : une page par périmètre, le même squelette pour tous, et un index qui les
    liste avec leur MD. Un nom inconnu est refusé, jamais rendu vide."""
    index = page_text(client.get("/perimetres"))
    assert "Les périmètres" in index

    assert client.get("/perimetre/nulle-part").status_code == 404


def test_the_ebitda_plan_is_named_when_absent_and_never_read_as_an_actual(client):
    """Le plan EBITDA par BU a sa place en haut de l'écran, comme un plan : sans le fichier,
    l'écran nomme ce qu'il attend, et rien ne convertit un écart de ventes en résultat."""
    page = page_text(client.get("/"))

    assert "var/ebitda-budget.xlsx absent" in page
    # Pas de colonne sans fichier, et la note de lecture dit qu'aucun réel n'est lu.
    assert "<th>EBITDA au budget</th>" not in client.get("/").text
    assert "la Finance ne produit pas d'EBITDA par BU au mois" in page_text(client.get("/analyses"))


def test_the_contribution_to_date_is_named_when_absent(client):
    """Le résultat suit-il les ventes : sans le fichier du compte de gestion, l'écran nomme ce
    qu'il attend, et n'invente aucune contribution."""
    page = page_text(client.get("/"))

    assert "var/pnl_bu.csv absent" in page
    assert "Contribution à fin" not in page


def test_the_contribution_to_date_reaches_the_perimeter_table_and_keeps_the_central_entry_apart(client):
    """Avec le fichier du compte de gestion, la table des périmètres porte la contribution à
    date et la ligne sous le verdict la somme sans l'écriture centrale."""
    from tests.conftest import TEST_DIR
    from tests.test_perf_pnl import FILE

    (TEST_DIR / "pnl_bu.csv").write_text(FILE, encoding="utf-8")
    try:
        page = page_text(client.get("/"))
    finally:
        (TEST_DIR / "pnl_bu.csv").unlink()

    assert "Contribution à fin juin 2026" in page
    assert "avril à juin 2026, 3 mois" in page
    assert "INT COST" in page and "tenue à part" in page
    assert "écartés du compte de gestion" in page
    assert "var/pnl_bu.csv absent" not in page


def test_the_week_is_on_the_screen_in_full_weeks_never_against_the_plan(client):
    """Priorité 3 : piloter le commerce à la semaine. La dernière semaine pleine, contre la
    précédente et la même de l'an dernier ; une semaine entamée est dite non comptée."""
    page = page_text(client.get("/"))

    assert "Semaine du " in page
    assert "sur la semaine précédente" in page
    assert "sur la même semaine l'an dernier" in page
    assert "vs même semaine l'an dernier" in page


def test_the_sell_in_of_the_month_is_on_the_screen_invoices_against_invoices(client):
    """Priorité 3 : le sell-in facturé depuis le 1er, contre les mêmes premiers jours
    facturés l'an dernier, jamais contre le plan."""
    page = page_text(client.get("/"))

    assert "Sell-in facturé du 1er au" in page
    assert "à jours ouvrés égaux" in page
    assert "jamais contre le plan" in page


def test_what_is_ahead_is_named_when_absent(client):
    """Priorité 3 : les temps forts à venir. Sans le fichier, l'écran nomme ce qu'il attend."""
    page = page_text(client.get("/"))

    assert "Ce qui arrive" in page
    assert "var/gifting.csv absent" in page


def test_the_page_watches_for_the_kpi_reading_as_well(client):
    """The background refresh lands the headline figures first and the KPIs minutes
    later. The page reloads on either, or the KPI panel stayed « pas encore lu » until
    somebody thought to reload — which is exactly the instruction not to give."""
    page = page_text(client.get("/"))

    assert "data-kpis-at=" in page
    assert "kpis" in client.get("/freshness").json()
    # Et la lecture produit, qui atterrit une minute après la première ouverture.
    assert "data-products-at=" in page
    assert "data-products-at=" in page_text(client.get("/analyses"))
    assert "products" in client.get("/freshness").json()


def test_a_kpi_reading_not_yet_made_is_said_as_such_and_not_as_a_missing_source(
    client, monkeypatch
):
    from app.perf import source as source_module

    def not_yet(self, wait_for_warehouse=True):
        raise source_module.NotReadYet("pas encore")

    monkeypatch.setattr(source_module.MockSource, "client_kpis", not_yet)
    page = page_text(client.get("/analyses"))

    assert "Pas encore lu sur cette machine" in page
    assert "Source pas encore connectée. Les lectures viennent de l'entrepôt" not in page


def test_the_subjects_to_carry_are_prepared_conversations_not_cards(client, db_session):
    """Priorité 4 : « montant en jeu · dure depuis plusieurs lectures » ne dit rien. Chaque
    sujet porté arrive avec l'écart, la tendance, la dernière lecture et une question ; les
    facteurs du moteur restent, en une ligne, parce que §C6 l'exige."""
    from app.domain import issues as I
    from app.perf import memory

    register = I.Register()
    register.observe(I.Observation(kind="gap_to_plan", scope="Japan", seen_at="2026-08-01",
                                   statement="3 mois consécutifs sous le plan",
                                   amount=-900_000.0, basis=I.STAKE))
    memory.save(db_session, register)
    db_session.commit()

    page = page_text(client.get("/"))

    assert "au plus trois conversations, préparées" in page
    assert "L'écart" in page and "La tendance" in page and "La question" in page
    assert "La dernière lecture" in page
    assert "Retenu pour : montant en jeu" in page
    assert "Pourquoi : montant en jeu" not in page
    # Le mock porte un engagement en retard sur ce marché : c'est la première question.
    assert "était dû le" in page or "qu'est-ce qui est engagé" in page


def test_the_three_board_figures_head_the_screen_and_the_month_stays_silent_before_a_week(client):
    """Nickel chrome : l'exercice, la contribution et le same-store sales en cartes, un mot
    chacun. Le mois n'imprime aucune fourchette avant une semaine pleine."""
    from tests.conftest import TEST_DIR
    from tests.test_perf_pnl import FILE

    (TEST_DIR / "pnl_bu.csv").write_text(FILE, encoding="utf-8")
    try:
        page = page_text(client.get("/"))
    finally:
        (TEST_DIR / "pnl_bu.csv").unlink()

    assert "Same-store sales" in page
    assert "magasins comparables, sell-out, vrac compris" in page
    assert "Poste par poste : ce qui porte l'écart de contribution" in page
    assert "L'an dernier au même stade" in page
    assert ("au-dessus du budget" in page or "sous le budget" in page or "au budget" in page)
    # Le paragraphe de quatre cents mots n'est plus là : la table le remplace.
    assert "Écart de contribution" not in page.split("Poste par poste")[0]


def test_the_red_zones_are_a_fixed_block_with_one_line_each(client):
    """Nommées par le lecteur, tenues avec leur chiffre — jamais découvertes par le moteur.
    Sans le fichier, le bloc dit ce qu'il attend."""
    from tests.conftest import TEST_DIR

    page = page_text(client.get("/"))
    assert "Les zones rouges" in page
    assert "red_zones.csv absent" in page

    (TEST_DIR / "red_zones.csv").write_text(
        "zone,scope,measure,target,note\nJapon,Japan,samestore,≥ 0 %,redressement\n"
        "Enseigne US,United States,profit_centre:ENSEIGNE,,montée en charge\n", encoding="utf-8")
    try:
        page = page_text(client.get("/"))
    finally:
        (TEST_DIR / "red_zones.csv").unlink()

    assert "Rien à découvrir ici : à tenir" in page
    assert "Japon" in page and "same-store sales" in page.lower()
    assert "à brancher" in page


def test_what_changed_since_last_monday_is_on_the_screen(client, db_session):
    """Le seul bloc qui a une mémoire : un sujet ouvert à cette lecture y est déjà."""
    page = page_text(client.get("/"))

    assert "Ce qui a changé depuis lundi dernier" in page
    assert ("sujet" in page.split("Ce qui a changé depuis lundi dernier")[1][:400]
            or "rien n'a bougé" in page.split("Ce qui a changé depuis lundi dernier")[1][:400])


def test_the_internal_white_spaces_live_on_the_analyses_page_with_their_hypotheses(client):
    page = page_text(client.get("/analyses"))

    assert "Les white spaces internes" in page
    assert "Beauté Research" in page


def test_what_works_by_product_lives_on_the_analyses_page_in_three_levels(client):
    page = page_text(client.get("/analyses"))

    assert "Ce qui marche, par produit" in page
    for word in ("Catégories ·", "Gammes ·", "Références ·"):
        assert word in page
    assert "Ce qui pousse" in page and "Ce qui recule" in page
    assert "Sans an dernier sur ces mois" in page and "Arrêté :" in page
    assert "hors vrac et hors gratuits" in page
    # Jamais sur l'écran du jour : c'est une analyse, pas une décision de lundi.
    assert "Ce qui marche, par produit" not in page_text(client.get("/"))


def test_each_perimeter_page_reads_what_works_by_product_on_its_own_markets(client, monkeypatch):
    """Le marketing global lit le groupe sur Analyses ; la région lit ses catégories et ses
    gammes sur sa page, la somme de ses marchés, et sait que les références sont au groupe."""
    from app.perf import page as page_module

    # Sans annuaire, la suite ne connaît aucun périmètre : un périmètre inventé, sur un
    # marché que la lecture produit inventée porte.
    known = {"Nord": {"markets": ["Japan"], "lead": "Une dirigeante"}}
    monkeypatch.setattr(page_module, "perimeters", lambda directory, month: known)
    page = page_text(client.get("/perimetre/nord"))

    assert "Ce qui marche, par produit" in page
    assert "Catégories ·" in page and "Gammes ·" in page
    assert "Références ·" not in page
    assert "les références ne sont lues qu'au niveau du groupe" in page.lower()


def test_a_region_page_carries_its_routed_subjects_beside_the_sell_in(client, monkeypatch):
    """Un sell-in qui chute sans phrase à côté se lit comme un effondrement. Les écarts du
    périmètre qui ne sont pas une conversation commerciale — frontière, définition, arrêt
    voulu — se disent sur sa page, au même endroit que sur Analyses."""
    from types import SimpleNamespace

    from app.perf import analytics, page as page_module

    known = {"Nord": {"markets": ["Japan"], "lead": "Une dirigeante"}}
    monkeypatch.setattr(page_module, "perimeters", lambda directory, month: known)
    routed = SimpleNamespace(class_label="Comptabilité", reason="une frontière, pas un résultat",
                             move_label="Aucune action du CEO", destination="Consolidation")
    fire = SimpleNamespace(unit=SimpleNamespace(market="Japan", label="Japan E-retailers"),
                           gap=-1000.0, routed=routed, boundary_standing="", question="")
    other = SimpleNamespace(unit=SimpleNamespace(market="Elsewhere", label="Elsewhere Retail"),
                            gap=-500.0, routed=routed, boundary_standing="", question="")
    monkeypatch.setattr(analytics, "routed_elsewhere", lambda dataset: [fire, other])
    page = page_text(client.get("/perimetre/nord"))

    assert "Pas une conversation commerciale" in page
    assert "Japan E-retailers" in page and "Elsewhere Retail" not in page


def test_the_clients_conversation_lives_on_analyses_and_on_each_region(client, monkeypatch):
    """Au global pour le marketing, par région pour la région : le pont clients × panier =
    ventes et le flux de la base, sur les deux pages, et jamais sur l'écran du jour."""
    from app.perf import page as page_module

    analyses = page_text(client.get("/analyses"))
    assert "Les clients" in analyses
    assert "Clients × panier = ventes" in analyses
    assert "D'où viennent les clients" in analyses
    assert "Clients × panier = ventes" not in page_text(client.get("/"))

    known = {"Nord": {"markets": ["Japan"], "lead": "Une dirigeante"}}
    monkeypatch.setattr(page_module, "perimeters", lambda directory, month: known)
    region = page_text(client.get("/perimetre/nord"))
    assert "Clients × panier = ventes" in region


def test_the_filling_index_lives_on_analyses_and_names_itself_an_index(client):
    page = page_text(client.get("/analyses"))

    assert "Le sell-in devant la vente" in page
    assert "un indice, pas une mesure" in page
    assert "aucun sell-through" in page
    assert "Le sell-in devant la vente" not in page_text(client.get("/"))


def test_the_day_screen_carries_a_clients_card_beside_same_store(client):
    page = page_text(client.get("/"))
    head = page.split("Qu'est-ce que je décide")[0]

    assert "Clients" in head and "clients enregistrés" in head
    assert "base perdue" in head and "le flux sur Analyses" in head


def test_the_supply_forecast_reaches_the_day_and_the_bias_the_analyses(client, monkeypatch, tmp_path):
    from app.config import settings

    path = tmp_path / "supply.csv"
    path.write_text("month,scope,osa,in_full,forecast_accuracy,bias,forecast_growth,note\n"
                    "2026-07,LOEP,97.6,96.4,58.3,-1.9,2.7,\n"
                    "2026-07,Northland,,93.9,,-9,,catalogue\n", encoding="utf-8")
    monkeypatch.setattr(type(settings), "supply_path", property(lambda self: path))

    today = page_text(client.get("/"))
    analyses = page_text(client.get("/analyses"))
    assert "Prévision supply de juillet 2026" in today
    assert "La prévision supply" in analyses and "Northland" in analyses
    assert "vend au-dessus de la prévision" in analyses


def test_partners_by_name_and_the_grey_and_bulk_live_on_analyses(client):
    analyses = page_text(client.get("/analyses"))

    assert "Les partenaires, par leur nom" in analyses
    assert "Le plan n'a pas de ligne par partenaire" in analyses
    assert "Orbis Market" in analyses and "E-retailers" in analyses
    assert "Le gris et le vrac" in analyses and "Trois sources, jamais additionnées" in analyses
    assert "FLAG_BULK 2 à 5" in analyses

    body = client.get("/freshness", headers={"Accept": "application/json"}).json()
    assert "partners" in body
