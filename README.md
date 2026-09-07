# CEO OS

Application privée, locale, sur données fictives. Sponsor : Adrien Geiger.

Un seul produit : le **CEO Performance Cockpit**, sur `/`. L'écran du lundi en cinq blocs —
le verdict, la semaine, trois conversations, les zones rouges, ce qui a changé — et une page
« Analyses » pour tout ce qui explique, classe, propose ou vérifie. Le prototype précédent,
Decision Room, a été retiré le 7 septembre 2026 ; son histoire est dans `PIVOT.md` et le
registre des sujets, seule pièce conservée, dans `app/domain/issues.py`.

**L'état du produit, ce qui manque et l'ordre des travaux sont dans `docs/PLAN.md`.**
C'est le document à lire en premier pour reprendre le travail : il porte aussi les règles
de mesure apprises sur de vraies données, qu'aucune relecture du code ne redonnerait.

**La langue de l'interface est le français.** La doctrine V6.1 demandait un écran en
anglais ; le lecteur a tranché pour le français, qui est déjà celle du terminal, des notes
de contexte et du registre. L'écran web est encore en anglais et doit être repris.

---

## Emplacement

Le projet vit dans **`~/dev/ceo-os`**, volontairement **hors de `~/Documents`** : macOS
protège ce dossier, et un processus lancé par un outil extérieur s'y voit refuser l'accès
en lecture — y compris à `.venv/pyvenv.cfg`, ce qui empêche tout démarrage.

Les documents source du brief restent, eux, dans `~/Documents/CEO OS/`.

## Démarrer

### Usage courant : double-cliquer

Le développement se fait sur GitHub ; ce poste ne fait que lire et exécuter. Une fois
l'installation faite (ci-dessous), l'usage courant tient en un geste : **double-cliquer sur
`start.command`** depuis le Finder, ou le glisser une fois dans le Dock.

Il récupère la dernière version depuis GitHub, démarre le serveur et ouvre le navigateur.
La mise à jour est en **avance rapide seulement** : le script ne fusionne rien et n'écrase
aucune modification locale. Si GitHub est injoignable ou si le dossier a divergé, il le dit
et démarre avec la version déjà présente.

Pour arrêter : `Ctrl-C` dans la fenêtre Terminal ouverte.

**Cette fenêtre devient le serveur** et n'accepte plus de commandes. Pour lancer autre
chose — tests, `manage.py check`, `manage.py warehouse` — ouvrir une **seconde** fenêtre
(`⌘T`) et s'y placer dans le dossier du projet. Du texte tapé dans la fenêtre du serveur
n'exécute rien : il est avalé par un processus qui n'attend pas de commandes.

### Installation, une seule fois

```bash
cd ~/dev
git clone https://github.com/ageiger75/bureau.git ceo-os
cd ceo-os
./start.command
```

Le clone est ce qui rend `start.command` capable de se mettre à jour, et c'est aussi ce qui
préserve les permissions des fichiers — un téléchargement en ZIP les perd, et `run.sh`
répond alors `permission denied`.

### En ligne de commande

```bash
cd ~/dev/ceo-os
./run.sh
```

Le script crée l'environnement virtuel, installe les dépendances, applique le schéma,
insère les données de démonstration et démarre le serveur sur <http://127.0.0.1:8000>.

Pour repartir de zéro : `./run.sh --reset`.

Si le shell répond `permission denied`, le bit d'exécution a été perdu en route — c'est ce
que fait un téléchargement en ZIP depuis GitHub, là où un `git clone` le conserve. Deux
sorties : `bash run.sh` immédiatement, ou `chmod +x run.sh manage.py` une fois pour toutes.

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

Vérifier le périmètre actif — quelle source de données, quelles requêtes restent à écrire :

```bash
.venv/bin/python manage.py check
```

Tester la connexion à l'entrepôt sans lire aucune donnée métier :

```bash
.venv/bin/python manage.py warehouse
```

---

## Ce que le produit ne fait pas

