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
                                     reconcile --from-warehouse lance la requête versionnée
    python -m app.cli refresh        oublie la lecture en cache : la prochaine ira à l'entrepôt
    python -m app.cli history        les vingt-quatre mois derrière le mois affiché
                                     --market NOM pour dérouler un marché mois par mois
                                     --plans pour ce qui n'a ni budget ni ventes en face
                                     --sell-in confronte le sell-in à son plan
                                     --refresh pour relire l'entrepôt au lieu du cache
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
from typing import Dict, List, Optional, Tuple

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

    # « Dossiers » et non « données de démonstration » : cette ligne parle des dossiers
    # de Decision Room dans SQLite, jamais des chiffres de performance, qui viennent d'une
    # tout autre source. Le mot précédent s'affichait à chaque lancement et laissait
    # croire que l'écran entier tournait sur des chiffres inventés.
    print("Dossiers Decision Room · %s" % seed(reset=reset))
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

    Le candidat est un CSV aux colonnes `market`, `segment`, `period`, `value` — le format
    qu'écrit `--spec`, pour que les deux fichiers se regardent en face. `--from-warehouse`
    lit à la place la requête versionnée `SELL_IN_HISTORY`, ce qui rend la mesure
    reproductible : une vérification qu'on ne peut pas relancer est une affirmation, pas
    une garantie.
    """
    import csv

    from .perf import budget as budget_module
    from .perf.budget import normalise_market, perimeter_of, previous_year

    from_warehouse = "--from-warehouse" in argv
    candidate_path = None
    if not from_warehouse:
        if not argv or argv[0].startswith("--"):
            print("Usage : manage.py reconcile CANDIDAT.csv [--perimeter sell-in]",
                  file=sys.stderr)
            print("        manage.py reconcile --from-warehouse", file=sys.stderr)
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
        # Keyed by market, not by entity: several entities of one country are summed
        # here, exactly as the screen folds them. A disagreement that survives this is a
        # disagreement about a country's revenue, not about which of its legal entities
        # booked it — the second would be invisible to a reader and is not worth a line.
        #
        # This held for single months and not for grouped ones, which is worse than not
        # holding at all: the property was written down here as though it were general,
        # and a reader — including its author — stopped checking the other path. See
        # `_resolve_combined`, where it had to be made true.
        key = (line.market, line.segment, previous_year(line.period))
        expected[key] = expected.get(key, 0.0) + line.last_year
        # A second way in, for a candidate that joins on the plan's own entity code. It is
        # a stronger key than a market name: names are typed by people and translated
        # twice on the way here, while the code is what the consolidation itself uses.
        if line.entity:
            month = previous_year(line.period)
            by_entity[(line.entity, line.segment, month)] = key
            # The workbook types the same entity two ways — bare `M_002` for most,
            # suffixed `M_017_UNLOC` for a few — while the consolidation always
            # writes the suffixed form. Registering the suffix as an alias lets a
            # candidate join on what the warehouse actually contains, instead of
            # asking a query to know how a spreadsheet happened to be typed. An
            # exact line written later overwrites the alias, so the plan's own
            # spelling always wins where it exists.
            alias = (line.entity + "_UNLOC", line.segment, month)
            if alias not in by_entity:
                by_entity[alias] = key

    if not expected:
        print("Aucun réalisé connu sur ce périmètre.", file=sys.stderr)
        return 2

    if from_warehouse:
        candidate = _candidate_from_warehouse()
        if candidate is None:
            return 2
    else:
        with candidate_path.open(encoding="utf-8-sig", newline="") as handle:
            candidate = list(csv.DictReader(handle))

    found = {}
    combined = []
    unknown = 0
    matched_on_entity = 0
    for record in candidate:
        segment = str(record.get("segment") or "").strip()
        period = str(record.get("period") or "").strip()
        entity = str(record.get("entity") or "").strip().upper()

        # A source may be unable to separate two months — a cumulative fact with a
        # snapshot missing in the middle. Splitting them by a rule of thumb would be
        # the one thing worth less than not having them: a figure invented to fill a
        # column. `2025-04..2025-05` says so instead, and is confronted with the plan's
        # own two months added together.
        months = _months_in(period)
        if len(months) > 1:
            combined.append((entity, segment, months, _value_of(record)))
            continue

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
        value = _value_of(record)
        if value is None:
            continue
        if key not in expected:
            unknown += 1
            continue
        found[key] = found.get(key, 0.0) + value

    # Combined months are resolved after the single ones, so a range never shadows a month
    # the candidate also produced on its own.
    grouped = _resolve_combined(combined, expected, by_entity, found)

    return _report_reconciliation(
        expected, found, unknown, wanted, matched_on_entity, grouped
    )


def _report_reconciliation(
    expected, found, unknown, perimeter, matched_on_entity=0, grouped=()
) -> int:
    checked = [c for c in grouped if c.resolved]
    grouped_agree = [c for c in checked if c.agrees]

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

    if checked:
        months_covered = sum(len(c.months) for c in checked)
        print("Mois groupés        %d figures couvrant %d mois, dont %d d'accord"
              % (len(checked), months_covered, len(grouped_agree)))
        print("                    inséparables à la source, confrontées à la somme du plan")
        for item in checked:
            if item.agrees:
                continue
            print("   %-30s %-22s %14s vs %s" % (
                item.label[:30],
                "%s→%s" % (item.months[0], item.months[-1]),
                _eur(item.target),
                _eur(item.value),
            ))
    orphaned = [c for c in grouped if not c.resolved]
    if orphaned:
        print("Groupes sans cible  %d — aucun des mois couverts n'est attendu ici"
              % len(orphaned))

    # Grouped figures count in the rate: a candidate that reproduces two inseparable
    # months as one correct total has done its job on those months, and a rate that
    # ignored them would flatter or damn it for a limitation of the source.
    covered += len(checked)
    if covered:
        rate = 100.0 * (len(agree) + len(grouped_agree)) / covered
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

    grouped_differ = [c for c in grouped if not c.agrees]
    print("")
    if not differ and not missing and not grouped_differ:
        print("Le candidat reproduit tous les réalisés connus. Utilisable.")
        return 0
    print("Le candidat ne reproduit pas encore les réalisés. Les écarts ci-dessus disent")
    print("où, ce qui vaut mieux à transmettre qu'une demande.")
    return 1


NOTE_HEADER = ("market", "channel", "since", "kind", "note", "source", "question")


def cmd_note(argv: List[str]) -> int:
    """Consigne ce que les chiffres ne peuvent pas dire.

    Une commande plutôt qu'un fichier à éditer : ces notes s'écrivent au moment où on
    comprend quelque chose, souvent entre deux réunions, et une seule ligne de terminal
    passe là où un tableur ne passe pas.

        manage.py note "Brazil" "Les taxes ont changé en juin, le budget est antérieur."
        manage.py note "Japan" "Fermeture d'un magasin phare." --kind one_off --since 2026-07
        manage.py note "United States" "Sephora.com est classé ailleurs." \\
            --kind reclassified --channel "WEBP - Web Partners"
        manage.py note --list
        manage.py note --forget 2
        manage.py note --forget 1,2,3     plusieurs d'un coup, sans recompter

    `--ask "…"` remplace la question que la note substitue, quand elle est déjà tranchée.
    """
    import csv

    from .perf import context
    from .perf.budget import normalise_market

    path = settings.context_path
    existing = _read_notes(path)

    if "--list" in argv:
        return _print_notes(existing, path)

    forget = _option(argv, "--forget")
    if forget:
        # Plusieurs numéros d'un coup, parce que les notes se posent souvent par paires —
        # une frontière a deux côtés — et qu'en les retirant une par une les numéros se
        # décalent à chaque suppression. Une consigne qui demande de recompter entre deux
        # commandes est une consigne qui sera mal exécutée, et ici se tromper de numéro
        # veut dire effacer la note de quelqu'un d'autre.
        try:
            indexes = sorted({int(part) for part in forget.replace(" ", ",").split(",")
                              if part}, reverse=True)
        except ValueError:
            print("Numéros attendus : manage.py note --forget 2  ·  --forget 1,2,3",
                  file=sys.stderr)
            return 2
        unknown = [n for n in indexes if not 1 <= n <= len(existing)]
        if unknown or not indexes:
            print("Aucune note numéro %s. `manage.py note --list` pour les voir."
                  % ", ".join(str(n) for n in unknown or ["?"]), file=sys.stderr)
            return 2
        # Du plus grand au plus petit : retirer la note 1 en premier renumérote toutes
        # les suivantes, et la deuxième suppression viserait alors la mauvaise ligne.
        dropped = [existing.pop(index - 1) for index in indexes]
        _write_notes(path, existing)
        for note in reversed(dropped):
            print("Oubliée : %s — %s" % (note["market"] or "tous marchés", note["note"]))
        print("")
        print("Il reste %d note%s. `manage.py note --list` pour les voir."
              % (len(existing), "" if len(existing) == 1 else "s"))
        return 0

    positional = [a for a in argv if not a.startswith("--")]
    # Les valeurs des options sont des positionnels aux yeux de ce découpage naïf ; on les
    # retire, sinon un `--since 2026-06` se ferait passer pour le texte de la note.
    for flag in ("--kind", "--since", "--channel", "--source", "--forget", "--ask"):
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
        "channel": context.resolve_channel(channel),
        "since": (_option(argv, "--since") or "").strip(),
        "kind": kind,
        "note": text,
        "source": _option(argv, "--source") or "CEO",
        # Replaces the kind's default question. Worth having: the default is a guess at
        # what a reader should do next, and the person writing the note sometimes knows
        # that question has already been settled.
        "question": _option(argv, "--ask") or "",
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
    print("Nouvelle question   %s" % (row["question"] or context.KIND_QUESTION[kind]))
    print("")
    print("Rechargez l'écran : le marché sort de « Qui challenger » et garde son écart.")
    return 0


def _candidate_from_warehouse():
    """Run the versioned reconciliation query, so the check is repeatable.

    The measurement that promoted sell-in out of "not measured" was produced by a
    throwaway script on one machine. Nobody else could reproduce it, and nobody could tell
    six months later whether it still held — which makes it a claim rather than a
    guarantee. Versioned, it runs monthly in one command.
    """
    if not settings.reads_warehouse:
        print("CEOOS_DATA_SOURCE n'est pas « snowflake » : rien à lire.", file=sys.stderr)
        return None

    from .perf import queries, warehouse

    if not queries.SELL_IN_HISTORY.strip():
        print("SELL_IN_HISTORY n'est pas écrite. Le contrat est dans app/perf/queries.py :",
              file=sys.stderr)
        print("  entity, segment, period, value — sur un exercice complet.", file=sys.stderr)
        return None

    _silence_third_party_noise()
    try:
        rows = warehouse.rows(queries.SELL_IN_HISTORY, label="SELL_IN_HISTORY")
    except Exception as exc:  # noqa: BLE001 — le message importe plus que le type
        print("Lecture impossible : %s" % exc, file=sys.stderr)
        return None

    print("Lu dans l'entrepôt  %d lignes" % len(rows))
    return [{str(k): v for k, v in row.items()} for row in rows]


def _value_of(record) -> Optional[float]:
    try:
        return float(str(record.get("value") or record.get("actual_eur") or ""))
    except ValueError:
        return None


def _months_in(period: str) -> List[str]:
    """`2025-04..2025-05` -> both months. A single month returns itself."""
    text = (period or "").strip()
    if ".." not in text:
        return [text] if text else []
    first, _, last = text.partition("..")
    first, last = first.strip(), last.strip()
    try:
        year, month = (int(part) for part in first.split("-"))
        end_year, end_month = (int(part) for part in last.split("-"))
    except ValueError:
        return [text]
    months = []
    while (year, month) <= (end_year, end_month) and len(months) < 24:
        months.append("%04d-%02d" % (year, month))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return months


class Combined:
    """Several months the candidate could not separate, confronted as one figure."""

    __slots__ = ("label", "months", "target", "value", "resolved")

    def __init__(self, label, months, target, value) -> None:
        self.label = label
        self.months = months
        self.target = target
        self.value = value
        self.resolved = target is not None

    @property
    def agrees(self) -> bool:
        if self.target is None:
            return False
        scale = abs(self.target) or 1.0
        return abs(self.value - self.target) / scale <= RECONCILE_TOLERANCE


def _resolve_combined(entries, expected, by_entity, found) -> List["Combined"]:
    """Confront each multi-month figure with the plan's own months added together.

    The months it covers are then removed from `expected`: they were checked, jointly, and
    counting them again as missing would report a gap that has just been closed.

    Entries that land on the same plan cells are added up before being confronted, and
    that is not a detail. Two entities can feed one market — China is billed by both
    `M_037` and `M_007_JDCOM` — so comparing either one alone against the market's whole
    figure makes it look short by exactly the other's revenue, and the second entry then
    finds its cells already spent and is reported as having no target at all. That
    manufactured a 3 to 6 M€ divergence on Chinese cross-border out of two entities whose
    annual totals both reconcile to the euro.
    """
    grouped: Dict[tuple, dict] = {}
    order: List[tuple] = []
    orphans: List[Combined] = []

    for entity, segment, months, value in entries:
        if value is None:
            continue
        keys = []
        for month in months:
            key = by_entity.get((entity, segment, month))
            if key is not None and key in expected and key not in keys:
                keys.append(key)
        if not keys:
            orphans.append(Combined("%s %s" % (entity, segment), months, None, value))
            continue
        signature = tuple(sorted(keys))
        if signature not in grouped:
            grouped[signature] = {
                "keys": keys,
                "months": months,
                "value": 0.0,
                "labels": [],
            }
            order.append(signature)
        bucket = grouped[signature]
        bucket["value"] += value
        bucket["labels"].append("%s %s" % (entity, segment))

    resolved: List[Combined] = []
    for signature in order:
        bucket = grouped[signature]
        target = sum(expected[key] for key in bucket["keys"] if key in expected)
        label = bucket["labels"][0]
        if len(bucket["labels"]) > 1:
            # Named rather than hidden: a figure that took two entities to make is a
            # different thing to check than one that took a single entity.
            label = "%s +%d" % (label, len(bucket["labels"]) - 1)
        resolved.append(Combined(label, bucket["months"], target, bucket["value"]))
        for key in bucket["keys"]:
            # Checked jointly, so no longer outstanding. Leaving them would report a gap
            # that has just been closed, and understate a candidate that did its job.
            expected.pop(key, None)
            found.pop(key, None)
    return resolved + orphans


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
        if row.get("question"):
            print("   Question : %s" % row["question"])
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


def cmd_history(argv: List[str]) -> int:
    """Déroule les vingt-quatre mois derrière le mois affiché.

    L'écran montre un mois. Cette commande montre la série dont il fait partie, et
    surtout les deux choses qu'un mois seul ne peut pas dire : quels marchés ratent leur
    plan depuis un an au même écart — un plan à recaler, pas un écart qui s'est ouvert —
    et combien de chiffre d'affaires n'a aucun budget en face. Le second point n'est pas
    un détail de tuyauterie : additionné sans le dire, il flatte l'année de plus de moitié.
    """
    if not settings.reads_warehouse:
        print("CEOOS_DATA_SOURCE n'est pas « snowflake » : rien à lire.", file=sys.stderr)
        return 2
    _silence_third_party_noise()
    from .perf import history as history_module
    from .perf import queries, warehouse

    if not queries.SALES_HISTORY.strip():
        print("La requête SALES_HISTORY n'est pas écrite.", file=sys.stderr)
        return 2

    # Le même cache que l'écran, et pour la même raison : deux ans d'historique sont la
    # lecture chère de cet entrepôt. Sans ça, regarder l'année, puis un marché, puis ce
    # qui n'a pas de plan coûterait trois fois la requête entière.
    from .perf import source as source_module

    stored = None if "--refresh" in argv else source_module.cached_history_rows()
    if stored is not None:
        rows, read_at_text = stored
        print("Lu en cache le %s. `--refresh` pour relire l'entrepôt." % read_at_text)
    else:
        print("Lecture de l'entrepôt — deux ans d'historique, comptez quelques minutes.")
        try:
            rows = warehouse.rows(queries.SALES_HISTORY, label="SALES_HISTORY")
        except Exception as exc:  # noqa: BLE001 — le message importe plus que le type
            print("Échec : %s" % exc, file=sys.stderr)
            return 1
        # Écrit là où l'écran le cherchera : peu importe qui a payé la requête.
        source_module.store_history_rows(rows)

    built = history_module.from_rows(rows)
    print("%d couples marché × canal, de %s à %s."
          % (len(built), built.periods[0] if built.periods else "?", built.latest_period))

    # Le classeur, quand il est là : l'année à date se mesure contre lui et non contre le
    # fait `goals`, qui ne couvre que 57 % du chiffre. Une année comparée à un plan
    # amputé de deux cinquièmes n'est pas une année, c'est une illusion d'optique.
    plan = None
    if settings.has_budget_file:
        from .perf import budget as budget_module

        plan = budget_module.load(settings.budget_path)

    if "--sell-in" in argv:
        return _print_sell_in(plan)

    market = _option(argv, "--market")
    if market:
        return _print_one_market(built, market, plan)
    if "--plans" in argv:
        return _print_unmatched(built)

    ytd = built.ytd(budget=plan)
    if ytd is not None:
        print("")
        print("%s (%s → %s, %d mois), mesurée contre %s :"
              % (ytd.label, ytd.first_period, ytd.last_period, ytd.months,
                 "le classeur de planification" if plan is not None
                 else "le fait `goals` de l'entrepôt"))
        print("  réalisé          %15s" % _eur(ytd.actual))
        print("  budget           %15s" % _eur(ytd.budget))
        print("  écart            %15s  %s" % (
            _eur(ytd.gap),
            # Une fraction dans le modèle, des pourcents à l'écran : la conversion se
            # fait ici, comme dans le gabarit, et jamais dans la propriété.
            "" if ytd.pct is None else "%+.1f %%" % (100.0 * ytd.pct),
        ))
        # Dit à côté du total et non en note de bas de page : c'est la raison pour
        # laquelle ce total est plus petit que la somme brute, et la raison pour
        # laquelle on peut s'y fier.
        print("  couverture       %15s" % (
            "—" if ytd.covered is None else "%.0f %% du vendu" % (100.0 * ytd.covered)))
        print("  sans plan        %15s  (%d cellules, hors total)"
              % (_eur(ytd.unbudgeted_actual), ytd.unbudgeted_lines))
        print("  plan à zéro      %15s  (%d cellules, hors total)"
              % (_eur(ytd.zero_goal_actual), ytd.zero_goal_lines))
        print("  sans vente       %15s  (%d cellules, hors total)"
              % (_eur(ytd.unsold_budget), ytd.unsold_lines))
        # Dit ici et pas en note de bas de page : ce chiffre n'est pas la Maison, c'est
        # la moitié de la Maison que l'entrepôt sait mesurer. Le sell-in n'a pas encore
        # d'historique, donc il n'est ni au réalisé ni au budget de cette ligne.
        print("")
        print("  Sell-out uniquement — les canaux que l'entrepôt mesure. Ce qui est")
        print("  facturé à des partenaires n'a pas encore d'historique ici.")

    # Une seule liste, mesurée contre le classeur. Le fait `goals` de l'entrepôt donnerait
    # deux ans de profondeur au lieu de quelques mois, mais l'entreprise a tranché qu'il
    # n'est pas fiable — et classer l'attention du dirigeant sur des chiffres que personne
    # ne défend coûte plus cher que d'attendre.
    if plan is not None:
        _print_trajectories(built, plan)

    covered = _months_of_plan(built, plan)
    print("")
    if plan is None:
        print("Sans le classeur, aucun plan de référence : rien à recaler.")
        return 0
    if covered < history_module.CHRONIC_WINDOW:
        # Dire pourquoi la liste est vide. « Aucun plan mal calé » et « la question ne
        # peut pas encore être posée » se ressemblent à l'écran et disent le contraire.
        print("Plans à recaler : la question demande douze mois clos couverts par le")
        print("classeur, et il y en a %d. Réponse possible à partir de %s."
              % (covered, _month_plus(built.latest_period,
                                      history_module.CHRONIC_WINDOW - covered)))
        return 0

    chronic = sorted(
        (
            (track, verdict)
            for track, verdict in (
                (t, t.chronic_for(plan)) for t in built.tracks.values()
            )
            if verdict is not None
        ),
        key=lambda pair: pair[1].months,
        reverse=True,
    )
    print("Plans à recaler — sous le plan tous les mois, au même écart :")
    if not chronic:
        print("  aucun.")
    for track, verdict in chronic:
        print("  %-38s %2d mois  ratio %.2f–%.2f  soit %.0f %% trop haut"
              % ("%s %s" % (track.market, track.channel), verdict.months,
                 verdict.low, verdict.high, verdict.shortfall_pct))
    return 0


def _print_sell_in(plan) -> int:
    """Le sell-in confronté à son plan, sans écrire une requête de plus.

    Les deux lectures nécessaires existent déjà : `SELL_IN_HISTORY` donne le dernier
    exercice clos mois par mois, aux taux du plan ; `SELL_IN` donne l'exercice en cours à
    date avec, en face de chaque mois, le même mois de l'an dernier aux mêmes taux. C'est
    cette propriété — les deux côtés énoncés aux mêmes taux — qui rend la réconciliation
    sell-in exacte à vingt-neuf centimes sur 375 M€, et elle se transporte ici telle
    quelle.
    """
    if plan is None:
        print("Classeur de planification absent : rien à confronter.", file=sys.stderr)
        return 2

    from .perf import history as history_module
    from .perf import queries, warehouse

    print("Lecture du sell-in — deux requêtes, quelques dizaines de secondes.")
    try:
        closed = warehouse.rows(queries.SELL_IN_HISTORY, label="SELL_IN_HISTORY")
        current = warehouse.rows(queries.SELL_IN, label="SELL_IN")
    except Exception as exc:  # noqa: BLE001 — le message importe plus que le type
        print("Échec : %s" % exc, file=sys.stderr)
        return 1

    found = history_module.sell_in_trajectories(closed, current, plan)
    print("%d couples marché × canal appariés au plan." % len(found))
    if not found:
        print("Aucun. La jointure se fait sur le code entité du plan : si elle ne prend")
        print("pas, c'est là qu'il faut regarder, pas dans les chiffres.")
        return 0

    flagged = [m for m in found if m.sentence]
    print("")
    if not flagged:
        print("Aucun plan sell-in ne s'écarte du réel de plus de dix points.")
    else:
        print("Plans sell-in qui s'écartent du réel :")
    for moved in sorted(flagged, key=lambda m: -abs(m.plan_growth - m.recent))[:20]:
        print("")
        print("  %s %s" % (moved.market, moved.channel))
        print("    plan année %s · exercice à date %s"
              % (_growth(moved.plan_growth), _growth(moved.recent)))
        for line in _wrapped(moved.sentence, 74):
            print("    %s" % line)

    # Ce que la source ne permet pas de dire, dit une fois plutôt que sous-entendu.
    print("")
    print("Une seule lecture du réel ici : la consolidation publie une comparaison,")
    print("pas une série. Elle dit ce qu'un mois a fait contre le même mois l'an")
    print("dernier, jamais ce que les douze mois d'avant avaient fait.")
    return 0


def _print_trajectories(built, plan) -> None:
    """Ce que le plan demande, confronté à ce que les ventes ont fait.

    C'est la lecture qui n'attend rien. Savoir si un plan est mal calé ne demande pas
    douze mois de plan : il demande douze mois de ventes — qu'on a, et auxquels on se fie
    — et un plan sur les mois à venir. Trié par l'écart entre les deux, parce que
    l'endroit où le plan s'éloigne le plus du réel est l'endroit où quelqu'un devra
    répondre d'un chiffre que personne n'aurait dû signer.
    """
    found = []
    for track in built.tracks.values():
        moved = track.trajectory(plan)
        if moved.sentence:
            found.append(moved)
    if not found:
        print("")
        print("Aucun plan ne s'écarte du réel de plus de dix points de croissance.")
        return

    found.sort(key=lambda m: -abs(m.stretch))
    print("")
    print("Plans qui s'écartent du réel — ce que le plan demande, contre ce que les")
    print("douze derniers mois ont livré. Aucun plan de l'an dernier n'est nécessaire :")
    print("la question se règle sur l'historique des ventes.")
    for moved in found[:20]:
        print("")
        print("  %s %s" % (moved.market, moved.channel))
        print("    plan %s · réel 12 mois %s · 3 derniers mois %s · %s"
              % (_growth(moved.plan_growth), _growth(moved.growth),
                 _growth(moved.recent), _direction(moved.direction)))
        # La phrase et pas seulement les chiffres : quatre pourcentages alignés se lisent
        # comme un tableau, et un tableau ne dit pas ce qu'il faut en faire.
        for line in _wrapped(moved.sentence, 74):
            print("    %s" % line)


DIRECTIONS = {
    "accelerating": "accélère",
    "slowing": "ralentit",
    "steady": "tendance stable",
}


def _direction(word: str) -> str:
    return DIRECTIONS.get(word, "tendance illisible")


def _wrapped(text: str, width: int) -> List[str]:
    """Coupe une phrase à la largeur d'un terminal, sans dépendance."""
    lines, current = [], ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = "%s %s" % (current, word) if current else word
    if current:
        lines.append(current)
    return lines


