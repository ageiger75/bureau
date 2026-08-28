"""System status: everything the cockpit needs to say about itself, off the CEO surface.

A screen that spends its lines on where its database file sits is a screen that has
confused two audiences. The person deciding what to do about Japan this week does not need
the SQLite path, the loopback address or the autonomy level — and every line of that kind
is a line taken from the five that matter.

None of it is deleted, because all of it is true and someone eventually asks. It lives
here, one click away, where the question is "how far can I trust this?" rather than "what
should I do?".
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import settings
from ..perf import provenance, queries, source as source_module
from ..web import render

router = APIRouter()


@router.get("/system")
def system_status(request: Request):
    source = source_module.current_source()
    return render(
        request,
        "system.html",
        {
            "user": None,
            "source": source,
            "environment": settings.env,
            "autonomy": settings.autonomy_level,
            "database": settings.database_url,
            "reads_warehouse": settings.reads_warehouse,
            "connection": settings.snowflake_connection or "—",
            "last_read": source_module.last_read(),
            # Named one by one: the 503 page lists these when nothing can be read at all,
            # and a reader who has seen that page needs somewhere to check the same list
            # once the screen is working again.
            "missing_queries": queries.missing(),
            "kpi_tracker": str(settings.kpi_path) if settings.has_kpi_file else "",
            "kpi_coverage": getattr(source, "kpi_coverage", ""),
            "measures": provenance.unsettled(),
        },
    )
