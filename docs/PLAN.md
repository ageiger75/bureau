# Plan de continuation · CEO Performance Cockpit

Écrit le 2 septembre 2026, après relecture de l'ensemble des échanges, du code et des deux
briefs (« Expression du besoin » du CEO, « Doctrine V6.1 »). Destiné à la prochaine session
de travail — quel que soit le modèle qui la tient — et au CEO lui-même. Ce document ne porte
aucun chiffre réel, aucun nom de marché, de personne ou de produit : ceux-là vivent dans
`var/`, ignoré par git, et dans les briefs qui ne sont pas versionnés.

À lire avant `AGENTS.md`, qui décrit *comment* contribuer ; ce document dit *quoi* faire et
dans quel ordre.

---

## 1. Où en est le produit

**Le socle tient.** FastAPI, Jinja2, SQLite, Python 3.9 strict, lecteurs XLSX et CSV en
bibliothèque standard, aucune ressource externe, écoute locale seulement, lecture seule
garantie deux fois (code et rôle d'entrepôt). La suite de tests est verte et chaque test
ferme un défaut qui a été vu, pas un défaut imaginé.

**Deux produits cohabitent dans le dépôt.** Decision Room (`/decisions`, 202 tests
d'origine, intact) et le Performance Cockpit (`/`, écran « Today », plus `/system`). Le
premier n'est plus la porte d'entrée mais n'a pas été retiré.

**L'écran web lit** : `analytics` (les écarts, leurs ponts, une liste de sujets
recalculée à chaque lecture), `routing`, `kpi`, `provenance`, `commitments`, `source`.

**La ligne de commande lit beaucoup plus.** Vingt et une commandes. Les quatre derniers
jours de travail vivent uniquement là : l'annuaire (`org`), les partenaires nommés
(`partners`), le détecteur de flux gris (`distribution`), et surtout **le registre des
sujets** (`issues`) — identité persistante, rôles, arbitrages, lectures successives,
moteur de sélection à trois créneaux d'attention et cinq de surveillance.

**Les sources que le cockpit sait lire** (toutes dans `var/`) : le classeur de
planification, le réalisé publié par la Finance, le reforecast, le suivi des KPI,
l'annuaire, les notes de contexte, les poids stratégiques, la divergence
entrepôt/consolidation, les partenaires, les signaux de distribution. Et l'entrepôt, par
une connexion nommée, jamais par un identifiant stocké.

**Deux systèmes, jamais mélangés en silence** : la consolidation (ce que la Finance
publie) et l'entrepôt (ce qui l'explique). Le chiffre du haut vient de la première ; les
cartes viennent du second et le disent.

---

## 2. Les sept besoins du CEO, et leur état

| Besoin | État | Où |
| --- | --- | --- |
| **B1** Lire et challenger périmètre par périmètre, le MD nommé | Partiel | L'annuaire est lu et place les marchés sous leur MD ; aucune page par périmètre |
| **B2** Le nom du partenaire, pas la famille de canal | Fait en CLI | `partners` ; rien à l'écran |
| **B3** Où j'en suis dans le mois, deux taux côte à côte, phasage réel | **Absent** | — |
| **B4** Le moteur client sous le chiffre | Partiel | Le suivi des KPI est lu avec ses règles de cadence et de sens ; pas de lecture ciblée à l'écran |
| **B5** L'euro gagné est-il le bon euro — le mix, la contribution | **Absent** | Le brief le nomme « le besoin le plus important » |
| **B6** Les moteurs nommés du plan, comme des objets avec owner et reste à livrer | **Absent** | — |
| **B7** Le plan lui-même est-il tenable | Fait | À l'écran, adressé à la Finance, hors du champ commercial |

Et les chapitres de la doctrine V6.1 :

