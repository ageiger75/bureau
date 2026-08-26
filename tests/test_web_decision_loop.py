"""Boucle décisionnelle complète : créer → contester → décider → suivre → apprendre.

Le brief §19 définit le « terminé » du MVP par ce parcours : « le parcours complet, de la
création du dossier à la revue, fonctionne dans un environnement de pilote ». Ce fichier
en est la traduction exécutable.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db import SessionFactory
from app.models import (
    Challenge,
    Commitment,
    DecisionCase,
    DecisionRecord,
    Option,
    Review,
)
from tests.conftest import create_case, page_text


# --------------------------------------------------------------------------- utilitaires


def _add_option(client, case_id: str, name: str, status_quo: bool = False) -> None:
    data = {"name": name, "reversibility": "costly"}
    if status_quo:
        data["is_status_quo"] = "1"
    client.post("/cases/%s/options" % case_id, data=data)


def _add_challenge(client, case_id: str, **overrides) -> None:
    data = {
        "objection": "La prémisse centrale n'est appuyée que sur deux observations.",
        "voice": "devils_advocate",
        "kind": "premise",
        "severity": "serious",
        "evidence": "Deux observations seulement.",
        "response": "Un test tranchera avant généralisation.",
        "status": "answered",
    }
    data.update(overrides)
    client.post("/cases/%s/challenges" % case_id, data=data)


def _option_ids(case_id: str):
    with SessionFactory() as session:
        return [
            o.id
            for o in session.scalars(
                select(Option).where(Option.case_id == case_id).order_by(Option.ordinal)
            ).all()
        ]


def _case_status(case_id: str) -> str:
    with SessionFactory() as session:
        return session.get(DecisionCase, case_id).status


def _first(model, case_id: str):
    with SessionFactory() as session:
        return session.scalars(select(model).where(model.case_id == case_id)).first()


def build_ready_case(client, title: str = "Sortie de trois emplacements") -> str:
    """Amène un dossier jusqu'à « Prêt à décider » par l'interface."""
    case_id = create_case(client, title=title)
    client.post(
        "/cases/%s/claims" % case_id,
        data={
            "text": "Les trois sites sont déficitaires depuis deux exercices.",
            "category": "sourced_fact",
            "source_ref": "Reporting retail, mars 2026",
            "quote": "Résultat d'exploitation négatif sur 24 mois.",
            "materiality": "high",
        },
    )
    client.post(
        "/cases/%s/claims" % case_id,
        data={
            "text": "Le reclassement se fera sans départ contraint.",
            "category": "assumption",
            "rationale": "Estimation People.",
            "best_test": "Recenser les postes ouverts par pays.",
            "materiality": "high",
        },
    )
    _add_option(client, case_id, "Fermer les trois")
    _add_option(client, case_id, "Fermer deux, garder le troisième")
    _add_option(client, case_id, "Statu quo", status_quo=True)
    _add_challenge(client, case_id)
    client.post(
        "/cases/%s/recommendation" % case_id,
        data={
            "option_id": _option_ids(case_id)[1],
            "position": "Je fermerais deux sites et garderais le troisième.",
            "reasons": "La perte est sourcée, l'effet digital ne l'est pas.",
            "would_change_if": "Si le bail du troisième ne peut pas être prolongé.",
        },
    )
    client.post("/cases/%s/status" % case_id, data={"status": "analysis"})
    client.post("/cases/%s/status" % case_id, data={"status": "ready"})
    assert _case_status(case_id) == "ready"
    return case_id


def decide(client, case_id: str, option_index: int = 1, **overrides):
    data = {
        "option_id": _option_ids(case_id)[option_index],
        "reasons": "La fenêtre de sortie ne se représentera pas.",
        "reservations": "L'effet sur le digital reste inconnu.",
        "success_criteria": "Aucun départ contraint. Zone à l'équilibre au T1 2027.",
        "change_conditions": "Recul des ventes en ligne de plus de 15 %.",
        "review_date": "2026-11-30",
    }
    data.update(overrides)
    return client.post(
        "/cases/%s/decision" % case_id, data=data, follow_redirects=True
    )


# --------------------------------------------------------------------------- challenge


def test_dossier_non_conteste_ne_peut_pas_etre_declare_pret(client):
    """Le risque principal du produit : confirmer l'intuition de départ."""
    case_id = create_case(client)
    client.post(
        "/cases/%s/claims" % case_id,
        data={"text": "Une hypothèse.", "category": "assumption", "rationale": "X"},
    )
    _add_option(client, case_id, "A")
    _add_option(client, case_id, "B", status_quo=True)
    client.post(
        "/cases/%s/recommendation" % case_id,
        data={"position": "Je ferais A.", "would_change_if": "Si B devient viable."},
    )
    client.post("/cases/%s/status" % case_id, data={"status": "analysis"})

    response = client.post(
        "/cases/%s/status" % case_id, data={"status": "ready"}, follow_redirects=True
    )

    assert "jamais été contesté" in page_text(response)
    assert _case_status(case_id) == "analysis"


