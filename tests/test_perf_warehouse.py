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


def test_every_query_is_still_a_placeholder():
    """A reminder in executable form: nothing has been written against the real schema.

    When these are filled in, this test is the one to delete — and its failure is the
    signal that the mapping tests should exist by then.
    """
    assert set(queries.missing()) == set(queries.ALL)


def test_an_unwritten_query_makes_the_source_refuse_rather_than_return_nothing():
    """An empty cockpit looks like a business with no problems. That is the most
    expensive lie this product could tell."""
    from app.perf.source import SnowflakeSource

    with pytest.raises(NotImplementedError):
        SnowflakeSource().dataset()


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
