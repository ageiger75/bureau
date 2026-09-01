"""Les sept périmètres, et qui répond au téléphone.

L'écran proposait une responsable pays comme interlocutrice directe du CEO, et rangeait
les responsables sous des zones qui ne sont aucun des périmètres pilotés. Un cockpit qui
installe son lecteur au-dessus de ses propres MD abîme une ligne hiérarchique
que la maison tient — et il le fait à chaque lecture, poliment, sans que rien ne signale
l'erreur.
"""

from __future__ import annotations

from app.perf import perimeter


def _person(first="A", last="NAME", role="General Manager", scope="Northland",
            zone="Northland", kind=perimeter.MD, manager=""):
    return perimeter.Person(first, last, role, scope, zone, kind, manager)


def test_the_role_decides_and_never_the_job_title():
    """Le piège, et il est réel dans la source : un patron de BU peut être titré
    « General Manager » quand un « Managing Director » est un responsable pays.

    Filtrer sur l'intitulé aurait promu le second devant le CEO et rétrogradé le premier.
    Le test porte donc sur le rattachement, jamais sur le libellé du poste.
    """
    titled_gm_but_bu_lead = _person(role="General Manager, Northland",
                                    kind=perimeter.MD)
    titled_md_but_country = _person(role="Managing Director Eastland & Westland",
                                    kind=perimeter.COUNTRY_GM, manager="A Lead")

    assert titled_gm_but_bu_lead.answers_to_ceo
    assert not titled_md_but_country.answers_to_ceo


def test_a_regional_lead_stops_answering_to_the_ceo_once_the_source_names_their_boss():
    """La faute que ce module empêche, dans l'autre sens. Les deux responsables travel
    retail régionaux ont longtemps été proposés au CEO parce que la source ne nommait
    personne au-dessus d'eux. Elle en nomme une maintenant : continuer à les proposer
    court-circuiterait une ligne que la maison tient, exactement comme proposer un GM
    pays par-dessus son MD."""
    regional = _person(scope="Travel Retail", kind=perimeter.TRAVEL_GM,
                       manager="La MD")
    lead = _person(first="B", scope="Travel Retail", kind=perimeter.MD)
    org = perimeter.Org([lead, regional], [])

    assert not regional.answers_to_ceo
    assert org.lead_for("Travel Retail") is lead
    assert org.without_lead() == []
    assert org.team_of("Travel Retail") == [regional]


def test_a_perimeter_without_a_lead_stays_without_one():
    """La substitution que ce module existe pour empêcher : un périmètre dont le patron
    n'est pas dans la source ne reçoit pas son responsable pays le plus proche. Il
    apparaît sans interlocuteur, ce qui est une information et se corrige à la source."""
    org = perimeter.Org([
        _person(scope="Northland", kind=perimeter.MD),
        _person(first="B", scope="Eastland", kind=perimeter.COUNTRY_GM,
                manager="Someone"),
    ], [])

    assert sorted(org.leads()) == ["Northland"]
    assert org.without_lead() == ["Eastland"]
    assert org.lead_for("Eastland") is None


def test_a_market_the_source_does_not_place_is_not_guessed():
    """La source nomme des zones — « Europe du Sud », « Nordics » — là où l'écran nomme
    des pays. Rattacher un marché au périmètre qui lui ressemble le plus enverrait une
    conversation à quelqu'un qui n'en est pas responsable, et personne ne le verrait."""
    org = perimeter.Org([
        _person(scope="Northland", zone="Eastland + Westland"),
        _person(first="B", scope="Southland", zone="Southern zone"),
    ], [])
    markets = ["Eastland", "Westland", "Midland"]

    assert perimeter.place(org, markets) == {"Eastland": "Northland",
                                             "Westland": "Northland"}
    assert perimeter.unplaced(org, markets) == ["Midland"]


def test_an_unknown_kind_of_attachment_is_refused_rather_than_assimilated(tmp_path):
    """Un rattachement que ce lecteur ne connaît pas est peut-être un troisième niveau.
    Le ranger d'office parmi les patrons de BU mettrait quelqu'un devant le CEO sans que
    personne l'ait décidé."""
    org = perimeter.load("/nowhere/at/all.xlsx")

    assert not org.usable
    assert org.faults


def test_the_team_of_a_perimeter_excludes_its_lead():
    """Les responsables pays s'affichent en détail. Ce qu'ils ne sont jamais, c'est le
    destinataire d'une conversation du CEO."""
    org = perimeter.Org([
        _person(scope="Northland", kind=perimeter.MD),
        _person(first="B", scope="Northland", kind=perimeter.COUNTRY_GM,
                manager="A NAME"),
        _person(first="C", scope="Northland", kind=perimeter.COUNTRY_GM,
                manager="A NAME"),
    ], [])

    team = org.team_of("Northland")
    assert len(team) == 2
    assert all(not person.answers_to_ceo for person in team)
