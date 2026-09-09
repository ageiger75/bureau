"""Ce qui marche, par produit : catégories, gammes, références.

La maison vend des produits, et le reste de l'écran ne parle que de marchés et de canaux.
Un marché qui recule, c'est des références qui reculent ; une croissance qu'on veut
copier, c'est une gamme qui pousse quelque part. Ce module lit le sell-out à trois
niveaux — la catégorie, la gamme, la référence — sur l'exercice à date contre les mêmes
mois de l'exercice précédent, et rend à chaque niveau ce qui pousse et ce qui recule, en
euros d'écart d'abord : un pourcentage sur une petite ligne n'est pas une conversation.

Trois lectures que le tableau porte sans phrase :

- **l'écart** en euros, ce que la ligne ajoute ou retire à la croissance du niveau ;
- **la part** de la ligne dans les ventes du niveau, pour qu'une gamme qui pousse de
  moitié sur rien ne passe pas avant une gamme qui pousse d'un dixième sur beaucoup ;
- **le dernier mois**, pour voir si ce que l'exercice dit tient encore.

Une référence lancée sur l'exercice n'a pas d'an dernier : elle est nommée à part, jamais
rangée dans « ce qui pousse » avec une croissance infinie. Une référence arrêtée non plus.
Les lignes viennent de la lecture produit de l'entrepôt, jamais d'une requête à
l'ouverture de la page : la règle de toute la maison.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from .analytics import format_eur, format_pct
from .weekly import MONTHS_FR

#: Les trois niveaux, dans l'ordre où ils se lisent, et leurs mots.
LEVELS = ("category", "range", "product")
LEVEL_WORDS = {"category": ("catégorie", "catégories"),
               "range": ("gamme", "gammes"),
               "product": ("référence", "références")}

#: Le périmètre du groupe, tel que la lecture le nomme.
GROUP = "LOEP"

#: L'exercice ouvre en avril.
FISCAL_OPENS = 4

#: Combien de lignes par sens et par niveau, à l'écran.
MOST = 5

#: Sous cette part des ventes du niveau, une ligne qui pousse ou recule est du bruit :
#: elle reste dans le tableau complet, pas dans les cinq de l'écran.
LEAST_SHARE = 0.002

#: Les libellés d'attente du référentiel : une référence créée avant d'être nommée. Ce
#: n'est pas un produit, et le plus fréquent des libellés en serait un sans cette règle.
PLACEHOLDER_PREFIXES = ("AVAILABLE SKU",)

#: Au-delà, les niveaux ne racontent plus la même somme, et la lecture le dit.
LEVELS_AGREE = 0.005


def _fiscal_year(period: str) -> int:
    year, month = int(period[:4]), int(period[5:7])
    return year + 1 if month >= FISCAL_OPENS else year


def _shift(period: str, months: int) -> str:
    year, month = int(period[:4]), int(period[5:7])
    index = year * 12 + (month - 1) + months
    return "%04d-%02d" % (index // 12, index % 12 + 1)


def _growth(now: float, before: Optional[float]) -> Optional[float]:
    if before is None or before <= 0:
        return None
    return now / before - 1.0


def _number(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _mended(name: str) -> str:
    """Un libellé lu en latin-1 puis rendu en UTF-8 porte des « Ã© » à la place des
    accents ; c'est le référentiel qui le porte, et l'écran n'a pas à le répéter."""
    if "Ã" not in name and "Â" not in name:
        return name
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def _key(text) -> str:
    """L'entrepôt écrit les pays en capitales et en sigles — USA, UK —, l'annuaire et le
    plan en toutes lettres : un marché est le même sous toutes ces graphies. La table des
    alias du plan est celle de toute la maison ; une région qui lisait le tiers de ce que
    sa semaine montrait avait perdu son premier marché sur trois lettres."""
    from .budget import normalise_market

    return normalise_market(str(text or "").strip()).casefold()


def month_fr(period: str) -> str:
    try:
        return "%s %s" % (MONTHS_FR[int(period[5:7]) - 1], period[:4])
    except (ValueError, IndexError):
        return period


