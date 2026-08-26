"""Parcours principaux : accueil → création → lecture → édition → persistance.

Les tests passent par le vrai formulaire HTML et vérifient que la donnée survit à un
nouveau chargement de page. Un test qui écrirait via l'ORM ne prouverait rien du parcours.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from app.main import app
from tests.conftest import create_case, page_text


# --------------------------------------------------------------------------- accueil


def test_accueil_repond_et_annonce_le_perimetre(client):
    response = client.get("/decisions")

    assert response.status_code == 200
    assert "Décisions" in page_text(response)
    # Le bandeau de périmètre doit être visible : un prototype ne doit pas passer pour
    # un outil authentifié dans lequel on dépose des données réelles.
    assert "Prototype" in page_text(response)
    assert "No authentication" in page_text(response)


def test_accueil_sans_dossier_propose_d_en_creer_un(client):
    response = client.get("/decisions")

    assert "Aucun dossier ouvert" in page_text(response)


def test_base_sans_utilisateur_affiche_un_ecran_d_amorcage(empty_client):
    """Plutôt qu'une page qui semble fonctionner avec zéro dossier."""
    response = empty_client.get("/decisions")

    assert response.status_code == 200
    assert "Base vide" in page_text(response)
    assert "app.cli seed" in page_text(response)


