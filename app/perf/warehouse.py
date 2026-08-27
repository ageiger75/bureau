"""Reading performance figures from Snowflake.

This module is the single declared exception to a rule the rest of the application still
obeys: nothing else opens a network connection. That exception is deliberate, narrow, and
guarded.

**Credentials.** None are read, stored or carried by this application. It names a
connection from `~/.snowflake/connections.toml` — the file the Snowflake CLI and Cortex
Code already maintain — and the connector resolves it. There is therefore no secret to
leak from this repository, and no password to rotate in a `.env`.

**Read-only.** Every statement passes `assert_read_only` before it reaches the warehouse.
That is a second lock, not the first: the real one is a role with no write grant, which
belongs to whoever administers Snowflake. Code cannot grant itself permissions it does not
have, and should not be trusted to withhold ones it does.

**The queries are not written here.** They depend on a schema this repository does not
know. `queries.py` holds them, one named constant each, and an unfilled query raises
rather than returning an empty result — an empty cockpit that looks calm is the worst
possible failure.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Sequence

from ..config import settings

#: Statements a reporting tool has any business issuing. Anything else is refused before
#: it reaches the network, whatever the role would have allowed.
READ_ONLY_PREFIXES = ("select", "with", "show", "describe", "desc", "explain")

#: Refused outright, even inside a comment or a second statement. The cockpit prepares,
#: flags and structures; it does not change anything anywhere.
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|truncate|drop|alter|create|grant|revoke|call|copy)\b",
    re.IGNORECASE,
)


class QueryRefused(RuntimeError):
    """A statement that is not a read. Raised before any connection is opened."""


class QueryNotConfigured(RuntimeError):
    """A query placeholder that nobody has filled in yet.

    Raised rather than returning nothing: a cockpit showing an empty section looks like a
    business with no problems, which is the most expensive lie it could tell.
    """


def strip_comments(sql: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", without_block)


def assert_read_only(sql: str) -> str:
    """Refuse anything that is not a read. Returns the statement when it passes."""
    if not sql or not sql.strip():
        raise QueryRefused("Empty statement.")

    body = strip_comments(sql).strip()
    if not body:
        raise QueryRefused("Statement contains nothing but comments.")

    lowered = body.lstrip().lower()
    if not lowered.startswith(READ_ONLY_PREFIXES):
        raise QueryRefused(
            "Only read statements are allowed (%s). Refused: %s"
            % (", ".join(READ_ONLY_PREFIXES), body.split()[0])
        )

    forbidden = FORBIDDEN.search(body)
    if forbidden:
        raise QueryRefused(
            "Statement contains a write keyword (%s). The cockpit never writes."
            % forbidden.group(0).upper()
        )

    # A second statement could smuggle a write past a SELECT prefix.
    if ";" in body.rstrip().rstrip(";"):
        raise QueryRefused("Only one statement per query.")

    return sql


#: A warehouse that has not answered in this long is not going to. Generous, because a
#: suspended warehouse genuinely takes time to resume and a cold month of sell-out is a
#: real scan — but finite, because an unbounded wait is indistinguishable from a hang.
QUERY_TIMEOUT_SECONDS = 300

#: Authentication goes through an external browser, so this waits on a person, not a
#: machine. Long enough to find the tab; short enough to give up on one nobody opened.
LOGIN_TIMEOUT_SECONDS = 180

LOG = logging.getLogger("ceoos.warehouse")


def _connect():
    """Open a connection from the named entry in ~/.snowflake/connections.toml.

    Imported lazily so the connector stays an optional dependency: the cockpit runs, and
    its whole test suite passes, on a machine that has never heard of Snowflake.
    """
    try:
        import snowflake.connector  # noqa: WPS433 — deliberate lazy import
    except ImportError as exc:  # pragma: no cover — depends on the local install
        raise RuntimeError(
            "The Snowflake connector is not installed. On Python 3.9 use:\n"
            "    .venv/bin/python -m pip install 'snowflake-connector-python==4.5.0'\n"
            "Versions from 4.7 onwards require Python 3.10 or later."
        ) from exc

    if not settings.snowflake_connection:
        raise RuntimeError("No connection name configured (CEOOS_SNOWFLAKE_CONNECTION).")

    return snowflake.connector.connect(
        connection_name=settings.snowflake_connection,
        # Without these, a warehouse that never answers hangs the page forever, and the
        # reader has no way to tell a slow query from a broken one. A refusal after a
        # known delay is a fact; a spinner is not.
        login_timeout=LOGIN_TIMEOUT_SECONDS,
        network_timeout=QUERY_TIMEOUT_SECONDS,
        client_session_keep_alive=False,
        session_parameters={"STATEMENT_TIMEOUT_IN_SECONDS": QUERY_TIMEOUT_SECONDS},
    )


def rows(sql: str, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
    """Run one read statement and return dictionaries keyed by lowercased column name.

    Snowflake returns column names uppercased; lowering them here keeps every caller from
    having to remember that, and keeps the mock and warehouse sources interchangeable.
    """
    assert_read_only(sql)

    started = time.time()
    connection = _connect()
    connected_at = time.time()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(sql, params or ())
            columns = [column[0].lower() for column in cursor.description]
            records = [dict(zip(columns, record)) for record in cursor.fetchall()]
        finally:
            cursor.close()
    finally:
        connection.close()

    # Logged, not silent: the first question anyone asks about a slow screen is where the
    # time went, and "connecting" and "querying" have entirely different remedies.
    LOG.info(
        "warehouse: %d rows · connect %.1fs · query %.1fs",
        len(records),
        connected_at - started,
        time.time() - connected_at,
    )
    return records


#: Session facts, no business data. Everything here is about who you are connected as,
#: which is exactly what has to be known before writing a single query.
SESSION_QUERY = """
select
    current_account()   as account,
    current_user()      as username,
    current_role()      as role,
    current_warehouse() as warehouse,
    current_database()  as database,
    current_schema()    as schema,
    current_region()    as region
