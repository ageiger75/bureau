"""Une mémoire par fichier : un classeur ou un cache lu une fois par version du fichier.

Chaque page relisait et reparsait tous les classeurs (plan, EBITDA, réalisés, magasins,
phasage) et tous les caches JSON de l'entrepôt (produits, partenaires, service, prévision)
à chaque requête. Sur la machine du lecteur, avec les vrais fichiers, c'était plusieurs
secondes par onglet — « mille ans ». Ici, la clé est le chemin, la date de modification et
la taille du fichier : un fichier redéposé est relu, un fichier inchangé ne l'est plus.

Ce qui est rendu est l'objet lu, le même à chaque appel : les lecteurs ne le modifient pas,
et la règle est écrite ici pour qu'un lecteur qui voudrait le faire le sache.
"""

from __future__ import annotations

import functools
import os
import threading
from typing import Any, Callable, Dict, Tuple

_LOCK = threading.Lock()
_STORE: Dict[Tuple, Any] = {}

#: Au-delà, la mémoire se vide entièrement : elle n'a pas vocation à grandir avec les
#: fichiers d'essai d'une suite de tests.
MOST_ENTRIES = 256


def _version(path) -> Tuple:
    try:
        stat = os.stat(path)
        return (os.path.abspath(str(path)), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return (os.path.abspath(str(path)), None, None)


def by_file(loader: Callable) -> Callable:
    """Décore un lecteur `load(path, *args, **kwargs)` : même fichier, même version, mêmes
    arguments → même objet, sans relire."""

    @functools.wraps(loader)
    def wrapped(path, *args, **kwargs):
        key = (loader.__module__, loader.__name__, _version(path), args, tuple(sorted(kwargs.items())))
        try:
            hash(key)
        except TypeError:
            return loader(path, *args, **kwargs)
        with _LOCK:
            if key in _STORE:
                return _STORE[key]
        value = loader(path, *args, **kwargs)
        with _LOCK:
            if len(_STORE) >= MOST_ENTRIES:
                _STORE.clear()
            _STORE[key] = value
        return value

    wrapped.forget = forget  # type: ignore[attr-defined]
    return wrapped


def forget() -> None:
    with _LOCK:
        _STORE.clear()
