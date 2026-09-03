"""Routeurs HTTP. Aucun ne contient de règle métier : ils lisent, appellent le domaine,
écrivent, puis redirigent."""

from . import (
    cases,
    challenge,
    claims,
    commitments,
    decision,
    home,
    issues,
    options,
    recommendation,
    reviews,
    system,
    today,
)

ROUTERS = (
    today.router,
    issues.router,
    home.router,
    cases.router,
    claims.router,
    options.router,
    recommendation.router,
    challenge.router,
    decision.router,
    commitments.router,
    reviews.router,
    system.router,
)


def include_all(app) -> None:
    for router in ROUTERS:
        app.include_router(router)
