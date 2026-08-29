"""Reading from the warehouse: the guard, the switch, and what stays unwritten.

Connecting a cockpit to a warehouse is where a reporting tool quietly becomes a tool that
can change things. These tests exist so that never happens by accident.

Nothing here opens a connection. The guard runs before any network call, which is the
whole point of it.
"""

from __future__ import annotations

import pytest

from app.perf import queries, warehouse


# --------------------------------------------------------------------- read-only guard


@pytest.mark.parametrize(
    "sql",
    [
        "select 1",
        "SELECT market, sales FROM perf.sales",
        "with recent as (select 1) select * from recent",
        "  show tables",
        "describe table perf.sales",
    ],
)
def test_reads_are_allowed(sql):
    assert warehouse.assert_read_only(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "delete from perf.sales",
        "update perf.sales set actual = 0",
        "insert into perf.sales values (1)",
        "merge into perf.sales using x on 1=1",
        "truncate table perf.sales",
        "drop table perf.sales",
        "alter table perf.sales add column x int",
        "create table t as select 1",
        "grant select on perf.sales to role r",
        "call some_procedure()",
        "copy into perf.sales from @stage",
    ],
)
def test_writes_are_refused_before_any_connection_is_opened(sql):
    """The cockpit prepares, flags and structures. It changes nothing, anywhere."""
    with pytest.raises(warehouse.QueryRefused):
        warehouse.assert_read_only(sql)


def test_a_write_hidden_behind_a_select_is_refused():
    """A second statement is the obvious way past a prefix check."""
    with pytest.raises(warehouse.QueryRefused):
        warehouse.assert_read_only("select 1; drop table perf.sales")


def test_a_write_hidden_in_a_comment_free_body_is_refused():
    with pytest.raises(warehouse.QueryRefused):
        warehouse.assert_read_only("/* harmless */ delete from perf.sales")


def test_a_statement_that_is_only_comments_is_refused():
    with pytest.raises(warehouse.QueryRefused):
        warehouse.assert_read_only("-- select 1")


def test_an_empty_statement_is_refused():
    with pytest.raises(warehouse.QueryRefused):
        warehouse.assert_read_only("   ")


def test_comments_do_not_hide_the_real_first_word():
    assert warehouse.strip_comments("-- note\nselect 1").strip().startswith("select")


# --------------------------------------------------------------------- unwritten queries


def test_only_the_written_queries_report_as_written():
    """Some queries are written against the real schema; the rest are not.

    Kept as an inventory rather than deleted: `missing()` is what the 503 page lists, so a
    query that silently stopped counting as written would produce a screen claiming a
    source is ready when it is not. Narrow this set as each query lands — and when it
    empties, the mapping tests are what should exist in its place.
    """
    assert set(queries.missing()) == {
        "MARKET_INDEX",
        "COMMITMENTS",
        "FORECAST_HISTORY",
    }


def test_readings_without_a_tracker_refuse_rather_than_score_nothing():
    """Written SQL is not a connected panel, and neither are values without targets.

    `KPI_READINGS` exists and its mapping is written, so both have left the list of what
    is missing. What remains required is the tracker: 25.1% is neither good nor bad until
    something says what was asked for. Without it this refuses — and the panel then says
    it is not connected, which is true — rather than rendering an empty list, which reads
    as "nothing to report".
    """
    from app.config import settings
    from app.perf.source import SnowflakeSource

    assert "KPI_READINGS" not in queries.missing()
    assert not settings.has_kpi_file, "the suite must not read a real tracker"
    with pytest.raises(NotImplementedError):
        SnowflakeSource().client_kpis()


@pytest.fixture
def without_planning_file(monkeypatch):
    """No workbook on disk — stated, not inherited.

    These tests used to pass because the developer's `var/` happened to be empty. Copying
    a real planning file there to look at it broke three of them, which is the wrong way
    to learn that a test depends on machine state.
    """
    from app.config import settings

    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: False))


def test_a_source_missing_a_piece_refuses_rather_than_returning_nothing(
    without_planning_file,
):
    """An empty cockpit looks like a business with no problems. That is the most
    expensive lie this product could tell."""
    from app.perf.source import SnowflakeSource

    with pytest.raises(NotImplementedError):
        SnowflakeSource().dataset()


