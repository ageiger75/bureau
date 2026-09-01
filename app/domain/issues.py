"""L'identité d'un sujet de management, et rien d'autre encore.

Le brief V6.1 §C1 fixe l'ordre de construction sans ambiguïté : l'identité persistante se
construit **avant** le moteur de sélection, parce qu'un top 3 sans identité serait une
amnésie hebdomadaire. Le cockpit trouverait chaque lundi les mêmes trois marchés, les
présenterait comme des découvertes, et le lecteur passerait l'année à redécouvrir ce qu'il
sait déjà. Ce module ne sélectionne donc rien et n'ordonne rien. Il répond à une seule
question, posée à chaque nouvelle preuve : **est-ce que je connais déjà ce sujet ?**

Quatre règles gouvernent le fichier, et chacune vient d'un défaut que le brief nomme.

**Un sujet est une conversation, pas un pays.** Le brief §C7 l'écrit contre l'évidence :
l'unité d'un sujet est la décision qu'il appelle, pas la géographie où on l'a vu. Un même
produit dégradé sur vingt-six marchés est *un* sujet — celui du responsable de l'offre —
et non vingt-six alertes. Un sujet couvre donc un ensemble de clés d'observation, et cet
ensemble grandit quand la même conversation se manifeste ailleurs.

**Une preuve nouvelle rejoint un sujet ouvert, elle n'en crée pas un second.** C'est la
règle « aucun issue_id recréé pour un sujet déjà ouvert » (§C9). Sans elle, chaque lecture
fabrique un doublon, les deux vieillissent séparément, et l'engagement pris sur l'un ne
solde jamais l'autre.

**Un sujet clos ne se rouvre pas en silence.** Une observation qui retombe sur un sujet
clos ouvre un nouveau sujet, qui *déclare* celui qu'il suit. Faire l'inverse — rouvrir
l'ancien — effacerait sa clôture, son motif et sa dernière preuve, que le brief exige de
conserver. Et le lien explicite rend calculable un critère de matérialité que le §C8
réclame : la répétition d'un problème déjà signalé.

**Un statut unique est refusé.** Le brief §C2 impose trois dimensions — tendance métier,
progrès de résolution, confiance — et le refus est structurel ici : il n'existe aucune
propriété qui rende « l'état » d'un sujet en un mot. Un mot unique force le lecteur à
deviner lequel des trois il regarde, et il devine mal : un sujet qui empire tout en étant
bien traité n'est ni « rouge » ni « vert ».

Module sans dépendance ORM ni HTTP, comme le reste du domaine : les règles se testent
seules, et la persistance viendra les envelopper sans les changer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- rôles CEO

#: Ce que le sujet demande au CEO (brief §C3). Le rôle n'est pas une priorité : il dit la
#: nature de l'intervention, et c'est le moteur de sélection — pas ce module — qui décidera
#: lesquels occupent les trois créneaux d'attention.
DECIDE = "DECIDE"
CHALLENGE = "CHALLENGE"
ALIGN = "ALIGN"
DELEGATE = "DELEGATE"
MONITOR = "MONITOR"

ROLES: Tuple[str, ...] = (DECIDE, CHALLENGE, ALIGN, DELEGATE, MONITOR)

#: Les seuls rôles qu'un créneau d'attention accepte (§C3). `DELEGATE` n'y figure que tant
#: que la délégation n'est pas actée, ce qui est un état du sujet et non une propriété du
#: rôle : la règle vit donc dans le moteur, et cette constante ne dit que le socle.
ATTENTION_ROLES: Tuple[str, ...] = (DECIDE, CHALLENGE, ALIGN)

# ------------------------------------------------------------------------- trois états

#: Tendance métier : où va le chiffre.
IMPROVING = "improving"
STABLE = "stable"
WORSENING = "worsening"
TRENDS: Tuple[str, ...] = (IMPROVING, STABLE, WORSENING)

#: Progrès de résolution : où va le traitement. Indépendant de la tendance — un sujet peut
#: empirer alors que son traitement avance, et c'est même le cas ordinaire au début.
ON_TRACK = "on_track"
AT_RISK = "at_risk"
BLOCKED = "blocked"
PROGRESS: Tuple[str, ...] = (ON_TRACK, AT_RISK, BLOCKED)

#: Confiance dans ce qu'on affirme. Reprend l'échelle du registre de provenance plutôt
#: qu'une seconde échelle parallèle : deux vocabulaires pour la même idée, c'est un sujet
#: « établi » sur un écran et « bêta » sur l'autre.
ESTABLISHED = "established"
PROBABLE = "probable"
UNCERTAIN = "uncertain"
UNAVAILABLE = "unavailable"
CONFIDENCES: Tuple[str, ...] = (ESTABLISHED, PROBABLE, UNCERTAIN, UNAVAILABLE)

# ---------------------------------------------------------------------- cycle de vie

#: Le sujet est né d'une observation et n'a pas encore été porté au CEO.
DETECTED = "detected"
#: Le sujet occupe un créneau d'attention.
IN_ATTENTION = "in_attention"
#: Le sujet est suivi sans occuper de créneau — délégué dans les temps, ou simple veille.
WATCHED = "watched"
#: Une décision a été prise de ne rien faire. Le sujet dort jusqu'à un fait nouveau ou sa
#: date de réexamen (§C1).
VARIANCE_ACCEPTED = "variance_accepted"
#: Le chiffre est revenu dans la zone attendue. Constatable par la machine.
NORMALIZED = "normalized"
#: Cause, action et résultat suffisamment établis. Jamais prononcé par la machine (§C9).
CLOSED = "closed"

STATUSES: Tuple[str, ...] = (DETECTED, IN_ATTENTION, WATCHED, VARIANCE_ACCEPTED,
                             NORMALIZED, CLOSED)

#: Les états dans lesquels un sujet accueille encore des preuves sous son identité. Un
#: sujet clos n'en fait pas partie : ce qui arrive après sa clôture appartient à un autre
#: sujet, qui le déclare.
OPEN_STATUSES: Tuple[str, ...] = (DETECTED, IN_ATTENTION, WATCHED, VARIANCE_ACCEPTED,
                                  NORMALIZED)

#: Transitions permises. Le retour en arrière est autorisé partout où il correspond à
#: quelque chose de réel : un sujet sorti de l'attention y revient si la promesse n'est pas
#: tenue, et un chiffre normalisé peut se dégrader de nouveau avant toute clôture.
ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    DETECTED: (IN_ATTENTION, WATCHED, VARIANCE_ACCEPTED),
    IN_ATTENTION: (WATCHED, VARIANCE_ACCEPTED, NORMALIZED, CLOSED),
    WATCHED: (IN_ATTENTION, VARIANCE_ACCEPTED, NORMALIZED, CLOSED),
    VARIANCE_ACCEPTED: (IN_ATTENTION, WATCHED, NORMALIZED, CLOSED),
    NORMALIZED: (IN_ATTENTION, WATCHED, CLOSED),
    CLOSED: (),
}

#: La clôture managériale est humaine (§C9). La machine peut désescalader et constater la
#: normalisation ; elle ne conclut pas qu'un sujet est réglé.
MACHINE_STATUSES: Tuple[str, ...] = (DETECTED, IN_ATTENTION, WATCHED, NORMALIZED)


class TransitionRefused(ValueError):
    """Transition d'état illégale. Message destiné à être affiché."""


