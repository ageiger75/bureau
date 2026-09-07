"""Routeurs HTTP. Aucun ne contient de règle métier : ils lisent, appellent le domaine,
écrivent, puis redirigent."""

from . import issues, system, today

ROUTERS = (
    today.router,
    issues.router,
    system.router,
)


def include_all(app) -> None:
    for router in ROUTERS:
        app.include_router(router)
