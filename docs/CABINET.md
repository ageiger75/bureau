# Le cockpit et le cabinet

Écrit le 24 octobre 2026, revu le 9 novembre 2026. Le cabinet est un ensemble d'agents Claude
Code qui vit sur le poste du lecteur, dans `~/cabinet`, hors de ce dépôt : il porte le
contexte personnel du lecteur, et rien de personnel n'approche le dépôt, même dans un
répertoire ignoré. Ce fichier dit ce que le cockpit lui donne et ce que le cabinet s'interdit
d'en faire. C'est la première pièce de la phase 8 du plan, l'analyse par une IA, et la
consigne qu'elle exigeait.

## Le partage des rôles

- Le cockpit **mesure** : déterministe, testé, en lecture seule, sans appel sortant.
- Le cabinet **raisonne et suit** : il assemble, contredit, rédige, prépare, et tient le
  suivi (les engagements des owners, les questions, les promesses, les conclusions et leurs
  dates de réexamen) dans sa boucle et son `memoire/decisions.md`.
- Le lecteur **décide**.

Depuis le 9 novembre 2026, le cockpit ne suit pas : aucun écran ni aucune commande n'écrit
plus au registre des sujets ni aux engagements, et l'export ne les porte plus. Ce qui change
la mesure reste au cockpit : les notes de contexte, les placements de marchés, les poids
stratégiques. Le cabinet a repris ce que le registre tenait le jour du gel.

Le cabinet ne recalcule jamais un chiffre que le cockpit tient, et le cockpit n'écrit jamais
une phrase qu'il ne sait pas tracer. Deux arithmétiques du même chiffre finissent par se
contredire devant un MD, et c'est le lecteur qui paie l'écart.

## Ce que le cockpit donne : `manage.py cabinet`

Un fichier par jour, `AAAA-MM-JJ-cockpit.md`, dans `CEOOS_CABINET_DIR`, sinon dans
`var/cabinet/`. L'en-tête dit la source, la date de chaque lecture et la façon de lire. Chaque
section est la sortie d'une commande qui existe déjà, telle que l'écran la rend. Un dossier de
visite demandé par `--marche` s'écrit à côté, dans son propre fichier
`AAAA-MM-JJ-cockpit-<marché>.md` (`--marche China` donne `-cockpit-china.md`, `--marche "United
States"` donne `-cockpit-united-states.md`) : deux dossiers dans la journée ne s'écrasent pas,
et la lecture du jour garde son nom. Un marché que le cockpit ne connaît pas est refusé, code 2,
sans rien écrire : un dossier vide se citerait comme un vrai.

| Section | Même lecture que |
| --- | --- |
| Où on atterrit, sommes-nous en ligne | `manage.py track` |
| Zones rouges | `manage.py zones` |
| Ce qui est tranché | `manage.py note --list` et `manage.py placements` : les notes de contexte et les placements de marchés, ce qui change la mesure |
| La semaine | `manage.py semaine` |
| Le sell-in du mois | `manage.py sellin` |
| Ce qui arrive | `manage.py tempsforts` |
| Le mois, marché par marché | `manage.py month` |
| Dossier de visite · marché | `manage.py marche <marché>`, avec `--marche <marché>`, dans `AAAA-MM-JJ-cockpit-<marché>.md` |

Trois propriétés, gardées par `tests/test_cabinet_export.py` :

1. **Rien n'est recalculé.** Une section dit mot pour mot ce que sa commande imprime, à deux
   retouches près qui protègent le lecteur : la clôture du bloc est plus longue que toute suite
   d'accents graves du texte, et une ligne du texte qui commence par « # » recule d'une espace,
   pour qu'un nom venu de l'entrepôt ne puisse ni fermer le bloc ni forger un titre de section.
2. **Rien n'y suit.** L'export ne porte ni sujets placés, ni engagements, ni conclusions : le
   suivi vit dans le cabinet, et deux registres finiraient par dire deux choses.
