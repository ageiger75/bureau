"""Les distributeurs déclarés par le lecteur, que l'entrepôt type comme des filiales.

Un distributeur n'est pas une filiale : ce qu'on lui facture est du sell-in du groupe. Or
le type du point de vente facturé, qui dit au cockpit quelles factures compter, range
certains distributeurs sous « filiale », et le cockpit les écartait avec l'intragroupe.
La correction durable est dans la donnée, chez l'équipe data ; d'ici là, le lecteur
déclare ici les centres de profit à compter, par leur code, et le cockpit les compte en
le disant. Le fichier vit dans `var/`, jamais dans le dépôt : un code de centre de profit
est une donnée de la maison.

    profit_centre,name,reason
    <code>,<nom du distributeur>,<pourquoi c'est un distributeur>
"""

from __future__ import annotations

import csv
from typing import Dict, List

from . import memo

REQUIRED = ("profit_centre", "name")


class Declared:
    """Les centres de profit déclarés distributeurs, et ce qui n'a pas pu être lu."""

    __slots__ = ("codes", "names", "faults")

    def __init__(self, names: Dict[str, str], faults: List[str]) -> None:
        self.names = dict(names)
        self.codes = set(self.names)
        self.faults = list(faults)

    @property
    def is_empty(self) -> bool:
        return not self.names

    def name_of(self, code: str) -> str:
        return self.names.get((code or "").strip().upper(), (code or "").strip().upper())


@memo.by_file
def load(path) -> Declared:
    names: Dict[str, str] = {}
    faults: List[str] = []
    try:
        with open(str(path), encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            header = [name.strip() for name in (reader.fieldnames or [])]
            missing = [name for name in REQUIRED if name not in header]
            if missing:
                return Declared({}, ["colonnes manquantes dans %s : %s" % (path, ", ".join(missing))])
            for number, record in enumerate(reader, start=2):
                code = (record.get("profit_centre") or "").strip().upper()
                name = (record.get("name") or "").strip()
                if not code:
                    faults.append("ligne %d sans centre de profit, ignorée" % number)
                    continue
                if code in names:
                    faults.append("ligne %d : centre de profit %s déjà déclaré, ignorée" % (number, code))
                    continue
                names[code] = name or code
    except OSError as exc:
        return Declared({}, ["%s illisible : %s" % (path, exc)])
    return Declared(names, faults)


def current() -> Declared:
    from ..config import settings

    if not settings.has_distributors_file:
        return Declared({}, [])
    return load(settings.distributors_path)