class ClosureRefused(ValueError):
    """Une clôture prononcée sans décideur humain."""


# ------------------------------------------------------------------------- observations


@dataclass(frozen=True)
class Observation:
    """Un fait mesuré, avant qu'on sache à quel sujet il appartient.

    `key` est ce qui décide de l'identité. Elle nomme **ce qui est observé et où**, dans
    cet ordre : `("gap_to_plan", "Brazil")`, `("divergence", "India")`, `("commitment",
    "c-118")`. Le couple est délibérément grossier — deux mesures différentes sur le même
    marché ne sont pas le même sujet, et la même mesure sur deux marchés peut l'être, ce
    que `Issue.covers` autorise.
    """

    kind: str
    scope: str
    seen_at: str
    #: Ce que la preuve dit, en une phrase affichable.
    statement: str = ""
    #: L'ordre de grandeur en jeu. Sert la matérialité, jamais l'identité.
    amount: Optional[float] = None
    confidence: str = ESTABLISHED
    #: D'où vient le fait — une clé du registre de provenance, pas une phrase.
    measure: str = ""

    @property
    def key(self) -> Tuple[str, str]:
        return (self.kind, self.scope)


@dataclass(frozen=True)
class Reading:
    """Une conclusion portée sur un sujet, et ce qui l'a fait changer.

    Le brief §C1 appelle ça la mémoire d'interprétation, et il en donne la raison en une
    parenthèse qui vaut tout le reste : « une correction de mapping n'efface pas le
    diagnostic opérationnel antérieur ». Un cockpit qui remplace sa conclusion sans garder
    la précédente fait disparaître le fait qu'il s'est trompé, et avec lui la seule trace
    qui permettait de savoir à quel point le croire.
    """

    conclusion: str
    at: str
    #: Vide pour la première lecture. Obligatoire ensuite — voir `Issue.reinterpret`.
    because: str = ""