| Chapitre | État |
| --- | --- |
| §C Sélection et mémoire des sujets | Construit, **et à l'écran depuis le 3 septembre** — restent les deux gestes humains (accepter une variance, clore) en formulaire |
| §D Trajectoire (atterrissage, plan non bridgé, saisonnalisé) | Absent |
| §E Surface (ordre d'écran, navigation, langue) | Absent |
| §F Câblage des KPI par contrat | Partiel (lecteur du tracker) |
| §6 du brief besoin — l'analyse par une IA | Réponse donnée en conversation, **jamais consignée** |
| Détecteur de flux gris | Construit en CLI, hors brief, demandé explicitement par le CEO |

---

## 3. Diagnostic

### Ce qui est bien

- **La discipline « une absence n'est pas un zéro »** est réelle, testée, et elle a attrapé
  des défauts vrais à répétition : des identifiants de remplacement pris pour des
  identités, des marchés non mesurés affichés à zéro, un plancher de matérialité rendu
  inopérant par une variable masquée, un compte de personnel qui paraissait petit en euros
  et pesait cinq fois plus en produit.
- **Le registre fait ce pour quoi il a été construit.** Une même preuve n'ouvre jamais
  deux sujets ; un sujet clos ne se rouvre pas mais désigne son successeur ; une lecture
  remplacée reste visible avec sa raison. Il a été relu trois fois en un après-midi sur
  un même sujet et les trois lectures sont conservées.
- **La vérification des retours de l'agent entrepôt est faite, pas relayée.** Plusieurs
  erreurs réelles ont été trouvées à l'arithmétique : une attribution que le fichier
  refusait, un total qui apparaissait sous deux noms, une légende de conversion fausse,
  un ratio dont le dénominateur ne correspondait pas au comportement mesuré.
- **La séparation domaine / persistance / HTTP** a rendu le pivot bon marché et permet
  de tester chaque règle sans serveur ni base.
- **La sécurité est cohérente** : aucun chiffre réel dans le dépôt, vérifié par un test ;
  `var/` ignoré ; lecture seule ; rien ne sort de la machine.

### Ce qui manque

1. ~~**Le registre n'atteint pas l'écran.**~~ Fait le 3 septembre : l'écran charge le
   registre, le classe et le rend, avec ses trois créneaux, ses arbitrages endormis et
   les sources qu'il n'a pas ouvertes. Restent les deux gestes humains en formulaire.
2. **Trois des sept besoins n'ont aucun code** : B3, B5, B6. Le besoin le plus important
   selon le CEO (B5) est à zéro.
3. **Le produit est devenu une ligne de commande.** Trois mille sept cents lignes de CLI,
   vingt et une commandes, et un écran web qui n'a pas bougé depuis quatre jours. Le CEO ne
   code pas ; on lui a demandé de coller des sorties de terminal plus d'une centaine de
   fois. Le terminal est commode pour celui qui construit, pas pour celui qui lit.
4. **La doctrine n'est pas dans le dépôt.** Les deux briefs, les règles de travail, les
   décisions prises en conversation (rôles, taux fixes, périmètres, ce qu'on ne mesure
   pas) vivent dans des fichiers attachés et dans le fil de discussion. Une session neuve
   ne les trouve pas.
5. **La branche principale a plus de deux cents commits de retard** sur la branche de
   travail. Quiconque arrive sur le dépôt voit un produit ancien.

### Ce qui doit être amélioré

- **L'écran attend l'entrepôt sans signe de vie.** À cache froid, la page met des minutes
  et l'onglet reste blanc : indiscernable d'un serveur planté. Le cache est bien conçu ;
  ce qui manque est un écran qui s'ouvre sur la dernière lecture et dit qu'une nouvelle
  arrive. `manage.py refresh` avant d'ouvrir contourne le problème sans le régler.

- **Les briefs envoyés à l'agent entrepôt encodaient des hypothèses non testées**, et
  plusieurs ont fabriqué des défauts : classer sur une valeur qui appartient presque
  entièrement à un seul marché ; interdire une comparaison entre canaux qui masquait une
  incitation économique ; limiter un miroir de prix à deux marchés, ce qui créait une
  absence ; comparer un prix de gros à un prix de détail. Règle : **chaque brief porte le
  test qui le falsifierait**, écrit avant l'envoi.
- **Les conclusions ont été enregistrées trop tôt.** Un sujet a été ouvert sur une
  coïncidence de forme et fermé deux heures plus tard par un test catégorique. Règle :
  les faits entrent au registre immédiatement ; **une lecture n'entre qu'après un test
  catégorique ou une connaissance du CEO**, jamais sur un ratio.
- **Trop de blocs terminal ont échoué au premier essai** — interpréteur système au lieu
  du venv, schéma en retard sur les modèles, rebase divergent, un espace réservé laissé
  dans une commande. Chaque échec coûte un aller-retour au CEO. Règle : tout bloc est
  exécuté d'abord contre une base dans l'état de la sienne ; le double-clic sur
  `start.command` fait pull, migration et démarrage sans qu'il tape rien.
- **La longueur des réponses.** Le CEO demande de mesurer et de voir. Les leviers, les
  recommandations d'action et les listes de questions à d'autres équipes sont hors de sa
  demande sauf s'il les réclame.

---

## 4. Règles de travail — à ne pas réapprendre

**Forme des échanges.** Un bloc de code cerné de trois accents graves est destiné au
terminal du CEO, et à rien d'autre ; l'interpréteur est toujours `.venv/bin/python
manage.py …`, jamais `python3`. Un brief pour l'agent entrepôt n'est jamais cerné. Un
message qui demande plusieurs gestes les numérote en BLOCs, une destination par bloc. Les
retours de l'agent entrepôt sont cités et vérifiés avant d'être commentés.

**Règles de mesure**, chacune née d'un défaut vu ici :

1. Une absence n'est jamais un zéro. Elle est nommée, avec son volume.
2. Un facteur qui se déclenche partout n'ordonne rien.
3. Un signal isolé est une mesure inhabituelle, pas un comportement. Deux le suggèrent,
   trois le nomment.
4. Un seuil absolu ne traverse jamais deux populations ; seuls les rangs se comparent.
5. Le dénominateur d'un ratio est ce à quoi le comportement se rapporte réellement, et
   le ratio le dit en une ligne.
6. **Un taux moyen ne répond jamais à une question marginale.** Ce qu'un canal a rapporté
   et ce que son prochain euro rapporterait sont deux nombres différents dès que les coûts
   ne suivent pas les ventes, et ils peuvent se classer dans l'ordre inverse.
7. **Un remplissage en forme de valeur n'est pas une valeur.** Une absence écrite
   « N/A » joint, compare, s'agrège et se moyenne, quand un `NULL` s'annonce. Ce défaut a
   été trouvé quatre fois par quatre chemins différents et a chaque fois produit une
   lecture fausse et confiante. Les sentinelles connues vivent dans `app/perf/sentinels`,
   avec la condition SQL à recopier telle quelle dans les briefs : un `IS NULL` seul y est
   insuffisant par construction.
8. **Une absence constatée dans une table n'est pas une absence dans l'entrepôt.** « Ce
   champ n'existe pas » ne se dit qu'après avoir cherché ailleurs que dans la table qu'on
   avait sous la main. Le statut de propriété des boutiques a été déclaré introuvable sur
   la foi d'un seul référentiel ; il vivait dans un second, jamais ouvert, et cette
   conclusion a fermé un chantier pendant plusieurs jours.
9. Aucune règle ne se déclenche sur une ligne à zéro.
10. Un signal ne conclut jamais : il désigne ce qu'il faut aller vérifier, et c'est un
   test catégorique — au ticket, à la ligne, au mois — qui tranche.
11. Deux bases ne s'additionnent jamais en silence. Quand elles sont comparées à dessein,
   l'en-tête le déclare.

**Registre.** Observer d'abord, conclure après. Une conclusion remplacée exige une raison.
La clôture est humaine et nommée. Un sujet est la décision qu'il appelle, pas la
géographie où on l'a vu.

**Sécurité.** Aucun chiffre, marché, personne ou produit réel dans le dépôt — le test
`tests/test_no_real_figures.py` l'impose et il doit rester vert. `var/` porte le réel et
reste ignoré. Rien de personnel n'approche le dépôt, même dans un répertoire ignoré.
L'application ne réécrit rien dans aucune source qu'elle lit.

---

## 5. Plan d'action, dans l'ordre

Chaque phase a un critère de recette binaire. On ne passe pas à la suivante sans lui.

### Phase 0 — Consolider (une demi-journée)

- Mettre la branche principale au niveau de la branche de travail.
- Réécrire l'en-tête du `README.md` pour que le Performance Cockpit soit le produit
  décrit en premier, et remplacer la « Suite proposée » héritée de Decision Room par un
  renvoi vers ce document.
- Ajouter un renvoi vers ce document en tête d'`AGENTS.md`.

*Recette* : une personne qui clone le dépôt lit d'abord le cockpit, et sait dans quel
ordre travailler.

### Phase 1 — Le registre à l'écran (priorité absolue)

La route de l'écran « Today » charge le registre (`memory.load`), le fait tourner dans le
moteur de sélection (`selection.rank`) après l'analyse de détection (`detection`), et
sauvegarde ce qui a changé. Les trois créneaux d'attention et les cinq de surveillance
viennent de là ; la liste recalculée d'`analytics` cesse d'être la source de l'attention
et devient une source de **preuves** pour le registre.

- Chaque carte porte : rôle CEO, chiffre et tendance, la raison d'entrée en mots (jamais le
  score), la question spécifique à sa preuve, la personne utile, l'échéance.