3. **Aucune lecture ne part derrière l'écran** (`source.disk_only`). Le serveur, ouvert dans
   l'autre fenêtre, tient ses caches à jour ; un fil lancé par une commande mourrait avec
   elle et pourrait croiser la lecture du serveur. Les lectures courtes expirées (le mois,
   la semaine, les factures au jour) se relisent comme au terminal, en quelques secondes.

**Les titres des sections sont une interface.** Le cabinet les cherche par leur nom. En
changer un se fait des deux côtés à la fois, test compris.

Le cabinet peut lancer l'export lui-même, par une seule commande autorisée dans ses
réglages : `~/dev/ceo-os/.venv/bin/python ~/dev/ceo-os/manage.py cabinet --vers
~/cabinet/entrees/cockpit`.

## Ce qui quitte la machine, et vers où

Le cockpit n'appelle aucun fournisseur d'IA : il écrit un fichier. Ce qui lit ce fichier,
en revanche, l'envoie au modèle. Le fichier porte des chiffres réels, et il entre dans Claude
sous le compte que Claude Code utilise sur le poste. D'où trois règles :

1. **Le dossier par défaut reste dans `var/`.** Écrire `CEOOS_CABINET_DIR` est une décision,
   pas un réglage : elle se prend quand le compte qui lira est celui que la maison a validé
   (le CTO et le CISO), jamais avant.
2. **Le fichier le dit lui-même**, dans son en-tête, à qui le dépose ailleurs.
3. **Rien n'y entre que l'écran ne montre déjà.** L'export n'est pas une porte vers des
   lectures que l'écran ne fait pas.

Coût et latence : l'export ne coûte rien et ne dépend pas du réseau, sauf une lecture courte
expirée. Le cabinet dépend du service et se paie en jetons ; ce n'est pas mesuré à ce jour.
Hors connexion, le cockpit reste entier et le cabinet s'arrête.

## Ce que le cabinet s'interdit

- **Recalculer un chiffre du cockpit.** Il le cite, avec sa section et la date de l'export.
- **Interroger l'entrepôt pour un chiffre que le cockpit tient.** Les vues sémantiques ne
  portent pas les règles que le cockpit a apprises une par une : les tickets comptés en clés
  distinctes et non en lignes, les héros sur la définition de la maison, les kits comptés une
  fois, l'intragroupe tenu à part, le canal lu sur le centre de profit, les sentinelles
  écrites « N/A ». Une seconde lecture donnerait un second chiffre, et le premier qui le
  verrait serait un MD.
- **Relitiger ce qui est tranché.** La section du même nom porte ce qui change la mesure, les
  notes de contexte et les placements, avec leur date ; les conclusions, les écarts acceptés
  et leurs dates de réexamen vivent dans le `memoire/decisions.md` du cabinet, qu'il lit avant
  de juger. Un sujet tranché revient sur un fait nouveau, nommé, ou à sa date.
- **Ordonner l'attention par un score.** Les trois sujets de la semaine, c'est le cabinet qui
  les choisit, sans note ni agrégat : dans l'ordre de l'écart mesuré par le cockpit, hors
  sujets tranchés jusqu'à leur réexamen ; un sujet que le cockpit ne mesure pas (la veille,
  un rendez-vous, une échéance) prend une place si la raison est dite.
- **Chercher un engagement dans le cockpit.** Il n'en tient plus aucun. Les engagements des
  owners, comme les questions et les promesses du lecteur, vivent dans la boucle du cabinet
  avec leur échéance ; le cockpit mesure ce qu'ils ont produit, et c'est tout.

## La traçabilité

La phase 8 l'exigeait avant toute construction : une phrase générée référence les champs
qu'elle décrit, et une phrase qui ne se trace pas ne s'affiche pas. Dans le cabinet, tout
chiffre tiré du cockpit porte la marque `[cockpit · <section>]`, et un contrôle par code
retrouve chaque chiffre ainsi marqué, à l'identique, dans l'export du jour. Un chiffre
introuvable est un bloquant, pas une coquille.
