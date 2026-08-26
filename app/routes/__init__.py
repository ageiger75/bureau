"""Routeurs HTTP. Aucun ne contient de règle métier : ils lisent, appellent le domaine,
écrivent, puis redirigent."""

from . import (
    cases,
    challenge,
    claims,
    commitments,
    decision,
    home,
    options,
    recommendation,
    reviews,
    today,
)

ROUTERS = (
    today.router,
    home.router,
    cases.router,
    claims.router,
    options.router,
    recommendation.router,
    challenge.router,
    decision.router,
    commitments.router,
    reviews.router,
)


def include_all(app) -> None:
    for router in ROUTERS:
        app.include_router(router)
