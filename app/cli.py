"""Commandes d'administration locale.

    python -m app.cli migrate        crée le schéma manquant
    python -m app.cli seed           insère les données fictives si la base est vide
    python -m app.cli seed --reset    efface tout et réinsère
    python -m app.cli check          vérifie la configuration et affiche le périmètre actif
    python -m app.cli warehouse      teste la connexion Snowflake sans lire de donnée métier
                                     --schemas / --tables SCHEMA / --columns SCHEMA.TABLE
    python -m app.cli note           consigne ce que les chiffres ne peuvent pas dire
                                     note "Marché" "Ce qui s'est passé" [--kind one_off]
                                     note --list · note --forget N
    python -m app.cli reconcile      confronte une extraction candidate aux réalisés connus
                                     reconcile CANDIDAT.csv [--perimeter sell-in]
    python -m app.cli refresh        oublie la lecture en cache : la prochaine ira à l'entrepôt
    python -m app.cli budget         lit le classeur de planification et dit ce qu'il couvre
                                     --period AAAA-MM pour détailler un mois
                                     --segments pour la vue par segment et par périmètre
                                     --spec FICHIER.csv exporte les réalisés de l'an dernier
                                     --perimeter sell-in|own|other|all (défaut sell-in)
    python -m app.cli serve          démarre le serveur (port lu dans PORT, défaut 8000)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from .config import settings
from .db import create_all, database_label

# L'adresse d'écoute est une constante du code, pas un argument de ligne de commande :
# un `--host 0.0.0.0` collé par erreur exposerait des dossiers confidentiels sur le réseau.
SERVE_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def serve_config() -> Tuple[str, int]:
    """Adresse et port d'écoute.

    Le port vient de la variable `PORT` afin que l'environnement puisse en assigner un
    libre ; l'hôte, lui, n'est pas configurable. Une valeur de port illisible retombe sur
    le défaut plutôt que d'empêcher le démarrage.
    """
    raw = os.environ.get("PORT", "").strip()
    try:
        port = int(raw) if raw else DEFAULT_PORT
    except ValueError:
        print(
            "PORT=%r illisible, repli sur %d." % (raw, DEFAULT_PORT), file=sys.stderr
        )
        port = DEFAULT_PORT
    if not 1 <= port <= 65535:
        print(
            "PORT=%d hors bornes, repli sur %d." % (port, DEFAULT_PORT), file=sys.stderr
        )
        port = DEFAULT_PORT
    return SERVE_HOST, port


def cmd_migrate() -> int:
    create_all()
    print("Schéma à jour · %s" % database_label())
    return 0


def cmd_seed(argv: List[str]) -> int:
    reset = "--reset" in argv
    if reset and not settings.is_local:
        # Un --reset hors local effacerait de vraies décisions.
        print(
            "Refusé : --reset n'est autorisé que si CEOOS_ENV=local (actuel : %s)."
            % settings.env,
            file=sys.stderr,
        )
        return 2

    from seed.demo import seed

    print("Données de démonstration · %s" % seed(reset=reset))
    return 0


def cmd_check() -> int:
    host, port = serve_config()
    print("Environnement       %s" % settings.env)
    print("Base                %s" % database_label())
    print("Niveau d'autonomie  %s" % settings.autonomy_level)
    print("Écoute              %s:%d (boucle locale uniquement)" % (host, port))

    if settings.reads_warehouse:
        from .perf import queries

        print("Données perf        Snowflake, connexion « %s » de ~/.snowflake/connections.toml"
              % settings.snowflake_connection)
        print("                    aucun identifiant lu ni stocké par l'application")
        restant = queries.missing()
        if restant:
            print("Requêtes à écrire   %s" % ", ".join(restant))
        else:
            print("Requêtes            toutes écrites")
    else:
        print("Données perf        fictives (CEOOS_DATA_SOURCE=mock)")

    if settings.has_budget_file:
        print("Plan                %s" % settings.budget_path)
    else:
        print("Plan                absent — copier le classeur dans %s" % settings.budget_path)

    from .perf import owners

    directory = owners.current()
    if len(directory):
        named = sum(1 for e in directory.entries if e.level == owners.COUNTRY_GM)
        print("Annuaire            %d entrées, dont %d GM pays" % (len(directory), named))
    else:
        print("Annuaire            absent — « Qui challenger » restera muet")
        print("                    déposer le fichier dans %s" % settings.owners_path)

    from .perf import context

    notes = context.current()
    if len(notes):
        print("Contexte            %d note(s), sur %s"
              % (len(notes), ", ".join(notes.markets()) or "tous marchés"))
    else:
        print("Contexte            aucune note — modèle dans docs/context.example.csv")

    print("Écritures externes  aucune. Le cockpit prépare, signale et structure.")
    print("Appels externes     %s" % (
        "l'entrepôt Snowflake en lecture seule, et rien d'autre"
        if settings.reads_warehouse
        else "aucun (ni Microsoft 365, ni fournisseur IA)"))
    return 0


#: Deux montants pour la même cellule sont d'accord en deçà de cet écart relatif. Assez
#: large pour absorber un arrondi et une conversion de devise, assez serré pour qu'une
#: définition fausse ne passe pas.
RECONCILE_TOLERANCE = 0.01


def cmd_reconcile(argv: List[str]) -> int:
    """Confronte une extraction candidate aux réalisés connus.

    « La donnée n'est pas propre » est une affirmation. Avec douze mois de réalisés par
    marché et par segment, elle devient une mesure. Une requête qui reproduit ces
    montants-là est utilisable, quel que soit l'état de la couche sémantique ; une requête
    qui ne les reproduit pas dit exactement où elle se trompe — ce qui vaut mieux à
    transmettre qu'une demande.

    Le candidat est un CSV aux colonnes `market`, `segment`, `period`, `value`. C'est le
    format qu'écrit `--spec`, pour que les deux fichiers se regardent en face.
    """
    import csv

    from .perf import budget as budget_module
    from .perf.budget import normalise_market, perimeter_of, previous_year

    if not argv or argv[0].startswith("--"):
        print("Usage : manage.py reconcile CANDIDAT.csv [--perimeter sell-in]",
              file=sys.stderr)
        return 2
    candidate_path = Path(argv[0])
    if not candidate_path.exists():
        print("Fichier introuvable : %s" % candidate_path, file=sys.stderr)
        return 2
    if not settings.has_budget_file:
        print("Classeur de planification absent : rien à quoi confronter.", file=sys.stderr)
        return 2

    wanted = (_option(argv, "--perimeter") or "sell-in").strip().lower()
    plan = budget_module.load(settings.budget_path)

    expected = {}
    by_entity = {}
    for line in plan.lines:
        if line.last_year is None:
            continue
        if wanted != "all" and perimeter_of(line.segment) != wanted:
            continue
        # Keyed on the month the actual belongs to, matching what `--spec` writes. The
        # two files have to describe the same months or nothing will ever agree.
        key = (line.market, line.segment, previous_year(line.period))
        expected[key] = expected.get(key, 0.0) + line.last_year
        # A second way in, for a candidate that joins on the plan's own entity code. It is
        # a stronger key than a market name: names are typed by people and translated
        # twice on the way here, while the code is what the consolidation itself uses.
        if line.entity:
            by_entity[(line.entity, line.segment, previous_year(line.period))] = key

    if not expected:
        print("Aucun réalisé connu sur ce périmètre.", file=sys.stderr)
        return 2

    found = {}
    unknown = 0
    matched_on_entity = 0
    with candidate_path.open(encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle):
            segment = str(record.get("segment") or "").strip()
            period = str(record.get("period") or "").strip()
            entity = str(record.get("entity") or "").strip().upper()

            key = None
            if entity:
                key = by_entity.get((entity, segment, period))
                if key is not None:
                    matched_on_entity += 1
            if key is None:
                key = (
                    normalise_market(str(record.get("market") or "")),
                    segment,
                    period,
                )
            try:
                value = float(str(record.get("value") or record.get("actual_eur") or ""))
            except ValueError:
                continue
            if key not in expected:
                unknown += 1
                continue
            found[key] = found.get(key, 0.0) + value

    return _report_reconciliation(
        expected, found, unknown, wanted, matched_on_entity
    )


def _report_reconciliation(
    expected, found, unknown, perimeter, matched_on_entity=0
) -> int:
    agree = []
    differ = []
    for key, target in expected.items():
        if key not in found:
            continue
        candidate = found[key]
        scale = abs(target) or 1.0
        if abs(candidate - target) / scale <= RECONCILE_TOLERANCE:
            agree.append(key)
        else:
            differ.append((key, target, candidate))

    missing = [key for key in expected if key not in found]
    covered = len(agree) + len(differ)

    print("Périmètre           %s" % perimeter)
    print("Cellules attendues  %d" % len(expected))
    print("Cellules trouvées   %d" % covered)
    print("D'accord            %d" % len(agree))
    print("En désaccord        %d" % len(differ))
    print("Absentes            %d" % len(missing))
    if unknown:
        print("Hors périmètre      %d lignes du candidat ne correspondent à rien d'attendu"
              % unknown)
    if matched_on_entity:
        print("Jointes par entité  %d lignes — la clé du plan plutôt qu'un nom de marché"
              % matched_on_entity)

    if covered:
        rate = 100.0 * len(agree) / covered
        print("")
        print("Taux d'accord       %.1f%% des cellules confrontées" % rate)

    # Ce que le taux ne dit pas : une définition fausse se voit à l'argent, pas au nombre
    # de cellules. Un marché majeur en désaccord pèse plus que trente marchés minuscules.
    if differ:
        differ.sort(key=lambda item: -abs(item[1] - item[2]))
        print("")
        print("Les plus gros écarts :")
        print("%-20s %-26s %-9s %14s %14s" % ("Marché", "Segment", "Mois", "Attendu", "Candidat"))
        for (market, segment, period), target, candidate in differ[:15]:
            print("%-20s %-26s %-9s %14s %14s" % (
                market[:20], segment[:26], period, _eur(target), _eur(candidate)))
        if len(differ) > 15:
            print("… et %d autres." % (len(differ) - 15))

    if missing:
        markets = sorted({key[0] for key in missing})
        print("")
        print("Rien trouvé pour %d cellules, sur %d marchés : %s"
              % (len(missing), len(markets), ", ".join(markets[:12])))
        if len(markets) > 12:
            print("… et %d autres marchés." % (len(markets) - 12))

    print("")
    if not differ and not missing:
        print("Le candidat reproduit tous les réalisés connus. Utilisable.")
        return 0
    print("Le candidat ne reproduit pas encore les réalisés. Les écarts ci-dessus disent")
    print("où, ce qui vaut mieux à transmettre qu'une demande.")
    return 1


NOTE_HEADER = ("market", "channel", "since", "kind", "note", "source")


def cmd_note(argv: List[str]) -> int:
    """Consigne ce que les chiffres ne peuvent pas dire.

    Une commande plutôt qu'un fichier à éditer : ces notes s'écrivent au moment où on
    comprend quelque chose, souvent entre deux réunions, et une seule ligne de terminal
    passe là où un tableur ne passe pas.

        manage.py note "Brazil" "Les taxes ont changé en juin, le budget est antérieur."
        manage.py note "Japan" "Fermeture d'un magasin phare." --kind one_off --since 2026-07
        manage.py note --list
        manage.py note --forget 2
    """
    import csv

    from .perf import context
    from .perf.budget import normalise_market
    from .perf.mapping import normalise_channel

    path = settings.context_path
    existing = _read_notes(path)

    if "--list" in argv:
        return _print_notes(existing, path)

    forget = _option(argv, "--forget")
    if forget:
        try:
            index = int(forget)
        except ValueError:
            print("Numéro attendu : manage.py note --forget 2", file=sys.stderr)
            return 2
        if not 1 <= index <= len(existing):
            print("Aucune note numéro %s. `manage.py note --list` pour les voir."
                  % forget, file=sys.stderr)
            return 2
        dropped = existing.pop(index - 1)
        _write_notes(path, existing)
        print("Oubliée : %s — %s" % (dropped["market"] or "tous marchés", dropped["note"]))
        return 0

    positional = [a for a in argv if not a.startswith("--")]
    # Les valeurs des options sont des positionnels aux yeux de ce découpage naïf ; on les
    # retire, sinon un `--since 2026-06` se ferait passer pour le texte de la note.
    for flag in ("--kind", "--since", "--channel", "--source", "--forget"):
        value = _option(argv, flag)
        if value in positional:
            positional.remove(value)

    if len(positional) < 2:
        print(cmd_note.__doc__, file=sys.stderr)
        return 2

    market, text = positional[0], positional[1]
    kind = (_option(argv, "--kind") or context.BASIS_CHANGE).strip().lower()
    if kind not in context.KINDS:
        print("Type inconnu : %s. Au choix : %s"
              % (kind, ", ".join(context.KINDS)), file=sys.stderr)
        print("  basis_change  le plan et le réalisé ne se comparent plus", file=sys.stderr)
        print("  one_off       un événement isolé est dans le chiffre", file=sys.stderr)
        return 2

    channel = _option(argv, "--channel") or ""
    row = {
        "market": normalise_market(market),
        "channel": normalise_channel(channel) if channel else "",
        "since": (_option(argv, "--since") or "").strip(),
        "kind": kind,
        "note": text,
        "source": _option(argv, "--source") or "CEO",
    }
    existing.append(row)
    _write_notes(path, existing)
    context.reset()

    print("Notée               %s%s" % (
        row["market"] or "tous marchés",
        " · %s" % row["channel"] if row["channel"] else "",
    ))
    print("Depuis              %s" % (row["since"] or "toujours"))
    print("Effet               %s" % context.KIND_MEANING[kind])
    print("Nouvelle question   %s" % context.KIND_QUESTION[kind])
    print("")
    print("Rechargez l'écran : le marché sort de « Qui challenger » et garde son écart.")
    return 0


def _read_notes(path) -> List[dict]:
    import csv

    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return [
                {key: (record.get(key) or "") for key in NOTE_HEADER}
                for record in csv.DictReader(handle)
                if (record.get("note") or "").strip()
                and not str(record.get("market") or "").startswith("#")
            ]
    except OSError:
        return []


def _write_notes(path, rows) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(NOTE_HEADER))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _print_notes(rows, path) -> int:
    from .perf import context

    if not rows:
        print("Aucune note. Pour en ajouter une :")
        print('  manage.py note "Brazil" "Les taxes ont changé en juin."')
        return 0
    print("Fichier             %s" % path)
    print("")
    for index, row in enumerate(rows, start=1):
        scope = row["market"] or "tous marchés"
        if row["channel"]:
            scope += " · " + row["channel"]
        print("%d. %s%s" % (index, scope,
                            "  (depuis %s)" % row["since"] if row["since"] else ""))
        print("   %s" % row["note"])
        print("   %s%s" % (
            context.KIND_MEANING.get(row["kind"], row["kind"]),
            "  — %s" % row["source"] if row["source"] else "",
        ))
        print("")
    print("Pour en retirer une : manage.py note --forget N")
    return 0


def cmd_refresh() -> int:
    """Oublie la lecture gardée sur le disque.

    La requête prend des minutes, donc elle est mise en cache une heure et survit aux
    redémarrages — sans quoi chaque relance la repaye. Reste à pouvoir dire « non, relis
    maintenant » quand l'entrepôt a bougé.
    """
    from .perf import source

    source.cache_forget()
    print("Cache oublié. La prochaine lecture ira à l'entrepôt.")
    return 0


def cmd_budget(argv: List[str]) -> int:
    """Lit le classeur de planification et dit ce qu'il contient.

    Aucun réseau, aucune base : c'est un fichier sur le disque. La commande existe pour
    répondre à la seule question qui compte avant de brancher l'entrepôt — le budget
    couvre-t-il bien les marchés dont on va lire les ventes ? Un classeur illisible ou
    incomplet vaut mieux découvert ici que devant un écran serein.
    """
    from .perf import budget as budget_module

    if not settings.has_budget_file:
        print("Classeur absent : %s" % settings.budget_path, file=sys.stderr)
        print("Copier le fichier de planification à cet emplacement, puis relancer.",
              file=sys.stderr)
        return 2

    try:
        plan = budget_module.load(settings.budget_path)
    except Exception as exc:  # noqa: BLE001 — le message importe plus que le type
        print("Lecture impossible : %s" % exc, file=sys.stderr)
        return 1

    periods = plan.periods()
    markets = plan.markets()
    print("Classeur            %s" % settings.budget_path)
    print("Lignes              %d" % len(plan.lines))
    print("Marchés             %d" % len(markets))
    print("Périodes            %d, de %s à %s" % (
        len(periods), periods[0] if periods else "?", periods[-1] if periods else "?"))

    destination = _option(argv, "--spec")
    if destination:
        return _write_actuals_spec(plan, destination, _option(argv, "--perimeter") or "sell-in")

    if "--segments" in argv:
        _print_segments(plan)
        return 0

    wanted = _option(argv, "--period")
    if wanted:
        if wanted not in periods:
            print("Période inconnue : %s" % wanted, file=sys.stderr)
            return 2
        _print_period(plan, wanted)
        return 0

    # Sans période demandée, un total par mois : une colonne vide ou un mois manquant
    # se voit d'un coup d'œil, ce qu'une somme annuelle cacherait.
    print("")
    print("%-10s %16s %16s" % ("Période", "Budget", "An dernier"))
    for period in periods:
        print("%-10s %16s %16s" % (
            period,
            _eur(plan.total_budget(period)),
            _eur(plan.total_last_year(period)),
        ))
    return 0


def _print_segments(plan) -> None:
    """What the file plans, by segment and by perimeter.

    The split matters more than it looks: the warehouse measures what the Maison sells to
    the end customer, while nearly two fifths of the plan is invoiced to someone who then
    resells it. No sell-out query will ever reproduce those lines, and reading their
    absence as a shortfall would be a serious mistake.
    """
    from .perf.budget import AMBIGUOUS_SEGMENTS, perimeter_of, segment_code

    # Every line, budgeted or not. Counting only budgeted ones would quietly drop last
    # year's revenue in channels nobody planned for this year — which is precisely the
    # kind of thing worth seeing, and it made two commands disagree by four million.
    totals = {}
    orphaned = 0.0
    for line in plan.lines:
        entry = totals.setdefault(line.segment, [0.0, 0.0, set()])
        entry[0] += line.budget or 0.0
        entry[1] += line.last_year or 0.0
        if line.budget:
            entry[2].add(line.market)
        elif line.last_year:
            orphaned += line.last_year

    grand = sum(v[0] for v in totals.values()) or 1.0
    print("")
    print("%-28s %-9s %12s %6s %12s %8s" % (
        "Segment", "Périmètre", "Budget", "Part", "FY-1 réalisé", "Marchés"))
    for segment, (budget, actual, markets) in sorted(
        totals.items(), key=lambda item: -item[1][0]
    ):
        print("%-28s %-9s %12s %5.1f%% %12s %8d" % (
            segment[:28],
            perimeter_of(segment),
            _eur(budget),
            100.0 * budget / grand,
            _eur(actual),
            len(markets),
        ))

    print("")
    by_perimeter = {}
    for segment, (budget, actual, _markets) in totals.items():
        slot = by_perimeter.setdefault(perimeter_of(segment), [0.0, 0.0])
        slot[0] += budget
        slot[1] += actual
    for name, (budget, actual) in sorted(by_perimeter.items(), key=lambda i: -i[1][0]):
        print("%-28s %-9s %12s %5.1f%% %12s" % (
            "", name, _eur(budget), 100.0 * budget / grand, _eur(actual)))

    if orphaned:
        print("")
        print("Réalisé l'an dernier sans budget cette année : %s" % _eur(orphaned))
        print("Un canal qui a facturé et que personne n'a planifié. Volontaire ou oublié,")
        print("il ne sera comparé à rien.")

    ambiguous = [s for s in totals if segment_code(s) in AMBIGUOUS_SEGMENTS]
    if ambiguous:
        print("")
        print("Sur la frontière : %s" % ", ".join(sorted(ambiguous)))
        print("Un marketplace en dépôt-vente ressemble plus à de l'e-commerce propre qu'à")
        print("du gros. Le contrat tranche, pas le code segment.")


def _write_actuals_spec(plan, destination: str, perimeter: str) -> int:
    """Écrit les réalisés de l'an dernier, mois par mois, comme cible de réconciliation.

    C'est le livrable pour l'IT, et sa nature compte : ce sont des **réalisés**, pas un
    budget. On ne valide pas une requête d'entrepôt contre un plan — un plan a le droit
    d'avoir tort. Contre douze mois de réalisés par marché et par segment, une définition
    fausse ne survit pas.
    """
    import csv

    from .perf.budget import perimeter_of, previous_year

    wanted = perimeter.strip().lower()
    if wanted not in ("sell-in", "own", "other", "all"):
        print("Périmètre inconnu : %s (sell-in, own, other, all)" % perimeter,
              file=sys.stderr)
        return 2

    rows = [
        line
        for line in plan.lines
        if line.last_year
        and (wanted == "all" or perimeter_of(line.segment) == wanted)
    ]
    if not rows:
        print("Aucun réalisé sur ce périmètre.", file=sys.stderr)
        return 1

    # Folded to one row per cell, exactly as the reconciliation reads it. The two used to
    # count differently — the file wrote every planning row, the check summed them by key —
    # so the same workbook announced 1 330 constraints and then expected 1 298. Both were
    # defensible on their own, which is the worst case: a reader comparing the two outputs
    # concludes there is a bug, and cannot tell which side has it.
    cells: Dict[tuple, List] = {}
    for line in rows:
        key = (line.market, line.segment, previous_year(line.period))
        if key in cells:
            cells[key][1] += line.last_year
        else:
            cells[key] = [line, line.last_year]

    ordered = sorted(cells.items(), key=lambda item: item[0])
    periods = sorted({key[2] for key in cells})
    path = Path(destination)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        # `entity` first, because it is the column that matters most and the one a reader
        # skims for. It is the plan's own answer to "which market does this revenue belong
        # to" — reaching for a company code or a customer hierarchy instead is reaching
        # for someone else's answer to the same question, and the two do not agree.
        writer.writerow(
            ["entity", "market", "region", "segment", "perimeter", "period", "actual_eur"]
        )
        for (market, segment, period), (line, total) in ordered:
            writer.writerow([
                line.entity,
                market,
                line.region,
                segment,
                perimeter_of(segment),
                # The month this figure belongs to, not the month whose plan it sits
                # beside. A specification that misdates its own evidence sends whoever
                # reads it looking for FY27 actuals in months that have not happened.
                period,
                "%.2f" % total,
            ])

    total = sum(entry[1] for entry in cells.values())
    print("Écrit               %s" % path)
    print("Périmètre           %s" % wanted)
    print("Contraintes         %d (marché × segment × mois)" % len(cells))
    print("Marchés             %d" % len({key[0] for key in cells}))
    print("Mois                %d, de %s à %s" % (
        len(periods), periods[0], periods[-1]))
    entities = sorted({entry[0].entity for entry in cells.values() if entry[0].entity})
    if entities:
        print("Entités             %d — la clé d'attribution du plan" % len(entities))
    print("Total réalisé       %s" % _eur(total))
    print("")
    print("Ce sont des réalisés, pas un budget : une requête d'entrepôt se valide contre")
    print("ce que l'entreprise a facturé, pas contre ce qu'elle avait prévu de facturer.")
    return 0


def _print_period(plan, period: str) -> None:
    lines = sorted(
        (l for l in plan.lines if l.period == period),
        key=lambda l: -(l.budget or 0.0),
    )
    print("")
    print("%-24s %-10s %16s %16s" % ("Marché", "Canal", "Budget", "An dernier"))
    for line in lines:
        print("%-24s %-10s %16s %16s" % (
            line.market[:24],
            line.channel,
            _eur(line.budget),
            _eur(line.last_year),
        ))


def _eur(value) -> str:
    """Des euros lisibles, et un tiret quand la case est vide.

    Un zéro affiché à la place d'une absence est exactement le mensonge que le reste du
    cockpit passe son temps à éviter.
    """
    if value is None:
        return "—"
    return "{:,.0f}".format(value).replace(",", " ")


def cmd_warehouse(argv: List[str]) -> int:
    """Prouve que la connexion fonctionne, sans lire une seule donnée métier."""
    if not settings.reads_warehouse:
        print("CEOOS_DATA_SOURCE n'est pas « snowflake » : rien à tester.", file=sys.stderr)
        return 2
    _silence_third_party_noise()
    from .perf import warehouse

    try:
        return _warehouse_action(warehouse, argv)
    except Exception as exc:  # noqa: BLE001 — le message importe plus que le type
        print("Échec : %s" % exc, file=sys.stderr)
        return 1


def _warehouse_action(warehouse, argv: List[str]) -> int:
    """Exploration en lecture seule, pour écrire les requêtes contre le vrai schéma."""
    facts = None

    if "--schemas" in argv:
        facts = warehouse.check()
        database = _option(argv, "--database") or facts.get("database")
        if not database:
            print("Aucune base : préciser --database NOM.", file=sys.stderr)
            return 2
        print("Schémas de %s :" % database)
        for name in warehouse.schemas(database):
            print("  %s" % name)
        return 0

    if "--tables" in argv:
        facts = warehouse.check()
        schema = _option(argv, "--tables")
        database = _option(argv, "--database") or facts.get("database")
        if not schema or not database:
            print("Usage : manage.py warehouse --tables SCHEMA [--database BASE]",
                  file=sys.stderr)
            return 2
        print("Objets de %s.%s :" % (database, schema))
        for item in warehouse.tables(database, schema, _option(argv, "--like") or ""):
            count = "" if item["rows"] is None else "  (%s lignes)" % item["rows"]
            print("  %-8s %s%s" % (item["kind"], item["name"], count))
        return 0

    if "--columns" in argv:
        facts = warehouse.check()
        target = _option(argv, "--columns") or ""
        parts = target.split(".")
        if len(parts) == 3:
            database, schema, table = parts
        elif len(parts) == 2:
            database, (schema, table) = facts.get("database"), parts
        else:
            print("Usage : manage.py warehouse --columns [BASE.]SCHEMA.TABLE",
                  file=sys.stderr)
            return 2
        print("Colonnes de %s.%s.%s :" % (database, schema, table))
        for column in warehouse.columns(database, schema, table):
            print("  %-34s %-18s %s" % (column["name"], column["type"], column["null"]))
        return 0

    print("Ouverture de la connexion « %s »." % settings.snowflake_connection)
    print("Une page d'authentification peut s'ouvrir dans le navigateur.")
    print()
    print(warehouse.describe_session())
    print()
    print("Explorer le schéma, sans lire de donnée métier :")
    print("  manage.py warehouse --schemas")
    print("  manage.py warehouse --tables SCHEMA [--like MOTIF%]")
    print("  manage.py warehouse --columns SCHEMA.TABLE")
    return 0


def _silence_third_party_noise() -> None:
    """Tait les avertissements des dépendances, jamais les nôtres.

    Le connecteur tire boto3 et une copie d'urllib3 qui préviennent, à chaque appel, que
    Python 3.9 vieillit et que macOS livre LibreSSL. Les deux sont vraies et sans effet
    ici, mais elles s'intercalent entre la question posée et la réponse — et une sortie
    illisible est une sortie qu'on cesse de lire.
    """
    import warnings

    for pattern in (
        r".*LibreSSL.*",
        r".*Boto3 will no longer support Python 3\.9.*",
        r".*Dependency 'keyring' is not installed.*",
    ):
        warnings.filterwarnings("ignore", message=pattern)


def _option(argv: List[str], flag: str) -> str:
    """Valeur suivant un drapeau, ou chaîne vide."""
    if flag in argv:
        position = argv.index(flag) + 1
        if position < len(argv) and not argv[position].startswith("--"):
            return argv[position]
    return ""


def cmd_serve(argv: List[str]) -> int:
    """Démarre le serveur. `--reload` pour le développement."""
    import uvicorn

    create_all()
    host, port = serve_config()
    print("CEO OS · http://%s:%d" % (host, port))
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload="--reload" in argv,
        log_level="info",
    )
    return 0


def main(argv: List[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    command = argv[0]
    if command == "migrate":
        return cmd_migrate()
    if command == "seed":
        return cmd_seed(argv[1:])
    if command == "check":
        return cmd_check()
    if command == "warehouse":
        return cmd_warehouse(argv[1:])
    if command == "budget":
        return cmd_budget(argv[1:])
    if command == "refresh":
        return cmd_refresh()
    if command == "note":
        return cmd_note(argv[1:])
    if command == "reconcile":
        return cmd_reconcile(argv[1:])
    if command == "serve":
        return cmd_serve(argv[1:])
    print("Commande inconnue : %s" % command, file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
