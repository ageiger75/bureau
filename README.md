# CEO OS — Decision Room

Prototype de la **tranche verticale 1** du MVP décrit dans
`Brief_Construction_CEO_OS_Decision_Room.docx`.

L'unité de travail est la décision : une question explicite, des affirmations qualifiées,
des options comparables, une position assumée. Ce n'est ni un tableau de bord, ni une
interface de chat.

Sponsor : Adrien Geiger · application privée, locale, sur données fictives.

---

## Emplacement

Le projet vit dans **`~/dev/ceo-os`**, volontairement **hors de `~/Documents`** : macOS
protège ce dossier, et un processus lancé par un outil extérieur s'y voit refuser l'accès
en lecture — y compris à `.venv/pyvenv.cfg`, ce qui empêche tout démarrage.

Les documents source du brief restent, eux, dans `~/Documents/CEO OS/`.

## Démarrer

```bash
cd ~/dev/ceo-os
./run.sh
```

Le script crée l'environnement virtuel, installe les dépendances, applique le schéma,
insère les données de démonstration et démarre le serveur sur <http://127.0.0.1:8000>.

Pour repartir de zéro : `./run.sh --reset`.

À la main :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed
.venv/bin/python manage.py serve          # ajouter --reload en développement
```

`manage.py` déduit la racine du projet de son propre emplacement : les commandes
fonctionnent depuis n'importe quel répertoire courant, ce qui n'est pas le cas de
`python -m app.cli`. C'est ce que doivent utiliser les outils extérieurs.

Le port suit la variable `PORT` si elle est définie, sinon 8000 :

```bash
PORT=8123 .venv/bin/python manage.py serve
```

L'**adresse** d'écoute, elle, n'est pas configurable : `127.0.0.1` est la constante
`SERVE_HOST` de `app/cli.py`. Un `--host 0.0.0.0` collé par erreur dans une commande ne doit
pas pouvoir exposer des dossiers confidentiels sur le réseau.

Tests :

```bash
.venv/bin/python -m pytest
```

Vérifier le périmètre actif :

```bash
.venv/bin/python manage.py check
```

---

## Ce que fait cette tranche

| Écran | Contenu |
| --- | --- |
| **Accueil** | Liste des dossiers, triés par urgence puis par fragilité. Bloc « demande attention ». |
| **Nouveau dossier** | Titre, question à trancher, contexte, échéance, confidentialité. |
| **Dossier** | Diagnostic, synthèse, cadrage, socle factuel, options, recommandation — sur une page, sections repliables. |

Le dossier couvre : question, contexte, échéance, statut, faits, hypothèses, éléments à
vérifier, options, recommandation. Tout est modifiable et enregistré en SQLite.

### Le point du produit

Le brief impose de séparer les faits des hypothèses (§4) et interdit de présenter une
moyenne ou un score de confiance comme une vérité (§10). Concrètement :

- **Quatre catégories obligatoires** : fait sourcé, hypothèse, opinion, à vérifier.
- **Avertissement, pas refus.** Un fait sans source est enregistré tel quel, puis signalé
  sur le dossier, sur l'accueil et dans le diagnostic. Bloquer la saisie pousserait à
  requalifier le fait douteux pour faire taire le message — ce qui effacerait justement
  l'information qu'on veut garder. *(Décision de périmètre prise avec le sponsor.)*
- **Deux ou trois options.** Moins de deux bloque le passage en « Prêt à décider », plus de
  trois aussi. Le statu quo manquant produit un avertissement.
- **Position nette obligatoire.** La recommandation exige « Voilà ce que je ferais » **et**
  les conditions qui l'invalideraient. Ces deux champs sont refusés s'ils sont vides —
  contrairement à un fait sans source, il n'y a ici aucune information à conserver.
- **Aucun score.** Le diagnostic liste des bloquants et des avertissements nommés, jamais
  une note agrégée. La couverture des sources n'est affichée que s'il existe au moins un
  fait : « 100 % » sur un ensemble vide serait de la fausse précision.
- **Désaccords affichés.** La recommandation a un champ dédié aux désaccords non résolus.

### États d'un dossier

`Brouillon → En analyse → Prêt à décider`, avec retour en arrière autorisé.

Le passage en « Prêt à décider » est le seul contrôlé par la maturité du dossier : c'est le
moment où l'outil affirme qu'une décision est possible.

Les états `Décidé`, `En exécution`, `À revoir` et `Clos` existent dans le vocabulaire mais
sont refusés avec une explication : ils supposent l'enregistrement d'une décision, des
engagements et une revue, qui arrivent en tranche 2.

---

## Ce que cette tranche ne fait pas

Volontairement absent, et **annoncé dans l'interface** plutôt que masqué — un écran vide
laisse croire à une donnée manquante alors qu'il s'agit d'une fonctionnalité non construite.

- Import PDF / PowerPoint / Word / Excel et lien vers le passage cité
- Agents IA (Source Analyst, Devil's Advocate, Functional Voices…)
- Authentification Entra ID, RBAC, journal d'audit
- Microsoft Graph, e-mails, toute intégration externe
- Écrans Challenge, Décision, Suivi, Revue
- Export Word / PDF

Le champ `source_ref` d'une affirmation est donc du texte libre
(« Board pack juillet 2026, p. 12 »). En tranche 3 il deviendra une clé étrangère vers un
passage indexé, ce qui rendra la citation cliquable jusqu'au document.

---

## Architecture

```
manage.py         point d'entrée indépendant du répertoire courant
app/
  main.py         FastAPI : middlewares, montage statique, page d'erreur
  config.py       configuration + garde-fous refusés au démarrage
  db.py           SQLAlchemy 2.0 : moteur, session, dépendance FastAPI
  models.py       User, DecisionCase, Claim, Option, Recommendation
  forms.py        lecture et validation de tous les formulaires
  services.py     pont entre les objets persistés et le domaine
  web.py          gabarits Jinja2, messages éphémères, filtres
  util.py         identifiants, horloge, nettoyage des saisies
  cli.py          migrate / seed / check / serve
  domain/         règles métier pures — ni HTTP, ni SQL, testables seules
    enums.py      vocabulaire et libellés français
    claims.py     qualification des affirmations et avertissements
    cases.py      maturité du dossier et transitions d'état
  routes/         home, cases, claims, options, recommendation
  templates/      Jinja2
  static/         ceo-os.css, ceo-os.js