def test_objection_bloquante_sans_reponse_empeche_de_declarer_pret(client):
    case_id = create_case(client)
    client.post(
        "/cases/%s/claims" % case_id,
        data={"text": "Une hypothèse.", "category": "assumption", "rationale": "X"},
    )
    _add_option(client, case_id, "A")
    _add_option(client, case_id, "B", status_quo=True)
    _add_challenge(client, case_id, severity="blocking", status="open", response="")
    client.post(
        "/cases/%s/recommendation" % case_id,
        data={"position": "Je ferais A.", "would_change_if": "Si B devient viable."},
    )
    client.post("/cases/%s/status" % case_id, data={"status": "analysis"})

    response = client.post(
        "/cases/%s/status" % case_id, data={"status": "ready"}, follow_redirects=True
    )

    assert "bloquante" in page_text(response)
    assert _case_status(case_id) == "analysis"


def test_objection_sans_preuve_est_enregistree_et_signalee(client):
    case_id = create_case(client)

    response = client.post(
        "/cases/%s/challenges" % case_id,
        data={
            "objection": "C'est plus risqué qu'annoncé.",
            "voice": "finance",
            "kind": "premise",
            "severity": "serious",
            "evidence": "",
        },
        follow_redirects=True,
    )

    page = page_text(response)
    assert "C'est plus risqué qu'annoncé." in page
    assert "sans élément concret" in page


def test_objection_est_modifiable_et_horodatee(client):
    case_id = create_case(client)
    _add_challenge(client, case_id, status="open", response="")
    item = _first(Challenge, case_id)

    client.post(
        "/cases/%s/challenges/%s" % (case_id, item.id),
        data={
            "objection": item.objection,
            "voice": item.voice,
            "kind": item.kind,
            "severity": item.severity,
            "evidence": item.evidence,
            "response": "Objection retenue, l'option a été revue.",
            "status": "accepted",
        },
    )

    page = page_text(client.get("/cases/%s" % case_id))
    assert "Objection retenue, l'option a été revue." in page
    assert "Acceptée" in page


def test_objection_d_un_autre_dossier_est_inaccessible(client):
    case_a = create_case(client, title="Dossier A")
    case_b = create_case(client, title="Dossier B")
    _add_challenge(client, case_a, objection="Objection du dossier A.")
    item = _first(Challenge, case_a)

    client.post(
        "/cases/%s/challenges/%s" % (case_b, item.id),
        data={"objection": "Tentative depuis B.", "voice": "finance", "kind": "premise"},
    )

    assert "Objection du dossier A." in page_text(client.get("/cases/%s" % case_a))


# --------------------------------------------------------------------------- décision


def test_decision_enregistree_fait_passer_le_dossier_en_decide(client):
    case_id = build_ready_case(client)

    response = decide(client, case_id)

    page = page_text(response)
    assert "Décision enregistrée" in page
    assert _case_status(case_id) == "decided"


def test_decision_cree_la_revue_a_la_date_choisie(client):
    """Une revue qu'il faut penser à planifier n'a jamais lieu."""
    case_id = build_ready_case(client)

    decide(client, case_id, review_date="2027-02-15")

    review = _first(Review, case_id)
    assert review is not None
    assert review.planned_date == "2027-02-15"
    # Les attentes d'origine sont figées au moment de la décision.
    assert "Aucun départ contraint" in review.initial_expectations


def test_decision_sans_criteres_de_succes_est_refusee(client):
    case_id = build_ready_case(client)

    response = decide(client, case_id, success_criteria="")

    assert "critères de succès sont obligatoires" in page_text(response)
    assert _first(DecisionRecord, case_id) is None
    assert _case_status(case_id) == "ready"


def test_decision_sans_date_de_revue_est_refusee(client):
    case_id = build_ready_case(client)

    response = decide(client, case_id, review_date="")

    assert "date de revue" in page_text(response)
    assert _first(DecisionRecord, case_id) is None