- Un bloc « depuis la dernière lecture » construit à partir des lectures et des
  transitions du registre.
- Deux gestes humains accessibles depuis l'écran, par formulaire local : accepter une
  variance (décideur, date, raison, réexamen), clore (nom, motif).
- Le sommeil d'un sujet arbitré et son réveil sur fait nouveau se voient.

*Recette* : ouvrir l'écran deux fois de suite montre les mêmes références de sujets ; une
lecture ajoutée en ligne de commande apparaît à l'écran ; jamais plus de trois sujets en
attention, cinq en surveillance ; un sujet arbitré ne revient pas la semaine suivante
sans fait nouveau.

### Phase 2 — B3, où j'en suis dans le mois

Un module `pace` : avancement du mois selon une courbe de phasage tirée du même mois de
l'an dernier au grain jour ou semaine, alignée sur les événements mobiles plutôt que sur
les dates ; avancement vers l'objectif du mois par périmètre et par canal ; les deux taux
côte à côte. Le sell-in n'avance pas en jours : tant qu'aucun calendrier d'expédition
n'est connecté, il affiche « non disponible ».

*Recette* : pour chaque périmètre, deux nombres lisibles en une seconde, chacun avec sa
base ; un canal sans phasage connu le dit au lieu d'interpoler.

*État (4 septembre)* : fait, sous réserve d'une requête à valider. Le module `pace` rend
les deux taux en fourchette ; `month` les joint au plan et à l'organigramme par
périmètre ; le panneau « Où en est le mois » est sous l'en-tête ; `manage.py month` rend
la même chose au terminal. La requête `MONTH_TO_DATE` — un mois, une dimension, bornée —
est écrite sur le modèle des autres et n'a pas encore tourné contre l'entrepôt : c'est
la première chose que la commande vérifiera. La forme des mois n'est pas alignée sur les
événements mobiles mais **mesurée** : là où les années ne s'accordent pas, la fourchette
le dit, et le calendrier sert à expliquer, jamais à corriger. Reste à faire : le sell-in,
qui attend un calendrier d'expédition.