def months_label(months: Sequence[str]) -> str:
    """« avril à août 2026 », ou « août 2026 » quand l'exercice n'a qu'un mois."""
    if not months:
        return ""
    if len(months) == 1:
        return month_fr(months[0])
    first, last = months[0], months[-1]
    if first[:4] == last[:4]:
        return "%s à %s" % (MONTHS_FR[int(first[5:7]) - 1], month_fr(last))
    return "%s à %s" % (month_fr(first), month_fr(last))


class Line:
    """Une catégorie, une gamme ou une référence : l'exercice, l'an dernier, le mois."""

    __slots__ = ("level", "name", "hero", "sales", "last_year", "month_sales",
                 "month_last_year", "share", "launched", "stopped")

    def __init__(self, level: str, name: str, sales: float, last_year: float,
                 month_sales: float, month_last_year: float, hero: bool = False,
                 launched: bool = False, stopped: bool = False) -> None:
        self.level = level
        self.name = name
        self.hero = hero
        self.sales = sales
        self.last_year = last_year
        self.month_sales = month_sales
        self.month_last_year = month_last_year
        #: La part des ventes du niveau sur l'exercice à date ; posée par le niveau.
        self.share = 0.0
        #: Rien sur ces mois l'an dernier : lancée, ou saisonnière. Ou l'inverse : arrêtée.
        self.launched = launched
        self.stopped = stopped

    @property
    def delta(self) -> float:
        return self.sales - self.last_year

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.sales, self.last_year)

    @property
    def month_delta(self) -> float:
        return self.month_sales - self.month_last_year

    @property
    def month_growth(self) -> Optional[float]:
        return _growth(self.month_sales, self.month_last_year)

    @property
    def growth_label(self) -> str:
        return format_pct(self.growth)

    @property
    def month_label(self) -> str:
        return format_pct(self.month_growth)

    @property
    def delta_label(self) -> str:
        return ("+" if self.delta > 0 else "") + format_eur(self.delta)


class Level:
    """Un niveau — toutes ses lignes, et les cinq qui poussent ou reculent le plus."""

    def __init__(self, level: str, lines: Sequence[Line]) -> None:
        self.level = level
        self.lines = sorted(lines, key=lambda line: -line.sales)
        self.total = sum(line.sales for line in self.lines)
        self.last_year = sum(line.last_year for line in self.lines)
        for line in self.lines:
            line.share = line.sales / self.total if self.total > 0 else 0.0

    @property
    def word(self) -> str:
        return LEVEL_WORDS[self.level][0]

    @property
    def words(self) -> str:
        return LEVEL_WORDS[self.level][1]

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.total, self.last_year)

    @property
    def delta(self) -> float:
        return self.total - self.last_year

    @property
    def established(self) -> List[Line]:
        return [line for line in self.lines if not line.launched and not line.stopped
                and line.share >= LEAST_SHARE]

    @property
    def growing(self) -> List[Line]:
        return sorted([line for line in self.established if line.delta > 0],
                      key=lambda line: -line.delta)[:MOST]

    @property
    def falling(self) -> List[Line]:
        return sorted([line for line in self.established if line.delta < 0],
                      key=lambda line: line.delta)[:MOST]

    @property
    def launched(self) -> List[Line]:
        return sorted([line for line in self.lines if line.launched],
                      key=lambda line: -line.sales)

    @property
    def stopped(self) -> List[Line]:
        return sorted([line for line in self.lines if line.stopped],
                      key=lambda line: -line.last_year)

    @property
    def launched_shown(self) -> List[Line]:
        """Les lancements qui pèsent : sous la part de bruit, ils se comptent sans se nommer."""
        return [line for line in self.launched if line.share >= LEAST_SHARE]

    @property
    def stopped_shown(self) -> List[Line]:
        return [line for line in self.stopped
                if self.last_year > 0 and line.last_year / self.last_year >= LEAST_SHARE]

    @property
    def concentration(self) -> Optional[float]:
        """La part de tout ce qui pousse que les cinq premières lignes portent."""
        positive = sum(line.delta for line in self.lines if line.delta > 0 and not line.launched)
        if positive <= 0:
            return None
        return sum(line.delta for line in self.growing) / positive

    @property
    def title(self) -> str:
        """« Gammes · 12, +4.2 % sur l'exercice »."""
        head = "%s · %d" % (self.words[0].upper() + self.words[1:], len(self.lines))
        if self.growth is not None:
            head += ", %s sur l'exercice" % format_pct(self.growth)
        return head

    @property
    def sentence(self) -> str:
        """Ce que le niveau dit en une ligne, sans les nombres du tableau."""
        parts = []
        growing = self.growing
        # « 4 catégories portent 100 % de ce qui pousse » quand quatre poussent : vrai, et
        # vide. La concentration ne se dit que lorsqu'elle sépare quelque chose.
        if growing and self.concentration is not None and self.concentration < 0.99:
            parts.append("%d %s portent %.0f %% de ce qui pousse" % (
                len(growing), self.words if len(growing) > 1 else self.word,
                self.concentration * 100))
        below = [line for line in self.lines if line.delta < 0 and not line.stopped]
        if below:
            parts.append("%s de recul sur %d %s" % (
                format_eur(sum(line.delta for line in below)), len(below),
                self.words if len(below) > 1 else self.word))
        # Un lancement ou un arrêt qui, tous ensemble, ne pèsent pas la part de bruit ne
        # valent pas une phrase : un arrêt de quelques euros n'est pas un fait de commerce.
        launched = sum(line.sales for line in self.launched)
        if self.launched and self.total > 0 and launched / self.total >= LEAST_SHARE:
            parts.append("%d sans an dernier, %s" % (len(self.launched), format_eur(launched)))
        stopped = sum(line.last_year for line in self.stopped)
        if self.stopped and self.last_year > 0 and stopped / self.last_year >= LEAST_SHARE:
            parts.append("%d arrêtée%s, %s l'an dernier" % (
                len(self.stopped), "s" if len(self.stopped) > 1 else "", format_eur(stopped)))
        return " · ".join(parts)


