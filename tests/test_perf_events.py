"""Le calendrier des dates mobiles, et l'épreuve que doit passer une explication.

Le module qui mesure les mois instables n'a besoin d'aucun calendrier : c'est sa force. Le
module testé ici prend le risque inverse, il nomme des causes, et le risque est réel — un
calendrier contient toujours un événement dans le mois qu'on regarde, donc une explication
est toujours disponible. Ces tests gardent surtout les trois façons dont un candidat doit
pouvoir échouer.
"""

from __future__ import annotations

from app.perf import events as E

HEADER = ("country,event_name,family,year,start_date,end_date,"
          "start_weekday,date_status,source,rule,region,event_id")


def _file(tmp_path, rows, header=HEADER, name="calendar.csv"):
    path = tmp_path / name
    path.write_text("\n".join([header] + list(rows)) + "\n", encoding="utf-8")
    return str(path)


def _row(year, start, country="Hong Kong", name="Fête mobile", end="", event_id="ev"):
    return "%s,%s,règle,%s,%s,%s,,observée,source,règle,National,%s" % (
        country, name, year, start, end, event_id)


def test_an_event_that_does_not_move_explains_nothing(tmp_path):
    """Le refus le plus important, parce que c'est celui qu'un œil ne fait pas : une date
    fixe qui traverse un mois instable est une coïncidence. Sans ce refus, tout mois de
    décembre serait « expliqué » par Noël."""
    read = E.load(_file(tmp_path, [_row("2023", "2023-09-10"),
                                   _row("2024", "2024-09-10"),
                                   _row("2025", "2025-09-10")]))
    cumulative = {"2023": 0.30, "2024": 0.60, "2025": 0.45}

    verdict = E.weigh(cumulative, read.series["ev"], week=2, month="09")

    assert verdict.label == E.IMMOBILE and not verdict.holds


def test_an_event_that_never_crosses_the_measured_week_explains_nothing(tmp_path):
    """Il bouge, le mois bouge, et les deux faits n'ont aucun rapport : l'événement se
    déplace de la troisième à la quatrième semaine pendant que l'écart se joue à la
    deuxième. C'est le piège d'un rapprochement fait à l'œil sur deux colonnes qui bougent
    toutes les deux."""
    read = E.load(_file(tmp_path, [_row("2023", "2023-09-18"),
                                   _row("2024", "2024-09-25"),
                                   _row("2025", "2025-09-20")]))
    cumulative = {"2023": 0.30, "2024": 0.60, "2025": 0.45}

    verdict = E.weigh(cumulative, read.series["ev"], week=2, month="09")

    assert verdict.label == E.OUTSIDE and not verdict.holds


def test_an_event_that_orders_every_year_the_right_way_holds(tmp_path):
    """Ce que « expliquer » veut dire ici, et pourquoi le test vaut quelque chose : les
    exercices où la fête est déjà passée ont tous fait plus que ceux où elle ne l'est pas.
    Tous — un seul exercice à contre-sens suffirait à faire tomber le candidat."""
    read = E.load(_file(tmp_path, [_row("2023", "2023-09-05"),    # semaine 1
                                   _row("2024", "2024-09-25"),    # semaine 4
                                   _row("2025", "2025-09-22")]))  # semaine 4
    cumulative = {"2023": 0.62, "2024": 0.30, "2025": 0.35}

    verdict = E.weigh(cumulative, read.series["ev"], week=2, month="09")

    assert verdict.holds
    assert verdict.inside == ["2023"] and verdict.outside == ["2024", "2025"]


def test_one_year_against_the_sense_is_enough_to_refuse(tmp_path):
    read = E.load(_file(tmp_path, [_row("2023", "2023-09-05"),
                                   _row("2024", "2024-09-25"),
                                   _row("2025", "2025-09-03")]))
    cumulative = {"2023": 0.62, "2024": 0.30, "2025": 0.28}   # 2025 tôt et pourtant bas

    verdict = E.weigh(cumulative, read.series["ev"], week=2, month="09")

    assert verdict.label == E.CONTRADICTS