### Phase 3 — B5, le mix

**Deux questions, deux taux, et les confondre inverserait la réponse.**

Le taux de contribution moyen d'un canal dit ce que ce canal a rapporté. Il ne dit **pas**
ce que le prochain euro rapporterait, et c'est pourtant la question que pose B5. La raison
est une structure de coûts, pas une nuance : le retail est un métier à coûts fixes — un
euro de plus dans une boutique ouverte ne coûte que le produit — quand le wholesale est un
métier à coûts variables, où la remise consentie *est* le coût et suit chaque euro. Le taux
moyen classe donc le wholesale devant le retail, et le taux marginal peut faire l'inverse.

Et le régime n'est pas uniforme à l'intérieur d'un même canal : **les loyers sont fixes
dans les marchés occidentaux et variables en Asie**, où ils sont un pourcentage du chiffre.
Un euro de plus dans une boutique occidentale et un euro de plus dans une boutique
asiatique ne valent donc pas la même chose, et aucun taux unique par canal ne peut le dire.

Ce que la phase construit :

- `var/contribution.csv` porte le **taux moyen** par canal, qui est connu, et un **régime
  de coûts** par marché — loyer fixe ou variable. Un canal vendu que le fichier ne nomme
  pas est **ABSENT**, jamais pris à zéro ni à la moyenne des autres.
- **La part loyer du coût marginal est mesurée, boutique par boutique.** Le référentiel
  immobilier de l'entrepôt porte un pourcentage de loyer variable par bail : là où il
  existe, un euro de plus vendu dans cette boutique perd exactement ce pourcentage ; là où
  le loyer est fixe, il n'en perd rien. La distinction n'est donc plus une hypothèse par
  marché, c'est une propriété de bail. **Elle se lit par boutique, jamais par marché**, et
  chaque agrégat par marché porte son taux de renseignement — qui va de moins de quatre
  pour cent à cinquante pour cent selon les pays, et vaut zéro dans plus de la moitié
  d'entre eux.
