"""Les requêtes de la consolidation : ce que leur texte doit garder.

Un instantané de consolidation daté dans le futur est apparu le 3 novembre 2026, à la fin
de l'exercice, sans que personne sache ce qu'il porte. Anchoré dessus, le sell-in consolidé
aurait pris une prévision ou des zéros pour l'exercice clos. Ces tests gardent la garde,
pas les chiffres : rien ici ne lit l'entrepôt.
"""

from __future__ import annotations

from app.perf import queries


def test_the_consolidation_never_anchors_on_a_snapshot_dated_in_the_future():
    assert queries.SELL_IN.count("snapshot_date <= current_date") == 1
    assert queries.SELL_IN_HISTORY.count("snapshot_date <= current_date") == 2
    # La garde vient avant le choix de l'instantané de référence, pas après.
    assert queries.SELL_IN.index("snapshot_date <= current_date") < queries.SELL_IN.index("freshness = 1")


def test_the_balance_query_keeps_the_contract_measured_by_the_warehouse_agent():
    """Le compte parent, les centres commerciaux hors intragroupe, les dimensions
    dédoublonnées sur leur version courante, le local au taux annuel, le mois borné au
    mois écoulé — et la requête nommée pour l'empreinte de son cache."""
    text = queries.BALANCE_MONTH
    assert "acc_p3_sig_c = 'PL100'" in text
    assert "bs_pcc_p6_c = 'CHANNELS'" in text
    assert "not in ('INT', 'TRA_INT', 'B2B_INT')" in text
    assert text.count("curr_ind = 'Y'") == 2 and text.count("select distinct") == 2
    assert "/ any_value(r.annual_rate)" in text and "actual_amount_eur" not in text
    assert "actual_amount_local is not null" in text
    assert "add_months(date_trunc('month', current_date), -1)" in text
    assert queries.ALL["BALANCE_MONTH"] is queries.BALANCE_MONTH
