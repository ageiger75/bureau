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
    """SALES_AND_DRIVERS is written against the real schema; the other five are not.

    Kept as an inventory rather than deleted: `missing()` is what the 503 page lists, so a
    query that silently stopped counting as written would produce a screen claiming a
    source is ready when it is not. Narrow this set as each query lands — and when it
    empties, the mapping tests are what should exist in its place.
    """
    assert set(queries.missing()) == {
        "SALES_HISTORY",
        "KPI_READINGS",
        "MARKET_INDEX",
        "COMMITMENTS",
        "FORECAST_HISTORY",
    }


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
    assert "SALES_HISTORY" in response.text
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

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None: [_sales_row()])
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

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None: [_sales_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    dataset = SnowflakeSource().dataset()

    assert dataset.period_label == "July 2026 sales"


def test_the_screen_is_stamped_with_when_it_was_read(monkeypatch):
    """The warehouse is not yet stable within a day: sell-out facts are reprocessed on
    recent months, so the same query hours apart returns different figures for some
    markets. Two screens that disagree are a scandal; two screens stamped an hour apart
    are a fact about the pipeline."""
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None: [_sales_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    dataset = SnowflakeSource().dataset()

    # A date alone would not distinguish two reads taken the same morning.
    assert dataset.as_of.endswith("UTC")
    assert ":" in dataset.as_of


def test_a_query_that_returns_nothing_is_a_refusal_not_a_blank_screen(monkeypatch):
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None: [])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())

    with pytest.raises(NotImplementedError):
        SnowflakeSource().dataset()


def test_a_disagreement_between_file_and_warehouse_survives_to_the_source(monkeypatch):
    """It has to reach the screen, or nobody learns the two sources are drifting."""
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource

    monkeypatch.setattr(
        warehouse, "rows", lambda sql, params=None: [_sales_row(sales_budget=1_000_000.0)]
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

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None: [_sales_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())
    monkeypatch.setattr(today_route, "current_source", lambda: SnowflakeSource())

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Japan" in response.text
    # And says so, rather than showing an empty board that reads as "nothing outstanding".
    assert "Not connected to this source yet" in response.text