- **Le reste du taux marginal n'est pas connu** et n'est pas inventé : personnel, logistique
  et marketing demandent une part fixe et une part variable qu'aucune source lue ici ne
  porte. L'écran le déclare absent, nommément, et ne présente jamais la seule part loyer
  comme un taux marginal complet.
- L'écran affiche l'écart de mix contre le mix planifié et l'écart de ventes repondéré aux
  taux moyens — présenté comme un calcul, coefficients affichés, **jamais** comme un
  résultat, et jamais comme un EBITDA.
- **Aucun classement « où pousser » ne se fait sur le taux moyen.** C'est la protection qui
  compte : sans elle, l'écran conseillerait de pousser le canal au taux le plus élevé,
  c'est-à-dire l'inverse de ce que la structure de coûts commande.

*Recette* : un mois à l'équilibre en ventes et hors plan en mix se voit ; aucun EBITDA n'est
produit ni suggéré ; la base de chaque chiffre est affichée ; le taux marginal est nommé
absent plutôt que remplacé par le taux moyen ; deux marchés de régimes différents ne sont
jamais comparés sur le même taux sans que l'écran le dise.

**État au 4 septembre 2026 — première pièce livrée.** `var/contribution.csv` se lit tel que
la maison l'écrit (`name,kind,average_rate,as_of,source` ; un nom peut couvrir deux canaux du
plan ; une ligne de partenaire est lue et jamais posée sur un canal). L'écran et `manage.py
mix` rendent, par canal et par poids au plan, la part planifiée, la part réalisée et les
points de mix — sans aucun taux — puis, quand le fichier en porte, l'écart de ventes × taux
moyen, séparé en effet volume et effet mix, identité gardée par test. Un canal sans taux est
absent avec son poids, la couverture est affichée, le taux marginal est déclaré absent, et
aucune ligne n'est rangée par taux. Reste à faire : le régime de coûts par marché, et la
part loyer du coût marginal lue par boutique dans le référentiel immobilier.

**Le fichier de clôture a changé de forme en août 2026**, et le fichier de la CFO est une
troisième forme des mêmes lignes. Le lecteur reconnaît les trois depuis les feuilles du
classeur — positions pour le flash d'origine, colonnes nommées pour le fichier de clôture
(une feuille par mois, la plus récente lue), taux constant pour l'extraction de la CFO —
et reproduit à l'euro le total, le budget et l'an dernier que le récapitulatif publie. Au
passage, une ligne qui ne porte qu'un an dernier est gardée : l'ancien lecteur la laissait
tomber, et l'an dernier de mai manquait d'un demi-million contre le flash. L'extraction de
la CFO porte aussi une feuille **par boutique**, avec son budget : c'est la maille de la
pièce suivante de cette phase, le régime de loyer lu bail par bail.

**Deuxième pièce livrée — la part loyer, boutique par boutique.** `var/stores.csv` (le
référentiel immobilier extrait de l'entrepôt : code, bail, part de loyer variable telle
qu'elle est écrite) se joint par le code à la feuille par magasin de l'extraction de la CFO
(`var/stores-sales.xlsx`). Par marché : boutiques, baux connus, couverture en ventes, part
loyer pondérée sur les seules boutiques au bail connu ; trois états jamais confondus —
part écrite, zéro écrit, rien d'écrit. Ce que le référentiel a appris en le lisant : le
code de consolidation est dans `STORE_CODE` pour la moitié des boutiques (le travel retail
suit une autre nomenclature) ; `VAR_RENT_PERCENT` vaut souvent un zéro écrit, qu'il faut
distinguer de l'absence ; `OWNERSHIP_DESC` oppose détenu et non détenu et ne dit rien du
régime de loyer ; le loyer fixe a sa colonne, `MONTHLY_RENT` ; les dates d'ouverture ne sont
renseignées nulle part. Les bornes du plan étaient fausses : la part variable positive va
de moins de deux pour cent à un peu moins de la moitié des boutiques selon les pays, et
trois pays sur quatre n'en ont aucune.

**Phase 3 close, le 4 septembre 2026 — recette.** Un mois à l'équilibre en ventes et
hors plan en mix se voit : l'août clos est à soixante mille euros du plan et cède quatre
points aux e-retailers. Aucun EBITDA n'est produit ni suggéré, et un test le garde. La
base de chaque chiffre est affichée : coefficients du mix, couverture des taux, couverture
des baux. Le taux marginal est nommé absent, deux fois, et la part loyer n'est jamais
présentée comme lui. Deux régimes ne sont jamais comparés sur le même taux sans que la
couverture le dise. Le référentiel immobilier a mesuré ce que le plan supposait : l'Asie
rend entre dix-sept et vingt-neuf pour cent de l'euro suivant au bailleur, la France et
l'Allemagne moins de cinq. Ce qui reste, et qui n'est pas du code : un type de contrat par
boutique — concession, franchise, distributeur, opérateur de travel retail —, que le
référentiel ne porte pas et que Cortex ne peut lire qu'en croisant des libellés ; un tiers
des boutiques chinoises et toutes celles du Vietnam et de Nouvelle-Zélande sans bail
renseigné ; et les 327 boutiques « Not Owned » hors travel retail, qui attendent une
réponse de l'immobilier. Demandé à l'équipe data dans le document qui lui est destiné.

**Les taux, réglés le 4 septembre 2026.** L'entrepôt convertit chaque devise à un taux
fixe, invariant sur huit exercices, et ce taux est exactement le taux budget FY27 du
classeur de plan, devise par devise. Le sell-in de l'entrepôt, le sell-out de l'entrepôt,
le plan et la consolidation « at budget rates » sont donc au même barème : le verdict de
l'exercice additionne du comparable, et la croissance en euros est la croissance en
devise locale. Une seule règle à garder : un taux se dérive d'une somme, jamais d'une
ligne, l'arrondi au centime sur de petits montants faussant le rapport ligne à ligne.

### Phase 4 — B1, une page par périmètre

Le même squelette pour les sept : où en est l'année, ce que le périmètre porte du plan,
l'avancement du mois (phase 2), le mix (phase 3), les sujets du registre qui le concernent
(phase 1), le dernier engagement, la seule question du jour. Le MD est nommé ; les GM
apparaissent en détail, jamais comme destinataires.

*Recette* : trente secondes avant un appel suffisent ; deux périmètres se comparent sans
que le format ait bougé.

**Première pièce livrée, le 4 septembre 2026.** `/perimetres` liste les périmètres avec
leur MD, les deux verdicts et l'atterrissage à ce rythme ; `/perimetre/<nom>` rend, sur
les marchés que l'annuaire place sous ce MD : les verdicts du mois et de l'exercice,
l'atterrissage — « si le reste tient le plan » et « à ce rythme », deux hypothèses et
aucune prévision —, les sujets du registre qui le concernent, les feux, le mois marché
par marché, le mix. La question du jour est le sujet porté cette semaine, sinon le plus
gros feu, sinon ce que le verdict du mois dit. Reste : la semaine écoulée (ce qui a bougé
depuis lundi, marché par marché), qui demande une lecture au jour que l'entrepôt ne fournit
pas encore au cockpit, et les white spaces, dont la donnée externe (Beauté Research pour
l'Asie) reste à voir.

**L'écran d'accueil refait autour des questions d'un CEO, le 4 septembre 2026.** Dans
leur ordre : où on atterrit, sommes-nous en ligne, qu'est-ce qui décroche et qui en
répond, qu'est-ce que je décide cette semaine, où est l'upside, le plan est-il crédible,
la donnée est-elle saine. L'atterrissage ouvre l'écran ; le verdict nomme sa composition
— « en ligne au total · en retard : Brésil, Japon », et « hors Greater China : en retard »
quand un seul périmètre porte le total ; aucun mot sur le mois avant une semaine pleine
lue, parce que quatre jours sans week-end ne mesurent rien ; le mois marché par marché
est replié sous chaque périmètre ; un seul cumul, une seule langue ; la provenance vit
dans « Comment lire cet écran ».

**L'usage d'abord, le 5 septembre 2026.** Relecture de toutes les demandes depuis le
début du projet : le premier besoin non servi n'était pas une lecture de plus, c'était de
pouvoir ouvrir l'application et la lire dans une seule langue. Trois gestes. Le lanceur
`start.command` libère le port avant de démarrer — un serveur resté ouvert dans une autre
fenêtre servait l'ancien code et le nouveau refusait de démarrer, ce qui est exactement le
cas « je n'arrive plus à ouvrir l'app » — puis met à jour, relance avec rechargement, ouvre
le navigateur. Tout ce que les cartes génèrent est en français : diagnostics, questions,
raisons du classement, badges (`CAUSE NON MESURÉE`, `SANS ENGAGEMENT`), gestes
(`Challenger`, `Enquêter`, `Demander la donnée`), phrases de plan, notes de contexte,
états des KPI, bandeau et pied de page ; les euros s'écrivent « 1.2 M€ » et « 432 k€ », les
pourcentages avec leur espace, les mois en français. Les leviers gardent leurs noms de
maison (`Sessions`, `Conversion`, `AOV`) et prennent leur article dans la phrase. Le bruit :
les plans sur effet de base sortent de la liste et sont comptés en une ligne ; la section
« Ask Performance CoS », qui annonçait ce qui n'existe pas, est retirée. Reste en anglais :
la page « État du système », registre technique qui n'est pas l'écran du CEO, et les
données de démonstration.

**Le plan EBITDA par périmètre, le 5 septembre 2026.** Le classeur du budget EBITDA par
BU de la Finance est lu (`var/ebitda-budget.xlsx`, `app/perf/ebitda.py`) sur sa feuille de
synthèse — la contribution de chaque BU et son taux, les flux que le budget nomme lui-même à
nettoyer, le pont vers l'EBITDA consolidé ajusté — et sur sa feuille COP, pour le pas de
marge opérationnelle que le plan demande à chaque région entre la dernière prévision de
l'exercice précédent et le budget. Deux BU du fichier font l'EMEA de l'annuaire ; le travel
retail et « Other » restent nommés hors périmètres. À l'écran : une colonne « EBITDA au
budget » dans la table des périmètres, une ligne sous le verdict, une carte sur chaque page
de périmètre. Ce que le module refuse : convertir un écart de ventes en EBITDA par un taux
moyen — le compte de gestion a mesuré qu'un réseau de boutiques perd plus d'un euro de
contribution par euro de vente perdu quand un partenaire en rapporte trente centimes, et la
marge marginale par canal et pays existe désormais dans `var/incremental_margin.csv`, à lire
comme prochaine pièce de B5 à la place du taux moyen. Demandé à la Finance : un EBITDA réel
mensuel par BU, et le contenu des honoraires imputés au canal distributeurs France.

### Phase 5 — B6, les moteurs du plan

Un fichier des moteurs nommés du plan (owner, montant embarqué sur l'année, livré à date,
état, question du mois), lu comme une source. Ce bloc **remplace** une partie du classement
des écarts plutôt que de s'y ajouter — c'est la contrainte « deux écrans ».

### Phase 6 — La surface (§E)

Ordre d'écran de la doctrine, navigation en cinq onglets, absorption de Decision Room par
Investigate et Commitments. Deux décisions du CEO sont nécessaires avant (voir §6).

### Phase 7 — Le détecteur de flux gris à l'écran

Une section sous Data Health ou Investigate, lisant le fichier des signaux avec ses
colonnes de rang. Le classement par distance se fait sur les rangs et non sur les
ratios bruts dès que le fichier les porte — le lecteur les reçoit déjà et les nomme
comme non lues.

### Phase 8 — L'analyse par une IA (§6 du brief besoin)

D'abord **consigner** la réponse déjà donnée : faisabilité, architecture, ce qui quitte la
machine et vers où, coût, latence, hors connexion. Ensuite seulement construire, et
seulement après les phases 1 à 3 : la couche déterministe doit être complète avant qu'une
lecture rédigée se pose dessus. Chaque phrase générée référence les champs numériques
qu'elle décrit ; une phrase non traçable ne s'affiche pas.

### En attente, sans date

Retrait de Decision Room ; PostgreSQL ; annuaire d'entreprise et audit — nécessaires avant
tout usage à plusieurs.

---

## 6. Décisions du lecteur

**Tranchées le 2 septembre.**

1. **La langue de l'interface est le français.** Le conflit 5 de la doctrine V6.1 — qui
   demandait un écran entièrement en anglais — est résolu dans l'autre sens. L'écran web
   est aujourd'hui en anglais et doit être repris ; le terminal, les notes et le registre
   sont déjà en français. Travail à porter en phase 6, mais toute chaîne nouvelle écrite
   d'ici là l'est en français.
2. **Les taux de contribution moyens par canal sont connus** — cinq lignes, lues dans le
   comité de pilotage de mai. Ils vivent dans `var/contribution.csv`, jamais dans le dépôt.
   Ils ne couvrent pas tout le périmètre vendu et deux d'entre eux nomment un partenaire
   plutôt qu'un canal : ce qui manque sera nommé, pas comblé. **Le taux marginal, lui,
   n'est pas connu** — voir la phase 3, qui dit pourquoi c'est la vraie question de B5 et
   pourquoi le taux moyen y répondrait à l'envers.
3. **Il n'existe pas de calendrier des événements mobiles — et il n'en faut pas.**
   L'alignement par semaine, d'abord retenu, a été cassé par le lecteur en une phrase :
   il corrige la dérive d'un ou deux jours et ne corrige rien quand la fête des mères
   passe de la deuxième à la troisième semaine, ou quand Black Friday change de semaine.
   La réponse ne demande aucun calendrier : **au lieu d'affirmer une forme, mesurer si une
   forme existe.** Avec plusieurs années, la dispersion d'une semaine dit tout. L'écran
   rend donc une fourchette et non un point — étroite, elle se lit comme un point ; large,
   elle dit que ce mois n'a pas de forme stable et que le lecteur ne doit rien en conclure.
   Une seule année de référence ne vérifie rien et le déclare. Effet de bord précieux : le
   fichier désigne de lui-même les marchés et les mois traversés par une date mobile.

**Encore ouvert.**

4. **Decision Room** : conserver ou retirer. Sans réponse, on conserve.

*Tranchée le 3 septembre.* **Pas de pondération stratégique pour l'instant : le classement
se fait sur le plus gros écart au plan.** L'argument du lecteur tient — le plan porte déjà
des croissances par canal et par pays, donc l'intention stratégique y est encodée. La
réserve, à garder en tête : un écart en euros favorise les grands marchés par construction,
et un petit marché qui rate une croissance ambitieuse peut compter davantage qu'un grand
qui rate de peu. Le fichier de poids reste lisible le jour où cette réserve devient gênante.

En le posant, un défaut réel a été trouvé et fermé : deux règles portaient le **flux**
entier d'un partenaire là où les autres portent un **écart**. Un flux vaut structurellement
dix à cent fois un écart, donc il occupait le premier créneau devant tous les marchés sous
plan, et il l'aurait occupé à jamais. Un montant déclare désormais ce qu'il mesure ; seul
un enjeu ordonne.
*Tranchée le 3 septembre, par la mesure et non par un avis.* Le régime de loyer se lit
dans le référentiel immobilier de l'entrepôt, bail par bail. La règle donnée par le lecteur
— variable en Asie, fixe à l'Ouest — est confirmée là où les baux sont renseignés, et de
façon franche : un marché asiatique majeur porte plus de deux cents boutiques en variable
seul contre trois en fixe, quand deux grands marchés européens n'ont aucune boutique en
variable. Le marché nord-américain, lui, est massivement en mixte — minimum garanti plus
pourcentage — ce qu'aucune règle à deux valeurs n'aurait dit.

## 7. Ce qui attend l'équipe data

Une seule liste, envoyée en une fois parce que le retour est lent :

1. La nomenclature des coffrets vendus en travel retail qui ne figurent ni dans la table
   des nomenclatures ni dans celle des packs.
2. Le statut des références à suffixe régional distribuées à un grand nombre
   d'opérateurs sans miroir domestique.
3. Une référence exclusive au travel retail porte-t-elle un prix de référence domestique ?
   Sans lui, elle est incomparable par construction.
4. Un compte de vente au personnel existe-t-il dans les marchés majeurs sous un libellé
   qu'une recherche par mots-clés ne trouve pas ?
5. Le compte de vente au personnel du marché où il est le plus lourd est-il un canal vers
   les salariés, ou un compte de facturation dont les bénéficiaires ne sont pas identifiés ?
6. Pourquoi la vente au personnel est-elle classée en cadeaux d'entreprise dans les deux
   marchés où elle existe côté facturation ?
7. Le point de vente physique portant le plus gros volume gratuit du monde n'a pas de
   code au référentiel des magasins.

La traçabilité code produit → lot → facture n'est pas systématisable : c'est acquis, et
cela signifie que le détecteur ne sera jamais calibré sur des cas connus. Il fonctionne
donc par tests catégoriques, et une unité achetée en rayon puis tracée à la main reste
la seule preuve opposable.

---

## 8. Ce qui reste ouvert chez l'agent entrepôt

Le test du gratuit non rattaché, descendu au point de vente, sur le marché qui en porte
la plus forte proportion et qui n'a jamais été regardé. Les six tests du dernier brief
sont sinon traités, et leurs résultats sont dans le registre.
