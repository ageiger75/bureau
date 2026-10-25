# Passation — session de septembre et octobre 2026

À lire par la session qui reprend le travail, après `AGENTS.md` et `docs/PLAN.md`. Ce
fichier dit qui travaille, comment, ce qui a été fait pendant cette session, ce qui est
ouvert, et les pièges rencontrés. Il ne contient aucun chiffre réel, aucun nom de
partenaire ni de personne, aucun code de centre de profit : la règle du dépôt vaut pour
lui aussi, et `tests/test_no_real_figures.py` la garde. Les chiffres vivent dans la
conversation et dans `var/`, jamais ici.

## 1. Qui travaille, et où

**Le lecteur** est le CEO. Il ne code pas. Il travaille depuis quatre endroits :

- **GitHub**, ce dépôt. La branche de travail est `claude/github-repo-setup-continue-f467r7` ;
  `master` est synchronisée à chaque poussée (`git push origin HEAD:master`). Le lecteur ne
  fait que `git pull --ff-only`.
- **Son Mac**, dossier `~/dev/ceo-os`. Fenêtre A : `start.command`, l'application sous
  uvicorn avec rechargement automatique du code. Fenêtre B : les commandes. Une nouvelle
  fenêtre Terminal s'ouvre dans le dossier personnel, pas dans le projet : chaque bloc de
  commandes commence par `cd ~/dev/ceo-os &&`. L'afficheur de `git diff` a été remplacé par
  `cat` (`git config --local core.pager cat`) parce qu'il bloquait la fenêtre. Le dépôt local
  a `pull.rebase` : un fichier modifié localement fait refuser la mise à jour.
- **Le navigateur**, dont il colle le texte des pages dans la conversation. C'est ainsi
  qu'on voit ce que l'écran dit vraiment ; ne jamais supposer, demander la page.
- **Cortex Code**, l'agent de l'entrepôt Snowflake. Il lit l'entrepôt, valide les requêtes
  avant qu'elles entrent dans le cockpit, et n'écrit que dans `var/` (ses comptes rendus
  `var/cortex-*.md`, sa mémoire `var/entrepot.md`). Il a modifié du code une fois, par
  exception, lors du rapprochement Finance ; ses modifications ont été reprises à la main
  dans le dépôt avec leurs tests, et ses copies locales effacées (`git checkout -- app tests`).

Le cockpit ne lit que le poste du lecteur : la session de développement n'a ni l'entrepôt,
ni l'annuaire, ni les fichiers de `var/`. Le jeu de démonstration n'a pas d'unités sell-in
et pas d'annuaire : les cartes de périmètre se testent à l'unité, pas par le web.

## 2. Conventions de la conversation

- **Un bloc encadré est une commande pour la Fenêtre B**, numéroté BLOC 1, 2, 3. Le
  lecteur les colle tels quels. Rien d'autre n'est encadré.
- **Un brief Cortex n'est jamais encadré**, il est « à transmettre tel quel » : une seule
  tâche bornée, une nouvelle session Cortex par brief, réponse en dix lignes dans un fichier
  `var/cortex-<sujet>.md`, ordre explicite de s'arrêter, ne pas modifier le code. Toujours
  refuser ses offres d'automatisation (launchd, agent mensuel). Ne jamais lui demander ce
  que le cockpit sait calculer. Le SQL s'écrit ici ; Cortex le valide avant qu'il soit poussé.
- **Les chiffres réels** sont permis dans la conversation et dans `var/`, nulle part ailleurs.
- **Jamais recommander `manage.py refresh` avant d'ouvrir une page** : les lectures partent
  en arrière-plan à l'ouverture et la page se recharge seule ; `refresh` ne fait qu'oublier
  un cache. Quand une relecture à la main s'impose, dire d'attendre quelques minutes.
- **Un commit ne part que si `pytest -q` rend zéro** (vérifier `${PIPESTATUS[0]}`, pas la
  sortie). Les commits portent les deux lignes de fin convenues et aucun identifiant de
  modèle. Le bac à sable refuse `git commit --amend` et toute poussée forcée.