def test_divergence_avec_la_recommandation_est_deduite_pas_seulement_declaree(client):
    """Le CEO ne doit pas avoir à cocher une case pour que l'écart soit visible à la revue."""
    case_id = build_ready_case(client)
    # La recommandation désigne l'option d'index 1 ; on en choisit une autre.
    decide(client, case_id, option_index=0)

    decision = _first(DecisionRecord, case_id)
    assert decision.diverges_from_recommendation is True


def test_divergence_sans_raison_ecrite_est_signalee(client):
    case_id = build_ready_case(client)

    response = decide(client, case_id, option_index=0)

    assert "sans que la raison soit écrite" in page_text(response)


def test_suivre_la_recommandation_ne_marque_aucune_divergence(client):
    case_id = build_ready_case(client)

    decide(client, case_id, option_index=1)

    assert _first(DecisionRecord, case_id).diverges_from_recommendation is False


def test_dossier_non_pret_ne_peut_pas_etre_decide_par_le_formulaire(client):
    """Sinon le diagnostic deviendrait un avis qu'il suffit de contourner d'écran."""
    case_id = create_case(client)
    _add_option(client, case_id, "A")

    response = client.post(
        "/cases/%s/decision" % case_id,
        data={
            "option_id": _option_ids(case_id)[0],
            "reasons": "Parce que.",
            "success_criteria": "Ça marchera.",
            "review_date": "2026-12-01",
        },
        follow_redirects=True,
    )

    assert "n'est pas prêt à décider" in page_text(response)
    assert _first(DecisionRecord, case_id) is None


def test_decision_est_modifiable_sans_creer_de_doublon(client):
    case_id = build_ready_case(client)
    decide(client, case_id)
    decide(client, case_id, reasons="Raison révisée après échange avec le COMEX.")

    page = page_text(client.get("/cases/%s" % case_id))
    assert "Raison révisée après échange avec le COMEX." in page

    with SessionFactory() as session:
        records = session.scalars(
            select(DecisionRecord).where(DecisionRecord.case_id == case_id)
        ).all()
        reviews = session.scalars(select(Review).where(Review.case_id == case_id)).all()
    assert len(records) == 1
    # Ré-arbitrer déplace la revue, il n'en empile pas une seconde.
    assert len(reviews) == 1


# --------------------------------------------------------------------------- engagements


def test_executer_exige_au_moins_un_engagement(client):
    case_id = build_ready_case(client)
    decide(client, case_id)

    response = client.post(
        "/cases/%s/status" % case_id, data={"status": "executing"}, follow_redirects=True
    )

    assert "elle s'oublie" in page_text(response)
    assert _case_status(case_id) == "decided"


def test_engagement_ajoute_puis_passage_en_execution(client):
    case_id = build_ready_case(client)
    decide(client, case_id)

    response = client.post(
        "/cases/%s/commitments" % case_id,
        data={
            "action": "Mettre en place le suivi mensuel des ventes en ligne.",
            "owner_name": "Direction e-commerce",
            "due_date": "2026-09-30",
            "status": "open",
            "is_critical": "1",
        },
        follow_redirects=True,
    )
    assert "Aucun message n'a été envoyé" in page_text(response)

    client.post("/cases/%s/status" % case_id, data={"status": "executing"})
    assert _case_status(case_id) == "executing"


def test_engagement_sans_proprietaire_est_signale(client):
    case_id = build_ready_case(client)
    decide(client, case_id)

    response = client.post(
        "/cases/%s/commitments" % case_id,
        data={"action": "Faire quelque chose.", "owner_name": "", "status": "open"},
        follow_redirects=True,
    )

    page = page_text(response)
    assert "sans propriétaire nommé" in page
    assert "n'est le nom de personne" in page


def test_engagement_en_retard_remonte_sur_l_accueil(client):
    case_id = build_ready_case(client)
    decide(client, case_id)
    client.post(
        "/cases/%s/commitments" % case_id,
        data={
            "action": "Action déjà en retard.",
            "owner_name": "Direction immobilier",
            "due_date": "2026-01-15",
            "status": "open",
            "is_critical": "1",
        },
    )

    page = page_text(client.get("/"))
    assert "Engagements en retard" in page
    assert "Action déjà en retard." in page
    assert "Critique" in page


def test_engagement_termine_ne_remonte_pas_comme_en_retard(client):
    case_id = build_ready_case(client)
    decide(client, case_id)
    client.post(
        "/cases/%s/commitments" % case_id,
        data={
            "action": "Action ancienne mais terminée.",
            "owner_name": "Direction People",
            "due_date": "2026-01-15",
            "status": "done",
            "evidence": "Note du 6 mai.",
        },
    )

    assert "Action ancienne mais terminée." not in page_text(client.get("/"))


