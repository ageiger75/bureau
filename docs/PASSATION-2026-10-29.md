# Passation — sessions de septembre à octobre 2026, au 29 octobre

À lire par la session qui reprend le travail, après `AGENTS.md` et `docs/PLAN.md`. Ce
fichier dit qui travaille, comment, ce que le cockpit sait faire de plus qu'au début de
l'automne, ce qui est ouvert, et les pièges rencontrés. Il ne contient aucun chiffre réel,
aucun nom de partenaire ni de personne, aucun code de centre de profit ni d'entité : la
règle du dépôt vaut pour lui aussi, et `tests/test_no_real_figures.py` la garde. Les
chiffres vivent dans la conversation et dans `var/`, jamais ici. Il remplace la passation
du 24 octobre, dont tout le contenu encore vrai est repris.

## 1. Qui travaille, et où

**Le lecteur** est le CEO. Il ne code pas. Il travaille depuis cinq endroits :

- **GitHub**, ce dépôt. La branche de travail est `claude/github-repo-setup-continue-f467r7` ;
  `master` est synchronisée à chaque poussée (`git push origin HEAD:master`). Le lecteur ne
  fait que `git pull --ff-only`.
- **Son Mac**, dossier `~/dev/ceo-os`. Fenêtre A : `start.command`, l'application sous
  uvicorn avec rechargement automatique du code ; le script arrête le superviseur puis
  l'ouvrier d'uvicorn, attend que le port se libère et n'ouvre le navigateur qu'après, pour
  qu'un double-clic avec une fenêtre déjà ouverte ne bloque plus. Fenêtre B : les commandes.
  Une nouvelle fenêtre Terminal s'ouvre dans le dossier personnel, pas dans le projet :
  chaque bloc de commandes commence par `cd ~/dev/ceo-os &&`. L'afficheur de `git diff` a
  été remplacé par `cat` (`git config --local core.pager cat`) parce qu'il bloquait la
  fenêtre. Le dépôt local a `pull.rebase` : un fichier modifié localement fait refuser la
  mise à jour.
- **Le navigateur**, dont il colle le texte des pages dans la conversation. C'est ainsi
  qu'on voit ce que l'écran dit vraiment ; ne jamais supposer, demander la page. Quand une
  page tombe en erreur interne, c'est le journal de la Fenêtre A qui porte la trace.
- **Cortex Code**, l'agent de l'entrepôt Snowflake. Il lit l'entrepôt, valide les requêtes
  avant qu'elles entrent dans le cockpit, confronte les fichiers de la Finance aux lectures
  du cockpit, et n'écrit que dans `var/` (ses comptes rendus `var/cortex-*.md`, ses rapports
  `var/ref2-rapport.md`, sa mémoire `var/entrepot.md`). Il a modifié du code une fois, par
  exception ; ses modifications ont été reprises à la main dans le dépôt avec leurs tests,
  et ses copies locales effacées (`git checkout -- app tests`). Depuis, « n'écris pas de
  patch, la bascule est faite dans le dépôt » lui est dit explicitement quand il le propose.
- **Une session Claude Code locale**, sur le poste, qui a ajouté `manage.py cabinet` (la
  lecture du jour en un fichier pour les agents de `~/cabinet`, contrat dans
  `docs/CABINET.md`) sur sa propre branche, fusionnée ici sans réécriture. Règle : une
  session locale pousse sur notre branche, ou le dit pour que l'on fusionne.

Le cockpit ne lit que le poste du lecteur : la session de développement n'a ni l'entrepôt,
ni l'annuaire, ni les fichiers de `var/`. Le jeu de démonstration n'a ni annuaire ni plan
EBITDA : un périmètre qui porte à la fois des factures et une ligne EBITDA ne se construit
que dans un test qui le monte exprès, et c'est ainsi qu'un plantage des pages de région a
été reproduit.

## 2. Conventions de la conversation

- **Un bloc encadré est une commande pour la Fenêtre B**, numéroté BLOC 1, 2, 3. Le
  lecteur les colle tels quels. Rien d'autre n'est encadré.
