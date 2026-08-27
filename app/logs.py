"""Making the application's own log lines actually appear.

Uvicorn configures logging for its own loggers and leaves every other one without a
handler, so anything below WARNING is silently dropped. That is how a timing line added to
diagnose a slow screen managed to never print once — the measurement existed and nobody
could see it, which is worse than not measuring at all.

One handler on one namespace. Nothing else in the application calls `basicConfig`, which
would fight uvicorn for the root logger.
"""

from __future__ import annotations

import logging
import sys

NAMESPACE = "ceoos"
_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return

    logger = logging.getLogger(NAMESPACE)
    logger.setLevel(level)
    # Not propagated: the root logger belongs to uvicorn, and sending these lines there
    # would print each one twice under `--reload`.
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    _configured = True
