"""The reader's judgement, and every rule it was written under.

A weight multiplies money. A typo moves a subject up or down the list the CEO reads on a
Monday, and the file is edited by hand between two looks at the screen — so every rule is
checked on load, and a broken row is refused and named rather than clamped into range.
"""

from __future__ import annotations

import io
import os

from app.perf import weights as W

HEADER = "market,channel,weight,confidence,evidence,reasoning\n"


def _file(tmp_path, body):
    path = tmp_path / "weights.csv"
    io.open(str(path), "w", encoding="utf-8").write(HEADER + body)
    return str(path)


def test_a_channel_row_overrides_its_market(tmp_path):
    loaded = W.load(_file(tmp_path,
                          'China,,1.40,FIRM,deck p1,pilier\n'
                          'China,webp,0.85,FIRM,deck p2,relais\n'))
    assert loaded.usable
    assert loaded.weight_for("China", "retail") == 1.40
    assert loaded.weight_for("China", "webp") == 0.85


def test_a_market_the_file_does_not_name_is_neutral(tmp_path):
    """Silence in the strategy is an answer, not a hole."""
    loaded = W.load(_file(tmp_path, 'China,,1.40,FIRM,deck,pilier\n'))
    assert loaded.weight_for("Portugal", "retail") == W.NEUTRAL


def test_a_weight_outside_the_band_is_refused_never_clamped(tmp_path):
    """Clamping would enact a decision nobody made, and say nothing about it."""
    loaded = W.load(_file(tmp_path, 'China,,2.50,FIRM,deck,trop haut\n'))
    assert not loaded.usable
    assert "hors des bornes" in loaded.faults[0]


def test_absent_may_only_be_neutral(tmp_path):
    """Without evidence a weight is an invention, and an invention moves attention."""
    loaded = W.load(_file(tmp_path, 'Spain,,1.30,ABSENT,,rien dans les documents\n'))
    assert not loaded.usable
    assert "ABSENT impose 1.00" in loaded.faults[0]


def test_a_claimed_weight_must_cite_something(tmp_path):
    loaded = W.load(_file(tmp_path, 'Spain,,1.30,FIRM,,parce que\n'))
    assert not loaded.usable
    assert "sans preuve" in loaded.faults[0]


def test_one_scope_cannot_carry_two_judgements(tmp_path):
    loaded = W.load(_file(tmp_path,
                          'China,,1.40,FIRM,deck,pilier\n'
                          'China,,1.10,FIRM,deck,autre avis\n'))
    assert not loaded.usable
    assert "déjà défini" in loaded.faults[0]


def test_a_file_that_half_parses_ranks_nothing(tmp_path):
    """Worse than no file: a ranking computed from half a judgement looks deliberate."""
    loaded = W.load(_file(tmp_path,
                          'China,,1.40,FIRM,deck,pilier\n'
                          'Spain,,9.00,FIRM,deck,faute\n'))
    assert not loaded.usable
    assert loaded.weight_for("China", "retail") == W.NEUTRAL


def test_a_missing_file_is_neutral_not_an_error(tmp_path):
    """The state the screen was in before the file existed. Degraded, never wrong."""
    loaded = W.load(str(tmp_path / "nothing.csv"))
    assert not loaded.usable
    assert loaded.weight_for("China", "retail") == W.NEUTRAL


def test_weights_on_business_the_plan_does_not_carry_are_named(tmp_path):
    loaded = W.load(_file(tmp_path,
                          'China,,1.40,FIRM,deck,pilier\n'
                          'Atlantis,,1.20,FIRM,deck,inconnu\n'))
    assert loaded.unknown_scopes((("China", "retail"),)) == ["Atlantis"]