def test_an_event_that_left_the_month_is_after_it_and_not_early_in_it(tmp_path):
    """Le défaut que ce classement ferme : la fête de la mi-automne tombe le 6 octobre une
    année. Lue par son seul rang de jour, elle devient un événement de première semaine —
    c'est-à-dire l'inverse exact de ce qu'elle est pour septembre, et le rapprochement
    conclut le contraire de la vérité."""
    read = E.load(_file(tmp_path, [_row("2023", "2023-09-29"),
                                   _row("2024", "2024-09-17"),
                                   _row("2025", "2025-10-06")]))

    places = read.series["ev"].places(["2023", "2024", "2025"], "09")

    assert places == {"2023": 5, "2024": 3, "2025": E.AFTER}


def test_the_selling_lead_is_declared_and_never_assumed(tmp_path):
    """Une fête se prépare : son chiffre se fait avant elle. L'hypothèse est légitime et
    elle change le verdict — donc elle est un paramètre que le lecteur voit, jamais une
    correction glissée dans le calcul."""
    read = E.load(_file(tmp_path, [_row("2023", "2023-09-29"), _row("2024", "2024-09-17"),
                                   _row("2025", "2025-10-06")]))
    series = read.series["ev"]

    assert series.places(["2025"], "09") == {"2025": E.AFTER}
    assert series.places(["2025"], "09", lead=12) == {"2025": 4}


def test_a_window_whose_end_never_moves_is_a_convention_and_is_flagged(tmp_path):
    """Des soldes « jusqu'au 31 janvier » huit années de suite ne décrivent pas la fin des
    soldes : elles décrivent le choix de celui qui a rempli la colonne. Consommée telle
    quelle, cette borne ferait conclure à une stabilité que personne n'a observée."""
    read = E.load(_file(tmp_path, [
        _row("2023", "2023-06-17", end="2023-07-15"),
        _row("2024", "2024-06-15", end="2024-07-15"),
        _row("2025", "2025-06-14", end="2025-07-15")]))

    assert read.series["ev"].conventional_end


def test_a_moving_end_is_not_flagged(tmp_path):
    read = E.load(_file(tmp_path, [
        _row("2023", "2023-06-17", end="2023-07-12"),
        _row("2024", "2024-06-15", end="2024-07-16")]))

    assert not read.series["ev"].conventional_end


def test_a_year_without_a_date_is_named_and_never_filled(tmp_path):
    """Le fichier dit lui-même « à annoncer » pour les campagnes futures. Compléter par la
    date de l'an dernier rendrait un tableau plein et faux."""
    read = E.load(_file(tmp_path, [_row("2024", "2024-11-21"), _row("2025", "")]))

    series = read.series["ev"]
    assert series.absent == ["2025"] and list(series.dated) == ["2024"]


def test_a_single_shared_year_proves_nothing(tmp_path):
    read = E.load(_file(tmp_path, [_row("2024", "2024-09-10")]))

    assert E.weigh({"2024": 0.4}, read.series["ev"], 2, "09").label == E.THIN


def test_the_exercise_is_translated_into_a_calendar_year_and_never_guessed():
    """Un décalage d'un an ne se voit pas : les années se recouvrent, le tableau reste
    lisible, et il compare le mois d'un exercice aux fêtes d'un autre. La convention de la
    maison — l'exercice 27 s'ouvre en avril 26 — est l'une des trois, pas la seule."""
    assert E.calendar_year("2027", "11", "cloture") == "2026"
    assert E.calendar_year("2027", "02", "cloture") == "2027"
    assert E.calendar_year("2026", "11", "ouverture") == "2026"
    assert E.calendar_year("2026", "02", "ouverture") == "2027"
    assert E.calendar_year("2026", "11", "calendaire") == "2026"


def test_only_the_events_that_touch_the_month_are_candidates(tmp_path):
    read = E.load(_file(tmp_path, [
        _row("2024", "2024-09-17", event_id="automne", name="Mi-automne"),
        _row("2024", "2024-06-10", event_id="dragons", name="Bateaux-dragons")]))

    assert [item.event_id for item in read.in_month("Hong Kong", "09")] == ["automne"]


def test_a_country_written_differently_still_joins(tmp_path):
    read = E.load(_file(tmp_path, [_row("2024", "2024-04-05", country="Tchéquie")]))

    assert read.of_country("TCHEQUIE") and read.of_country("tchequie")