class Review:
    """Un périmètre, ses niveaux, et ce qui manque pour le lire."""

    def __init__(self, scope: str = GROUP, period: str = "", months: Sequence[str] = (),
                 levels: Sequence[Level] = (), absent: Sequence[str] = ()) -> None:
        self.scope = scope
        self.period = period
        self.months = list(months)
        self.levels = list(levels)
        self.absent = list(absent)

    @property
    def usable(self) -> bool:
        return bool(self.levels)

    def level(self, name: str) -> Optional[Level]:
        for level in self.levels:
            if level.level == name:
                return level
        return None

    @property
    def basis(self) -> str:
        return ("sell-out %s, exercice à date, contre les mêmes mois de l'exercice précédent · "
                "hors vrac et hors gratuits · l'écart est ce que la ligne ajoute ou retire "
                "à la croissance" % months_label(self.months))

    @property
    def headline(self) -> str:
        """Le niveau le plus fin qui se lit, en une phrase, avec la croissance du tout."""
        if not self.levels:
            return ""
        top = self.levels[0]
        head = "Sur l'exercice à date, les ventes font %s (%s contre l'an dernier)" % (
            format_eur(top.total), format_pct(top.growth))
        return head + "."

    question = ("Ce qui pousse : tiré par la demande, ou poussé par un lancement et une "
                "promotion qui ne se répéteront pas ? Ce qui recule : la rupture, le prix, "
                "ou la place en rayon ?")


def aggregate(rows: Iterable[dict], markets: Sequence[str], scope: str) -> List[dict]:
    """Les lignes d'un périmètre : la somme, mois par mois, des catégories et des gammes de
    ses marchés. Les références ne sont lues qu'au groupe, donc elles n'y sont pas."""
    wanted = {_key(market) for market in markets}
    summed: Dict[tuple, float] = {}
    heroes: Dict[tuple, bool] = {}
    for row in rows:
        if _key(row.get("scope")) not in wanted:
            continue
        level = str(row.get("level") or "").strip().lower()
        if level == "product" or level not in LEVELS:
            continue
        key = (level, str(row.get("name") or "").strip(), str(row.get("period") or "")[:7])
        summed[key] = summed.get(key, 0.0) + _number(row.get("net_sales"))
        if str(row.get("is_hero") or "").strip().lower() in ("1", "true", "yes", "oui"):
            heroes[key] = True
    return [{"scope": scope, "level": level, "name": name, "period": period,
             "net_sales": value, "is_hero": 1 if heroes.get((level, name, period)) else 0}
            for (level, name, period), value in summed.items()]


