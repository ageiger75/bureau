"""Archive : « Dossier archivé et retrouvable » (brief §6).

Retrouvable veut dire atteignable depuis l'interface. Un dossier qui n'existe plus qu'au
bout d'une adresse conservée ailleurs n'est pas archivé, il est perdu proprement — et la
leçon de sa revue, seul produit réutilisable d'une décision passée, l'est avec lui.

Le parcours de clôture n'est pas réécrit ici : il est importé du fichier qui en fait foi,
pour qu'une seule définition de « mener un dossier jusqu'à sa revue » existe dans la suite.
"""

from __future__ import annotations

from app.models import Review
from tests.conftest import create_case, page_text
from tests.test_web_decision_loop import _first, _to_review, build_ready_case


def close_case(client, title: str, lessons: str, option_index: int = 1) -> str:
    """Mène un dossier jusqu'à sa clôture par la revue, et retourne son identifiant.

    `option_index` permet de décider contre la recommandation, qui désigne l'index 1.
    """
    case_id = build_ready_case(client, title=title)
    review_id = _to_review(client, case_id, option_index=option_index)
    client.post(
        "/cases/%s/review/%s/complete" % (case_id, review_id),
        data={
            "observed_results": "Zone revenue à l'équilibre.",
            "lessons": lessons,
            "next_step": "keep",
        },
    )
    assert _first(Review, case_id).is_completed
    return case_id


def test_archive_vide_le_dit_plutot_que_d_afficher_une_page_blanche(client):
    response = client.get("/cases")

    assert response.status_code == 200
    assert "Aucun dossier clos" in page_text(response)


def test_dossier_clos_est_retrouvable_depuis_l_archive(client):
    close_case(
        client,
        "Sortie de trois emplacements",
        "Mesurer l'effet digital avant de fermer, pas après.",
    )

    page = page_text(client.get("/cases"))

    assert "Sortie de trois emplacements" in page
    # La leçon s'affiche sans qu'il faille ouvrir le dossier : c'est ce qui la rend réutilisable.
    assert "Mesurer l'effet digital avant de fermer" in page


def test_archive_est_atteignable_depuis_l_accueil(client):
    """Sans ce lien, l'archive existerait sans que personne puisse y arriver."""
    assert 'href="/cases"' in client.get("/").text


def test_dossier_ouvert_ne_figure_pas_dans_l_archive(client):
    create_case(client, title="Dossier encore ouvert")

    assert "Dossier encore ouvert" not in page_text(client.get("/cases"))


def test_archive_date_le_jour_ou_la_revue_s_est_tenue(client):
    """Pas la date prévue : ce qui compte est le jour où les faits ont été confrontés."""
    from app.util import today_iso

    close_case(client, "Dossier daté", "Une leçon.")

    assert today_iso() in page_text(client.get("/cases"))


def test_ecart_avec_la_recommandation_reste_visible_apres_cloture(client):
    """C'est précisément ce qu'on relit à froid : l'outil disait autre chose."""
    close_case(
        client,
        "Décision contre l'avis de l'outil",
        "L'outil avait raison sur l'effet digital.",
        option_index=0,
    )

    assert "Écart avec la recommandation" in page_text(client.get("/cases"))


def test_dossier_suivant_la_recommandation_n_est_pas_marque_en_ecart(client):
    close_case(client, "Décision alignée", "Rien à signaler.", option_index=1)

    assert "Écart avec la recommandation" not in page_text(client.get("/cases"))
