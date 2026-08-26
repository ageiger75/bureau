"""Point d'entrée FastAPI de CEO OS — Decision Room.

Deux garde-fous sont posés ici plutôt que dans la documentation :
  * l'application refuse toute requête ne venant pas de la boucle locale ;
  * aucun client HTTP sortant n'est instancié — le prototype n'appelle ni Microsoft 365,
    ni fournisseur d'IA, ni service externe (brief §14).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from . import __version__
from .config import LOOPBACK_HOSTS, ROOT, settings
from .db import create_all
from .routes import include_all
from .web import render


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Crée le schéma manquant au démarrage.

    Acceptable pour un prototype mono-utilisateur. Dès qu'un schéma contiendra de vraies
    décisions, il faudra passer à Alembic (voir README, « Vers PostgreSQL »).
    """
    create_all()
    yield


app = FastAPI(
    title="CEO OS — Decision Room",
    version=__version__,
    docs_url=None,       # pas de surface d'API publiée : l'interface est en HTML
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="ceoos_session",
    same_site="strict",
    https_only=not settings.is_local,
    max_age=8 * 3600,
)


@app.middleware("http")
async def loopback_only(request: Request, call_next):
    """Refuse toute requête dont le client n'est pas local.

    `uvicorn --host 127.0.0.1` suffit normalement. Ce contrôle est le second verrou : un
    reverse proxy mal configuré, ou un `--host 0.0.0.0` collé par erreur dans une commande,
    exposerait sinon des dossiers confidentiels sur le réseau.
    """
    client_host = request.client.host if request.client else ""
    if client_host not in LOOPBACK_HOSTS:
        return Response(
            "CEO OS n'est accessible que depuis la machine locale.",
            status_code=403,
            media_type="text/plain; charset=utf-8",
        )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """En-têtes de sécurité.

    La CSP interdit toute ressource externe : ni police, ni script, ni image distante.
    C'est aussi une garantie vérifiable qu'aucune donnée de dossier ne fuit par une balise.
    """
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; font-src 'self'; connect-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    # Les pages contiennent des dossiers confidentiels : jamais de cache disque partagé.
    response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")
include_all(app)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    """Page d'erreur lisible plutôt qu'un JSON brut, l'interface étant en HTML."""
    if exc.status_code == 404:
        message = "Ce dossier n'existe pas, ou n'est pas accessible."
    elif exc.status_code == 503:
        message = str(exc.detail)
    else:
        message = str(exc.detail)
    return render(
        request,
        "error.html",
        {"status_code": exc.status_code, "message": message, "user": None},
        status_code=exc.status_code,
    )
