"""Routeurs HTTP. Aucun ne contient de règle métier : ils lisent, appellent le domaine,
écrivent, puis redirigent."""

from . import system, today

ROUTERS = (
    today.router,
    system.router,
)


def include_all(app) -> None:
    for router in ROUTERS:
        app.include_router(router)
