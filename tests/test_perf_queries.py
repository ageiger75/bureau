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