@dataclass(frozen=True)
class Arbitration:
    """La décision de ne rien faire, tracée comme une décision (§C1).

    Le brief insiste sur ce point parce que l'inverse est le comportement par défaut de
    toutes les revues : un sujet qu'on a regardé et laissé passer disparaît sans trace, et
    resurgit le mois suivant comme s'il était neuf. Ici il porte un décideur, une date, une
    raison en une ligne, et une date de réexamen facultative.
    """

    decided_by: str
    at: str
    reason: str
    review_on: Optional[str] = None


# ------------------------------------------------------------------------------- sujet


@dataclass
class Issue:
    """Un sujet de management, et sa mémoire.

    Mutable, à la différence du reste du domaine : c'est précisément l'objet dont on veut
    qu'il traverse les lectures. Un sujet figé serait recréé à chaque cycle, ce qui est le
    défaut que ce module existe pour empêcher.

    Les champs sont progressifs (§C1) : rien n'est exigé à la détection au-delà d'une
    identité et d'une preuve. Ce qui manque manque, et se voit.
    """

    issue_id: str
    title: str
    #: Les clés d'observation que ce sujet couvre. Un sujet peut en couvrir plusieurs —
    #: c'est ainsi qu'un produit dégradé sur vingt-six marchés reste un seul sujet.
    covers: List[Tuple[str, str]] = field(default_factory=list)
    evidence: List[Observation] = field(default_factory=list)
    readings: List[Reading] = field(default_factory=list)
    status: str = DETECTED
    role: str = MONITOR
    #: Le responsable du sujet. Le brief §C1 n'autorise que deux niveaux d'owner : celui-ci
    #: et l'owner de chaque engagement. Les owners de KPI et de prévision vivent dans leurs
    #: propres objets, et les ramener ici en ferait un troisième niveau qui n'existe pas.
    accountable: str = ""
    #: Vrai dès que le rôle a été posé — par la règle qui a ouvert le sujet, ou par un
    #: humain. Sans ce drapeau, « MONITOR » ne se distingue pas de « pas encore qualifié »,
    #: et une règle requalifierait chaque semaine un sujet que quelqu'un avait tranché.
    role_set: bool = False
    arbitration: Optional[Arbitration] = None
    #: Le sujet clos dont celui-ci est la réapparition, quand il y en a un.
    follows: str = ""
    #: Le sujet dans lequel celui-ci a été versé, quand il l'a été. Distinct de `follows`,
    #: qui pointe vers le passé : confondre les deux ferait d'une fusion une rechute.
    merged_into: str = ""
    closed_reason: str = ""

    trend: str = STABLE
    progress: str = ON_TRACK
    confidence: str = ESTABLISHED

    # ------------------------------------------------------------------ identité

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def owns(self, key: Tuple[str, str]) -> bool:
        return key in self.covers

    def record(self, observation: "Observation") -> None:
        """Rattacher une preuve, et étendre la couverture si elle vient d'ailleurs.

        Refusé sur un sujet clos : ce qui arrive après la clôture appartient à un autre
        sujet. Voir `Register.observe`, qui en ouvre un et le relie.
        """
        if not self.is_open:
            raise TransitionRefused(
                "Sujet %s clos : une preuve nouvelle ouvre un sujet qui le suit, elle "
                "n'efface pas sa clôture." % self.issue_id)
        self.evidence.append(observation)
        if observation.key not in self.covers:
            self.covers.append(observation.key)
        # La confiance d'un sujet est celle de sa preuve la plus faible. Prendre la plus
        # forte ferait passer pour établi un sujet dont la moitié des faits sont incertains,
        # ce qui est exactement l'inverse du service rendu.
        if CONFIDENCES.index(observation.confidence) > CONFIDENCES.index(self.confidence):
            self.confidence = observation.confidence

    @property
    def last_seen(self) -> str:
        return self.evidence[-1].seen_at if self.evidence else ""

    @property
    def scopes(self) -> List[str]:
        """Les périmètres où ce sujet se manifeste, sans doublon et dans l'ordre vu."""
        seen: List[str] = []
        for _kind, scope in self.covers:
            if scope not in seen:
                seen.append(scope)
        return seen

    # -------------------------------------------------------------------- lecture

    @property
    def conclusion(self) -> str:
        return self.readings[-1].conclusion if self.readings else ""

    @property
    def previous_conclusion(self) -> str:
        return self.readings[-2].conclusion if len(self.readings) > 1 else ""

    def reinterpret(self, conclusion: str, at: str, because: str = "") -> None:
        """Poser une conclusion. Toute conclusion qui en remplace une autre dit pourquoi.

        Le motif n'est pas décoratif : sans lui, la conclusion précédente reste visible
        mais inexplicable, et le lecteur ne peut pas distinguer une correction de mapping
        d'un retournement du métier. Ce sont deux nouvelles opposées.
        """
        if self.readings and not because.strip():
            raise ValueError(
                "Changer la conclusion d'un sujet exige d'en dire la raison : sans elle, "
                "le lecteur ne peut pas distinguer une correction de donnée d'un "
                "retournement du métier.")
        self.readings.append(Reading(conclusion=conclusion, at=at, because=because))

    # ------------------------------------------------------------------ transitions

    def move_to(self, status: str, by: str = "") -> None:
        """Changer d'état, ou refuser en disant ce qui manque.

        `by` nomme qui prononce le changement. Il n'est exigé que pour la clôture, et il
        l'est vraiment : la machine peut désescalader un sujet et constater que le chiffre
        est rentré dans sa zone, elle ne peut pas conclure qu'il est réglé.
        """
        if status not in STATUSES:
            raise TransitionRefused("État inconnu : %s." % status)
        allowed = ALLOWED_TRANSITIONS.get(self.status, ())
        if status not in allowed:
            raise TransitionRefused(
                "Un sujet %s ne passe pas à %s. Transitions permises : %s."
                % (self.status, status, ", ".join(allowed) or "aucune"))
        if status == CLOSED and not by.strip():
            raise ClosureRefused(
                "La clôture d'un sujet est managériale : elle porte un nom. La machine "
                "désescalade et constate la normalisation, elle ne conclut pas.")
        self.status = status

    def accept_variance(self, arbitration: "Arbitration") -> None:
        """Arbitrer qu'on ne fait rien, et le tracer.

        Le sujet ne remonte plus tant qu'aucun fait nouveau n'arrive et que sa date de
        réexamen n'est pas atteinte — c'est `Register.due_for_review` qui le réveille.
        """
        if not arbitration.decided_by.strip():
            raise ValueError("Une variance acceptée porte le nom de qui l'a acceptée.")
        if not arbitration.reason.strip():
            raise ValueError(
                "Une variance acceptée porte sa raison en une ligne : sans elle, le sujet "
                "reviendra et personne ne saura pourquoi il avait été écarté.")
        self.move_to(VARIANCE_ACCEPTED)
        self.arbitration = arbitration

    def close(self, by: str, reason: str) -> None:
        if not reason.strip():
            raise ClosureRefused("Une clôture conserve son motif (brief §C9).")
        self.move_to(CLOSED, by=by)
        self.closed_reason = reason


