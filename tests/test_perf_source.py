

def test_the_screen_serves_an_expired_reading_rather_than_making_anyone_wait():
    """A cockpit that occasionally takes three minutes to open is a cockpit nobody opens.

    Expired is not absent: an hour-old reading answers the same questions as a fresh one,
    and a page held open for the length of a warehouse read answers none. Refreshing is
    something the reader asks for, never something that happens to them.
    """
    import inspect

    from app.perf import source as source_module
    from app.routes import today as today_route

    signature = inspect.signature(source_module.SnowflakeSource.dataset)
    assert "wait_for_warehouse" in signature.parameters
    assert signature.parameters["wait_for_warehouse"].default is True

    # The screen is the one caller that must never wait, and it only accepts the cost when
    # the reader asked for it by refreshing.
    called = inspect.getsource(today_route.today)
    assert "wait_for_warehouse=refresh" in called


def test_the_units_are_rebuilt_when_the_published_file_changes(monkeypatch):
    """The closing file is dropped into `var/` from a terminal while the server runs,
    exactly as the notes are. The units in memory carry the published month baked in, so
    a new file waited an hour or a restart to reach the top of the screen while every
    terminal command already read it. The file's timestamp is part of what the cache is
    keyed on now."""
    import os

    from app.config import settings
    from app.perf import source as source_module
    from app.perf import warehouse
    from app.perf.source import SnowflakeSource
    from tests.test_perf_actuals import MAISON, _named, _workbook
    from tests.test_perf_warehouse import _budget_for, _sales_row

    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None, label='': [_sales_row()])
    monkeypatch.setattr(SnowflakeSource, "_budget", lambda self: _budget_for())
    path = settings.actuals_path
    if path.exists():
        os.remove(str(path))
    try:
        before = SnowflakeSource().dataset()
        assert not before.headline_is_published

        # The screen is July's; a file speaking for August is refused, and says so.
        _workbook(path, {"DATA AUGUST": _named([
            [MAISON, "E001", "GE COUNTRIES", "Northland", "Sell out", "Retail",
             120.0, 110.0, 100.0],
        ])})
        wrong_month = SnowflakeSource().dataset()
        assert not wrong_month.headline_is_published
        assert "August" in wrong_month.published_note and "July" in wrong_month.published_note

        _workbook(path, {"DATA JULY": _named([
            [MAISON, "E001", "GE COUNTRIES", "Northland", "Sell out", "Retail",
             120.0, 110.0, 100.0],
        ])})
        after = SnowflakeSource().dataset()

        assert after.headline_is_published
        assert after.headline_actual == 120_000.0
        assert after.published_note == ""
    finally:
        if path.exists():
            os.remove(str(path))
        source_module.cache_clear()