def test_sonde_de_sante(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --------------------------------------------------------------------------- création


def test_formulaire_de_creation_repond(client):
    response = client.get("/cases/new")

    assert response.status_code == 200
    assert "Question à trancher" in page_text(response)


def test_creation_puis_lecture(client):
    case_id = create_case(client, title="Flagship Milan")

    response = client.get("/cases/%s" % case_id)

    assert response.status_code == 200
    assert "Flagship Milan" in page_text(response)
    assert "Faut-il faire A plutôt que B" in page_text(response)
    assert "DR-" in page_text(response)  # référence lisible attribuée


def test_creation_apparait_sur_l_accueil(client):
    create_case(client, title="Dossier visible sur l'accueil")

    response = client.get("/decisions")

    assert "Dossier visible sur l'accueil" in page_text(response)


def test_creation_sans_question_est_refusee_avec_le_texte_conserve(client):
    response = client.post(
        "/cases",
        data={"title": "Titre saisi", "question": "", "confidentiality": "confidential"},
    )

    assert response.status_code == 400
    assert "La question à trancher est obligatoire" in page_text(response)
    # Le titre saisi est renvoyé : l'utilisateur ne doit pas retaper son texte.
    assert "Titre saisi" in page_text(response)


def test_creation_sans_titre_est_refusee(client):
    response = client.post(
        "/cases", data={"title": "", "question": "Une vraie question ?"}
    )

    assert response.status_code == 400
    assert "Le titre est obligatoire" in page_text(response)


def test_date_invalide_est_signalee(client):
    response = client.post(
        "/cases",
        data={"title": "T", "question": "Q ?", "deadline": "31/12/2026"},
    )

    assert response.status_code == 400
    assert "AAAA-MM-JJ" in page_text(response)


def test_confidentialite_falsifiee_est_refusee(client):
    """Une valeur d'énumération hors liste est une erreur, pas une valeur à corriger."""
    response = client.post(
        "/cases",
        data={"title": "T", "question": "Q ?", "confidentiality": "public"},
    )

    assert response.status_code == 400
    assert "Valeur inattendue" in page_text(response)


def test_references_sont_sequentielles(client):
    first = page_text(client.get("/cases/%s" % create_case(client, title="Un")))
    second = page_text(client.get("/cases/%s" % create_case(client, title="Deux")))

    assert "001" in first
    assert "002" in second


# --------------------------------------------------------------------------- cadrage


def test_cadrage_est_enregistre_et_relu(client):
    case_id = create_case(client)

    client.post(
        "/cases/%s/framing" % case_id,
        data={
            "title": "Titre révisé",
            "question": "Question révisée ?",
            "context": "Contexte révisé.",
            "deadline": "2027-01-15",
            "confidentiality": "strictly_confidential",
            "real_decision": "La vraie décision est ailleurs.",
            "scope_out": "Le prix\nLe calendrier produit",
            "constraints": "Réponse sous trois jours",
            "blind_spot": "Nous mesurons le trafic, pas le retour client.",
            "executive_summary": "Synthèse de test.",
        },
    )

    page = page_text(client.get("/cases/%s" % case_id))
    assert "Titre révisé" in page
    assert "La vraie décision est ailleurs." in page
    assert "Nous mesurons le trafic, pas le retour client." in page
    assert "Synthèse de test." in page
    assert "Strictement confidentiel" in page


def test_cadrage_refuse_une_question_vide_sans_ecraser_l_existant(client):
    case_id = create_case(client, question="Question initiale ?")

    client.post(
        "/cases/%s/framing" % case_id,
        data={"title": "Titre", "question": ""},
    )

    page = page_text(client.get("/cases/%s" % case_id))
    assert "Question initiale ?" in page


# --------------------------------------------------------------------------- affirmations


def test_fait_sans_source_est_enregistre_et_signale(client):
    """Le choix produit : avertissement, pas refus. Le fait entre, et il est marqué."""
    case_id = create_case(client)

    client.post(
        "/cases/%s/claims" % case_id,
        data={
            "text": "Le marché italien croît de 8 % par an.",
            "category": "sourced_fact",
            "materiality": "high",
        },
    )

    page = page_text(client.get("/cases/%s" % case_id))
    assert "Le marché italien croît de 8 % par an." in page
    assert "Aucune source" in page
    assert "relié à aucune source" in page


def test_fait_source_est_affiche_avec_sa_source(client):
    case_id = create_case(client)

    client.post(
        "/cases/%s/claims" % case_id,
        data={
            "text": "Le droit d'entrée est non récupérable.",
            "category": "sourced_fact",
            "source_ref": "Projet de bail, art. 14",
            "quote": "Le droit d'entrée reste acquis au bailleur.",
            "materiality": "high",
        },
    )

    page = page_text(client.get("/cases/%s" % case_id))
    assert "Projet de bail, art. 14" in page
    assert "Le droit d'entrée reste acquis au bailleur." in page


def test_affirmation_vide_est_refusee(client):
    """L'erreur est affichée sur la page qui suit la redirection.

    Un message éphémère n'est lisible qu'une fois : il faut donc l'observer sur la réponse
    du POST — un GET ultérieur l'aurait déjà consommé.
    """
    case_id = create_case(client)

    response = client.post(
        "/cases/%s/claims" % case_id,
        data={"text": "", "category": "assumption"},
        follow_redirects=True,
    )

    assert "ne peut pas être vide" in page_text(response)


def test_affirmation_est_modifiable(client):
    case_id = create_case(client)
    client.post(
        "/cases/%s/claims" % case_id,
        data={"text": "Version initiale.", "category": "assumption"},
    )
    claim_id = _first_claim_id(case_id)

    client.post(
        "/cases/%s/claims/%s" % (case_id, claim_id),
        data={
            "text": "Version corrigée.",
            "category": "sourced_fact",
            "source_ref": "Note interne, juin 2026",
            "quote": "Extrait.",
            "materiality": "medium",
        },
    )

    page = page_text(client.get("/cases/%s" % case_id))
    assert "Version corrigée." in page
    assert "Version initiale." not in page
    assert "Note interne, juin 2026" in page


def test_affirmation_est_supprimable(client):
    case_id = create_case(client)
    client.post(
        "/cases/%s/claims" % case_id,
        data={"text": "À retirer.", "category": "opinion"},
    )
    claim_id = _first_claim_id(case_id)

    client.post("/cases/%s/claims/%s/delete" % (case_id, claim_id))

    assert "À retirer." not in page_text(client.get("/cases/%s" % case_id))


def test_affirmation_d_un_autre_dossier_est_inaccessible(client):
    """Un identifiant seul ne doit jamais suffire à atteindre le contenu d'un autre dossier."""
    case_a = create_case(client, title="Dossier A")
    case_b = create_case(client, title="Dossier B")
    client.post(
        "/cases/%s/claims" % case_a,
        data={"text": "Affirmation du dossier A.", "category": "assumption"},
    )
    claim_id = _first_claim_id(case_a)

    client.post(
        "/cases/%s/claims/%s" % (case_b, claim_id),
        data={"text": "Tentative depuis B.", "category": "assumption"},
    )

    assert "Affirmation du dossier A." in page_text(client.get("/cases/%s" % case_a))
    assert "Tentative depuis B." not in page_text(client.get("/cases/%s" % case_a))


# --------------------------------------------------------------------------- options


def test_options_sont_ajoutees_et_relues(client):
    case_id = create_case(client)

    _add_option(client, case_id, "Ouvrir avant décembre", risks="Trois ans fermes")
    _add_option(client, case_id, "Ne rien faire", status_quo=True)

    page = page_text(client.get("/cases/%s" % case_id))
    assert "Ouvrir avant décembre" in page
    assert "Ne rien faire" in page
    assert "Trois ans fermes" in page
    assert "Statu quo" in page


def test_option_sans_nom_est_refusee(client):
    case_id = create_case(client)

    response = client.post(
        "/cases/%s/options" % case_id, data={"name": ""}, follow_redirects=True
    )

    assert "Le nom de l'option est obligatoire" in page_text(response)
    assert "0 option ·" in page_text(client.get("/cases/%s" % case_id))


def test_quatrieme_option_declenche_un_avertissement(client):
    case_id = create_case(client)
    for name in ("A", "B", "C"):
        _add_option(client, case_id, name)

    response = client.post(
        "/cases/%s/options" % case_id, data={"name": "D"}, follow_redirects=True
    )

    assert "Plus de trois options" in page_text(response)


def test_supprimer_l_option_recommandee_detache_la_recommandation(client):
    case_id = create_case(client)
    _add_option(client, case_id, "Option retenue")
    option_id = _first_option_id(case_id)
    client.post(
        "/cases/%s/recommendation" % case_id,
        data={
            "option_id": option_id,
            "position": "Je ferais ceci.",
            "would_change_if": "Si le trafic est infirmé.",
        },
    )

    response = client.post(
        "/cases/%s/options/%s/delete" % (case_id, option_id), follow_redirects=True
    )

    assert response.status_code == 200
    assert "ne désigne plus aucune option" in page_text(response)


# --------------------------------------------------------------------------- recommandation


def test_recommandation_exige_position_et_conditions_d_invalidation(client):
    """Le brief §4 : une recommandation qu'aucun fait ne pourrait invalider n'en est pas une.

    Ces deux champs sont refusés, et non signalés par un avertissement : contrairement à un
    fait sans source, il n'y a ici aucune information à conserver.
    """
    case_id = create_case(client)

    response = client.post(
        "/cases/%s/recommendation" % case_id,
        data={"position": "Je ferais ceci.", "would_change_if": ""},
        follow_redirects=True,
    )

    assert "Préciser ce qui ferait changer d'avis" in page_text(response)
    # Rien n'a été enregistré : le dossier n'affiche toujours aucune position.
    assert "Aucune position prise" in page_text(client.get("/cases/%s" % case_id))


def test_recommandation_est_enregistree_et_relue(client):
    case_id = create_case(client)
    _add_option(client, case_id, "Réduction progressive")
    option_id = _first_option_id(case_id)

    client.post(
        "/cases/%s/recommendation" % case_id,
        data={
            "option_id": option_id,
            "position": "Je réduirais progressivement.",
            "reasons": "Le recul du prix plein est sourcé",
            "would_change_if": "Si la perte de volume dépasse 8 %",
            "open_disagreements": "La direction commerciale estime la perte au double.",
        },
    )

    page = page_text(client.get("/cases/%s" % case_id))
    assert "Je réduirais progressivement." in page
    assert "Voilà ce que je ferais" in page
    assert "Si la perte de volume dépasse 8 %" in page
    # Les désaccords ne sont jamais masqués (brief §9).
    assert "La direction commerciale estime la perte au double." in page


def test_recommandation_est_modifiable_sans_doublon(client):
    case_id = create_case(client)
    for position in ("Première position.", "Position révisée."):
        client.post(
            "/cases/%s/recommendation" % case_id,
            data={"position": position, "would_change_if": "Condition."},
        )

    page = page_text(client.get("/cases/%s" % case_id))
    assert "Position révisée." in page
    assert "Première position." not in page


# --------------------------------------------------------------------------- cycle de vie


def test_parcours_complet_jusqu_a_pret_a_decider(client):
    """La tranche verticale de bout en bout : créer, sourcer, comparer, prendre position."""
    case_id = create_case(client, title="Calendrier promotionnel")

    client.post(
        "/cases/%s/claims" % case_id,
        data={
            "text": "La part de prix plein recule de 13 points en trois ans.",
            "category": "sourced_fact",
            "source_ref": "Revue commerciale 2026, tableau 3.2",
            "quote": "61 % (2023) → 48 % (2026).",
            "materiality": "high",
        },
    )
    client.post(
        "/cases/%s/claims" % case_id,
        data={
            "text": "La perte de volume restera sous 6 %.",
            "category": "assumption",
            "rationale": "Élasticité observée sur deux temps forts.",
            "best_test": "Tester sur un marché comparable.",
            "materiality": "high",
        },
    )
    _add_option(client, case_id, "Réduction progressive")
    _add_option(client, case_id, "Statu quo", status_quo=True)
    # Le dossier doit avoir été contesté, et la prémisse avoir reçu une réponse.
    _add_challenge(
        client,
        case_id,
        objection="L'élasticité retenue vient de deux temps forts seulement.",
        evidence="Analyse 2025, deux observations.",
        response="Un marché test tranchera avant généralisation.",
        status="answered",
    )
    client.post(
        "/cases/%s/recommendation" % case_id,
        data={
            "position": "Je réduirais progressivement.",
            "would_change_if": "Si la perte de volume dépasse 8 %.",
        },
    )

    # Brouillon → En analyse → Prêt à décider
    client.post("/cases/%s/status" % case_id, data={"status": "analysis"})
    response = client.post(
        "/cases/%s/status" % case_id, data={"status": "ready"}, follow_redirects=True
    )

    assert "Prêt à décider" in page_text(response)
    assert "Aucun bloquant" in page_text(response)


def test_dossier_incomplet_ne_passe_pas_en_pret(client):
    case_id = create_case(client)
    client.post("/cases/%s/status" % case_id, data={"status": "analysis"})

    response = client.post(
        "/cases/%s/status" % case_id, data={"status": "ready"}, follow_redirects=True
    )

    assert "n'est pas prêt" in page_text(response)


def test_passer_en_decide_sans_enregistrer_la_decision_est_refuse(client):
    """Changer le statut ne doit pas suffire : le brief §2 reproche précisément aux
    réunions de produire une décision dont les raisons sont perdues."""
    case_id = create_case(client)

    response = client.post(
        "/cases/%s/status" % case_id, data={"status": "decided"}, follow_redirects=True
    )

    assert "non prévu" in page_text(response) or "écran Décision" in page_text(response)


def test_diagnostic_est_affiche_sur_le_dossier(client):
    case_id = create_case(client)

    page = page_text(client.get("/cases/%s" % case_id))

    assert "Ce qui empêche de décider" in page
    assert "Aucune position prise" in page
    assert "jamais été contesté" in page


# --------------------------------------------------------------------------- erreurs et accès


def test_dossier_inconnu_repond_404_lisible(client):
    response = client.get("/cases/inexistant")

    assert response.status_code == 404
    assert "Erreur 404" in page_text(response)


def test_requete_non_locale_est_refusee(ceo):
    """Second verrou derrière `uvicorn --host 127.0.0.1` : un dossier confidentiel ne doit
    pas devenir accessible parce qu'une commande a été lancée avec --host 0.0.0.0."""
    del ceo
    with TestClient(app, client=("203.0.113.7", 51234)) as remote:
        response = remote.get("/decisions")

    assert response.status_code == 403
    assert "machine locale" in page_text(response)


def test_entetes_de_securite_sont_poses(client):
    response = client.get("/decisions")

    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_html_est_echappe(client):
    """Le contenu vient de documents externes : une balise saisie doit rester du texte.

    Seul test à lire le HTML brut : c'est précisément l'échappement qu'il vérifie.
    """
    case_id = create_case(client, title="<script>alert(1)</script>")

    raw = client.get("/cases/%s" % case_id).text

    assert "<script>alert(1)</script>" not in raw
    assert "&lt;script&gt;" in raw


# --------------------------------------------------------------------------- données fictives


def test_donnees_de_demonstration_exposent_leurs_defauts(seeded_client):
    """Le jeu de démonstration est volontairement imparfait : il sert à vérifier que
    l'outil signale, pas à afficher une belle page."""
    page = page_text(seeded_client.get("/decisions"))

    assert "DR-2026-001" in page
    assert "DR-2026-002" in page
    assert "DR-2026-003" in page
    assert "Demande attention" in page


def test_dossier_de_demonstration_avec_fait_non_source_est_signale(seeded_client):
    """DR-2026-001 porte trois défauts volontaires : un fait sans source, deux comptages
    divergents et aucune recommandation. Ils doivent tous être visibles."""
    case_id = _case_id_by_reference("DR-2026-001")

    page = page_text(seeded_client.get("/cases/%s" % case_id))

    assert "Aucune source" in page
    assert "relié à aucune source" in page
    assert "Aucune position prise" in page
    # Les deux chiffres de trafic coexistent : aucun n'est arbitrairement retenu.
    assert "42 000" in page
    assert "28 000" in page


# --------------------------------------------------------------------------- utilitaires


def _add_option(client, case_id: str, name: str, status_quo: bool = False, **extra) -> None:
    data = {"name": name, "reversibility": "costly"}
    if status_quo:
        data["is_status_quo"] = "1"
    data.update(extra)
    client.post("/cases/%s/options" % case_id, data=data)


def _add_challenge(client, case_id: str, objection: str, **extra) -> None:
    data = {
        "objection": objection,
        "voice": "devils_advocate",
        "kind": "premise",
        "severity": "serious",
    }
    data.update(extra)
    client.post("/cases/%s/challenges" % case_id, data=data)


def _first_claim_id(case_id: str) -> str:
    from app.db import SessionFactory
    from app.models import Claim

    with SessionFactory() as session:
        from sqlalchemy import select

        claim = session.scalars(select(Claim).where(Claim.case_id == case_id)).first()
        assert claim is not None
        return claim.id


def _first_option_id(case_id: str) -> str:
    from sqlalchemy import select

    from app.db import SessionFactory
    from app.models import Option

    with SessionFactory() as session:
        option = session.scalars(select(Option).where(Option.case_id == case_id)).first()
        assert option is not None
        return option.id


def _case_id_by_reference(reference: str) -> str:
    from sqlalchemy import select

    from app.db import SessionFactory
    from app.models import DecisionCase

    with SessionFactory() as session:
        case = session.scalars(
            select(DecisionCase).where(DecisionCase.reference == reference)
        ).first()
        assert case is not None, "dossier %s absent du jeu de démonstration" % reference
        return case.id
