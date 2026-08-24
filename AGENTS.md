# Contribuer à CEO OS

À lire avant de modifier ce dépôt. Complète le `README.md`, qui décrit le produit.

## Contraintes du socle

Non négociables, elles viennent du poste et du brief :

- **Python 3.9 strict.** Pas de `X | None` (utiliser `Optional[X]`), pas de `match`/`case`,
  pas de `dict | dict`. Le poste n'a que CPython 3.9.6.
- **Aucun Node, npm, bundler, React ni Docker.** Gabarits Jinja2 côté serveur, CSS local,
  JavaScript vanilla.
- **Aucune ressource externe.** La CSP est `default-src 'self'` : pas de CDN, pas de police
  distante, pas de `<style>` ni de `onclick` en ligne. Classes CSS et `addEventListener`.
- **Aucun appel réseau sortant.** Ni Microsoft 365, ni fournisseur d'IA, ni service tiers.
- **Écoute sur 127.0.0.1 uniquement.** L'hôte est la constante `SERVE_HOST` de
  `app/cli.py`, jamais un argument de ligne de commande. Le port, lui, suit la variable
  `PORT` pour que l'environnement puisse en assigner un libre.
- **`EXECUTE` reste impossible.** Le produit ne doit pouvoir ni envoyer, ni modifier, ni
  accepter, ni engager quoi que ce soit à l'extérieur. Ce n'est pas un réglage : c'est refusé
  par `app/config.py`.

Avant d'ajouter une dépendance : elle sera lue par un moteur de gabarit sur du contenu
provenant de documents externes. Chaque paquet est une surface d'attaque. L'extraction
DOCX/PPTX/XLSX, quand elle arrivera, se fera avec `zipfile` + XML de la bibliothèque
standard plutôt qu'avec trois paquets tiers.

## Où va le code

| Besoin | Fichier |
| --- | --- |
| Une règle métier | `app/domain/` — ni import FastAPI, ni import SQLAlchemy |
| Un libellé français | `app/domain/enums.py`, jamais en dur dans un gabarit |
| Lire un formulaire | `app/forms.py` |
| Une requête ou un calcul sur les objets persistés | `app/services.py` |
| Une route | `app/routes/` — lit, appelle le domaine, écrit, redirige |
| Une commande d'administration | `app/cli.py`, atteinte via `manage.py` |
| Un composant d'affichage | `app/templates/macros.html` |

Une route qui contient un `if` métier est au mauvais endroit : deux écrans finiraient par
juger différemment le même dossier.

## Principes produit à ne pas contourner

Ils viennent du brief §4 et §10, et ce sont eux qui font le produit :

1. **Vérité avant confort.** Si un raisonnement est fragile, l'outil le dit et explique
   pourquoi. Ne jamais adoucir un message de diagnostic pour rendre un écran plus agréable.
2. **Faits séparés des hypothèses.** Les quatre catégories sont obligatoires. Ne jamais
   requalifier automatiquement une affirmation : l'utilisateur est averti, il tranche.
3. **Aucun score, aucune moyenne.** Pas de note de confiance, pas d'agrégat. Afficher les
   éléments qui soutiennent l'analyse, les désaccords, et ce qui reste à vérifier.
   Une statistique calculée sur un ensemble vide ne s'affiche pas.
4. **Deux ou trois options.** Pas de fausse alternative pour remplir un tableau.
5. **Une position nette.** Toute recommandation dit ce qu'elle ferait et ce qui la
   ferait changer d'avis.
6. **Les désaccords ne se lissent pas.**
7. **Humain responsable.** L'outil prépare, alerte et structure. Le CEO décide.

### Refus ou avertissement ?

La distinction est délibérée, et un nouveau champ doit se ranger dans l'une des deux cases.

- **Avertissement** quand l'information incomplète a de la valeur. Un fait sans source est
  enregistré : savoir que quelqu'un a présenté cela comme établi est en soi utile. Bloquer
  pousserait à le requalifier en hypothèse pour faire taire le message.
- **Refus** quand il n'y a rien à conserver. Une recommandation sans position n'est pas une
  recommandation fragile, c'est une absence de recommandation.

Le point de bascule de la première règle est isolé dans
`app/domain/claims.py::resolve_category` : si la politique devait durcir, c'est le seul
endroit à changer.

## Tests

```bash
.venv/bin/python -m pytest
```

Les commandes s'invoquent par `manage.py`, jamais par `python -m app.cli` : ce dernier
suppose que le répertoire courant est la racine du projet, ce qui est faux dès qu'un outil
extérieur démarre le processus. `tests/test_manage_entrypoint.py` garde cette propriété.

- Les tests du domaine ne montent ni base ni serveur.
- Les tests de parcours passent par le **vrai formulaire HTML** et vérifient que la donnée
  survit à un nouveau chargement de page. Écrire via l'ORM ne prouverait rien du parcours.
- Deux pièges déjà rencontrés, documentés dans `tests/conftest.py` :
  - Jinja2 échappe les apostrophes en `&#39;`. Utiliser `page_text(response)` pour les
    assertions sur du texte français ; lire `response.text` brut uniquement dans le test
    d'échappement.
  - `TestClient` suit les redirections par défaut, ce qui **consomme** les messages
    éphémères. Une assertion sur un message doit porter sur la réponse du POST.
- `pytest.ini` transforme les `DeprecationWarning` du paquet `app` en erreurs. C'est
  volontaire : c'est ainsi que `on_event` a été remplacé par un gestionnaire `lifespan`.

Toute nouvelle règle du domaine arrive avec son test. Toute nouvelle route arrive avec un
test de parcours et un test de cloisonnement entre dossiers.

## Conventions de base de données

Le schéma doit rester applicable sur PostgreSQL sans réécriture. Voir « Vers PostgreSQL »
dans le `README.md` : types génériques, UUID en `String(32)`, dates ISO en `String`, aucune
valeur par défaut côté serveur, aucun `PRAGMA` hors de `app/db.py`.

## Langue

Interface, libellés, messages d'erreur, commentaires et tests en français. Les identifiants
de code (noms de variables, de champs, de fonctions) en anglais.

Les messages lus par le CEO sont soignés : « 1 fait(s) présenté(s) » n'est pas acceptable,
et zéro reste au singulier — « 0 option », pas « 0 options ».

## Données

Aucune donnée réelle dans ce dépôt. Le jeu de démonstration est fictif et
**volontairement imparfait** : il sert à vérifier que l'outil signale les défauts. Ne pas
le « corriger » pour rendre les écrans plus flatteurs.
