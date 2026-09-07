"""L'euro suivant en boutique, pays par pays.

Ces tests gardent trois choses : la pente est la mesure et sa précision se dit toujours ;
un pays sous le plancher n'a pas de pente et le dit ; le bail explique le côté d'où
récupérer l'euro suivant sans jamais devenir un chiffre. Toutes les valeurs sont inventées.
"""

from __future__ import annotations

import pathlib

from app.perf import retail_margin as R
from app.perf.analytics import format_eur

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "docs" / "incremental_margin_retail.example.csv"


def _read(tmp_path, text=None):
    path = tmp_path / "incremental_margin_retail.csv"
    path.write_text(text if text is not None else EXAMPLE.read_text(encoding="utf-8"),
                    encoding="utf-8")
    return R.load(str(path))


def test_the_example_file_reads_with_the_world_apart_and_the_countries_named(tmp_path):
    read = _read(tmp_path)

    assert not read.faults
    assert read.world is not None and read.world.market == R.WORLD
    assert [line.market for line in read.countries] == ["Northland", "Eastland", "Westland"]
    assert [line.market for line in read.measured] == ["Northland", "Eastland"]
    assert read.years == "FY2023 FY2024 FY2025 FY2026"


def test_the_sentence_says_the_measure_its_precision_the_drift_and_the_side(tmp_path):
    read = _read(tmp_path)
    north = read.of("Northland")

    assert north.precision == "haute" and north.precision_up == "moyenne"
    assert north.sentence.startswith(
        "un euro de plus en boutique en rapporte 44 centimes (600 observations, précision haute)")
    assert "45 centimes quand la boutique croît (précision moyenne)" in north.sentence
    assert "une boutique perd %s par an" % format_eur(9000.0) in north.sentence
    assert north.side == R.LANDLORD
    assert "le bailleur prend 21 centimes, l'exploitation en garde 73 centimes avant lui" in north.sentence
    assert north.sentence.endswith("c'est le bail qui pèse")


def test_a_negative_residual_says_that_growing_does_not_pay_before_the_landlord(tmp_path):
    east = _read(tmp_path).of("Eastland")

    assert east.side == R.OPERATIONS
    assert "croître n'y paie pas, et le bail n'y est pour rien" in east.sentence
    assert east.precision == "moyenne"


def test_a_country_under_the_floor_has_no_slope_and_says_why(tmp_path):
    west = _read(tmp_path).of("Westland")

    assert not west.measured
    assert west.sentence == "non mesuré : sous le plancher de 40 observations"


def test_market_names_follow_the_cockpit_and_the_world_is_recognised():
    assert R.normalise("UK") == "United Kingdom"
    assert R.normalise("USA") == "United States"
    assert R.normalise("CHINA") == "China"
    assert R.normalise("HK LOCAL") == "Hong Kong"
    assert R.normalise("MONDE") == R.WORLD


def test_a_perimeter_gets_its_markets_measured_first_by_slope(tmp_path):
    read = _read(tmp_path)

    lines = read.for_markets(["Westland", "Eastland", "Northland", "Nowhere"])

    assert [line.market for line in lines] == ["Northland", "Eastland", "Westland"]


def test_a_slope_without_r2_is_refused_rather_than_shown_precise(tmp_path):
    text = ("market,slope_pct,r2,method\n"
            "NORTHLAND,44.0,,pente\n")
    read = _read(tmp_path, text)

    assert not read.of("Northland").measured
    assert any("sans R²" in fault for fault in read.faults)


def test_missing_columns_and_missing_file_are_named_not_crashed(tmp_path):
    assert R.load(str(tmp_path / "absent.csv")).is_empty
    read = _read(tmp_path, "market,slope_pct\nNORTHLAND,44.0\n")
    assert read.is_empty and "colonnes manquantes" in read.faults[0]


def test_the_page_carries_the_lines_of_its_markets(tmp_path):
    from app.perf import page as page_module
    from app.perf.mock import dataset

    read = _read(tmp_path)
    data = dataset()
    built = page_module.build("Somewhere", "Quelqu'un", ["Northland", "Westland"], data, None,
                              None, retail=read)

    assert [line.market for line in built.retail] == ["Northland", "Westland"]
    assert built.retail_years == read.years
    assert page_module.build("Elsewhere", "", ["Nowhere"], data, None, None).retail == []


def test_a_fixed_lease_is_said_as_such_and_never_as_zero_cents(tmp_path):
    text = ("market,slope_pct,r2,method,residual_slope_pct,lease_pct\n"
            "SOUTHLAND,63.0,0.8,pente,56.0,0.0\n")
    south = _read(tmp_path, text).of("Southland")

    assert "0 centime" not in south.sentence
    assert "le bail est fixe, le bailleur ne prend rien sur l'euro suivant" in south.sentence


def test_the_page_carries_the_prepared_conversations_of_its_markets(tmp_path):
    from types import SimpleNamespace

    from app.perf import page as page_module
    from app.perf.mock import dataset

    here = SimpleNamespace(market="Northland", issue=SimpleNamespace(scopes=["Northland"]))
    away = SimpleNamespace(market="Elsewhere", issue=SimpleNamespace(scopes=["Elsewhere"]))
    watched = SimpleNamespace(issue=SimpleNamespace(scopes=["Northland"]), line="x")
    prepared = SimpleNamespace(conversations=[here, away], watch=[watched])

    built = page_module.build("Somewhere", "", ["Northland"], dataset(), None, None,
                              prepared=prepared)

    assert built.talks == [here] and built.watch_lines == [watched]