"""


def check() -> dict:
    """Prove the connection works without reading any business data."""
    result = rows(SESSION_QUERY)
    return result[0] if result else {}


def describe_session() -> str:
    """The connection, in the terms needed to write a query against it."""
    facts = check()
    if not facts:
        return "Connecté, mais la session n'a rien renvoyé."

    lines = ["Connecté."]
    for label, key in (
        ("Compte", "account"),
        ("Utilisateur", "username"),
        ("Rôle", "role"),
        ("Entrepôt", "warehouse"),
        ("Base", "database"),
        ("Schéma", "schema"),
        ("Région", "region"),
    ):
        value = facts.get(key)
        lines.append("  %-13s %s" % (label, value if value else "— non défini par la connexion"))

    if not facts.get("warehouse"):
        lines.append("")
        lines.append(
            "  Aucun entrepôt actif : une requête de données échouera tant qu'il n'y en a"
        )
        lines.append(
            "  pas. Ajouter `warehouse = \"...\"` à la connexion dans connections.toml."
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- exploring

#: How many rows an exploration command prints. A warehouse can hold thousands of
#: objects; a wall of names helps nobody write a query.
EXPLORE_LIMIT = 200


def schemas(database: str) -> List[str]:
    """Schemas visible to the current role in `database`."""
    found = rows("show schemas in database %s" % _identifier(database))
    return [record.get("name", "") for record in found]


def tables(database: str, schema: str, like: str = "") -> List[Dict[str, Any]]:
    """Tables and views in one schema, with their row counts where Snowflake knows them.

    Views are included: a warehouse's modelled layer usually lives in views, and those are
    exactly the objects to prefer over raw tables.
    """
    scope = "%s.%s" % (_identifier(database), _identifier(schema))
    pattern = " like '%s'" % _like(like) if like else ""

    found = rows("show tables%s in schema %s" % (pattern, scope))
    result = [
        {"name": r.get("name", ""), "kind": "table", "rows": r.get("rows")}
        for r in found
    ]
    views = rows("show views%s in schema %s" % (pattern, scope))
    result.extend(
        {"name": r.get("name", ""), "kind": "view", "rows": None} for r in views
    )
    result.sort(key=lambda item: item["name"])
    return result[:EXPLORE_LIMIT]


def columns(database: str, schema: str, table: str) -> List[Dict[str, Any]]:
    """Column names and types of one object."""
    target = "%s.%s.%s" % (
        _identifier(database),
        _identifier(schema),
        _identifier(table),
    )
    found = rows("describe table %s" % target)
    return [
        {"name": r.get("name", ""), "type": r.get("type", ""), "null": r.get("null?")}
        for r in found
    ]


def _identifier(name: str) -> str:
    """Refuse anything that is not a plain SQL identifier.

    These names reach the statement by string interpolation, because `SHOW` and
    `DESCRIBE` do not accept bind parameters for object names. That makes this check the
    only thing standing between a typed name and the statement, so it is strict rather
    than clever: letters, digits and underscores, nothing else.
    """
    if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", name):
        raise QueryRefused(
            "Invalid identifier %r. Letters, digits and underscores only." % name
        )
    return name.upper()


def _like(pattern: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_%$]*", pattern or ""):
        raise QueryRefused("Invalid pattern %r." % pattern)
    return pattern.upper()