- **Un brief Cortex n'est jamais encadré**, il est « à transmettre tel quel » : une seule
  tâche bornée, métadonnées d'abord, une nouvelle session Cortex par brief, réponse en dix
  lignes dans un fichier `var/cortex-<sujet>.md`, ordre explicite de s'arrêter, ne pas
  modifier le code. Toujours refuser ses offres d'automatisation (launchd, agent mensuel).
  Ne jamais lui demander ce que le cockpit sait calculer. Le SQL s'écrit ici ; Cortex le
  valide avant qu'il soit poussé. Quand il a déjà mesuré une règle sur l'entrepôt, la mesure
  vaut validation et la règle s'écrit dans le dépôt avec sa raison, jamais avec ses chiffres.
- **Les chiffres réels** sont permis dans la conversation et dans `var/`, nulle part
  ailleurs. Les rapports que le lecteur téléverse se lisent hors du dépôt ; rien n'en est
  copié dans un fichier versionné.
- **Jamais recommander `manage.py refresh` avant d'ouvrir une page** : les lectures partent
  en arrière-plan à l'ouverture et la page se recharge seule ; `refresh` ne fait qu'oublier
  un cache. Quand une relecture à la main s'impose, dire d'attendre quelques minutes.
- **Un commit ne part que si `pytest -q` rend zéro** (vérifier `${PIPESTATUS[0]}`, pas la
  sortie). Les commits portent les deux lignes de fin convenues et aucun identifiant de
  modèle. Le bac à sable refuse `git commit --amend` et toute poussée forcée.
- **Vérité avant confort**, même sur les lectures de la session précédente : quand une
  vérification Cortex a contredit une hypothèse énoncée en conversation, la correction a été
  dite au lecteur en premier. Et quand un correctif vient d'être poussé, dire au lecteur
  qu'une trace d'erreur collée juste après peut dater d'avant le pull.

## 3. Ce que le cockpit sait faire, par thème

Chaque thème a sa note dans `docs/PLAN.md`, section « sell-in » et section 6 ; le code est
nommé ici pour qu'on le retrouve.

### 3.1 Cinq apprentissages de l'équipe data et de Cortex

Appliqués dans l'ordre : le drapeau vrac n'est validé par la Finance qu'en Chine et à
Hong Kong (`perf/grey.py`, « drapeau non validé » partout ailleurs) ; les filtres de la
maison sur le sell-in — types de point de vente commerciaux, kits comptés une fois — et
les factures aux filiales du groupe tenues à part et nommées (`perf/invoiced.py`,
`perf/queries.py`) ; le gris sans drapeau lu sur la remise explicite des lignes payées, la
revente étant le gros ticket remisé bien plus que les autres (`perf/shadow.py`) ; les héros
par le drapeau produit et le fait que la Chine n'identifie pas ses clients à l'encaissement
(`perf/products.py`, `perf/clients.py`) ; le livré sur commandé retiré, parce que la vue des
commandes n'en porte qu'un proxy, et remplacé par le carnet ouvert (`perf/orderbook.py`).

### 3.2 Le mois « sell-in compris »

La carte `page.Together` ajoute au verdict sell-out le sell-in facturé à date contre le
plan. Règles arrêtées sur de vraies données : l'attendu est de préférence les factures de
l'an dernier à jours ouvrés égaux au rythme du plan sur son an dernier, mêmes lignes ;
quand la source voit plus que l'an dernier du plan, on ne demande jamais plus que le plan
lui-même ; sous un plancher ou au-delà d'un plafond de couverture, pas de mot, la raison ;
quand le sell-out seul et le sell-in seul ne disent pas le même mot, la carte dit les deux
avant la somme. Le travel retail est une BU, pas une géographie : ses factures vont au
périmètre qui porte ses entités du plan. Un périmètre sans sell-out se lit sur son sell-in
seul. `manage.py ensemble <périmètre>` décompose tout : marchés du verdict, pays facturés
avec l'an dernier et où l'annuaire les range, lignes du plan avec leur an dernier et les
factures de l'an dernier du marché, partenaires du mois à date, carnet, carte.