def test_the_planning_file_is_checked_before_the_network(without_planning_file):
    """A missing local file is not worth a round trip, and the refusal reads better when
    nothing has been read yet. Also: without budgets every market is unbudgeted, so the
    cockpit would render calm on a business it never compared to anything."""
    from app.perf.source import SnowflakeSource

    with pytest.raises(NotImplementedError) as refusal:
        SnowflakeSource().dataset()

    assert "planning workbook" in str(refusal.value)


# --------------------------------------------------------------------- the switch


def test_the_default_source_is_mock():
    """A warehouse is never reached by default, and never by accident."""
    from app.perf.source import MockSource, current_source

    assert isinstance(current_source(), MockSource)


def test_asking_for_snowflake_without_a_connection_name_is_refused(monkeypatch):
    """Two things must be said out loud before anything leaves the machine."""
    from app.config import ConfigError, load_settings

    monkeypatch.setenv("CEOOS_DATA_SOURCE", "snowflake")
    monkeypatch.delenv("CEOOS_SNOWFLAKE_CONNECTION", raising=False)

    with pytest.raises(ConfigError):
        load_settings()


def test_the_connection_is_named_never_carried(monkeypatch):
    """No credential is read, stored or transported by this application: it names an
    entry in the file the Snowflake CLI already maintains."""
    from app.config import load_settings

    monkeypatch.setenv("CEOOS_DATA_SOURCE", "snowflake")
    monkeypatch.setenv("CEOOS_SNOWFLAKE_CONNECTION", "loep")

    resolved = load_settings()

    assert resolved.snowflake_connection == "loep"
    assert resolved.reads_warehouse
    # Nothing resembling a secret exists on the settings object.
    for field in ("password", "private_key", "token", "passphrase"):
        assert not hasattr(resolved, field)


def test_the_connector_is_optional(monkeypatch):
    """The cockpit runs, and its whole suite passes, on a machine that has never heard
    of Snowflake. The import is lazy for exactly that reason."""
    import sys

    assert "snowflake" not in sys.modules


def test_the_session_query_reads_nothing_but_session_facts():
    """Proving the connection works must never touch business data."""
    from app.perf import warehouse

    warehouse.assert_read_only(warehouse.SESSION_QUERY)
    assert "current_role()" in warehouse.SESSION_QUERY
    # No table, no schema, nothing that belongs to the business.
    assert " from " not in warehouse.SESSION_QUERY.lower()


# --------------------------------------------------------------------------- exploring


def test_an_identifier_containing_a_write_word_is_still_readable():
    """A table called CUSTOMER_UPDATE is a table, not a write.

    Object names reach SHOW and DESCRIBE by string interpolation, because Snowflake does
    not bind parameters for them. This is therefore the case most likely to produce a
    false refusal, and the one most likely to be met in a real warehouse.
    """
    for sql in (
        "describe table DWH.SALES.CUSTOMER_UPDATE",
        "select is_deleted from DWH.CRM.CLIENTS",
        "select * from DWH.SALES.DELETE_FLAGS",
    ):
        assert warehouse.assert_read_only(sql) == sql


@pytest.mark.parametrize(
    "name",
    ["DWH; drop table t", "a b", "sales--", "'; select 1 --", "", "1SALES.x"],
)
def test_an_object_name_that_is_not_an_identifier_is_refused(name):
    """The only thing between a typed name and an interpolated statement."""
    with pytest.raises(warehouse.QueryRefused):
        warehouse._identifier(name)


def test_a_valid_identifier_is_accepted_and_upper_cased():
    assert warehouse._identifier("sales_daily") == "SALES_DAILY"


def test_a_search_pattern_cannot_smuggle_sql():
    with pytest.raises(warehouse.QueryRefused):
        warehouse._like("x' or 1=1 --")


# ------------------------------------------------- pointing at an unready source


def test_an_unready_source_explains_itself_instead_of_crashing(
    monkeypatch, without_planning_file
):
    """Pointing at a warehouse whose queries are unwritten is a normal state during
    connection, not a fault. A stack trace would say neither what is missing nor how to
    get back.
    """
    from starlette.testclient import TestClient

    import app.routes.today as today_route
    from app.main import app
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(today_route, "current_source", lambda: SnowflakeSource())

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 503
    assert "Data source not ready" in response.text
    # It names what is still missing. The SQL and the mapping now exist, so the first
    # thing standing in the way is the planning workbook on the machine.
    assert "planning workbook" in response.text
    assert "MARKET_INDEX" in response.text
    # And it says how to get back to a working screen.
    assert "CEOOS_DATA_SOURCE=mock" in response.text