- **Vérité avant confort**, même sur les lectures de la session précédente : quand une
  vérification Cortex a contredit une hypothèse énoncée en conversation, la correction a été
  dite au lecteur en premier.

## 3. Ce qui a été fait, par thème

Chaque thème a sa note dans `docs/PLAN.md`, section « sell-in » et suivantes ; le code est
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

Deux règles de plus le 25 octobre. Un pays qui facture ce mois-ci sans une seule facture
l'an dernier dans la source reste dans le facturé à date, sort de la croissance et est
nommé avec son montant (`invoiced.Line.unseen`, `unseen_note`) : au groupe, par périmètre,
par canal, dans `manage.py ensemble`. Et quand le classeur de la consolidation ferme deux
mois à la fois, le dossier de visite dit que le sell-in est lu sur cet intervalle, à part,
et somme le plan sur ses mois (`budget.months_of`, `visit.period_phrase`).

### 3.3 Le carnet de commandes ouvert

Au niveau du groupe par canal, en trois paquets sur la date de promesse au client. Par
périmètre et par partenaire sur la page de chaque périmètre, sur le pays du client facturé
tel que la dimension le nomme (il n'y a pas d'ISO2 ; la requête `ORDER_BOOK` porte
`country`, `code`, `label`, validés par Cortex, totaux inchangés à l'euro) et ramené au nom
de marché. Une note `on_hold` du fichier de contexte marque un canal « tenu exprès » : sans
marché, elle tient le canal partout et son retard est retiré du jugement ; avec un marché,
elle ne marque que le périmètre qui le porte, sans rien retirer. Le carnet a sa propre
section sur les trois pages, parce que le premier du mois aucune facture du mois n'est lue
et il disparaissait avec. Le fil de relecture à l'âge nommait la lecture retirée et jamais
le carnet : corrigé (`perf/reread.py`).

### 3.4 Le biais de prévision

Un marché de prévision au réel presque nul rendait un biais de plusieurs milliers de pour
cent et une précision négative sur le groupe. Au-delà de `supplychain.BIAS_UNREADABLE`, la
ligne est hors lecture, nommée à part, le groupe se lit sur les autres, la précision ne
descend jamais sous zéro.

### 3.5 Le rapprochement Finance de septembre

Cortex a confronté les fichiers Finance de septembre aux lectures du cockpit. La
consolidation, le sell-in par canal, le sell-out et le parc tombent juste à de petits
écarts près. Deux défauts corrigés : le chiffre publié n'est posé à côté d'une ligne que
si le fichier parle du mois de la ligne (`mapping.units_from_rows`), et le Luxembourg se
range sous l'entité belge (`budget.MARKET_ALIASES`). Trois vérifications supplémentaires
(`var/cortex-finance-*.md`) ont établi : en Chine et à Hong Kong l'écart est une règle
uniforme magasin par magasin, de l'ordre de cinq points, ni le parc ni le vrac, présente
aussi au Brésil les deux années, la piste la plus forte étant le taux de change constant,
qui n'explique pas le saut de Hong Kong en septembre ; au Brésil, la Finance déduit depuis
mai la nouvelle structure fiscale sans retraiter l'an dernier, et sa croissance mélange
deux bases ; aux États-Unis, un seul client a changé de canal en mai, sans retraitement de
l'an dernier dans la consolidation, ce qui gonfle la croissance affichée des chaînes et
déforme celle des e-retailers.

### 3.6 Les partenaires à périmètre constant

Les codes de centre de profit que `var/partners.csv` nomme d'un même nom se lisent en une
ligne, sur le canal du code qui facture en dernier, l'an dernier gardé
(`accounts._merge_named`). Une succession que personne n'a nommée est dite sur Analyses,
jamais fusionnée d'office (`Review.succession_note`). Le lecteur a nommé les deux codes du
partenaire américain reclassé ; Cortex a confirmé que c'est la seule succession de cette
nature, tous pays confondus.

### 3.7 Le dossier de visite

Le dossier porte les produits du marché, les statuts de fermeture du fichier de la CFO
(`CEOOS_STORE_CLOSED_STATUSES` dans `.env`), le côté sell-in avec le ciseau, le drapeau
non validé. La consolidation livre des intervalles quand un instantané manque (deux mois
écrits `AAAA-MM..AAAA-MM`) : le plan les rencontre maintenant en additionnant ses propres
mois (`budget.Budget.line`, `months_of`), et un sell-in d'une autre période que le sell-out
se lit à part, sans part du mois ni question du ciseau (`visit.Dossier.sell_in_apart`).

### 3.8 L'annuaire et les pays

L'annuaire a une feuille de recherche par pays, préférée, que Cortex a complétée pour les
pays d'export et le travel retail. Les factures sont nommées par la norme ISO quand le
sell-out ne nomme pas le pays (`perf/countries.py`). Les placements décidés par le lecteur :
les distributeurs d'Amérique du Sud et d'Afrique du Sud sous la BU EMEA, le travel retail
sous sa propre BU, les pays d'export sous EMEA.

### 3.9 Le 25 octobre, en plus

- Une session Claude Code locale sur le poste a ajouté `manage.py cabinet` (la lecture du
  jour en un fichier pour les agents de `~/cabinet`, contrat dans `docs/CABINET.md`) sur sa
  propre branche ; fusionnée ici sans réécriture, pour que le poste avance en avance rapide.
  Règle : une session locale pousse sur notre branche, ou le dit pour que l'on fusionne.
- Les lectures expirées du cache sont servies et relues derrière l'écran, le carnet compris
  (`source._query_rows`, `reread.reread_all`) : il était resté onze à vingt-trois jours sans
  relecture.
- Un pays et son entité voisine lus sous deux noms par l'entrepôt sont un seul marché
  (`month.build` fusionne par nom normalisé).
- Le bloc partenaires de `manage.py ensemble` dit quand sa lecture date d'avant le mois, au
  lieu d'afficher une chute entière.
- `start.command` arrête le superviseur puis l'ouvrier d'uvicorn, attend le port, et n'ouvre
  le navigateur qu'après : relancer avec une fenêtre déjà ouverte ne bloque plus.
- Les pages APAC et EMEA tombaient en erreur interne : le plan sell-in du mois écrasait le
  plan EBITDA dans `page.build`. Corrigé, deux tests.

## 4. Les fichiers de `var/` que le lecteur tient

Ils ne sont pas dans le dépôt. La nouvelle session ne les voit pas ; elle demande au
lecteur ce qu'ils contiennent quand elle en a besoin (`grep`, `head`, un bloc Python).

- `context.csv` : une note `on_hold` sur le canal travel retail, sans marché, depuis
  septembre (livraisons baissées exprès, l'avance sur le plan le permettait) ; une note
  `on_hold` sur les grands magasins d'un marché d'Océanie, client qui ne règle plus ; une
  note `basis_change` sur le retail brésilien, à compléter de la règle fiscale quand la
  Finance la donnera ; deux notes `reclassified` sur les canaux américains, antérieures.
- `partners.csv` : les deux codes du partenaire américain reclassé, nommés d'un même nom.
  Une ligne exige une base, un centre de profit, un nom et un chiffre de douze mois ; un
  doublon ou un montant illisible rend le fichier entier inutilisable, d'où les blocs qui
  relisent le fichier avec le cockpit après l'avoir écrit.
- `actuals.xlsx` : le fichier Finance de septembre ; `var/actuals/` garde les mois.
- `cortex-*.md` : les comptes rendus des étapes sept à onze ; `entrepot.md` : la mémoire de
  Cortex, dont le rapprochement Finance.
- `warehouse-*.json` : les caches de lecture. `warehouse-rows.json` tient la lecture
  principale, sell-in de la consolidation compris ; `warehouse-kpis.json` les KPI suivis.

## 5. Ce que les écrans disent au 12 octobre, sans chiffres

- **Amérique du Nord** : en retard sur le mois, et ce n'est pas du stock qui attend. Le
  carnet par partenaire a montré que le premier e-retailer n'a presque rien d'ouvert : il
  commande moins. Les chaînes et un grand magasin sont en avance ; une enseigne a presque
  tout son retard bloqué à la livraison ; une part du retard n'a pas de centre de profit.
- **EMEA** : sell-out en retard, sell-in en avance, et la carte dit les deux. Le sell-in
  est porté par les e-retailers et une enseigne nouvelle au Royaume-Uni pendant que les
  grands magasins reculent avec le sell-out : un déplacement de canal, pas un plan faux. Le
  plan EMEA est prudent sur les distributeurs et juste sur les filiales.
- **Travel retail** : le retard du carnet est tenu exprès, et les factures d'octobre
  montrent une reprise.
- **APAC** : ses filiales facturent hors de la source ; la carte le dit et ne juge pas.
- **États-Unis, dossier** : le sell-in vient du dernier intervalle de la consolidation,
  deux mois, dit à part désormais.

## 6. Questions ouvertes

**Pour la Finance**, un message a été préparé en conversation : quel taux constant pour
le yuan, le dollar de Hong Kong, la pataca et le réal ; quelle déduction uniforme, magasin
par magasin, sépare le net caisse du net publié en Chine et à Hong Kong, le vrac étant déjà
sur sa propre ligne ; pourquoi Hong Kong saute en septembre ; la règle de déduction fiscale
brésilienne depuis mai et le retraitement de l'an dernier ; le retraitement de l'an dernier
du partenaire américain reclassé dans la consolidation.

**Pour l'équipe data** : le droit de lecture de la vue sémantique pour le rôle du cockpit ;
l'arbitrage de la colonne de montant du sell-in (taux annuel contre valeur nette facturée) ;
les défauts de la vue des commandes (livré en proxy, pas de pays de destination, lignes
sans centre de profit) ; les entités APAC qui facturent hors de la source ; le volume
intragroupe hongrois ; la consolidation qui livre des intervalles et n'a pas septembre.

**Pour le management**, les questions que le cockpit a produites : pourquoi le premier
e-retailer américain commande moins ; ce qu'une enseigne américaine a acheté se vend-il ;
le canal télévision américain éteint ; la reprise des livraisons en travel retail ; les
grands magasins européens contre les e-retailers ; l'engagement japonais sur le digital.

## 7. Pistes suivantes

- Retraiter les croissances par canal de la consolidation à partir des codes que les notes
  de reclassement nomment : le module `boundary` sait déjà dater une note et suivre un
  partenaire d'un centre à l'autre.
- Porter le code de centre de profit dans les factures au jour (`SELL_IN_DAILY`), pour que
  le tableau « par canal » se lise à périmètre constant ; c'est une requête, donc Cortex.
- Le carnet par pays de destination, si l'équipe data l'ajoute à la vue.
- Le coefficient brésilien sur la note, et le net Finance à côté du net entrepôt pour la
  Chine et Hong Kong, quand la Finance aura répondu.
- Les lignes du plan dont la source n'a jamais vu l'an dernier, marché par marché : le
  facturé des pays sans an dernier est déjà mis à part de la croissance ; reste à le
  rapprocher des lignes du plan qu'il devrait rencontrer.
- Une façon de nommer un code dans le fichier des partenaires sans inventer un chiffre de
  douze mois.

## 8. Reprendre

Lire `AGENTS.md`, `docs/PLAN.md`, ce fichier. Demander au lecteur la page qu'il regarde
plutôt que de la deviner. Écrire la règle dans le domaine, son test à côté, lancer la suite,
commettre, pousser la branche et `master`, puis donner le bloc `cd ~/dev/ceo-os && git pull
--ff-only`. Les commandes qui ont le plus servi : `manage.py ensemble "<périmètre>"`,
`manage.py refresh --supply`, `manage.py frontieres`, `manage.py partenaires`, et un bloc
Python qui lit un cache de `var/` pour voir ce que l'entrepôt a vraiment livré.