Un pays qui facture ce mois-ci sans une seule facture le même mois l'an dernier dans la
source — une entité nouvelle, un pays que la source ne voyait pas — faisait lire à son
périmètre une croissance à trois chiffres. Il reste dans le facturé à date, sort de la
croissance à jours ouvrés égaux et à dates égales, et est nommé avec son montant
(`invoiced.Line.unseen`, `unseen_note`) : au groupe, par périmètre, par canal, dans
`manage.py ensemble`. Quand tout le facturé vient de tels pays, pas de croissance, la
raison. Et quand le classeur de la consolidation ferme deux mois à la fois, le dossier de
visite dit que le sell-in est lu sur cet intervalle, à part, et somme le plan sur ses mois
(`budget.months_of`, `visit.period_phrase`).

### 3.3 Le carnet de commandes ouvert

Au niveau du groupe par canal, en trois paquets sur la date de promesse au client. Par
périmètre et par partenaire sur la page de chaque périmètre, sur le pays du client facturé
tel que la dimension le nomme (il n'y a pas d'ISO2 ; la requête `ORDER_BOOK` porte
`country`, `code`, `label`, validés par Cortex, totaux inchangés à l'euro) et ramené au nom
de marché. Une note `on_hold` du fichier de contexte marque un canal « tenu exprès » : sans
marché, elle tient le canal partout et son retard est retiré du jugement ; avec un marché,
elle ne marque que le périmètre qui le porte, sans rien retirer. Le carnet a sa propre
section sur les trois pages, parce que le premier du mois aucune facture du mois n'est lue
et il disparaissait avec. Le carnet n'a pas le défaut de change des factures (3.10).

### 3.4 Le biais de prévision

Un marché de prévision au réel presque nul rendait un biais de plusieurs milliers de pour
cent et une précision négative sur le groupe. Au-delà de `supplychain.BIAS_UNREADABLE`, la
ligne est hors lecture, nommée à part, le groupe se lit sur les autres, la précision ne
descend jamais sous zéro.

### 3.5 Le rapprochement Finance, et ce qu'il a fermé

Cortex a confronté les fichiers Finance de septembre aux lectures du cockpit. La
consolidation, le sell-in par canal, le sell-out et le parc tombent juste à de petits
écarts près. Deux défauts corrigés : le chiffre publié n'est posé à côté d'une ligne que
si le fichier parle du mois de la ligne (`mapping.units_from_rows`), et le Luxembourg se
range sous l'entité belge (`budget.MARKET_ALIASES`). Trois vérifications
(`var/cortex-finance-*.md`) ont établi qu'en Chine et à Hong Kong l'écart est une règle
uniforme magasin par magasin, de l'ordre de cinq points, ni le parc ni le vrac, présente
aussi au Brésil les deux années.

Trois questions fermées depuis. **Le taux de change est hors de cause** (`var/cortex-taux.md`) :
le « constant » du fichier Finance est le taux annuel, le même que l'entrepôt, et le
« publié » le taux moyen du mois ; les écarts de la Chine réunifiée et du Brésil sont des
écarts de montant local, entre le net caisse et le net publié, et la question va à la
Finance. **Le saut de Hong Kong en septembre** est un déplacement de périmètre : la Finance
range Hong Kong et Macao sous la Chine depuis le reforecast 2 ; dit par des notes de
contexte, et par un placement décidé (3.8), sans fusion des marchés dans le code. **Le
Brésil** : la Finance déduit depuis mai la nouvelle structure fiscale sans retraiter l'an
dernier, sa croissance mélange deux bases, la règle reste à obtenir. Aux États-Unis, un
seul client a changé de canal en mai, sans retraitement de l'an dernier dans la
consolidation ; le cockpit prend l'an dernier au plan et n'est pas touché.

### 3.6 Les partenaires à périmètre constant

Les codes de centre de profit que `var/partners.csv` nomme d'un même nom se lisent en une
ligne, sur le canal du code qui facture en dernier, l'an dernier gardé
(`accounts._merge_named`). Une succession que personne n'a nommée est dite sur Analyses,
jamais fusionnée d'office (`Review.succession_note`). Le lecteur a nommé les deux codes du
partenaire américain reclassé ; Cortex a confirmé que c'est la seule succession de cette
nature, tous pays confondus. Le bloc partenaires de `manage.py ensemble` dit quand sa
lecture date d'avant le mois, au lieu d'afficher une chute entière.

### 3.7 Le dossier de visite

Le dossier porte les produits du marché, les statuts de fermeture du fichier de la CFO
(`CEOOS_STORE_CLOSED_STATUSES` dans `.env`), le côté sell-in avec le ciseau, le drapeau
non validé. La consolidation livre des intervalles quand un instantané manque (deux mois
écrits `AAAA-MM..AAAA-MM`) : le plan les rencontre en additionnant ses propres mois
(`budget.Budget.line`, `months_of`), et un sell-in d'une autre période que le sell-out se
lit à part, sans part du mois ni question du ciseau (`visit.Dossier.sell_in_apart`).

### 3.8 L'annuaire, l'organigramme et les placements décidés

Trois sources rangent un marché sous un périmètre, dans cet ordre (`month.place_markets`) :
l'annuaire (`var/owners.xlsx`, un pays par ligne avec sa BU, une feuille de recherche par
pays que Cortex a complétée pour l'export et le travel retail), puis l'organigramme
(`var/org.xlsx`, qui nomme des zones et ne place que ce qu'il nomme sans ambiguïté), puis
les placements décidés (`var/placements.csv`, un marché, un périmètre, une date de fin,
une raison), qui passent par-dessus les deux jusqu'à leur échéance. Les factures sont
nommées par la norme ISO quand le sell-out ne nomme pas le pays (`perf/countries.py`).

Deux pièges. `manage.py org --markets` ne lit que l'organigramme : sa liste de marchés
« non rattachés » n'est pas celle de l'écran, l'annuaire place pays par pays avant lui.
Et l'annuaire range encore Hong Kong, ses distributeurs et Macao sous APAC, quand la ligne
hiérarchique d'aujourd'hui et la Finance mettent Hong Kong et Macao sous la Grande Chine :
le lecteur l'a tranché le 29 octobre par les placements décidés — Hong Kong et Macao sous
la Grande Chine, les distributeurs de Hong Kong sous APAC, jusqu'à la fin de l'exercice.
La correction durable est l'annuaire, à sa prochaine mise à jour ; `manage.py placements`
montre qui répond de chaque marché.

### 3.9 Le reforecast 2 de la Finance, et le millésime

Cortex a confronté le reforecast 2 au cockpit (`var/ref2-rapport.md`, `var/entrepot.md`
§5.12). Ce qui tient à l'euro : le budget et l'an dernier du classeur du cockpit sont ceux
du reforecast ; le réalisé d'avril à août de la consolidation le retrouve par entité et
canal ; le sell-in consolidé des huit canaux est identique, et les croissances américaines
et britanniques qui semblaient folles sont réelles. Les différences sont de périmètre, de
calendrier et de rangement, jamais de données :

- **Comptes.** Les ventes nettes au grain pays tiennent sur cinq comptes ; le cockpit n'en
  lit que deux, ce qui laisserait dehors café, spa et une part du retail. Sans effet
  aujourd'hui : ses requêtes consolidées ne lisent que les huit canaux de sell-in, où les
  trois autres comptes sont nuls (dit dans `queries.py`). Règle pour la suite.
- **Septembre du reforecast** est un mois figé à la date du reforecast, pas le réel
  publié : le cockpit a raison de lire le fichier FS, et un écart sur ce mois n'est pas
  un écart de performance.
- **Rangement.** Mêmes totaux, axes renommés : l'export Europe devient une ligne
  distributeurs, la Suède une ligne nordique, les distributeurs du travel retail de Hong
  Kong passent sous un pays « autre », la Finlande est éteinte, Hong Kong et Macao sont sous
  la Chine. Joindre la Finance sur le code d'entité, jamais sur le libellé pays.
- **Ce que le cockpit n'avait pas : la prévision d'octobre à mars**, par entité et canal.
  La Finance phase l'année : un second semestre de sell-in presque plat après un premier
  semestre fort, et quelques lignes qui s'inversent. Les alertes « plan à recaler » du
  cockpit comparent un plan annuel à un cumul ; elles sont justes sur le passé, et la
  question est le second semestre.

**Le millésime est construit** (`app/perf/reforecast.py`, `manage.py reforecast`,
`var/reforecast.xlsx`), sur la décision déjà prise dans `provenance.py` : le plan reste le
budget, un reforecast se lit à côté, jamais à sa place. Le lecteur a sa propre grammaire de
colonnes — trois formes de mois et deux irrégularités relevées par Cortex sur le vrai
classeur (`var/cortex-ref2-format.md`) — et pose lui-même le partage que l'en-tête ne fait
pas : un reforecast numéro n couvre trois fois n mois réalisés, dont le dernier est figé,
le reste est prévision ; la règle est imprimée en tête de la commande et dans la note de
l'écran, pour être contestée là. L'écran du jour porte l'écart attendu par la Finance à
côté des trois hypothèses d'atterrissage ; la page du périmètre sa phrase (exercice
attendu, prévision du reste contre l'an dernier, les deux semestres, le sell-in à part) ;
Analyses le découpe par périmètre et nomme la part que les périmètres de l'écran ne portent
pas. Les marchés du fichier que le mois n'a pas rencontrés rejoignent leur périmètre par
l'annuaire puis l'organigramme (`reforecast.complete_known`), comme le mois. Vérifié sur
le vrai classeur : toutes les colonnes de mois comprises, le groupe retrouve les chiffres
de Cortex à l'euro. `--structure` imprime chaque colonne telle que le lecteur l'a
comprise ; `--markets` retrouve un chiffre du fichier marché par marché, et dit « ligne
éteinte » d'une entité à zéro partout.

### 3.10 Les factures : la mesure de la maison, et l'empreinte des lectures courtes

Cortex a mesuré que la colonne de montant lue jusqu'ici applique aux factures du hub de
Hong Kong émises dans une autre devise que la sienne le taux de cette autre devise : travel
retail gonflé, distributeurs creusés, sur tous les mois lus, au jour et par partenaire. Les
factures au jour et par partenaire lisent désormais la mesure que la maison désigne, qui
retrouve la consolidation canal par canal ; hors du hub les deux colonnes sont égales à
l'euro (`queries.SELL_IN_DAILY`, `PARTNER_SELL_IN`, test gardien dans
`test_perf_invoiced.py`). Le consolidé et le carnet n'ont pas ce défaut. Toute lecture
sell-in au jour antérieure au 25 octobre est à relire avec cette colonne.

Les lectures courtes (mois, jour, factures) portent l'empreinte de leur requête
(`source._rows_or_last`) : une lecture faite par une autre requête n'est plus servie, même
fraîche, même en dernier recours, parce qu'un chiffre faux daté reste faux. Les lectures
longues l'avaient déjà. Un cache expiré est servi et relu derrière l'écran, le carnet
compris (`source._query_rows`, `reread.reread_all`) : il était resté des semaines sans
relecture.

### 3.11 Robustesse, apprise sur le poste

- Les pages des régions facturées tombaient en erreur interne : dans `page.build`, la
  variable du plan sell-in du mois écrasait celle du plan EBITDA, et la carte « EBITDA au
  budget » lisait un montant comme un plan. Corrigé, deux tests qui montent un périmètre
  avec factures et ligne EBITDA.
- Un pays et son entité voisine lus sous deux noms par l'entrepôt sont un seul marché
  (`month.build` fusionne par nom normalisé) ; sinon le pays comptait deux fois.
- `start.command` relançait l'ouvrier sous un superviseur encore vivant : voir section 1.

## 4. Les fichiers de `var/` que le lecteur tient

Ils ne sont pas dans le dépôt. La nouvelle session ne les voit pas ; elle demande au
lecteur ce qu'ils contiennent quand elle en a besoin (`grep`, `head`, un bloc Python,
`manage.py check` pour savoir lesquels sont présents).