def for_markets(rows: Iterable[dict], markets: Sequence[str], scope: str, note: str = "") -> Review:
    """La lecture d'un périmètre, sur la somme de ses marchés."""
    rows = list(rows or [])
    review = build(aggregate(rows, markets, scope), scope, note=note)
    if review.usable:
        review.absent = [reason for reason in review.absent if "niveau du groupe" not in reason]
        review.absent.append("les références ne sont lues qu'au niveau du groupe ; ici, les "
                             "catégories et les gammes de %s" % ", ".join(markets))
    return review


#: Sous cette part, la lecture produit ne couvre pas les ventes que la lecture des KPI
#: rapporte pour le même périmètre et le même mois : des lignes sans produit au
#: référentiel, ou un pays écrit autrement. Le bloc le dit avant d'être lu comme un tout.
COVERED = 0.9

#: Les clés de la lecture des KPI qui portent les ventes du mois, la plus proche d'abord :
#: hors vrac comme la lecture produit, sinon toutes.
SALES_KEYS = ("net_sales_hors_bulk", "net_sales")


def coverage(rows: Iterable[dict], kpi_rows: Sequence, scopes_wanted: Sequence[str],
             period: str) -> List[tuple]:
    """Par périmètre lu : (nom, ventes par produit, ventes des KPI, part couverte) sur un
    mois, ou rien quand l'une des deux lectures manque."""
    rows = list(rows or [])
    # Les ventes du mois de la lecture des KPI, par périmètre replié et par clé : les
    # lignes viennent en dictionnaires (l'entrepôt) ou en séquences (le cache, les tests).
    sales: Dict[tuple, float] = {}
    for row in kpi_rows or []:
        if isinstance(row, dict):
            lowered = {str(name).lower(): value for name, value in row.items()}
            row_scope, key, when, value = (lowered.get("scope"), lowered.get("kpi_key"),
                                           lowered.get("period"), lowered.get("value"))
        elif len(row) >= 4:
            row_scope, key, when, value = row[0], row[1], row[2], row[3]
        else:
            continue
        key = str(key or "").strip()
        if key in SALES_KEYS and str(when or "")[:7] == period and value is not None:
            try:
                sales[(_key(row_scope), key)] = float(value)
            except (TypeError, ValueError):
                continue
    found: List[tuple] = []
    for scope in scopes_wanted:
        by_product = sum(_number(row.get("net_sales")) for row in rows
                         if _key(row.get("scope")) == _key(scope)
                         and str(row.get("level") or "").strip().lower() == "category"
                         and str(row.get("period") or "")[:7] == period)
        by_kpi = next((sales[(_key(scope), key)] for key in SALES_KEYS
                       if (_key(scope), key) in sales), None)
        if by_kpi is None or by_kpi <= 0:
            continue
        found.append((scope, by_product, by_kpi, by_product / by_kpi))
    return found


def check_coverage(review: Review, rows: Iterable[dict], kpi_rows: Sequence,
                   scopes_wanted: Sequence[str]) -> Review:
    """Ajoute à la lecture ce qu'elle ne couvre pas, marché par marché, quand la lecture
    des KPI en sait plus qu'elle sur le même mois."""
    if not review.usable or not review.period:
        return review
    short = [(scope, share) for scope, _, _, share in
             coverage(rows, kpi_rows, scopes_wanted, review.period) if share < COVERED]
    if short:
        review.absent.append(
            "la lecture produit ne couvre qu'une partie des ventes lues par ailleurs sur %s : %s "
            "— des lignes sans produit au référentiel, à vérifier avant de lire ce bloc comme "
            "un tout" % (month_fr(review.period),
                         ", ".join("%s %.0f %%" % (scope, share * 100) for scope, share in short)))
    return review


