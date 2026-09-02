"""Une lecture : ce que les sources disent, ce que le registre en fait, ce qui remonte.

Ce module existe pour une raison précise. Le passage qui lit les sources et dépose leurs
faits dans le registre vivait dans `cli.py`, et il **imprimait** au fur et à mesure. Un
écran ne pouvait donc pas s'en servir sans le réécrire — et deux fois la même règle, à deux
endroits, c'est le doublon qui revient le jour où l'une des deux change sans l'autre. Le
défaut est déjà arrivé ici sur les libellés de marché ; il ne se voit qu'à retardement,
quand un chiffre diverge entre l'écran et le terminal sans qu'aucun test ne tombe.

La séparation est donc : **ce module lit et rend un compte rendu, il n'affiche rien.** Le
terminal l'imprime, l'écran le rend. Le jour où une troisième surface arrive, elle lit la
même chose.

Une propriété du compte rendu mérite d'être dite parce que l'inverse était plus court :
**une source absente et une source vide ne portent pas la même valeur.** `None` veut dire
« je n'ai pas regardé », `0` veut dire « j'ai regardé et il n'y avait rien ». Les confondre
ferait lire une absence comme un feu vert, ce qui est le défaut que ce cockpit passe son
temps à fermer — et il se serait glissé ici même, dans le compte rendu qui sert à le
détecter ailleurs.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional, Sequence, Tuple

from ..config import settings


class Sources:
    """Ce qui a été lu, et ce qui n'a pas pu l'être. Jamais un zéro pour une absence."""

    __slots__ = ("units", "period", "partners", "partner_faults", "owners_given")

    def __init__(self, units: Optional[int] = None, period: str = "",
                 partners: Optional[int] = None,
                 partner_faults: Optional[Sequence[str]] = None,
                 owners_given: Optional[int] = None) -> None:
        #: Nombre d'unités de performance lues, ou `None` si l'écran n'a rien à lire.
        self.units = units
        #: La période que porte la lecture, telle que la source la nomme.
        self.period = period
        #: Lignes du fichier des partenaires, ou `None` si le fichier est absent.
        self.partners = partners
        #: Les lignes que le lecteur de partenaires a refusées, avec leur motif.
        self.partner_faults: List[str] = list(partner_faults or ())
        #: Sujets nouvellement rattachés à leur MD, ou `None` si l'annuaire est absent.
        #: La distinction compte : sans annuaire, « personne n'en répond » s'applique à
        #: tous les sujets et cesse d'ordonner quoi que ce soit.
        self.owners_given = owners_given

    @property
    def missing(self) -> List[str]:
        """Les sources que cette lecture n'a pas pu ouvrir, nommées pour l'écran."""
        absent = []
        if self.units is None:
            absent.append("écran de performance")
        if self.partners is None:
            absent.append("partenaires")
        if self.owners_given is None:
            absent.append("annuaire")
        return absent


class Scan:
    """Ce qu'une lecture a produit dans le registre."""

    __slots__ = ("sources", "fired", "opened", "grew", "returning", "quiet")

    def __init__(self, sources: "Sources", fired: int = 0, opened=(), grew=(),
                 returning=(), quiet=()) -> None:
        self.sources = sources
        #: Combien de règles se sont déclenchées, avant tout rapprochement d'identité.
        self.fired = fired
        self.opened = list(opened)
        self.grew = list(grew)
        #: Les sujets qui suivent un sujet clos. Une rechute n'est pas une découverte.
        self.returning = list(returning)
        #: Ouverts, mais muets à ce passage. Muet n'est pas résolu.
        self.quiet = list(quiet)

    @property
    def changed(self) -> bool:
        return bool(self.fired)


def observe(register, today: str = "", dataset=None) -> "Scan":
    """Lire les sources et déposer leurs faits dans le registre. N'affiche rien.

    `dataset` est passé par l'appelant quand il l'a déjà lu — c'est le cas de l'écran, qui
    l'a chargé pour le reste de la page. Le relire coûterait une seconde requête à
    l'entrepôt pour un résultat identique, et surtout : deux lectures d'un même écran ne
    porteraient pas forcément la même heure, donc pas forcément les mêmes chiffres.
    """
    from . import detection
    from . import partners as partners_module
    from . import perimeter as perimeter_module
    from . import selection as selection_module
    from . import source as source_module

    today = today or date.today().isoformat()
    seen: List = []
    sources = Sources()

    if dataset is None:
        dataset = source_module.current_source().dataset()
    units = getattr(dataset, "units", None) if dataset is not None else None
    sources.period = getattr(dataset, "period", "") if dataset is not None else ""
    if units:
        sources.units = len(units)
        seen.extend(detection.from_units(units, period=sources.period, today=today))

    if settings.has_partners_file:
        read = partners_module.current()
        sources.partners = len(read)
        sources.partner_faults = list(read.faults)
        seen.extend(detection.from_partners(read, sources.period, today=today))

    result = detection.post(register, seen)

    # Rattacher les sujets de marché à leur MD **avant** de compter quoi que ce soit.
    # Sans cette étape, « personne n'en répond » se déclenchait sur tous les sujets à la
    # fois : un facteur qui s'applique partout n'ordonne rien et n'explique rien.
    if settings.has_org_file:
        org = perimeter_module.load(str(settings.org_path))
        sources.owners_given = selection_module.assign_owners(register, org)

    return Scan(sources=sources, fired=len(seen), opened=result["opened"],
                grew=result["grew"], returning=result["returning"],
                quiet=detection.silent(register, seen))


def read(session, today: str = "", dataset=None,
         save: bool = True) -> Tuple[object, "Scan"]:
    """La lecture entière : charger le registre, l'alimenter, le classer, l'écrire.

    Rend `(Week, Scan)` — ce qui remonte, et d'où cela vient. L'écriture est conditionnelle
    et le paramètre est explicite : une surface qui ne fait que regarder n'a pas à laisser
    de trace, et une surface qui alimente doit le faire exprès.

    Les poids stratégiques sont optionnels et leur absence est portée par la semaine
    (`weights_read`), jamais avalée : sans eux, le classement redevient un classement par
    taille, ce qui n'est pas ce qu'un plan sert à faire.
    """
    from . import memory
    from . import selection as selection_module
    from . import weights as weights_module

    today = today or date.today().isoformat()
    register = memory.load(session)
    scan = observe(register, today, dataset=dataset)
    if save and scan.changed:
        memory.save(session, register)

    read_weights = weights_module.current() if settings.has_weights_file else None
    return selection_module.rank(register, today, weights=read_weights), scan