seed/demo.py      3 dossiers fictifs
tests/            70 tests
var/              base SQLite et journaux (git-ignoré)
```

Le domaine ne connaît ni FastAPI ni SQLAlchemy. C'est ce qui permet de tester les règles
qui comptent — « un fait sans source est signalé », « moins de deux options n'est pas un
arbitrage » — sans monter une base ni un serveur.

### Choix techniques

| Couche | Choix | Raison |
| --- | --- | --- |
| Interface | Jinja2 côté serveur, CSS local, JS vanilla | Aucun Node, npm, bundler ni Docker sur le poste. Une page reste lisible et modifiable sans JavaScript. |
| API | FastAPI, un seul service | Brief §12 : « limiter la complexité opérationnelle ». |
| Base | SQLAlchemy 2.0 + SQLite | Portable PostgreSQL, voir ci-dessous. |
| Python | 3.9 strict | Version disponible sur le poste : ni `X \| None`, ni `match`/`case`. |

### Vers PostgreSQL

La bascule doit se limiter à `CEOOS_DATABASE_URL`. Pour que ce soit vrai, le code
s'interdit :

- les types propres à un moteur — uniquement `String`, `Text`, `Integer`, `Boolean` ;
- les identifiants auto-incrémentés — UUID hexadécimal en `String(32)`, ce qui évite aussi
  les URL énumérables ;
- les valeurs par défaut calculées côté serveur — tout est explicite en Python ;
- les fonctions SQL propres à un moteur — pas de `datetime('now')` ni `strftime` ;
- les `PRAGMA` ailleurs que dans `db.py`, derrière un test de dialecte.

Deux points restent à traiter le jour de la bascule :

1. **Alembic.** Le prototype utilise `create_all`, suffisant tant qu'aucune vraie décision
   n'est en base. Dès qu'il faut faire évoluer un schéma peuplé, Alembic devient nécessaire.
2. **`pgvector`.** Prévu par le brief §12 pour la recherche sémantique, inutile ici : il n'y
   a pas encore de passages indexés à retrouver.

---

## Sécurité

Traitée comme une fonctionnalité, pas comme une phase finale (brief §20).

| Contrôle | Mise en œuvre |
| --- | --- |
| Écoute locale | Trois verrous : l'hôte est une constante de `app/cli.py` et non un argument, `run.sh` ne passe aucun `--host`, et un middleware refuse toute requête dont le client n'est pas sur la boucle locale. |
| CSP | `default-src 'self'` : aucune ressource externe, ni police, ni CDN. Interdit aussi tout style ou script en ligne — d'où l'absence d'attributs `style=` et de `onclick` dans le code. |
| Cache | `Cache-Control: no-store` sur toutes les pages. |
| Échappement | Jinja2 en mode auto-échappement. Les filtres `paragraphs` et `bullets` échappent avant de construire le HTML : accepter du balisage dans un champ alimenté par des documents externes ouvrirait une porte d'injection. |
| Nettoyage | Les caractères de contrôle sont retirés des saisies — ils servent à dissimuler du contenu dans un texte d'apparence anodine. |
| Énumérations | Une valeur hors liste est refusée avec une erreur visible, jamais corrigée en silence. |
| Cloisonnement | Une affirmation ou une option n'est atteignable que par le dossier qui la porte : un identifiant seul ne suffit pas. |
| EXECUTE | `CEOOS_AUTONOMY_LEVEL=EXECUTE` est refusé **par le code**, pas seulement par la configuration. Le produit ne peut ni envoyer, ni modifier, ni engager quoi que ce soit à l'extérieur. |
| Appels sortants | Aucun. Pas de client HTTP instancié. |

**Il n'y a pas d'authentification dans cette tranche.** L'identité courante est le premier
utilisateur CEO trouvé en base. Un bandeau permanent le rappelle en haut de chaque page,
pour qu'aucune donnée réelle ne soit déposée dans un prototype qui ne les protège pas.

### Git

`.gitignore` exclut `.env`, `var/` (base et journaux) et `.venv/`.

La racine du dépôt est `~/dev/ceo-os`. Les documents Word confidentiels du brief sont
restés dans `~/Documents/CEO OS/` et n'ont donc aucun risque d'entrer dans un historique
Git.

Aucun dépôt n'est initialisé à ce jour : `git init` depuis `~/dev/ceo-os` si besoin.

---

## Données de démonstration

Trois dossiers fictifs, **volontairement imparfaits** : ils servent à vérifier que l'outil
signale les défauts, pas à présenter une belle page.

| Référence | État | Défaut installé exprès |
| --- | --- | --- |
| `DR-2026-001` Flagship Milan | En analyse | Un fait affirmé sans source ; deux comptages de trafic qui se contredisent (42 000 vs 28 000) sans qu'aucun soit retenu ; une hypothèse déterminante sans test ; aucune recommandation. |
| `DR-2026-002` Calendrier promotionnel | Prêt à décider | Dossier abouti, avec un désaccord non résolu affiché tel quel. |
| `DR-2026-003` Reformulation | Brouillon | Échéance déjà dépassée, une seule hypothèse, aucune option. |

Aucun nom, chiffre ou document réel de L'OCCITANE n'y figure.

---

## Suite proposée

| Tranche | Contenu | Pourquoi dans cet ordre |
| --- | --- | --- |
| 2 | Challenge, décision, engagements, revue | Ferme la boucle décisionnelle avec les écrans déjà cadrés. |
| 3 | Import de documents et passages cités | Rend la traçabilité réelle : `source_ref` devient un lien. |
| 4 | Agents IA, prompts versionnés, jeu d'évaluation | Ne vaut la peine qu'une fois les passages indexés disponibles. |
| 5 | Entra ID, RBAC, audit | Nécessaire avant tout usage multi-utilisateurs. |
| 6 | Microsoft Graph en lecture seule | Dernier, conformément au brief §20. |

Le brief conclut : tester d'abord sur trois décisions historiques, et ne pas poursuivre les
intégrations si le produit n'améliore pas nettement la qualité du cadrage et du challenge.
Cette tranche existe pour rendre ce test possible.
