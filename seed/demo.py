"""Données de démonstration — entièrement fictives.

Le brief §20 recommande de tester le prototype sur données fictives avant toute décision
réelle. Ces trois dossiers sont donc **volontairement imparfaits** : ils servent à vérifier
que l'outil signale les défauts, pas à montrer une belle page.

  * DR-2026-001 : un fait affirmé sans source, une hypothèse déterminante sans test,
    deux chiffres qui se contredisent, une objection bloquante sans réponse, et aucune
    recommandation.
  * DR-2026-002 : dossier abouti et réellement contesté, prêt à décider, avec un désaccord
    non résolu affiché tel quel.
  * DR-2026-003 : brouillon avec échéance déjà dépassée.
  * DR-2026-004 : décidé et en exécution — décision qui s'écarte de la recommandation avec
    sa raison écrite, un engagement critique en retard, un autre bloqué, et une revue échue.

Aucun nom, chiffre ou document réel de L'OCCITANE n'apparaît ici.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionFactory, create_all
from app.domain.enums import (
    CaseStatus,
    ChallengeKind,
    ChallengeStatus,
    ChallengeVoice,
    ClaimCategory,
    CommitmentStatus,
    Confidentiality,
    Materiality,
    NextStep,
    Reversibility,
    ReviewStatus,
    Severity,
    UserRole,
)
from app.util import today
from app.models import (
    Challenge,
    Claim,
    Commitment,
    DecisionCase,
    DecisionRecord,
    Option,
    Recommendation,
    Review,
    User,
)

# Les échéances sont **relatives à aujourd'hui**. Une première version les avait figées en
# absolu, pour la reproductibilité ; au bout de quelques jours tout était « dépassé » et le
# jeu ne montrait plus ce qu'il devait montrer — une échéance proche, une lointaine, une
# dépassée. Aucun test ne dépend de ces dates : ils construisent leurs propres dossiers.
def _in_days(offset: int) -> str:
    return (today() + timedelta(days=offset)).isoformat()


def _iso_days_ago(offset: int) -> str:
    moment = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=offset)
    return moment.isoformat()


def _users(session: Session) -> List[User]:
    users = [
        User(
            email="adrien.geiger@example-fictif.test",
            display_name="Adrien Geiger",
            role=UserRole.CEO.value,
        ),
        User(
            email="chief.of.staff@example-fictif.test",
            display_name="Chief of Staff",
            role=UserRole.CHIEF_OF_STAFF.value,
        ),
    ]
    session.add_all(users)
    session.flush()
    return users


# --------------------------------------------------------------------------- dossier 1


def _case_milan(session: Session, ceo: User, cos: User) -> DecisionCase:
    case = DecisionCase(
        reference="DR-2026-001",
        title="Flagship Milan · centre historique",
        question=(
            "Faut-il ouvrir un flagship en propre dans le centre historique de Milan "
            "avant décembre 2026, ou différer de douze mois ?"
        ),
        context=(
            "Un emplacement se libère sur un axe très passant. Le bail proposé est de neuf "
            "ans, avec trois ans fermes et un droit d'entrée élevé.\n\n"
            "Le sujet est revenu trois fois en comité depuis mars sans arbitrage : chaque "
            "réunion a produit un accord de principe, jamais une décision. La question est "
            "posée maintenant parce que le bailleur demande une réponse sous trois jours."
        ),
        status=CaseStatus.ANALYSIS.value,
        deadline=_in_days(2),        # échéance proche
        confidentiality=Confidentiality.CONFIDENTIAL.value,
        real_decision=(
            "La décision n'est pas « Milan oui ou non ». Elle est : acceptons-nous "
            "d'immobiliser un capital significatif sur un actif peu réversible, dans une "
            "ville où nous n'avons pas encore démontré que le trafic se transforme en "
            "clients qui reviennent ?"
        ),
        scope_out=(
            "Le format du réseau italien dans son ensemble\n"
            "La stratégie de prix en Italie\n"
            "Le renouvellement des corners existants"
        ),
        constraints=(
            "Réponse au bailleur attendue sous trois jours\n"
            "Trois ans fermes, sortie coûteuse\n"
            "Aucune équipe retail locale constituée à ce jour"
        ),
        blind_spot=(
            "Nous raisonnons sur le trafic de la rue, qui se mesure, et non sur le nectar : "
            "ce qui ferait revenir un client une deuxième fois. Personne dans le dossier ne "
            "répond à cette question."
        ),
        executive_summary=(
            "Un emplacement rare, une échéance imposée par le bailleur, et un socle factuel "
            "mince. Deux chiffres de trafic circulent sans que l'écart soit expliqué. "
            "L'hypothèse déterminante — un panier moyen supérieur de 20 % en flagship — "
            "n'est appuyée sur aucune mesure et n'a pas de test prévu.\n\n"
            "Aucune position n'est encore prise dans ce dossier."
        ),
        owner_id=ceo.id,
        created_by_id=cos.id,
    )
    session.add(case)
    session.flush()

    session.add_all(
        [
            # Deux chiffres divergents : aucun n'est arbitrairement retenu (brief §15).
            Claim(
                case_id=case.id,
                text="Le flux piéton de l'axe est estimé à 42 000 passages par jour.",
                category=ClaimCategory.SOURCED_FACT.value,
                source_ref="Étude bailleur, avril 2026, p. 7",
                quote="Flux moyen constaté : 42 000 passages/jour (relevé mars 2026).",
                as_of_date="2026-03-31",
                materiality=Materiality.HIGH.value,
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text="Le flux piéton du même axe est estimé à 28 000 passages par jour.",
                category=ClaimCategory.SOURCED_FACT.value,
                source_ref="Note interne retail Italie, juin 2026, annexe 2",
                quote="Comptage indépendant sur deux semaines : ~28 000 passages/jour.",
                as_of_date="2026-06-15",
                materiality=Materiality.HIGH.value,
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text=(
                    "Les deux comptages de trafic diffèrent de 33 % sans que la méthode, "
                    "la saison ou le périmètre exact soient documentés."
                ),
                category=ClaimCategory.MISSING_VERIFICATION.value,
                materiality=Materiality.HIGH.value,
                best_test=(
                    "Demander les deux protocoles de comptage et faire relever une semaine "
                    "en commun. Coût faible, délai deux semaines."
                ),
                created_by=cos.display_name,
            ),
            # Défaut volontaire : présenté comme un fait, aucune source.
            Claim(
                case_id=case.id,
                text=(
                    "Un flagship en propre génère un panier moyen supérieur de 20 % "
                    "à un corner."
                ),
                category=ClaimCategory.SOURCED_FACT.value,
                materiality=Materiality.HIGH.value,
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text=(
                    "Une équipe retail locale peut être recrutée et formée en quatre mois, "
                    "pour une ouverture avant décembre."
                ),
                category=ClaimCategory.ASSUMPTION.value,
                materiality=Materiality.HIGH.value,
                rationale=(
                    "Avancé par la direction régionale, par analogie avec une ouverture "
                    "espagnole en 2024. Le marché du travail milanais n'a pas été examiné."
                ),
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text="Le droit d'entrée est non récupérable en cas de sortie anticipée.",
                category=ClaimCategory.SOURCED_FACT.value,
                source_ref="Projet de bail, art. 14",
                quote="Le droit d'entrée reste acquis au bailleur en toute hypothèse.",
                materiality=Materiality.HIGH.value,
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text="Un flagship à Milan serait un signal fort de retour de la Maison en Italie.",
                category=ClaimCategory.OPINION.value,
                source_ref="Comité retail, 12 juin 2026",
                materiality=Materiality.MEDIUM.value,
                created_by=cos.display_name,
            ),
        ]
    )

    session.add_all(
        [
            Option(
                case_id=case.id,
                ordinal=0,
                name="Ouvrir avant décembre 2026",
                description="Signature sous trois jours, ouverture en fin d'année.",
                benefits=(
                    "Emplacement rare sécurisé\n"
                    "Vitrine cohérente avec l'intention de marque\n"
                    "Effet d'annonce sur le marché italien"
                ),
                risks=(
                    "Droit d'entrée engagé sur un trafic non vérifié\n"
                    "Équipe non constituée : qualité d'accueil incertaine à l'ouverture\n"
                    "Trois ans fermes en cas d'erreur"
                ),
                assumptions=(
                    "Le trafic haut (42 000) est le bon\n"
                    "Recrutement et formation tiennent en quatre mois"
                ),
                success_conditions=(
                    "Directeur de boutique recruté avant octobre\n"
                    "Taux de retour client mesuré dès le premier trimestre"
                ),
                reversibility=Reversibility.IRREVERSIBLE.value,
                reversibility_note="Droit d'entrée perdu, trois ans fermes.",
                time_to_effect="Chiffre d'affaires significatif à 9-12 mois",
                created_by=cos.display_name,
            ),
            Option(
                case_id=case.id,
                ordinal=1,
                name="Différer de douze mois et vérifier",
                description=(
                    "Refuser cet emplacement, lever les deux inconnues, et revenir sur le "
                    "marché milanais avec un dossier étayé."
                ),
                benefits=(
                    "Décision prise sur un trafic mesuré\n"
                    "Temps de constituer une équipe locale\n"
                    "Capital non immobilisé"
                ),
                risks=(
                    "L'emplacement sera pris par un concurrent\n"
                    "Signal d'hésitation auprès des équipes italiennes"
                ),
                assumptions=(
                    "D'autres emplacements comparables se libéreront dans l'année"
                ),
                success_conditions=(
                    "Protocole de comptage commun établi avant décembre\n"
                    "Mesure du taux de retour client sur les corners existants"
                ),
                reversibility=Reversibility.EASY.value,
                reversibility_note="Aucun engagement pris.",
                time_to_effect="Aucun effet avant 12 mois",
                created_by=cos.display_name,
            ),
            Option(
                case_id=case.id,
                ordinal=2,
                name="Statu quo : rester en corners",
                description="Ne pas ouvrir de flagship à Milan, renforcer les corners existants.",
                is_status_quo=True,
                benefits=("Aucun capital immobilisé\nRisque opérationnel nul"),
                risks=(
                    "Aucune démonstration de la Maison en Italie\n"
                    "Sujet qui reviendra une quatrième fois en comité"
                ),
                success_conditions=("Décision assumée et communiquée, pas un report implicite"),
                reversibility=Reversibility.EASY.value,
                time_to_effect="Immédiat",
                created_by=cos.display_name,
            ),
        ]
    )
    # Le dossier est contesté, mais une objection bloquante reste sans réponse : le
    # diagnostic doit le refuser en « Prêt à décider » pour cette raison précise.
    session.add_all(
        [
            Challenge(
                case_id=case.id,
                voice=ChallengeVoice.DEVILS_ADVOCATE.value,
                kind=ChallengeKind.PREMISE.value,
                objection=(
                    "Tout le dossier repose sur le trafic de la rue. Or aucun élément ne "
                    "relie le trafic au chiffre d'affaires d'une boutique en propre."
                ),
                evidence=(
                    "Les deux comptages disponibles divergent de 33 %, et aucun ne mesure "
                    "la conversion."
                ),
                severity=Severity.BLOCKING.value,
                status=ChallengeStatus.OPEN.value,
                created_by=cos.display_name,
            ),
            Challenge(
                case_id=case.id,
                voice=ChallengeVoice.CLIENT.value,
                kind=ChallengeKind.IGNORED_SIGNAL.value,
                objection=(
                    "Personne n'a mesuré le taux de retour client sur les corners italiens "
                    "existants. On ignore donc s'il y a du nectar avant d'ouvrir plus grand."
                ),
                evidence="Aucun indicateur de réachat suivi sur l'Italie à ce jour.",
                severity=Severity.SERIOUS.value,
                status=ChallengeStatus.OPEN.value,
                created_by=cos.display_name,
            ),
            Challenge(
                case_id=case.id,
                voice=ChallengeVoice.PEOPLE.value,
                kind=ChallengeKind.FUNCTIONAL_IMPACT.value,
                objection=(
                    "Quatre mois pour recruter et former un directeur de boutique à Milan "
                    "est optimiste sur ce marché du travail."
                ),
                evidence="",  # défaut volontaire : objection sans élément à l'appui
                severity=Severity.SERIOUS.value,
                status=ChallengeStatus.OPEN.value,
                created_by=cos.display_name,
            ),
        ]
    )
    # Aucune recommandation : le dossier doit apparaître bloqué au diagnostic.
    return case


# --------------------------------------------------------------------------- dossier 2


def _case_promo(session: Session, ceo: User, cos: User) -> DecisionCase:
    case = DecisionCase(
        reference="DR-2026-002",
        title="Calendrier promotionnel · réduction de la profondeur des remises",
        question=(
            "Faut-il réduire la profondeur maximale des remises de 40 % à 25 % sur les "
            "temps forts commerciaux de 2027 ?"
        ),
        context=(
            "La profondeur des remises a augmenté depuis trois exercices. Le volume suit, "
            "la marge résiste, mais le prix plein perd du terrain sur les gammes d'entrée.\n\n"
            "Le sujet croise directement le chiffre et la valeur long terme."
        ),
        status=CaseStatus.READY.value,
        deadline=_in_days(40),       # échéance lointaine
        confidentiality=Confidentiality.CONFIDENTIAL.value,
        real_decision=(
            "La décision n'est pas « moins de promotions ». Elle est : acceptons-nous de "
            "renoncer à du volume court terme pour arrêter d'acheter le retour du client "
            "au prix plutôt qu'au produit ?"
        ),
        scope_out=(
            "Le niveau de prix catalogue\n"
            "Le calendrier des lancements produits\n"
            "Les mécaniques de fidélité hors remise"
        ),
        constraints=(
            "Décision nécessaire avant le cadrage budgétaire 2027\n"
            "Engagements déjà pris avec deux partenaires distributeurs"
        ),
        blind_spot=(
            "Nous mesurons bien l'effet sur le volume, mal l'effet sur la perception de "
            "valeur. Le second met deux ans à se voir et ne se rattrape pas vite."
        ),
        executive_summary=(
            "Trois exercices de remises croissantes ont fait progresser le volume sans "
            "dégrader la marge à court terme, mais la part du chiffre réalisée à prix plein "
            "recule sur les gammes d'entrée.\n\n"
            "Trois options : réduction en une fois, réduction progressive sur deux ans, "
            "statu quo. La réduction progressive est recommandée. Le désaccord avec les "
            "équipes commerciales sur l'ampleur de la perte de volume n'est pas résolu et "
            "reste affiché."
        ),
        owner_id=ceo.id,
        created_by_id=cos.id,
    )
    session.add(case)
    session.flush()

    session.add_all(
        [
            Claim(
                case_id=case.id,
                text=(
                    "La part du chiffre d'affaires réalisée à prix plein sur les gammes "
                    "d'entrée est passée de 61 % à 48 % en trois exercices."
                ),
                category=ClaimCategory.SOURCED_FACT.value,
                source_ref="Revue commerciale annuelle 2026, tableau 3.2",
                quote="Prix plein gammes d'entrée : 61 % (2023) → 52 % (2025) → 48 % (2026).",
                as_of_date="2026-06-30",
                materiality=Materiality.HIGH.value,
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text=(
                    "La marge brute consolidée est restée stable sur la même période, "
                    "à moins d'un point d'écart."
                ),
                category=ClaimCategory.SOURCED_FACT.value,
                source_ref="Reporting finance, clôture juin 2026",
                quote="Marge brute : 72,4 % (2023) → 71,8 % (2026).",
                as_of_date="2026-06-30",
                materiality=Materiality.MEDIUM.value,
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text=(
                    "Le taux de réachat à douze mois des clients recrutés en forte remise "
                    "est inférieur de 14 points à celui des clients recrutés à prix plein."
                ),
                category=ClaimCategory.SOURCED_FACT.value,
                source_ref="Analyse cohortes CRM, mai 2026, p. 4",
                quote="Réachat 12 mois : 31 % (recrutés en remise ≥30 %) vs 45 % (prix plein).",
                as_of_date="2026-05-31",
                materiality=Materiality.HIGH.value,
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text=(
                    "Une réduction de la profondeur de remise entraînera une perte de "
                    "volume comprise entre 3 % et 6 % la première année."
                ),
                category=ClaimCategory.ASSUMPTION.value,
                materiality=Materiality.HIGH.value,
                rationale=(
                    "Fourchette issue de l'élasticité observée sur deux temps forts 2025. "
                    "Les équipes commerciales estiment la perte à 10-12 %."
                ),
                best_test=(
                    "Tester 25 % de profondeur maximale sur un seul marché comparable au "
                    "premier temps fort 2027, avant de généraliser."
                ),
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text=(
                    "L'effet d'une baisse de profondeur sur la perception de valeur par le "
                    "client n'est mesuré par aucun indicateur suivi aujourd'hui."
                ),
                category=ClaimCategory.MISSING_VERIFICATION.value,
                materiality=Materiality.MEDIUM.value,
                best_test=(
                    "Ajouter deux questions de perception prix au baromètre client "
                    "trimestriel existant. Coût marginal."
                ),
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text=(
                    "Les deux partenaires distributeurs concernés accepteront un plafond "
                    "de remise plus bas s'il est annoncé six mois à l'avance."
                ),
                category=ClaimCategory.OPINION.value,
                source_ref="Entretien direction commerciale, juillet 2026",
                materiality=Materiality.MEDIUM.value,
                created_by=cos.display_name,
            ),
        ]
    )

    options = [
        Option(
            case_id=case.id,
            ordinal=0,
            name="Réduction en une fois dès 2027",
            description="Plafond à 25 % appliqué à tous les temps forts 2027.",
            benefits=("Signal clair, interne et externe\nEffet sur la valeur dès 2027"),
            risks=(
                "Perte de volume concentrée sur un seul exercice\n"
                "Tension avec les partenaires distributeurs\n"
                "Aucun apprentissage progressif possible"
            ),
            assumptions=("La perte de volume reste dans la fourchette 3-6 %"),
            success_conditions=("Annonce aux partenaires six mois avant application"),
            reversibility=Reversibility.COSTLY.value,
            reversibility_note="Revenir en arrière après une annonce publique coûte en crédibilité.",
            time_to_effect="Effet sur le volume immédiat, sur la valeur perçue à 18-24 mois",
            created_by=cos.display_name,
        ),
        Option(
            case_id=case.id,
            ordinal=1,
            name="Réduction progressive sur deux ans",
            description="Plafond à 32 % en 2027, puis 25 % en 2028, avec un marché test dès 2027.",
            benefits=(
                "Le désaccord sur l'élasticité se tranche par la mesure, pas par l'autorité\n"
                "Perte de volume étalée\n"
                "Partenaires préparés en deux temps"
            ),
            risks=(
                "Signal plus faible en interne\n"
                "Deux ans d'attention managériale sur le sujet"
            ),
            assumptions=("Le marché test est représentatif du reste du réseau"),
            success_conditions=(
                "Marché test désigné avant novembre 2026\n"
                "Indicateur de perception prix ajouté au baromètre client\n"
                "Point d'arbitrage formel après le premier temps fort 2027"
            ),
            reversibility=Reversibility.EASY.value,
            reversibility_note="La deuxième étape peut être ajustée au vu des résultats.",
            time_to_effect="Effet mesurable dès le premier temps fort 2027",
            created_by=cos.display_name,
        ),
        Option(
            case_id=case.id,
            ordinal=2,
            name="Statu quo : maintenir 40 %",
            description="Aucun changement de plafond en 2027.",
            is_status_quo=True,
            benefits=("Volume préservé\nAucune tension partenaire"),
            risks=(
                "La part de prix plein continue de reculer\n"
                "Le recrutement client reste orienté vers les clients qui ne reviennent pas"
            ),
            success_conditions=("Décision assumée, avec un point de revue à douze mois"),
            reversibility=Reversibility.EASY.value,
            time_to_effect="Aucun changement",
            created_by=cos.display_name,
        ),
    ]
    session.add_all(options)
    session.flush()

    session.add(
        Recommendation(
            case_id=case.id,
            option_id=options[1].id,
            position=(
                "Je réduirais progressivement, avec un marché test dès le premier temps fort "
                "2027. Le désaccord porte sur l'ampleur de la perte de volume : entre 3-6 % "
                "et 10-12 %, l'écart est trop grand pour être tranché par un arbitrage "
                "d'autorité, et suffisamment mesurable pour être tranché par un test."
            ),
            reasons=(
                "Le recul du prix plein est sourcé et régulier, pas conjoncturel\n"
                "L'écart de réachat de 14 points montre que la remise profonde achète des "
                "clients qui ne reviennent pas : c'est un problème de nectar, pas de volume\n"
                "L'élasticité réelle est inconnue et coûte peu à mesurer\n"
                "La marge stable donne le temps de procéder par étapes"
            ),
            success_conditions=(
                "Marché test désigné avant novembre 2026\n"
                "Indicateur de perception prix ajouté au baromètre client\n"
                "Arbitrage formel de l'étape 2028 après le premier temps fort 2027"
            ),
            would_change_if=(
                "La perte de volume mesurée sur le marché test dépasse 8 %\n"
                "L'écart de réachat s'explique par un effet de mix produit et non par la remise\n"
                "Un partenaire distributeur conditionne son référencement au maintien de 40 %"
            ),
            open_disagreements=(
                "Direction commerciale : estime la perte de volume à 10-12 %, soit le double "
                "de la fourchette retenue ici. Le désaccord n'est pas résolu et le test est "
                "précisément là pour le trancher.\n"
                "Direction financière : préfère la réduction en une fois pour ne pas étaler "
                "l'incertitude sur deux exercices budgétaires."
            ),
            author=cos.display_name,
        )
    )

    # Dossier réellement contesté, avec une prémisse testée : il peut donc être déclaré
    # prêt à décider.
    session.add_all(
        [
            Challenge(
                case_id=case.id,
                option_id=options[1].id,
                voice=ChallengeVoice.DEVILS_ADVOCATE.value,
                kind=ChallengeKind.PREMISE.value,
                objection=(
                    "La fourchette de perte de volume vient de deux temps forts seulement. "
                    "Deux observations ne font pas une élasticité."
                ),
                evidence="Élasticité estimée sur les temps forts de mai et novembre 2025.",
                severity=Severity.BLOCKING.value,
                response=(
                    "Objection retenue : c'est précisément pourquoi l'option recommandée "
                    "passe par un marché test avant généralisation, au lieu de trancher "
                    "sur la fourchette."
                ),
                status=ChallengeStatus.ACCEPTED.value,
                answered_by=cos.display_name,
                answered_at=_iso_days_ago(12),
                created_by=cos.display_name,
            ),
            Challenge(
                case_id=case.id,
                voice=ChallengeVoice.FINANCE.value,
                kind=ChallengeKind.FUNCTIONAL_IMPACT.value,
                objection=(
                    "Étaler sur deux exercices rend l'atterrissage 2027 et 2028 plus "
                    "difficile à prévoir qu'une baisse unique."
                ),
                evidence="Deux exercices budgétaires concernés au lieu d'un.",
                severity=Severity.SERIOUS.value,
                response=(
                    "Écart assumé : l'incertitude sur l'élasticité coûte plus cher qu'une "
                    "prévision moins nette."
                ),
                status=ChallengeStatus.REJECTED.value,
                answered_by=cos.display_name,
                answered_at=_iso_days_ago(12),
                created_by=cos.display_name,
            ),
            Challenge(
                case_id=case.id,
                voice=ChallengeVoice.BRAND.value,
                kind=ChallengeKind.ADVERSE_SCENARIO.value,
                objection=(
                    "Si les concurrents maintiennent 40 %, la Maison peut passer pour chère "
                    "sans passer pour désirable."
                ),
                evidence="Aucune donnée sur les plafonds de remise des concurrents directs.",
                severity=Severity.SERIOUS.value,
                response=(
                    "Réserve conservée telle quelle : le marché test devra observer la "
                    "réaction concurrentielle, pas seulement le volume."
                ),
                status=ChallengeStatus.ANSWERED.value,
                answered_by=cos.display_name,
                answered_at=_iso_days_ago(11),
                created_by=cos.display_name,
            ),
            Challenge(
                case_id=case.id,
                voice=ChallengeVoice.LONG_TERM.value,
                kind=ChallengeKind.PREMISE.value,
                objection=(
                    "On suppose que la perception de valeur se répare en deux ans. Rien ne "
                    "l'établit."
                ),
                evidence="Aucun indicateur de perception prix suivi aujourd'hui.",
                severity=Severity.MINOR.value,
                response="Accepté comme inconnue : d'où l'ajout au baromètre client.",
                status=ChallengeStatus.ACCEPTED.value,
                answered_by=cos.display_name,
                answered_at=_iso_days_ago(11),
                created_by=cos.display_name,
            ),
        ]
    )
    return case


# --------------------------------------------------------------------------- dossier 3


def _case_reformulation(session: Session, ceo: User, cos: User) -> DecisionCase:
    case = DecisionCase(
        reference="DR-2026-003",
        title="Reformulation · substitution d'un ingrédient en tension d'approvisionnement",
        question=(
            "Faut-il reformuler un produit d'entrée de gamme pour substituer un ingrédient "
            "dont l'approvisionnement est tendu, ou réduire les volumes de production ?"
        ),
        context=(
            "Brouillon ouvert après une alerte supply. Les sources n'ont pas encore été "
            "réunies et aucune option n'est formulée."
        ),
        status=CaseStatus.DRAFT.value,
        deadline=_in_days(-8),       # échéance dépassée
        confidentiality=Confidentiality.STRICTLY_CONFIDENTIAL.value,
        blind_spot=(
            "Le dossier est traité comme un sujet supply. C'est peut-être d'abord un sujet "
            "de promesse produit."
        ),
        owner_id=ceo.id,
        created_by_id=ceo.id,
    )
    session.add(case)
    session.flush()

    session.add(
        Claim(
            case_id=case.id,
            text=(
                "La tension d'approvisionnement durera au moins deux campagnes de récolte."
            ),
            category=ClaimCategory.ASSUMPTION.value,
            materiality=Materiality.HIGH.value,
            rationale="Avancée en alerte supply, sans document joint à ce stade.",
            created_by=ceo.display_name,
        )
    )
    return case


# --------------------------------------------------------------------------- dossier 4


def _case_boutiques(session: Session, ceo: User, cos: User) -> DecisionCase:
    """Dossier décidé en avril et en cours d'exécution.

    Il exerce toute la fin de la boucle : engagements dont un critique en retard, revue
    déjà échue, et une décision qui s'écarte de la recommandation de l'outil — avec la
    raison écrite, puisque c'est exactement ce qu'on veut relire à la revue.
    """
    case = DecisionCase(
        reference="DR-2026-004",
        title="Réseau Europe du Nord · sortie de trois emplacements déficitaires",
        question=(
            "Faut-il fermer trois boutiques déficitaires en Europe du Nord à l'échéance des "
            "baux, ou tenter un dernier plan de redressement sur douze mois ?"
        ),
        context=(
            "Trois emplacements sont déficitaires depuis deux exercices. Les baux arrivent "
            "à échéance de façon rapprochée, ce qui ouvre une fenêtre de sortie sans "
            "indemnité.\n\n"
            "La décision a été prise en avril 2026. Le dossier est conservé ici parce que "
            "son exécution est en cours et que sa revue arrive."
        ),
        status=CaseStatus.EXECUTING.value,
        deadline=_in_days(-130),     # décidé il y a plus de quatre mois
        confidentiality=Confidentiality.STRICTLY_CONFIDENTIAL.value,
        real_decision=(
            "La décision n'est pas « fermer ou pas ». Elle est : acceptons-nous de retirer "
            "la Maison de trois villes où elle est visible, pour arrêter de financer une "
            "présence que le client ne fait pas vivre ?"
        ),
        scope_out=(
            "Le reste du réseau nordique\n"
            "Le positionnement prix sur la zone\n"
            "La distribution en grands magasins"
        ),
        constraints=(
            "Fenêtre de sortie limitée à l'échéance des baux\n"
            "Obligations sociales à respecter dans trois pays différents"
        ),
        blind_spot=(
            "Nous jugeons ces boutiques sur leur compte d'exploitation propre. Nous ne "
            "savons pas ce qu'elles apportent à la notoriété locale des autres canaux."
        ),
        executive_summary=(
            "Trois emplacements déficitaires depuis deux exercices, une fenêtre de sortie "
            "sans indemnité, et une inconnue non levée : l'effet de la fermeture sur les "
            "ventes en ligne de la même ville.\n\n"
            "Décision prise en avril : fermeture des trois, contre la recommandation de "
            "l'outil qui proposait de n'en fermer que deux et d'utiliser la troisième comme "
            "mesure de cet effet. La raison de l'écart est consignée."
        ),
        owner_id=ceo.id,
        created_by_id=cos.id,
    )
    session.add(case)
    session.flush()

    session.add_all(
        [
            Claim(
                case_id=case.id,
                text=(
                    "Les trois emplacements cumulent une perte d'exploitation sur les deux "
                    "derniers exercices."
                ),
                category=ClaimCategory.SOURCED_FACT.value,
                source_ref="Reporting retail, clôture mars 2026, annexe 4",
                quote="Résultat d'exploitation négatif sur les 24 derniers mois pour les 3 sites.",
                as_of_date="2026-03-31",
                materiality=Materiality.HIGH.value,
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text=(
                    "Les baux des trois sites arrivent à échéance dans une fenêtre de "
                    "cinq mois, sans indemnité de sortie."
                ),
                category=ClaimCategory.SOURCED_FACT.value,
                source_ref="Revue des baux, février 2026",
                quote="Échéances : mai, juillet et septembre 2026, sans pénalité.",
                materiality=Materiality.HIGH.value,
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text=(
                    "L'effet d'une fermeture sur les ventes en ligne de la même ville n'est "
                    "pas mesuré."
                ),
                category=ClaimCategory.MISSING_VERIFICATION.value,
                materiality=Materiality.HIGH.value,
                best_test=(
                    "Conserver un des trois sites douze mois de plus et comparer les ventes "
                    "en ligne des trois villes."
                ),
                created_by=cos.display_name,
            ),
            Claim(
                case_id=case.id,
                text=(
                    "Le personnel des trois sites peut être reclassé dans le réseau ou en "
                    "e-commerce sans départ contraint."
                ),
                category=ClaimCategory.ASSUMPTION.value,
                materiality=Materiality.HIGH.value,
                rationale="Estimation People, sur la base des postes ouverts en mars.",
                best_test="Recenser les postes réellement ouverts par pays avant annonce.",
                created_by=cos.display_name,
            ),
        ]
    )

    options = [
        Option(
            case_id=case.id,
            ordinal=0,
            name="Fermer les trois à l'échéance des baux",
            description="Sortie des trois emplacements dans la fenêtre de cinq mois.",
            benefits=("Fin du financement de la perte\nSortie sans indemnité"),
            risks=(
                "Perte de visibilité dans trois villes\n"
                "Effet inconnu sur les ventes en ligne locales\n"
                "Reclassement de trois équipes en même temps"
            ),
            assumptions=("Le reclassement se fait sans départ contraint"),
            success_conditions=(
                "Aucun départ contraint\n"
                "Ventes en ligne des trois villes suivies pendant douze mois"
            ),
            reversibility=Reversibility.IRREVERSIBLE.value,
            reversibility_note="Rouvrir dans les mêmes rues coûterait un droit d'entrée neuf.",
            time_to_effect="Effet sur le résultat dès le trimestre suivant chaque sortie",
            created_by=cos.display_name,
        ),
        Option(
            case_id=case.id,
            ordinal=1,
            name="Fermer deux, garder le troisième comme mesure",
            description=(
                "Sortie de deux sites, maintien du troisième douze mois pour mesurer l'effet "
                "de la présence physique sur les ventes en ligne locales."
            ),
            benefits=(
                "L'inconnue principale est levée par la mesure, pas par l'opinion\n"
                "Deux tiers de la perte arrêtés immédiatement"
            ),
            risks=(
                "Douze mois de perte supplémentaire sur un site\n"
                "Fenêtre de sortie sans indemnité perdue pour ce site"
            ),
            assumptions=("Un site suffit à mesurer l'effet"),
            success_conditions=("Protocole de mesure défini avant la première fermeture"),
            reversibility=Reversibility.COSTLY.value,
            time_to_effect="Enseignement disponible à douze mois",
            created_by=cos.display_name,
        ),
        Option(
            case_id=case.id,
            ordinal=2,
            name="Statu quo : plan de redressement sur douze mois",
            description="Maintien des trois sites avec un plan de redressement.",
            is_status_quo=True,
            benefits=("Aucun retrait de visibilité\nAucun sujet social"),
            risks=(
                "Troisième exercice de perte\n"
                "Fenêtre de sortie sans indemnité définitivement perdue"
            ),
            success_conditions=("Retour à l'équilibre d'au moins deux sites en douze mois"),
            reversibility=Reversibility.COSTLY.value,
            time_to_effect="Douze mois",
            created_by=cos.display_name,
        ),
    ]
    session.add_all(options)
    session.flush()

    session.add_all(
        [
            Challenge(
                case_id=case.id,
                option_id=options[0].id,
                voice=ChallengeVoice.DEVILS_ADVOCATE.value,
                kind=ChallengeKind.PREMISE.value,
                objection=(
                    "Fermer les trois d'un coup supprime la seule occasion de mesurer ce "
                    "que la présence physique apporte au digital."
                ),
                evidence="L'inconnue est déclarée dans le dossier et reste non levée.",
                severity=Severity.BLOCKING.value,
                response=(
                    "Objection reconnue et assumée : la fenêtre de sortie sans indemnité a "
                    "été jugée plus coûteuse à perdre que l'enseignement à gagner."
                ),
                status=ChallengeStatus.ACCEPTED.value,
                answered_by=ceo.display_name,
                answered_at=_iso_days_ago(130),
                created_by=cos.display_name,
            ),
            Challenge(
                case_id=case.id,
                voice=ChallengeVoice.PEOPLE.value,
                kind=ChallengeKind.FUNCTIONAL_IMPACT.value,
                objection=(
                    "Trois reclassements simultanés dans trois pays, avec trois droits du "
                    "travail différents."
                ),
                evidence="Trois juridictions concernées, aucune équipe RH locale dédiée.",
                severity=Severity.SERIOUS.value,
                response="Un référent par pays est désigné avant toute annonce.",
                status=ChallengeStatus.ANSWERED.value,
                answered_by=cos.display_name,
                answered_at=_iso_days_ago(134),
                created_by=cos.display_name,
            ),
            Challenge(
                case_id=case.id,
                voice=ChallengeVoice.BRAND.value,
                kind=ChallengeKind.ADVERSE_SCENARIO.value,
                objection=(
                    "Trois retraits rapprochés peuvent se lire comme un repli de la Maison "
                    "sur la zone."
                ),
                evidence="Trois sorties visibles en cinq mois dans une même région.",
                severity=Severity.SERIOUS.value,
                response=(
                    "Séquencement et récit assumés : sortie présentée comme un choix de "
                    "concentration, pas comme un retrait."
                ),
                status=ChallengeStatus.ANSWERED.value,
                answered_by=cos.display_name,
                answered_at=_iso_days_ago(133),
                created_by=cos.display_name,
            ),
            Challenge(
                case_id=case.id,
                voice=ChallengeVoice.FINANCE.value,
                kind=ChallengeKind.FUNCTIONAL_IMPACT.value,
                objection="Garder un site douze mois de plus coûte une année de perte.",
                evidence="Perte d'exploitation constatée sur le site en question.",
                severity=Severity.SERIOUS.value,
                response="Argument retenu dans l'arbitrage final.",
                status=ChallengeStatus.ACCEPTED.value,
                answered_by=ceo.display_name,
                answered_at=_iso_days_ago(130),
                created_by=cos.display_name,
            ),
        ]
    )

    session.add(
        Recommendation(
            case_id=case.id,
            option_id=options[1].id,
            position=(
                "Je fermerais deux sites et garderais le troisième douze mois. L'inconnue "
                "sur l'effet de la présence physique sur le digital est déterminante et ne "
                "se lèvera jamais autrement : une fois les trois fermés, la question restera "
                "ouverte pour toutes les décisions de réseau à venir."
            ),
            reasons=(
                "La perte est sourcée, l'effet sur le digital ne l'est pas\n"
                "Deux fermetures arrêtent déjà les deux tiers de la perte\n"
                "L'enseignement servira à toutes les prochaines décisions de réseau"
            ),
            success_conditions=(
                "Protocole de mesure défini avant la première fermeture\n"
                "Point d'arbitrage sur le troisième site à douze mois"
            ),
            would_change_if=(
                "Le bail du troisième site ne peut pas être prolongé aux conditions actuelles\n"
                "La perte mensuelle du troisième site dépasse le coût d'une étude équivalente"
            ),
            open_disagreements=(
                "Direction financière : considère qu'une année de perte supplémentaire ne "
                "s'achète pas contre un enseignement non garanti."
            ),
            author=cos.display_name,
        )
    )
    session.flush()

    # Décision : le CEO tranche contre la recommandation, et écrit pourquoi.
    decision = DecisionRecord(
        case_id=case.id,
        option_id=options[0].id,
        reasons=(
            "La fenêtre de sortie sans indemnité ne se représentera pas\n"
            "Un troisième exercice de perte n'est pas défendable devant les équipes\n"
            "L'effet sur le digital peut être approché autrement, par comparaison entre villes"
        ),
        reservations=(
            "L'effet de la présence physique sur les ventes en ligne locales reste inconnu\n"
            "Le reclassement sans départ contraint est une hypothèse, pas un fait"
        ),
        success_criteria=(
            "Aucun départ contraint dans les trois pays\n"
            "Ventes en ligne des trois villes suivies mensuellement pendant douze mois\n"
            "Résultat d'exploitation de la zone à l'équilibre au premier trimestre 2027"
        ),
        change_conditions=(
            "Les ventes en ligne d'une des trois villes reculent de plus de 15 % après la "
            "fermeture\n"
            "Un départ contraint devient inévitable"
        ),
        diverges_from_recommendation=True,
        divergence_reason=(
            "La recommandation privilégiait l'enseignement ; j'ai privilégié la fenêtre de "
            "sortie. Je l'assume, et c'est précisément ce qu'il faudra relire à la revue : "
            "si les ventes en ligne décrochent, l'outil avait raison et je le saurai."
        ),
        review_date=_in_days(-6),
        decided_by_id=ceo.id,
        decided_at=_iso_days_ago(130),
    )
    session.add(decision)
    session.flush()

    session.add_all(
        [
            Commitment(
                case_id=case.id,
                action=(
                    "Mettre en place le suivi mensuel des ventes en ligne des trois villes"
                ),
                owner_name="Direction e-commerce",
                due_date=_in_days(-24),      # engagement critique en retard
                status=CommitmentStatus.OPEN.value,
                is_critical=True,
                evidence="",
                created_by=cos.display_name,
            ),
            Commitment(
                case_id=case.id,
                action="Désigner un référent RH par pays avant toute annonce",
                owner_name="Direction People",
                due_date=_in_days(-100),
                status=CommitmentStatus.DONE.value,
                is_critical=True,
                evidence="Trois référents désignés, note du 6 mai 2026.",
                created_by=cos.display_name,
            ),
            Commitment(
                case_id=case.id,
                action="Conduire la sortie du bail du troisième site",
                owner_name="Direction immobilier",
                due_date=_in_days(22),
                status=CommitmentStatus.IN_PROGRESS.value,
                evidence="Deux sorties réalisées, la troisième en cours.",
                created_by=cos.display_name,
            ),
            Commitment(
                case_id=case.id,
                action="Reclasser les équipes des deux premiers sites",
                owner_name="Direction People",
                due_date=_in_days(7),
                status=CommitmentStatus.BLOCKED.value,
                is_critical=True,
                evidence=(
                    "Six personnes reclassées sur neuf. Trois postes attendus en "
                    "e-commerce ne sont pas ouverts."
                ),
                created_by=cos.display_name,
            ),
        ]
    )

    # Revue échue : c'est le signal principal que ce dossier doit remonter sur l'accueil.
    session.add(
        Review(
            case_id=case.id,
            planned_date=_in_days(-6),   # revue échue
            initial_expectations=(
                "Aucun départ contraint dans les trois pays\n"
                "Ventes en ligne des trois villes suivies mensuellement pendant douze mois\n"
                "Résultat d'exploitation de la zone à l'équilibre au premier trimestre 2027\n"
                "Les ventes en ligne d'une des trois villes reculent de plus de 15 % après la "
                "fermeture\n"
                "Un départ contraint devient inévitable"
            ),
            status=ReviewStatus.PLANNED.value,
        )
    )
    return case


# --------------------------------------------------------------------------- entrée


def seed(reset: bool = False) -> str:
    """Insère les données de démonstration. Sans effet si la base en contient déjà."""
    create_all()

    with SessionFactory() as session:
        if reset:
            # Ordre imposé par les clés étrangères.
            for model in (
            Review,
            Commitment,
            DecisionRecord,
            Challenge,
            Recommendation,
            Claim,
            Option,
            DecisionCase,
            User,
        ):
                for row in session.scalars(select(model)).all():
                    session.delete(row)
            session.commit()

        existing = session.scalars(select(DecisionCase)).first()
        if existing is not None:
            return "données déjà présentes, rien à faire"

        ceo, cos = _users(session)
        _case_milan(session, ceo, cos)
        _case_promo(session, ceo, cos)
        _case_reformulation(session, ceo, cos)
        _case_boutiques(session, ceo, cos)
        session.commit()

    return "4 dossiers fictifs et 2 utilisateurs créés"