def test_a_market_can_carry_several_countries_because_the_judgement_is_not_the_code(
        tmp_path):
    """Black Friday n'est d'aucun pays et ne s'applique pas partout. Savoir où il compte
    est un jugement de commerce ; le fichier est l'endroit où ce jugement s'écrit."""
    path = tmp_path / "markets.csv"
    path.write_text("market,country\nCanada,Canada\nCanada,International\n",
                    encoding="utf-8")

    pairs, faults = E.load_markets(str(path))

    assert pairs["canada"] == ["Canada", "International"] and faults == []


def test_a_file_missing_its_columns_says_so_rather_than_reading_nothing(tmp_path):
    read = E.load(_file(tmp_path, ["Hong Kong,2024"], header="country,year"))

    assert not read.usable and "colonnes manquantes" in read.faults[0]


def test_an_absent_file_is_an_empty_reading_and_not_a_crash(tmp_path):
    read = E.load(str(tmp_path / "nulle-part.csv"))

    assert not read.usable and read.faults == []


def test_the_other_column_name_is_accepted_because_two_files_already_exist(tmp_path):
    read = E.load(_file(tmp_path, ["Hong Kong,Fête,règle,2024,2024-09-17"],
                        header="country,event,family,year,start_date"))

    assert len(read) == 1


def test_a_fiscal_label_is_read_as_an_exercise_and_not_as_a_calendar_year():
    """« FY2024 » annonce de lui-même un exercice. Lu comme une année civile, le
    rapprochement compare le mois d'un exercice aux fêtes d'une autre année — sans rien
    casser et sans rien signaler. Le seul symptôme visible était « trop peu d'exercices »
    sur chaque ligne, ce qui ressemble à un calendrier trop court."""
    assert E.is_fiscal("FY2024") and not E.is_fiscal("2024")
    assert E.calendar_year("FY2024", "11", "cloture") == "2023"
    assert E.calendar_year("FY2024", "02", "cloture") == "2024"
    assert E.calendar_year("EX 2024", "11", "calendaire") == "2024"


def test_a_label_without_four_digits_is_left_alone_rather_than_invented():
    assert E.calendar_year("provisoire", "11", "cloture") == "provisoire"


def test_the_same_country_written_in_two_languages_still_joins():
    """La forme des mois vient de l'entrepôt, en anglais ; les calendriers d'une recherche,
    en français. Sans cette table, seuls les pays qui s'écrivent pareil se joignaient — et
    un pays non joint rend exactement la même page vide qu'un pays sans fête."""
    assert E.same_country("CZECH REPUBLIC", "Tchéquie")
    assert E.same_country("KOREA", "Corée du Sud")
    assert E.same_country("USA", "États-Unis")
    assert E.same_country("Hong Kong", "hong kong")
    assert not E.same_country("SWEDEN", "Suisse")


def test_an_unlisted_country_still_joins_to_itself(tmp_path):
    """La table est un secours, pas une autorité : un pays qu'elle ignore doit continuer à
    se joindre à son propre nom, sinon l'ajout d'un marché casserait la lecture."""
    read = E.load(_file(tmp_path, [_row("2024", "2024-04-05", country="Marchés inventés")]))

    assert read.of_country("marches inventes")


def test_a_window_that_opens_in_another_month_still_covers_this_one(tmp_path):
    """L'absence fausse que ce filtre ferme : des soldes du 25 décembre au 31 janvier
    couvrent janvier entier. Filtrées sur leur mois d'ouverture, elles disparaissaient, et
    l'écran annonçait « aucun événement ne tombe en janvier » — ce qui referme la question
    au lieu de l'ouvrir, et c'est pire qu'un trou."""
    read = E.load(_file(tmp_path, [
        _row("2024", "2023-12-25", country="Suède", end="2024-01-31"),
        _row("2025", "2024-12-25", country="Suède", end="2025-01-31")]))

    assert read.in_month("Suède", "01") and read.in_month("Suède", "12")
    assert not read.in_month("Suède", "03")