def test_rearbitrage_demande_est_signale(client):
    case_id = build_ready_case(client)
    decide(client, case_id)
    client.post(
        "/cases/%s/commitments" % case_id,
        data={"action": "Action bloquée.", "owner_name": "X", "status": "open"},
    )
    item = _first(Commitment, case_id)

    response = client.post(
        "/cases/%s/commitments/%s" % (case_id, item.id),
        data={
            "action": item.action,
            "owner_name": item.owner_name,
            "status": "rearbitration_needed",
        },
        follow_redirects=True,
    )

    assert "La décision d'origine est en cause" in page_text(response)


def test_engagement_d_un_autre_dossier_est_inaccessible(client):
    case_a = build_ready_case(client, title="Dossier A")
    decide(client, case_a)
    client.post(
        "/cases/%s/commitments" % case_a,
        data={"action": "Engagement du dossier A.", "owner_name": "X", "status": "open"},
    )
    item = _first(Commitment, case_a)
    case_b = create_case(client, title="Dossier B")

    client.post(
        "/cases/%s/commitments/%s" % (case_b, item.id),
        data={"action": "Tentative depuis B.", "owner_name": "Y", "status": "open"},
    )

    assert "Engagement du dossier A." in page_text(client.get("/cases/%s" % case_a))


# --------------------------------------------------------------------------- revue


def _to_review(client, case_id: str, option_index: int = 1) -> str:
    # Revue déjà échue : c'est le signal que le dossier doit remonter sur l'accueil.
    decide(client, case_id, option_index=option_index, review_date="2026-01-31")
    client.post(
        "/cases/%s/commitments" % case_id,
        data={
            "action": "Suivre l'exécution.",
            "owner_name": "Direction retail",
            "due_date": "2026-09-30",
            "status": "done",
            "evidence": "Fait.",
        },
    )
    client.post("/cases/%s/status" % case_id, data={"status": "executing"})
    client.post("/cases/%s/status" % case_id, data={"status": "to_review"})
    assert _case_status(case_id) == "to_review"
    return _first(Review, case_id).id


def test_revue_echue_remonte_sur_l_accueil(client):
    case_id = build_ready_case(client, title="Dossier à revoir")
    _to_review(client, case_id)

    page = page_text(client.get("/"))
    assert "Revues" in page
    assert "Échue" in page


def test_revue_est_enregistree_par_etapes(client):
    case_id = build_ready_case(client)
    review_id = _to_review(client, case_id)

    client.post(
        "/cases/%s/review/%s" % (case_id, review_id),
        data={"observed_results": "Les ventes en ligne ont reculé de 4 %."},
    )

    page = page_text(client.get("/cases/%s" % case_id))
    assert "Les ventes en ligne ont reculé de 4 %." in page
    assert _case_status(case_id) == "to_review"


def test_clore_une_revue_incomplete_est_refuse_mais_le_texte_est_conserve(client):
    case_id = build_ready_case(client)
    review_id = _to_review(client, case_id)

    response = client.post(
        "/cases/%s/review/%s/complete" % (case_id, review_id),
        data={"observed_results": "Recul de 4 %.", "lessons": "", "next_step": ""},
        follow_redirects=True,
    )

    page = page_text(response)
    assert "sans leçon" in page
    assert _case_status(case_id) == "to_review"
    # Le travail saisi n'est pas perdu pour autant.
    assert "Recul de 4 %." in page_text(client.get("/cases/%s" % case_id))


def test_revue_terminee_clot_le_dossier(client):
    case_id = build_ready_case(client)
    review_id = _to_review(client, case_id)

    response = client.post(
        "/cases/%s/review/%s/complete" % (case_id, review_id),
        data={
            "observed_results": "Recul de 4 % sur deux des trois villes.",
            "gaps": "Plus marqué qu'attendu sur une ville.",
            "invalidated_assumptions": "Le reclassement sans départ contraint n'a pas tenu.",
            "lessons": "Mesurer l'effet digital avant de fermer, pas après.",
            "next_step": "keep",
        },
        follow_redirects=True,
    )

    assert "dossier clos" in page_text(response)
    assert _case_status(case_id) == "closed"


def test_pas_encore_renvoie_le_dossier_en_analyse(client):
    """« Pas encore » est une issue pleine de la doctrine maison, pas une absence de
    décision : le dossier repart en analyse au lieu d'être classé."""
    case_id = build_ready_case(client)
    review_id = _to_review(client, case_id)

    response = client.post(
        "/cases/%s/review/%s/complete" % (case_id, review_id),
        data={
            "observed_results": "Trop tôt pour conclure sur l'effet digital.",
            "lessons": "La fenêtre de mesure était trop courte.",
            "next_step": "not_yet",
            "next_step_note": "Reprise si les ventes se stabilisent avant mars 2027.",
        },
        follow_redirects=True,
    )

    assert "repart en analyse" in page_text(response)
    assert _case_status(case_id) == "analysis"