Volontairement absent, et **annoncé dans l'interface** plutôt que masqué — un écran vide
laisse croire à une donnée manquante alors qu'il s'agit d'une fonctionnalité non construite.

- Import PDF / PowerPoint / Word / Excel et lien vers le passage cité
- Agents IA (Source Analyst, Devil's Advocate, Functional Voices…)
- Authentification Entra ID, RBAC, journal d'audit
- Microsoft Graph, e-mails, toute intégration externe
- Recherche transverse et export Word / PDF

Le champ `source_ref` d'une affirmation est donc du texte libre
(« Board pack juillet 2026, p. 12 »). En tranche 3 il deviendra une clé étrangère vers un
passage indexé, ce qui rendra la citation cliquable jusqu'au document.

De même, les voix du challenge (Avocat du diable, Finance, Client, Marque, Long terme) sont
**tenues par des humains** : l'outil signale celles qui n'ont pas été entendues, il ne les
simule pas.

---

## Architecture

```
manage.py         point d'entrée indépendant du répertoire courant
app/
  main.py         FastAPI : middlewares, montage statique, page d'erreur
  config.py       configuration + garde-fous refusés au démarrage
  db.py           SQLAlchemy 2.0 : moteur, session, dépendance FastAPI
  models.py       User, DecisionCase, Claim, Option, Recommendation,
                  Challenge, DecisionRecord, Commitment, Review
  forms.py        lecture et validation de tous les formulaires
  services.py     pont entre les objets persistés et le domaine
  web.py          gabarits Jinja2, messages éphémères, filtres
  util.py         identifiants, horloge, nettoyage des saisies
  cli.py          migrate / seed / check / serve
  domain/         règles métier pures — ni HTTP, ni SQL, testables seules
    enums.py      vocabulaire et libellés français
    warnings.py   bloquants et avertissements : code, message, correctif
    claims.py     qualification des affirmations
    cases.py      cycle de vie, transitions, maturité, urgence
    challenge.py  objections, voix attendues, prémisse testée
    commitments.py niveaux d'alerte et synthèse d'exécution
    reviews.py    contrôles de revue et conditions de clôture
  routes/         common, home, cases, claims, options, recommendation,
                  challenge, decision, commitments, reviews
  templates/      Jinja2, sections du dossier dans partials/
  static/         ceo-os.css, ceo-os.js
seed/demo.py      4 dossiers fictifs
tests/            300 tests
var/              base SQLite et journaux (git-ignoré)
```

Le domaine ne connaît ni FastAPI ni SQLAlchemy. C'est ce qui permet de tester les règles
qui comptent — « un fait sans source est signalé », « moins de deux options n'est pas un
arbitrage », « un dossier jamais contesté n'est pas prêt » — sans monter une base ni un
serveur.

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
| Cloisonnement | Une affirmation, une option, une objection, un engagement ou une revue n'est atteignable que par le dossier qui la porte : un identifiant seul ne suffit pas. |
| EXECUTE | `CEOOS_AUTONOMY_LEVEL=EXECUTE` est refusé **par le code**, pas seulement par la configuration. Le produit ne peut ni envoyer, ni modifier, ni engager quoi que ce soit à l'extérieur. |
| Appels sortants | Aucun. Pas de client HTTP instancié — et un test parcourt `app/` pour le vérifier à chaque exécution. |

**Il n'y a pas d'authentification dans cette tranche.** L'identité courante est le premier
utilisateur CEO trouvé en base. Un bandeau permanent le rappelle en haut de chaque page,
pour qu'aucune donnée réelle ne soit déposée dans un prototype qui ne les protège pas.

### Git

`.gitignore` exclut `.env`, `var/` (base et journaux) et `.venv/`.

Les documents Word confidentiels du brief restent hors du dépôt et n'ont donc aucun risque
d'entrer dans un historique Git.

`.env.example` documente chaque variable, et `.claude/setup.sh` prépare une session de
travail — environnement, dépendances, schéma, données fictives — pour qu'un dépôt fraîchement
cloné démarre sans intervention.

---
