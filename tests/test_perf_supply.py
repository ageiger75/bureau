"""Le rapport supply mensuel, lu comme une source. Marchés et valeurs inventés."""

from __future__ import annotations

from app.perf import supply as S


def _write(tmp_path, text):
    path = tmp_path / "supply.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_the_latest_month_is_read_and_the_sentences_follow_the_report_s_convention(tmp_path):
    path = _write(tmp_path, "\n".join([
        "month,scope,osa,in_full,forecast_accuracy,bias,forecast_growth,note",
        "2026-06,LOEP,97.5,96.0,50.0,1.0,2.0,",
        "2026-07,LOEP,97.6,96.4,58.3,-1.9,2.7,Q1 +3 · Q2 +3",
        "2026-07,Northland,,93.9,,-9,,transition de catalogue",
        "2026-07,Eastland,,,,8,,",
        "2026-07,Westland,99.0,98.5,60.0,-1,,",
    ]))
    review = S.load(path)

    assert review.month == "2026-07" and len(review.lines) == 4
    assert round(review.group.growth, 6) == 0.027 and round(review.group.in_full, 6) == 0.964
    assert review.forecast_sentence == ("prévision supply de juillet 2026 : l'exercice à +2.7 % sur "
                                        "le précédent (Q1 +3 · Q2 +3)")
    assert "sous la cible : Northland (sell-in livré en entier 93.9 %)" in review.service_sentence
    assert review.bias_sentence == ("vendent au-dessus de leur prévision : Northland -9 % · "
                                    "en dessous : Eastland +8 %")
    assert review.for_scope("northland").over_forecast
    assert review.markets[-1].bias_label == "-1.0 % (vend au-dessus de la prévision)"


def test_an_absent_or_malformed_file_is_a_stated_absence():
    assert not S.load("/nowhere/supply.csv").usable
    review = S.load(__file__)
    assert not review.usable and review.faults


def test_percent_cells_accept_the_report_s_spellings():
    assert round(S._pct("97.6"), 6) == 0.976 and round(S._pct("-1,9 %"), 6) == -0.019 and S._pct("") is None
    assert round(S._pct("−1.9"), 6) == -0.019