- `budget.xlsx` : le plan, feuille `DATA BASE`, identique au budget du reforecast à l'euro.
- `owners.xlsx` : l'annuaire ; `org.xlsx` : l'organigramme (voir 3.8).
- `placements.csv` : trois placements décidés jusqu'à la fin de l'exercice — Hong Kong et
  Macao sous la Grande Chine, les distributeurs de Hong Kong sous APAC (29 octobre) ; la
  raison écrite date de l'ancienne décision et peut être réécrite.
- `context.csv` : dix notes au 29 octobre, sans doublon. Une note `on_hold` sur le canal
  travel retail, sans marché, depuis septembre (livraisons baissées exprès, l'avance sur le
  plan le permettait) ; une note `on_hold` sur les grands magasins d'un marché d'Océanie,
  client qui ne règle plus ; une note `basis_change` sur le Brésil et une sur son
  e-commerce, depuis mai, action pour la Finance ; trois notes `basis_change` sur la Chine,
  Hong Kong et Macao depuis septembre, le passage des deux sous la Chine chez la Finance ;
  une note `one_off` sur la Chine, un café fermé ; deux notes `reclassified` sur les canaux
  américains, antérieures. Une note `basis_change` sort le marché de « Qui challenger »
  tant qu'elle court : c'est voulu pour la Chine jusqu'à ce que le plan soit recoupé sur
  les trois, et se retire avec `manage.py note --forget`.