def _growth(value) -> str:
    return "n/a" if value is None else "%+.0f %%" % (100.0 * value)


def _months_of_plan(built, plan) -> int:
    """Combien de mois clos le classeur couvre, sur la fenêtre de l'historique."""
    if plan is None:
        return 0
    return len({
        month.period
        for track in built.tracks.values()
        for month in track.months
        if month.actual is not None
        and plan.budget_for(track.market, track.channel, month.period)
    })


def _month_plus(period: str, months: int) -> str:
    """'2026-07' + 8 mois -> '2027-03'."""
    try:
        year, month = (int(part) for part in period.split("-"))
    except ValueError:
        return "?"
    total = year * 12 + (month - 1) + months
    return "%04d-%02d" % (total // 12, total % 12 + 1)


def _print_one_market(built, market: str, plan=None) -> int:
    """Un marché, mois par mois. Ce que l'écran ne montre jamais."""
    tracks = [t for t in built.tracks.values() if t.market.lower() == market.lower()]
    if not tracks:
        print("Aucune série pour « %s »." % market, file=sys.stderr)
        return 2
    for track in sorted(tracks, key=lambda t: t.channel):
        print("")
        print("%s %s :" % (track.market, track.channel))
        for month in track.months:
            # Un tiret et non un zéro : « pas de plan » et « plan à zéro » sont deux
            # faits différents, et le second n'existe pas dans ce classeur.
            print("  %s  %15s  %15s  %15s" % (
                month.period,
                _eur(month.actual),
                _eur(month.goal),
                _eur(plan.budget_for(track.market, track.channel, month.period)
                     if plan is not None else None),
            ))
        verdict = track.chronic_for(plan)
        if verdict is not None:
            print("  → %s" % verdict.sentence)
    return 0


def _print_unmatched(built) -> int:
    """Ce que le plan ne couvre pas — avec, cette fois, un dénominateur.

    Un total seul ne dit rien. « 245 M€ de vente chinoise sans objectif » se lit tout
    autrement selon que le marché a des objectifs onze mois sur vingt-quatre ou aucun :
    dans un cas quelqu'un a oublié des mois, dans l'autre le fait `goals` ne couvre pas ce
    marché du tout. La commande imprime donc, pour chaque couple, la part de son chiffre
    qui n'a pas de cible et le nombre de mois concernés.
    """
    rows = []
    total_actual = paired = unbudgeted = zero_goal = 0.0
    without_sales: Dict[str, float] = {}

    for track in built.tracks.values():
        name = "%s %s" % (track.market, track.channel)
        sold = missing = zeroed = 0.0
        months_sold = months_missing = 0
        for month in track.months:
            if month.actual is not None:
                sold += month.actual
                months_sold += 1
            if month.has_goal:
                paired += month.actual
            elif month.is_zero_goal:
                zeroed += month.actual
                months_missing += 1
            elif month.goal is None and month.actual is not None:
                missing += month.actual
                months_missing += 1
            elif month.actual is None and month.goal:
                without_sales[name] = without_sales.get(name, 0.0) + month.goal
        total_actual += sold
        unbudgeted += missing
        zero_goal += zeroed
        if missing or zeroed:
            rows.append((name, missing + zeroed, zeroed, months_missing, months_sold, sold))

    outside = unbudgeted + zero_goal
    print("")
    # Ce rapport porte sur le fait `goals` et sur lui seul : c'est un diagnostic de
    # l'entrepôt, pas une mesure de la performance. L'année à date, elle, se mesure
    # contre le classeur — voir `manage.py history` sans argument.
    print("Couverture du fait `goals` de l'entrepôt sur %d mois :" % len(built.periods))
    print("  vendu au total          %15s" % _eur(total_actual))
    print("  dont couvert par un objectif %10s   %s" % (
        _eur(paired), _share(paired, total_actual)))
    print("  dont aucune ligne d'objectif %10s   %s" % (
        _eur(unbudgeted), _share(unbudgeted, total_actual)))
    # Séparé, parce que ce sont deux conversations : une cible que personne n'a saisie,
    # et une cible que quelqu'un a mise à zéro. La seconde se lit sinon comme un exploit.
    print("  dont objectif à zéro         %10s   %s" % (
        _eur(zero_goal), _share(zero_goal, total_actual)))

    print("")
    print("Vendu sans objectif, du plus gros au plus petit :")
    if not rows:
        print("  rien.")
    for name, amount, zeroed, missing_months, sold_months, sold in sorted(
        rows, key=lambda r: -r[1]
    )[:25]:
        note = "  dont %s à objectif zéro" % _eur(zeroed) if zeroed else ""
        print("  %-34s %14s  %5s de son chiffre  %2d/%2d mois%s"
              % (name, _eur(amount), _share(amount, sold),
                 missing_months, sold_months, note))
    print("  %-34s %14s" % ("total", _eur(outside)))

    print("")
    print("Budgété sans vente en face :")
    if not without_sales:
        print("  rien.")
    for name, amount in sorted(without_sales.items(), key=lambda p: -p[1])[:20]:
        print("  %-34s %14s" % (name, _eur(amount)))
    if without_sales:
        print("  %-34s %14s" % ("total", _eur(sum(without_sales.values()))))
    return 0


def _share(part: float, whole: float) -> str:
    """Un pourcentage, ou un tiret quand il n'y a rien à diviser."""
    if not whole:
        return "—"
    return "%.0f %%" % (100.0 * part / whole)


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
    if command == "history":
        return cmd_history(argv[1:])
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
