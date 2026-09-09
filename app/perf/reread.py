"""La relecture automatique : l'entrepôt relu par le serveur lui-même, derrière l'écran.

Le serveur ne relisait l'entrepôt qu'au démarrage, par la relecture que `start.command`
lance derrière la première page. Un serveur qu'on laisse tourner servait donc des chiffres
de plusieurs jours, portant leur date, et la consigne « relancez-le chaque matin » est de
celles qui ne tiennent pas. Ici, un fil dort, se réveille de temps en temps, et relit tout
quand la lecture principale a passé l'âge — le jeu de données et son historique, les KPI,
les produits — dans cet ordre, comme `?refresh=1`.

La règle de la maison tient : jamais une requête sous un lecteur. Le fil ne sert
personne ; la page, qui guette les horodatages, se recharge quand la lecture atterrit.
Rien n'est écrit ailleurs que dans les caches du disque, et rien n'est envoyé.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from ..config import settings
from . import source

LOG = logging.getLogger("ceoos.reread")

#: Le fil se réveille à cette cadence pour regarder l'âge de la lecture.
EVERY_SECONDS = 15 * 60

_thread: Optional[threading.Thread] = None


def due(max_age_seconds: float, age: Optional[float] = None) -> bool:
    """Vrai quand la lecture a passé l'âge, ou n'a jamais eu lieu."""
    if max_age_seconds <= 0:
        return False
    if age is None:
        age = source.reading_age()
    return age is None or age >= max_age_seconds


def reread_all() -> None:
    """Tout relire, dans l'ordre de `?refresh=1`, en attendant l'entrepôt : personne
    n'est devant."""
    current = source.current_source()
    current.dataset(refresh=True, wait_for_warehouse=True)
    for name in ("client_kpis", "product_rows", "client_rows", "partner_rows",
                 "osa_rows", "forecast_rows", "order_rows", "bulk_rows"):
        reader = getattr(current, name, None)
        if reader is None:
            continue
        try:
            reader(wait_for_warehouse=True)
        except NotImplementedError as missing:
            LOG.info("reread: %s not connected (%s)", name, missing)


def start(max_age_hours: Optional[float] = None, every: float = EVERY_SECONDS,
          work: Callable[[], None] = reread_all) -> bool:
    """Lance le fil, une fois par vie du serveur, seulement devant un entrepôt et seulement
    quand l'âge est réglé. Rend vrai s'il est parti."""
    global _thread
    hours = settings.reread_hours if max_age_hours is None else max_age_hours
    if not settings.reads_warehouse or hours <= 0 or _thread is not None:
        return False
    max_age = hours * 3600.0

    def loop() -> None:
        while True:
            time.sleep(every)
            if not due(max_age):
                continue
            LOG.info("reread: the reading is older than %.1f h, reading the warehouse again", hours)
            try:
                work()
            except Exception as exc:  # pragma: no cover — depends on the warehouse
                LOG.warning("reread: failed, will try again later (%s)", exc)

    _thread = threading.Thread(target=loop, name="reread", daemon=True)
    _thread.start()
    return True
