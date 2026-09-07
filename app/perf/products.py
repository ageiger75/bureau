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
        #: Pas d'an dernier du tout : lancée sur l'exercice. Ou l'inverse : arrêtée.
        self.launched = launched
        self.stopped = stopped

    @property
    def delta(self) -> float:
        return self.sales - self.last_year

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.sales, self.last_year)

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
        if growing and self.concentration is not None and len(growing) < len(
                [line for line in self.lines if line.delta > 0 and not line.launched]):
            parts.append("%d %s portent %.0f %% de ce qui pousse" % (
                len(growing), self.words if len(growing) > 1 else self.word,
                self.concentration * 100))
        falling = self.falling
        if falling:
            lost = sum(line.delta for line in self.lines if line.delta < 0 and not line.stopped)
            parts.append("%d %s recule%s, %s en tout" % (
                len(falling), self.words if len(falling) > 1 else self.word,
                "nt" if len(falling) > 1 else "", format_eur(lost)))
        if self.launched:
            parts.append("%d lancée%s sur l'exercice, %s" % (
                len(self.launched), "s" if len(self.launched) > 1 else "",
                format_eur(sum(line.sales for line in self.launched))))
        if self.stopped:
            parts.append("%d arrêtée%s, %s l'an dernier" % (
                len(self.stopped), "s" if len(self.stopped) > 1 else "",
                format_eur(sum(line.last_year for line in self.stopped))))
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


def scopes(rows: Iterable[dict]) -> List[str]:
    """Les périmètres lus, le groupe d'abord."""
    found = sorted({str(row.get("scope") or "") for row in rows} - {""})
    if GROUP in found:
        found.remove(GROUP)
        found.insert(0, GROUP)
    return found


def _read(rows: Iterable[dict], scope: str) -> Dict[str, Dict[str, dict]]:
    """level → name → {period → sales, hero}."""
    read: Dict[str, Dict[str, dict]] = {}
    for row in rows:
        if str(row.get("scope") or "") != scope:
            continue
        level = str(row.get("level") or "").strip().lower()
        if level not in LEVELS:
            continue
        period = str(row.get("period") or "")[:7]
        if len(period) != 7:
            continue
        name = str(row.get("name") or "").strip() or "(sans nom)"
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
            ever_before = any(period < opens and value > 0 for period, value in series.items())
            lines.append(Line(level, name, sales, last_year,
                              series.get(anchor, 0.0), series.get(_shift(anchor, -12), 0.0),
                              hero=entry["hero"],
                              launched=last_year <= 0 and not ever_before and sales > 0,
                              stopped=sales <= 0 and last_year > 0))
        if lines:
            levels.append(Level(level, lines))
    missing = [LEVEL_WORDS[level][1] for level in LEVELS if level not in read]
    if missing and scope != GROUP:
        absent.append("les %s ne sont lues qu'au niveau du groupe" % " et ".join(missing))
    elif missing:
        absent.append("la lecture ne porte pas les %s" % " ni les ".join(missing))
    return Review(scope, anchor, months, levels, absent)