def test_a_candidate_that_separates_the_years_by_nothing_is_marked(tmp_path):
    """« Aucun contre-exemple » n'est pas « voilà la cause ». Un candidat qui ordonne les
    exercices d'un millième les ordonne sans expliquer un point de la distance qu'on lui
    demande d'expliquer — et sans cette réserve, il s'écrit du même mot qu'un candidat qui
    en sépare dix points."""
    read = E.load(_file(tmp_path, [_row("2023", "2023-03-05"), _row("2024", "2024-03-25"),
                                   _row("2025", "2025-03-22")]))
    cumulative = {"2023": 0.523, "2024": 0.522, "2025": 0.373}

    verdict = E.weigh(cumulative, read.series["ev"], 2, "03", mobility=0.150)

    assert verdict.label == E.AGREES and verdict.narrow and not verdict.holds
    assert abs(verdict.margin - 0.001) < 1e-9


def test_a_candidate_that_separates_them_clearly_holds(tmp_path):
    read = E.load(_file(tmp_path, [_row("2023", "2023-03-05"), _row("2024", "2024-03-25"),
                                   _row("2025", "2025-03-22")]))
    cumulative = {"2023": 0.869, "2024": 0.765, "2025": 0.770}

    verdict = E.weigh(cumulative, read.series["ev"], 2, "03", mobility=0.163)

    assert verdict.holds and verdict.split == "1 contre 2"


def test_a_fixed_gifting_date_is_judged_on_its_weekday_and_not_on_a_boundary(tmp_path):
    """La Saint-Valentin, le White Day, le 11.11 tombent le même jour du mois chaque
    année : ils ne peuvent jamais déplacer un mois, et l'épreuve des cumuls les renvoie
    immobiles à juste titre. Ce qui bouge est leur jour de semaine — et un cadeau acheté
    pour un samedi ne s'achète pas au même moment qu'un cadeau pour un mardi. Sans cette
    seconde épreuve, les moments qui font le plus de chiffre dans cette maison n'étaient
    jamais testés du tout."""
    read = E.load(_file(tmp_path, [
        _row("2024", "2024-02-14", country="Corée du Sud"),   # mercredi
        _row("2025", "2025-02-14", country="Corée du Sud"),   # vendredi
        _row("2026", "2026-02-14", country="Corée du Sud")]))  # samedi
    part = {"2024": 0.22, "2025": 0.40, "2026": 0.42}

    verdict = E.weigh_weekday(part, read.series["ev"], "02", variation=0.30)

    assert verdict.holds and verdict.inside == ["2025", "2026"]


def test_the_weekday_test_can_fail_like_the_other_one(tmp_path):
    read = E.load(_file(tmp_path, [
        _row("2024", "2024-02-14", country="Corée du Sud"),
        _row("2025", "2025-02-14", country="Corée du Sud"),
        _row("2026", "2026-02-14", country="Corée du Sud")]))
    part = {"2024": 0.42, "2025": 0.30, "2026": 0.31}

    assert E.weigh_weekday(part, read.series["ev"], "02").label == E.CONTRADICTS


def test_a_date_that_never_changes_the_nature_of_its_day_says_so(tmp_path):
    """Trois années où la date tombe toujours en semaine : rien à comparer, et surtout
    rien à conclure d'une part qui varie pour une autre raison."""
    read = E.load(_file(tmp_path, [
        _row("2024", "2024-02-14", country="Corée du Sud"),   # mercredi
        _row("2027", "2027-02-14", country="Corée du Sud")]))  # dimanche → écarté ci-dessous
    read.series["ev"].by_year.pop("2027")
    read.series["ev"].by_year["2023"] = E.Event(
        "Corée du Sud", "Fête", "fixe", "2023", "2023-02-14")   # mardi

    verdict = E.weigh_weekday({"2023": 0.30, "2024": 0.22}, read.series["ev"], "02")

    assert verdict.label == E.IMMOBILE


def test_the_gifting_day_is_read_from_the_date_and_not_from_a_column():
    """Une colonne de jour de semaine est une donnée dérivée, donc une donnée qui peut
    contredire sa propre source sans que rien ne le signale."""
    assert E.falls_on_a_gifting_day("2026-02-14") is True      # samedi
    assert E.falls_on_a_gifting_day("2024-02-14") is False     # mercredi
    assert E.falls_on_a_gifting_day("") is None