- `partners.csv` : les deux codes du partenaire américain reclassé, nommés d'un même nom.
  Une ligne exige une base, un centre de profit, un nom et un chiffre de douze mois ; un
  doublon ou un montant illisible rend le fichier entier inutilisable, d'où les blocs qui
  relisent le fichier avec le cockpit après l'avoir écrit.
- `actuals.xlsx` : le fichier Finance de septembre ; `var/actuals/` garde les mois.
- `reforecast.xlsx` : le classeur du reforecast 2, tel que la Finance le diffuse, copié
  sans modification ; sa feuille `DATABASE REF…` est lue.
- `ref2-rapport.md`, `cortex-taux.md`, `cortex-ref2-format.md`, `cortex-finance-*.md`,
  `cortex-carnet-pays.md`, `cortex-partenaires-codes.md` : les comptes rendus de Cortex ;
  `entrepot.md` : sa mémoire, dont les règles de méthode que le CEO impose.
- `warehouse-*.json` : les caches de lecture, chacun avec l'empreinte de sa requête.
  `warehouse-rows.json` tient la lecture principale, sell-in de la consolidation compris ;
  `warehouse-kpis.json` les KPI suivis ; `warehouse-invoiced.json` les factures au jour.

## 5. Ce que les écrans disent au 29 octobre, sans chiffres