# ---------------------------------------------------------------------------- registre


def _next_id(existing: Sequence[str]) -> str:
    """Un identifiant lisible et stable, jamais réattribué.

    Numéroté sur le plus grand déjà émis et non sur le nombre de sujets vivants : après une
    clôture, compter les vivants redonnerait un numéro déjà porté, et deux sujets partageant
    un identifiant sont pires que deux sujets sans identifiant du tout.
    """
    highest = 0
    for value in existing:
        _prefix, _sep, number = value.partition("-")
        if number.isdigit():
            highest = max(highest, int(number))
    return "ISS-%03d" % (highest + 1)


class Register:
    """Tous les sujets connus, et la règle qui décide si une preuve en crée un.

    C'est le cœur de la mémoire. Le reste du module décrit un sujet ; cette classe répond
    à la seule question que pose une lecture hebdomadaire : ce que je viens de mesurer,
    est-ce que je le connais déjà ?
    """

    __slots__ = ("issues",)

    def __init__(self, issues: Optional[Sequence["Issue"]] = None) -> None:
        self.issues: List[Issue] = list(issues or ())

    def __len__(self) -> int:
        return len(self.issues)

    # ---------------------------------------------------------------- consultation

    def of(self, issue_id: str) -> Optional["Issue"]:
        for issue in self.issues:
            if issue.issue_id == issue_id:
                return issue
        return None

    def open_issues(self) -> List["Issue"]:
        return [issue for issue in self.issues if issue.is_open]

    def holding(self, key: Tuple[str, str]) -> Optional["Issue"]:
        """Le sujet **ouvert** qui couvre déjà cette clé, s'il existe.

        Le premier trouvé, et non le meilleur : deux sujets ouverts couvrant la même clé
        est une faute que `merge` répare, pas une ambiguïté qu'on arbitre à chaque lecture.
        """
        for issue in self.issues:
            if issue.is_open and issue.owns(key):
                return issue
        return None

    def closed_holding(self, key: Tuple[str, str]) -> Optional["Issue"]:
        """Le sujet clos le plus récent qui couvrait cette clé."""
        found: Optional[Issue] = None
        for issue in self.issues:
            if issue.status == CLOSED and issue.owns(key):
                found = issue
        return found

    # --------------------------------------------------------------------- écriture

    def observe(self, observation: "Observation", title: str = "") -> "Issue":
        """Ranger une preuve : dans le sujet qui la porte déjà, ou dans un sujet neuf.

        Trois cas, et le troisième est celui qui fait la mémoire.

        Un sujet ouvert couvre déjà la clé : la preuve le rejoint, aucun identifiant n'est
        émis. C'est la règle « aucun issue_id recréé pour un sujet déjà ouvert ».

        Aucun sujet ne la couvre : un sujet naît.

        Un sujet **clos** la couvrait : un sujet naît quand même, et déclare celui qu'il
        suit. Rouvrir l'ancien effacerait sa clôture et son motif ; ne rien lier ferait
        d'une rechute une découverte. Le lien est ce qui rend la répétition calculable —
        un critère de matérialité que le brief réclame et qu'aucune donnée ne porte.
        """
        held = self.holding(observation.key)
        if held is not None:
            held.record(observation)
            return held

        previous = self.closed_holding(observation.key)
        issue = Issue(
            issue_id=_next_id([i.issue_id for i in self.issues]),
            title=title or observation.statement or "%s · %s" % observation.key,
            follows=previous.issue_id if previous is not None else "",
        )
        issue.record(observation)
        self.issues.append(issue)
        return issue

    def attach(self, issue_id: str, observation: "Observation") -> "Issue":
        """Rattacher une preuve à un sujet nommé, en étendant sa couverture.

        Le geste par lequel un sujet devient transversal : la même mesure vue sur un
        deuxième marché rejoint la conversation qu'elle prolonge au lieu d'en ouvrir une
        parallèle. Il est explicite parce qu'il est un jugement — la machine ne devine pas
        que deux marchés relèvent de la même décision.
        """
        issue = self.of(issue_id)
        if issue is None:
            raise KeyError("Aucun sujet %s." % issue_id)
        holder = self.holding(observation.key)
        if holder is not None and holder is not issue:
            raise TransitionRefused(
                "La clé %s appartient déjà au sujet ouvert %s. Fusionner les deux sujets "
                "plutôt que de partager une clé entre eux."
                % (str(observation.key), holder.issue_id))
        issue.record(observation)
        return issue

    def merge(self, keep_id: str, absorb_id: str, because: str) -> "Issue":
        """Réunir deux sujets ouverts qui étaient la même conversation.

        Le sujet absorbé est clos avec son motif et garde son identifiant : il a pu être
        cité dans un compte rendu, et un identifiant qui disparaît transforme une trace en
        énigme. Sa couverture et ses preuves passent au sujet conservé, chronologiquement,
        pour que l'histoire relue ait le bon ordre.
        """
        keep, absorb = self.of(keep_id), self.of(absorb_id)
        if keep is None or absorb is None:
            raise KeyError("Sujet inconnu : %s." % (keep_id if keep is None else absorb_id))
        if keep is absorb:
            raise ValueError("Un sujet ne se fusionne pas avec lui-même.")
        if not because.strip():
            raise ValueError("Une fusion porte sa raison : deux sujets réunis sans motif "
                             "sont indistinguables d'un doublon jamais vu.")
        for observation in absorb.evidence:
            keep.evidence.append(observation)
            if observation.key not in keep.covers:
                keep.covers.append(observation.key)
        keep.evidence.sort(key=lambda o: o.seen_at)
        absorb.status = CLOSED
        absorb.closed_reason = because
        absorb.merged_into = keep.issue_id
        return keep

    # ------------------------------------------------------------------- réveil

    def due_for_review(self, today: str) -> List["Issue"]:
        """Les variances acceptées dont la date de réexamen est atteinte.

        Sans ce réveil, « on accepte l'écart et on revoit en janvier » est une phrase qui
        ne se produit jamais : personne ne tient la liste, et le sujet ne revient que si
        quelqu'un s'en souvient.
        """
        due: List[Issue] = []
        for issue in self.issues:
            if issue.status != VARIANCE_ACCEPTED or issue.arbitration is None:
                continue
            when = issue.arbitration.review_on
            if when and when <= today:
                due.append(issue)
        return due

    def repeated(self) -> List["Issue"]:
        """Les sujets qui sont la réapparition d'un sujet clos.

        La matérialité au-delà des euros (§C8) compte la répétition d'un problème déjà
        signalé. Elle ne se lit dans aucune donnée : elle se lit ici, ou nulle part.
        """
        return [issue for issue in self.issues if issue.follows and issue.is_open]