def test_revenir_sur_la_decision_rouvre_le_dossier(client):
    case_id = build_ready_case(client)
    review_id = _to_review(client, case_id)

    client.post(
        "/cases/%s/review/%s/complete" % (case_id, review_id),
        data={
            "observed_results": "Recul de 22 % des ventes en ligne.",
            "lessons": "La présence physique portait le digital local.",
            "next_step": "reverse",
        },
    )

    assert _case_status(case_id) == "analysis"


def test_revue_terminee_ne_se_reecrit_pas(client):
    case_id = build_ready_case(client)
    review_id = _to_review(client, case_id)
    client.post(
        "/cases/%s/review/%s/complete" % (case_id, review_id),
        data={
            "observed_results": "Résultat initial.",
            "lessons": "Leçon initiale.",
            "next_step": "keep",
        },
    )

    response = client.post(
        "/cases/%s/review/%s" % (case_id, review_id),
        data={"observed_results": "Réécriture."},
        follow_redirects=True,
    )

    assert "ne se réécrivent pas" in page_text(response)
    assert "Résultat initial." in page_text(client.get("/cases/%s" % case_id))


def test_dossier_clos_disparait_de_l_accueil_mais_reste_accessible(client):
    """« Dossier archivé et retrouvable » (brief §6)."""
    case_id = build_ready_case(client, title="Dossier à clore")
    review_id = _to_review(client, case_id)
    client.post(
        "/cases/%s/review/%s/complete" % (case_id, review_id),
        data={
            "observed_results": "Constat.",
            "lessons": "Leçon.",
            "next_step": "keep",
        },
    )

    assert "Dossier à clore" not in page_text(client.get("/"))
    page = page_text(client.get("/cases/%s" % case_id))
    assert "Dossier à clore" in page
    assert "Leçon." in page


# --------------------------------------------------------------------------- bout en bout


def test_parcours_complet_de_la_creation_a_la_cloture(client):
    """La définition de terminé du brief §19, en un seul test."""
    case_id = build_ready_case(client, title="Parcours complet")

    decide(client, case_id, review_date="2026-01-31")
    assert _case_status(case_id) == "decided"

    client.post(
        "/cases/%s/commitments" % case_id,
        data={
            "action": "Suivre les ventes en ligne des trois villes.",
            "owner_name": "Direction e-commerce",
            "due_date": "2026-09-30",
            "status": "done",
            "evidence": "Tableau de suivi en place.",
        },
    )
    client.post("/cases/%s/status" % case_id, data={"status": "executing"})
    assert _case_status(case_id) == "executing"

    client.post("/cases/%s/status" % case_id, data={"status": "to_review"})
    review_id = _first(Review, case_id).id

    client.post(
        "/cases/%s/review/%s/complete" % (case_id, review_id),
        data={
            "observed_results": "Zone revenue à l'équilibre, aucun départ contraint.",
            "gaps": "Recul digital de 4 %, sous le seuil de ré-arbitrage.",
            "invalidated_assumptions": "L'hypothèse de reclassement a tenu.",
            "lessons": "Mesurer l'effet digital avant de fermer.",
            "next_step": "keep",
        },
    )
    assert _case_status(case_id) == "closed"

    # Tout est retrouvable avec son contexte : raisons, réserves, engagements, leçons.
    page = page_text(client.get("/cases/%s" % case_id))
    assert "La fenêtre de sortie ne se représentera pas." in page
    assert "L'effet sur le digital reste inconnu." in page
    assert "Mesurer l'effet digital avant de fermer." in page
    assert "Suivre les ventes en ligne des trois villes." in page


def test_aucune_action_externe_dans_toute_la_boucle(client):
    """Brief §15 : « Aucune donnée externe n'est modifiée et aucun message n'est envoyé. »

    Vérifié par l'absence de tout client HTTP sortant dans le code de l'application, et
    non par une simple lecture : c'est la garantie la plus facile à perdre par accident.
    """
    import pathlib

    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in ("import httpx", "import requests", "urllib.request", "smtplib"):
            if needle in text:
                offenders.append("%s : %s" % (path.name, needle))

    assert offenders == [], "client réseau sortant détecté : %s" % offenders