- **Le reforecast de la Finance** : le groupe légèrement sous le plan sur l'exercice, avec
  un sell-in presque plat au second semestre après un premier semestre fort. Les deux
  plus gros écarts au plan sont le Japon, dont l'ambition sell-in du plan n'est pas tenue
  et n'est pas reportée sur le second semestre, et le Brésil, dont une part est la
  déduction fiscale notée. L'Australie suit, avec son grand magasin à l'arrêt. Le second
  semestre sell-in d'EMEA passe en négatif ; celui d'APAC est le plus en retrait du groupe.
  Le travel retail est au-dessus du plan grâce à son premier semestre, puis ralentit
  exprès. La Grande Chine est sous le plan parce que Hong Kong et Macao sont attendus en
  net recul, quand la ligne Chine seule est au plan à quelques dizaines d'euros près — à
  faire expliquer. Le renversement le plus net est la ligne des distributeurs ex-travel
  retail de Hong Kong, attendue en recul marqué sur le reste de l'exercice quand le plan
  attendait une hausse, masqué dans l'année par le premier semestre.
- **Amérique du Nord** (lecture du 12 octobre) : en retard sur le mois, et ce n'est pas du
  stock qui attend. Le carnet par partenaire a montré que le premier e-retailer n'a presque
  rien d'ouvert : il commande moins. Les chaînes et un grand magasin sont en avance ; une
  enseigne a presque tout son retard bloqué à la livraison ; une part du retard n'a pas de
  centre de profit.
- **EMEA, travel retail et APAC** : les lectures de sell-in au jour faites avant le 25
  octobre portaient la colonne fautive du hub (3.10) ; le doute du lecteur sur ces chiffres
  était fondé, et il portait sur les distributeurs du Moyen-Orient et sur le hub, pas sur
  le consolidé ni sur le carnet. À relire après la bascule.
- **États-Unis, dossier** : le sell-in vient du dernier intervalle de la consolidation,
  deux mois, dit à part désormais.

## 6. Questions ouvertes