def scopes(rows: Iterable[dict]) -> List[str]:
    """Les périmètres lus, le groupe d'abord."""
    seen: Dict[str, str] = {}
    for row in rows:
        name = str(row.get("scope") or "").strip()
        if name:
            seen.setdefault(_key(name), name)
    found = sorted(seen.values())
    group = next((name for name in found if _key(name) == _key(GROUP)), None)
    if group is not None:
        found.remove(group)
        found.insert(0, group)
    return found


def _read(rows: Iterable[dict], scope: str) -> Dict[str, Dict[str, dict]]:
    """level → name → {period → sales, hero}."""
    read: Dict[str, Dict[str, dict]] = {}
    wanted = _key(scope)
    for row in rows:
        if _key(row.get("scope")) != wanted:
            continue
        level = str(row.get("level") or "").strip().lower()
        if level not in LEVELS:
            continue
        period = str(row.get("period") or "")[:7]
        if len(period) != 7:
            continue
        name = _mended(str(row.get("name") or "").strip()) or "(sans nom)"
        if name.upper().startswith(PLACEHOLDER_PREFIXES):
            continue
        entry = read.setdefault(level, {}).setdefault(name, {"periods": {}, "hero": False})
        entry["periods"][period] = entry["periods"].get(period, 0.0) + _number(row.get("net_sales"))
        if str(row.get("is_hero") or "").strip().lower() in ("1", "true", "yes", "oui"):
            entry["hero"] = True
    return read


def build(rows: Iterable[dict], scope: str = GROUP, note: str = "") -> Review:
    """Les trois niveaux d'un périmètre, sur ce que la lecture produit a rapporté."""
    rows = list(rows or [])
    absent: List[str] = []
    if note:
        absent.append(note)
    read = _read(rows, scope)
    if not read:
        if not note:
            absent.append("aucune vente par produit lue pour %s" % scope)
        return Review(scope, absent=absent)
    periods = sorted({period for entries in read.values() for entry in entries.values()
                      for period in entry["periods"]})
    anchor = periods[-1]
    opens = "%04d-%02d" % (_fiscal_year(anchor) - 1, FISCAL_OPENS)
    year = [period for period in periods if opens <= period <= anchor]
    present = set(periods)
    months = [period for period in year if _shift(period, -12) in present]
    if not months:
        absent.append("l'an dernier n'est pas dans la lecture : rien à comparer sur %s"
                      % months_label(year))
        return Review(scope, anchor, year, absent=absent)
    if len(months) < len(year):
        absent.append("l'exercice est comparé sur %s seulement, faute d'an dernier avant"
                      % months_label(months))
    before = [_shift(period, -12) for period in months]
    levels: List[Level] = []
    for level in LEVELS:
        entries = read.get(level)
        if not entries:
            continue
        lines = []
        for name, entry in entries.items():
            series = entry["periods"]
            sales = sum(series.get(period, 0.0) for period in months)
            last_year = sum(series.get(period, 0.0) for period in before)
            if sales <= 0 and last_year <= 0:
                continue
            # Sans an dernier sur ces mois, une croissance n'existe pas : la ligne est
            # nommée à part, qu'elle soit neuve ou saisonnière, jamais classée en tête de
            # « ce qui pousse » avec un pourcentage infini.
            lines.append(Line(level, name, sales, last_year,
                              series.get(anchor, 0.0), series.get(_shift(anchor, -12), 0.0),
                              hero=entry["hero"],
                              launched=last_year <= 0 < sales,
                              stopped=sales <= 0 < last_year))
        if lines:
            levels.append(Level(level, lines))
    totals = [level.total for level in levels if level.total > 0]
    if len(totals) > 1 and (max(totals) - min(totals)) > LEVELS_AGREE * max(totals):
        absent.append("les niveaux ne s'accordent pas sur l'exercice à date : %s — une "
                      "lecture incomplète, ou des libellés écartés qui pèsent"
                      % ", ".join("%s %s" % (level.words, format_eur(level.total))
                                  for level in levels))
    missing = [LEVEL_WORDS[level][1] for level in LEVELS if level not in read]
    if missing and scope != GROUP:
        absent.append("les %s ne sont lues qu'au niveau du groupe" % " et ".join(missing))
    elif missing:
        absent.append("la lecture ne porte pas les %s" % " ni les ".join(missing))
    return Review(scope, anchor, months, levels, absent)