# ------------------------------------------------------- warehouse rows to a screen
#
# The wiring between the query and the model. These tests stub the connection: what they
# check is the assembly, not the SQL, which only the warehouse itself can validate.


def _sales_row(market="Japan", **overrides):
    row = {
        "market": market,
        "region": "APAC",
        "channel": "ecommerce",
        "period": "2026-07",
        "sales_actual": 1_259_700.0,
        "sessions": 1_640_000.0,
        "orders": 12_800.0,
        "sessions_last_year": 1_824_000.0,
        "orders_last_year": 17_800.0,
    }
    row.update(overrides)
    return row


def _budget_for(market="Japan"):
    from app.perf.budget import Budget, BudgetLine

    return Budget(
        [
            BudgetLine(
                market=market,
                region="APAC",
                segment="EBU",
                channel="ecommerce",
                period="2026-07",
                budget=1_861_700.0,
                last_year=1_622_900.0,
            )
        ]
    )


def test_the_source_assembles_a_dataset_from_warehouse_rows(monkeypatch):
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None, label='': [_sales_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    dataset = SnowflakeSource().dataset()

    assert [unit.market for unit in dataset.units] == ["Japan"]
    assert dataset.sales_actual == 1_259_700.0
    assert dataset.sales_budget == 1_861_700.0


def test_the_period_label_names_the_month_it_actually_shows(monkeypatch):
    """The query anchors on the last complete month. A screen headed "MTD" would promise
    a month in progress while showing one that has closed."""
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None, label='': [_sales_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    dataset = SnowflakeSource().dataset()

    assert dataset.period_label.startswith("July 2026 sales")
    # Read on the 27th, "July" alone looks like a stale screen rather than the freshest
    # month that has actually closed.
    assert "last complete month" in dataset.period_label


def test_the_screen_is_stamped_with_when_it_was_read(monkeypatch):
    """The warehouse is not yet stable within a day: sell-out facts are reprocessed on
    recent months, so the same query hours apart returns different figures for some
    markets. Two screens that disagree are a scandal; two screens stamped an hour apart
    are a fact about the pipeline."""
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None, label='': [_sales_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    dataset = SnowflakeSource().dataset()

    # A date alone would not distinguish two reads taken the same morning.
    assert dataset.as_of.endswith("UTC")
    assert ":" in dataset.as_of


def test_a_query_that_returns_nothing_is_a_refusal_not_a_blank_screen(monkeypatch):
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None, label='': [])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    with pytest.raises(NotImplementedError):
        SnowflakeSource().dataset()


def test_a_disagreement_between_file_and_warehouse_survives_to_the_source(monkeypatch):
    """It has to reach the screen, or nobody learns the two sources are drifting."""
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(
        warehouse, "rows", lambda sql, params=None, label='': [_sales_row(sales_budget=1_000_000.0)]
    )
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    source = SnowflakeSource()
    source.dataset()

    assert len(source.conflicts) == 1


def test_performance_renders_even_though_commitments_are_not_connected(monkeypatch):
    """The panels connect on their own schedule. One missing piece dims its own panel;
    it does not take down a screen whose main job now works."""
    from starlette.testclient import TestClient

    import app.routes.today as today_route
    from app.main import app
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None, label='': [_sales_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())
    monkeypatch.setattr(today_route, "current_source", lambda: SnowflakeSource())

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Japan" in response.text
    # And says so, rather than showing an empty board that reads as "nothing outstanding".
    assert "Not connected to this source yet" in response.text


# ------------------------------------------------------------- not querying every time
#
# The warehouse read takes minutes; the facts behind it move once a day. Re-running the
# query on every page load costs the reader everything and buys nothing — and a CEO who
# waits two minutes to refresh a screen stops refreshing it.


def test_a_second_read_does_not_hit_the_warehouse_again(monkeypatch):
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    calls = []

    def counted(sql, params=None, label=''):
        calls.append(sql)
        return [_sales_row()]

    monkeypatch.setattr(warehouse, "rows", counted)
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    SnowflakeSource().dataset()
    one_read = len(calls)
    SnowflakeSource().dataset()

    assert one_read > 0
    assert len(calls) == one_read
    source_module.cache_clear()


def test_the_cache_survives_a_new_source_object(monkeypatch):
    """`current_source()` builds one per request. A cache that dies with the request is
    not a cache."""
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    # Labelled, because the screen now pays for three queries and only one of them is
    # the current month. Counting reads in the aggregate would make this test pass or
    # fail on the caching of a query it is not about.
    calls = []
    monkeypatch.setattr(
        warehouse,
        "rows",
        lambda sql, params=None, label='': calls.append(label) or [_sales_row()],
    )
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    first = SnowflakeSource().dataset()
    one_read = len(calls)
    second = SnowflakeSource().dataset()

    assert first is second
    assert one_read > 0
    assert len(calls) == one_read
    source_module.cache_clear()


def test_an_expired_cache_reads_again(monkeypatch):
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    # Labelled, because the screen now pays for three queries and only one of them is
    # the current month. Counting reads in the aggregate would make this test pass or
    # fail on the caching of a query it is not about.
    calls = []
    monkeypatch.setattr(
        warehouse,
        "rows",
        lambda sql, params=None, label='': calls.append(label) or [_sales_row()],
    )
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())
    monkeypatch.setattr(source_module, "CACHE_SECONDS", -1)

    SnowflakeSource().dataset()
    SnowflakeSource().dataset()

    assert calls.count("SALES_AND_DRIVERS") == 2
    source_module.cache_clear()


def test_a_refresh_is_not_refused_by_the_cache(monkeypatch):
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    # Labelled, because the screen now pays for three queries and only one of them is
    # the current month. Counting reads in the aggregate would make this test pass or
    # fail on the caching of a query it is not about.
    calls = []
    monkeypatch.setattr(
        warehouse,
        "rows",
        lambda sql, params=None, label='': calls.append(label) or [_sales_row()],
    )
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    SnowflakeSource().dataset()
    SnowflakeSource().dataset(refresh=True)

    assert calls.count("SALES_AND_DRIVERS") == 2
    source_module.cache_clear()


def test_a_cached_screen_still_says_when_it_was_read(monkeypatch):
    """The cache must never make a stale figure look fresh. The stamp is the read, not
    the render, so a cached screen carries the older time and says so."""
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None, label='': [_sales_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    first = SnowflakeSource().dataset()
    second = SnowflakeSource().dataset()

    assert second.as_of == first.as_of
    source_module.cache_clear()


def test_the_conflicts_survive_a_cached_read(monkeypatch):
    """They are computed during the read, so a cached screen would otherwise lose them
    and quietly stop reporting that the two sources disagree."""
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(
        warehouse, "rows", lambda sql, params=None, label='': [_sales_row(sales_budget=1_000_000.0)]
    )
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    SnowflakeSource().dataset()
    later = SnowflakeSource()
    later.dataset()

    assert len(later.conflicts) == 1
    source_module.cache_clear()


# ---------------------------------------------------------- surviving a restart
#
# The cost that actually bites is not a second page load, it is a second launch: the
# server is restarted far more often than an hour goes by, and each restart used to pay
# the full query again.


def test_a_restart_reuses_the_last_read(monkeypatch):
    """A fresh process, a fresh source object, no cached dataset in memory — and still no
    query, because the rows are on disk."""
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    # Labelled, because the screen now pays for three queries and only one of them is
    # the current month. Counting reads in the aggregate would make this test pass or
    # fail on the caching of a query it is not about.
    calls = []
    monkeypatch.setattr(
        warehouse,
        "rows",
        lambda sql, params=None, label='': calls.append(label) or [_sales_row()],
    )
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    SnowflakeSource().dataset()
    one_read = len(calls)
    source_module.cache_clear()  # the process ends; the file does not
    SnowflakeSource().dataset()

    assert one_read > 0
    assert len(calls) == one_read


def test_a_restarted_screen_still_carries_the_original_read_time(monkeypatch):
    """The whole point of stamping the read is that it stays said. A restart that
    restamped would quietly turn an hour-old figure into a fresh one."""
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None, label='': [_sales_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    first = SnowflakeSource().dataset()
    source_module.cache_clear()
    monkeypatch.setattr(source_module, "read_at", lambda: "2099-01-01 00:00 UTC")
    second = SnowflakeSource().dataset()

    assert second.as_of == first.as_of


def test_a_corrupt_cache_costs_one_query_and_nothing_else(monkeypatch):
    """A cache that can break a screen is worse than no cache."""
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    source_module._cache_path().write_text("{ this is not json", encoding="utf-8")

    calls = []
    monkeypatch.setattr(
        warehouse, "rows", lambda sql, params=None, label='': calls.append(sql) or [_sales_row()]
    )
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    dataset = SnowflakeSource().dataset()

    # One read and no retry. Counted per statement rather than in total, so the
    # test says what it means whatever number of queries a read needs.
    assert calls, "a corrupt cache must fall back to reading, not to nothing"
    assert len(calls) == len(set(calls))
    assert dataset.sales_actual > 0


def test_an_expired_file_is_ignored(monkeypatch):
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    # Labelled, because the screen now pays for three queries and only one of them is
    # the current month. Counting reads in the aggregate would make this test pass or
    # fail on the caching of a query it is not about.
    calls = []
    monkeypatch.setattr(
        warehouse,
        "rows",
        lambda sql, params=None, label='': calls.append(label) or [_sales_row()],
    )
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    SnowflakeSource().dataset()
    source_module.cache_clear()
    monkeypatch.setattr(source_module, "CACHE_SECONDS", -1)
    SnowflakeSource().dataset()

    assert calls.count("SALES_AND_DRIVERS") == 2


def test_forgetting_the_cache_reaches_the_disk(monkeypatch):
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    # Labelled, because the screen now pays for three queries and only one of them is
    # the current month. Counting reads in the aggregate would make this test pass or
    # fail on the caching of a query it is not about.
    calls = []
    monkeypatch.setattr(
        warehouse,
        "rows",
        lambda sql, params=None, label='': calls.append(label) or [_sales_row()],
    )
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    SnowflakeSource().dataset()
    source_module.cache_forget()
    SnowflakeSource().dataset()

    assert calls.count("SALES_AND_DRIVERS") == 2
    # Forgetting means forgetting everything on disk, the history included. A `--refresh`
    # that left a two-year history behind would answer half the question it was asked.
    assert calls.count("SALES_HISTORY") == 2


def test_the_cached_rows_are_primitives(monkeypatch):
    """Stored as plain JSON, never as pickled objects: a cache file is data the next
    version of this code has to be able to read, or refuse cleanly."""
    import json

    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None, label='': [_sales_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    SnowflakeSource().dataset()
    stored = json.loads(source_module._cache_path().read_text(encoding="utf-8"))

    assert stored["rows"][0]["market"] == "Japan"
    assert "read_at" in stored


# ------------------------------------------------------------------ sell-in, separately
#
# It comes from a different source with a different cadence. Reading it inside the
# sell-out read would mean one outage taking down both — and the sell-out three fifths of
# the plan are worth showing even on a day the other two fifths are unavailable.


def test_sell_in_is_read_when_its_query_exists(monkeypatch):
    from app.perf import queries, warehouse
    from app.perf.source import SnowflakeSource

    asked = []

    def rows(sql, params=None, label=''):
        asked.append(sql)
        if sql == "SELL IN SQL":
            return [{
                "entity": "M_103", "market": "Japan", "region": "APAC",
                "segment": "DIS - Distributors", "period": "2026-07",
                "sales_actual": 480_000.0, "sales_last_year": 430_000.0,
            }]
        return [_sales_row()]

    monkeypatch.setattr(warehouse, "rows", rows)
    monkeypatch.setattr(queries, "SELL_IN", "SELL IN SQL")
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    dataset = SnowflakeSource().dataset()

    assert "SELL IN SQL" in asked
    assert {u.channel for u in dataset.units} == {"ecommerce", "dis"}


def test_a_sell_in_outage_costs_its_own_lines_and_no_others(monkeypatch, capsys):
    """Two fifths of the plan going missing is a bad day. Refusing to render the other
    three fifths over it would help nobody, and the screen already says what it cannot
    see."""
    from app.perf import queries, warehouse
    from app.perf.source import SnowflakeSource

    def rows(sql, params=None, label=''):
        if sql == "SELL IN SQL":
            raise RuntimeError("object does not exist")
        return [_sales_row()]

    monkeypatch.setattr(warehouse, "rows", rows)
    monkeypatch.setattr(queries, "SELL_IN", "SELL IN SQL")
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    dataset = SnowflakeSource().dataset()

    assert [u.channel for u in dataset.units] == ["ecommerce"]
    assert dataset.sales_actual > 0


def test_an_unwritten_sell_in_query_is_not_reached_for(monkeypatch):
    from app.perf import queries, warehouse
    from app.perf.source import SnowflakeSource

    asked = []
    monkeypatch.setattr(
        warehouse, "rows", lambda sql, params=None, label='': asked.append(sql) or [_sales_row()]
    )
    monkeypatch.setattr(queries, "SELL_IN", "")
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    SnowflakeSource().dataset()

    # Named rather than counted: the screen reads several queries, and a count would turn
    # "the unwritten one was skipped" into "exactly this many exist today".
    assert not any("f_management_operating_profit_country" in sql for sql in asked)


def test_a_cached_read_does_not_count_sell_in_twice(monkeypatch):
    """The disk cache holds sell-out and sell-in together, because that is what was
    concatenated before it was written. Reading it and then appending sell-in again
    would inflate every invoiced euro on the second render — and a screen that grows
    its own revenue by being looked at twice is the worst failure available here.
    """
    from app.perf import queries
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    sell_in = {
        "entity": "M_103",
        "market": "Japan",
        "region": "JAPAN",
        "segment": "DIS - Distributors",
        "period": "2026-06",
        "sales_actual": 500.0,
        "sales_last_year": 400.0,
    }

    def counted(sql, params=None, label=''):
        if "f_management_operating_profit_country" in sql:
            return [dict(sell_in)]
        return [_sales_row()]

    monkeypatch.setattr(warehouse, "rows", counted)
    monkeypatch.setattr(queries, "SELL_IN", "select 1 from f_management_operating_profit_country")
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    first = SnowflakeSource().dataset()
    source_module.cache_clear()  # the process restarts; the file does not
    cached = SnowflakeSource().dataset()

    assert cached.sales_actual == first.sales_actual


# ------------------------------------------------------- the history behind the month


def _history_row(period="2026-07", actual=1_000_000.0, budget=1_200_000.0):
    return {
        "market": "Japan",
        "channel": "ecommerce",
        "period": period,
        "sales_actual": actual,
        "sales_budget": budget,
    }


def _labelled(monkeypatch, history_rows):
    """A warehouse that answers each query differently, and records what was asked."""
    from app.perf import warehouse

    asked = []

    def rows(sql, params=None, label=''):
        asked.append(label)
        if label == "SALES_HISTORY":
            return [dict(row) for row in history_rows]
        return [_sales_row()]

    monkeypatch.setattr(warehouse, "rows", rows)
    return asked


def test_the_history_reaches_the_screen(monkeypatch):
    from app.perf import source as source_module
    from app.perf.source import SnowflakeSource

    _labelled(monkeypatch, [
        _history_row("2026-06", 900_000.0, 1_200_000.0),
        _history_row("2026-07", 1_000_000.0, 1_200_000.0),
    ])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    dataset = SnowflakeSource().dataset()

    assert dataset.ytd is not None
    # The workbook is the plan, and it covers July here but not June. So July is the
    # matched pair and June is unbudgeted — not quietly filled from the goals fact, which
    # is the whole point: a total assembled from two definitions of "plan" reconciles
    # with neither of them.
    assert dataset.ytd.actual == 1_000_000.0
    assert dataset.ytd.budget == 1_861_700.0
    assert dataset.ytd.unbudgeted_actual == 900_000.0
    assert dataset.ytd.plan_source == "the planning workbook"
    # The trend runs on the workbook too, so it reaches exactly as far as the workbook
    # does — one month here. The rows also carry the warehouse's own targets, which would
    # buy two years of depth; using them would mean ranking on a source the business has
    # ruled unreliable, so the depth is given up on purpose.
    assert dataset.units[0].months_below_budget == 1
    source_module.cache_clear()


def test_the_history_is_cached_apart_from_the_month(monkeypatch):
    """Two years of history is the expensive read, and a month that closed a year ago
    will not move again. Paying for it on every refresh would put the whole wait back."""
    from app.perf import source as source_module
    from app.perf.source import SnowflakeSource

    asked = _labelled(monkeypatch, [_history_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    SnowflakeSource().dataset()
    SnowflakeSource().dataset(refresh=True)

    assert asked.count("SALES_AND_DRIVERS") == 2
    assert asked.count("SALES_HISTORY") == 1
    source_module.cache_clear()


def test_a_history_that_ends_before_the_month_on_screen_is_read_again(monkeypatch):
    """The only staleness that can mislead anyone. A cached history is as current as it
    needs to be while its last month is the month being read — and useless the moment it
    is not, because the month everyone is looking at would be missing from its own trend.
    """
    from app.perf import source as source_module
    from app.perf.source import SnowflakeSource

    asked = _labelled(monkeypatch, [_history_row("2026-05")])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    SnowflakeSource().dataset()
    source_module.cache_clear()
    SnowflakeSource().dataset()

    assert asked.count("SALES_HISTORY") == 2


def test_a_history_that_fails_does_not_take_the_screen_with_it(monkeypatch):
    """It is context around the figures, not the figures. Without it the cockpit compares
    one month to one plan, which is what it did before this existed."""
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    def rows(sql, params=None, label=''):
        if label == "SALES_HISTORY":
            raise RuntimeError("the history view is not granted to this role")
        return [_sales_row()]

    monkeypatch.setattr(warehouse, "rows", rows)
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    dataset = SnowflakeSource().dataset()

    assert dataset.sales_actual > 0
    assert dataset.ytd is None
    source_module.cache_clear()


def test_the_terminal_and_the_screen_share_one_history_read(monkeypatch):
    """Two years of history is the expensive read here. A command that ignored the
    screen's cache would pay it again in full — and three times over for someone looking
    at the year, then at a market, then at what carries no plan."""
    from app.perf import source as source_module

    rows = [_history_row("2026-07")]
    source_module.store_history_rows(rows)

    stored = source_module.cached_history_rows()

    assert stored is not None
    kept, read_at_text = stored
    assert kept == rows
    assert read_at_text.endswith("UTC")


def test_a_history_written_from_the_terminal_is_found_by_the_screen(monkeypatch):
    """Whoever paid for the query, the other one benefits. Otherwise the first screen
    opened after a terminal session pays for a read that already happened."""
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    source_module.store_history_rows([_history_row("2026-07", 900_000.0, 1_200_000.0)])
    asked = _labelled(monkeypatch, [])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    dataset = SnowflakeSource().dataset()

    assert "SALES_HISTORY" not in asked
    assert dataset.ytd is not None
    source_module.cache_clear()


def test_the_screen_shows_one_month_of_sell_in_and_the_year_keeps_them_all():
    """One query, two questions. The screen is a month and the year to date is a year, so
    the query stopped deciding and the callers filter. Before this, the year to date added
    one month of sell-in to four months of sell-out and nothing said so — €21m where €98m
    belonged."""
    from app.perf.source import _sell_in_month

    rows = [{"market": "Japan", "channel": "ecommerce", "period": "2026-07"}]
    rows += [{"market": "Japan", "segment": "DIS - Distributors",
              "period": "2026-%02d" % n, "sales_actual": 100.0} for n in range(4, 8)]

    current = _sell_in_month(rows, rows[1:], "2026-07")

    assert len(current) == 2
    assert {str(r.get("period")) for r in current} == {"2026-07"}


def test_two_sources_that_close_on_different_months_do_not_empty_the_screen():
    """The consolidation is cut on a snapshot date, the sell-out warehouse on a
    transaction date, and they can disagree. Filtering blindly on the sell-out month would
    drop the whole sell-in perimeter and leave a calm-looking page missing a third of the
    Maison — the one failure this module exists to prevent."""
    from app.perf.source import _sell_in_month

    rows = [{"market": "Japan", "channel": "ecommerce", "period": "2026-07"}]
    rows += [{"market": "Japan", "segment": "DIS - Distributors",
              "period": "2026-%02d" % n, "sales_actual": 100.0} for n in range(4, 7)]

    current = _sell_in_month(rows, rows[1:], "2026-07")

    # The sell-out row and the sell-in's own latest month, not an empty perimeter.
    assert len(current) == 2
    assert any(r.get("segment") and r["period"] == "2026-06" for r in current)


def test_the_headline_month_names_the_other_one_when_they_differ():
    """On real data the two sources diverged — sell-out closed on July, the consolidation
    on June — and the headline still said "July 2026 sales" over a figure holding June's
    shipments."""
    from app.perf.source import _period_label

    assert _period_label("2026-07") == "July 2026 sales · last complete month"
    assert _period_label("2026-07", "2026-07") == "July 2026 sales · last complete month"
    assert _period_label("2026-07", "2026-06").endswith("· partner invoices to June")