**Pour la Finance** : quelle écriture uniforme, magasin par magasin, sépare le net caisse
du net publié en Chine réunifiée et au Brésil avant la fiscalité, le vrac étant déjà sur
sa propre ligne, le taux de change étant hors de cause ; la règle de déduction fiscale
brésilienne depuis mai et le retraitement de l'an dernier ; le retraitement de l'an dernier
du partenaire américain reclassé dans la consolidation. Du reforecast : quels canaux
portent le ralentissement du sell-in au second semestre, phasage des commandes ou recul
attendu ; pourquoi la ligne des distributeurs ex-travel retail de Hong Kong s'inverse ; qui
est cette ligne sans pays et pourquoi sans pays ; pourquoi la ligne Chine est attendue
exactement au plan avec un phasage différent ; la définition exacte des comptes de café,
spa et autre chiffre d'affaires retail ; à quelle date septembre a été figé.

**Pour l'équipe data** : le droit de lecture de la vue sémantique pour le rôle du cockpit ;
le défaut de change de la colonne de montant des factures sur le hub de Hong Kong, tranché
côté cockpit par la mesure de la maison, à signaler parce que d'autres lecteurs la lisent ;
les instantanés de consolidation d'avril, juillet et septembre, absents de l'exercice
courant ; les défauts de la vue des commandes (livré en proxy, pas de pays de destination,
lignes sans centre de profit) ; les entités APAC qui facturent hors de la source ; le
volume intragroupe hongrois ; la consolidation qui livre des intervalles.

**Pour le management**, les questions que le cockpit a produites : pourquoi le premier
e-retailer américain commande moins ; ce qu'une enseigne américaine a acheté se vend-il ;
le canal télévision américain éteint ; la reprise des livraisons en travel retail ; les
grands magasins européens contre les e-retailers ; l'engagement japonais sur le digital.

**Pour le lecteur** : corriger l'annuaire (Hong Kong et Macao sous la Grande Chine), puis
retirer les deux placements décidés ; répondre à Cortex qu'il reprend le §4.3 de sa
mémoire avec la nouvelle colonne, en dix lignes, et rien d'autre.

## 7. Pistes suivantes

- `manage.py compare` sur le format du reforecast 2 : le lecteur du millésime sait lire la
  feuille, il reste à lui faire produire le trimestre clos que `compare` attend, en tenant
  le mois figé à part.
- Les alertes « plan à recaler » de `manage.py history` avec, à côté de chacune, ce que la
  Finance attend du reste de l'exercice sur le même périmètre.
- Retraiter les croissances par canal de la consolidation à partir des codes que les notes
  de reclassement nomment : le module `boundary` sait déjà dater une note et suivre un
  partenaire d'un centre à l'autre.
- Porter le code de centre de profit dans les factures au jour (`SELL_IN_DAILY`), pour que
  le tableau « par canal » se lise à périmètre constant ; c'est une requête, donc Cortex.
- Le carnet par pays de destination, si l'équipe data l'ajoute à la vue.
- Le coefficient brésilien sur la note, et le net Finance à côté du net entrepôt pour la
  Chine réunifiée, quand la Finance aura répondu.
- Les lignes du plan dont la source n'a jamais vu l'an dernier, marché par marché : le
  facturé des pays sans an dernier est déjà mis à part de la croissance ; reste à le
  rapprocher des lignes du plan qu'il devrait rencontrer.
- Une façon de nommer un code dans le fichier des partenaires sans inventer un chiffre de
  douze mois.
- Deux définitions identiques de `_pnl_review` se suivent dans `routes/today.py` ; la
  seconde l'emporte. À dédoubler quand on y touche.

## 8. Reprendre

Lire `AGENTS.md`, `docs/PLAN.md`, ce fichier. Demander au lecteur la page qu'il regarde
plutôt que de la deviner. Écrire la règle dans le domaine, son test à côté, lancer la suite,
commettre, pousser la branche et `master`, puis donner le bloc `cd ~/dev/ceo-os && git pull
--ff-only`. Les commandes qui ont le plus servi : `manage.py ensemble "<périmètre>"`,
`manage.py reforecast` (`--structure`, `--markets`), `manage.py placements`,
`manage.py note --list`, `manage.py refresh --supply`, `manage.py frontieres`,
`manage.py partenaires`, `manage.py check`, et un bloc Python qui lit un cache de `var/`
pour voir ce que l'entrepôt a vraiment livré.
