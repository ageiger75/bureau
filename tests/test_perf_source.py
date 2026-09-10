

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
    called = inspect.getsource(today_route._screen)
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
        assert "août" in wrong_month.published_note and "juillet" in wrong_month.published_note

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


def test_the_period_label_elides_before_a_vowel():
    from app.perf.source import _period_label

    assert _period_label("2026-08").startswith("Ventes d'août 2026")
    assert _period_label("2026-07").startswith("Ventes de juillet 2026")


def _kpi_source(monkeypatch):
    """A `SnowflakeSource` whose tracker and join are stubbed, so only the cache rule is
    under test — the workbook reader and the registry have their own suites."""
    from types import SimpleNamespace

    from app.config import settings
    from app.perf import kpi_registry, source as source_module, tracker

    monkeypatch.setattr(type(settings), "has_kpi_file", property(lambda self: True))
    monkeypatch.setattr(tracker, "read_tracker", lambda path: SimpleNamespace(entries=[]))
    monkeypatch.setattr(
        kpi_registry, "join_report",
        lambda registry, rows: SimpleNamespace(kpis=list(rows), unmatched_keys=[]),
    )
    monkeypatch.setattr(source_module, "_kpi_coverage", lambda report, registry: "")
    return source_module.SnowflakeSource()


def test_the_kpi_panel_never_makes_a_reader_wait_for_its_three_minute_read(monkeypatch):
    """The reading is a three-minute query, and the page used to run it the first time
    its day-old cache expired: one second for a day, then four minutes once, and the
    reader learnt that the cockpit is slow. A reader now gets the last reading whatever
    its age; only a refresh pays the query."""
    import pytest

    from app.perf import source as source_module, warehouse

    source = _kpi_source(monkeypatch)
    calls = []
    monkeypatch.setattr(
        warehouse, "rows",
        lambda sql, params=None, label="": calls.append(label) or [("fresh",)],
    )
    written = []
    monkeypatch.setattr(source_module, "_write_kpi_cache", lambda rows: written.append(rows))
    caches = {"fresh": None, "any": None}
    monkeypatch.setattr(
        source_module, "_read_kpi_cache",
        lambda any_age=False: caches["any" if any_age else "fresh"],
    )

    # Never read: the reader is told so, and the warehouse is not touched.
    with pytest.raises(source_module.NotReadYet):
        source.client_kpis(wait_for_warehouse=False)
    assert calls == []

    # Expired: served as it is, with the warehouse still untouched.
    caches["any"] = [("yesterday",)]
    assert source.client_kpis(wait_for_warehouse=False) == [("yesterday",)]
    assert calls == []

    # A refresh, or any caller with nobody in front of it, pays the read and stores it.
    assert source.client_kpis() == [("fresh",)]
    assert calls == ["KPI_READINGS"] and written == [[("fresh",)]]


def test_the_history_is_served_expired_rather_than_re_read_under_a_reader(monkeypatch):
    """Expired by age and not by anchor is the same history, a day older. Only a history
    that does not end on the month on screen is worth a query while someone waits."""
    from types import SimpleNamespace

    from app.perf import history as history_module
    from app.perf import queries, source as source_module, warehouse

    monkeypatch.setattr(queries, "SALES_HISTORY", "select 1")
    reads = []
    monkeypatch.setattr(
        warehouse, "rows",
        lambda sql, params=None, label="": reads.append(label) or [{"period": "2026-08"}],
    )
    monkeypatch.setattr(source_module, "_write_disk_cache", lambda *a, **k: None)

    def stored(name=source_module.CACHE_FILE, max_age=None):
        if name != source_module.HISTORY_CACHE_FILE:
            return None
        if max_age == float("inf"):
            return [{"period": "2026-08"}], 0.0, "long ago"
        return None  # expired by age

    monkeypatch.setattr(source_module, "_read_disk_cache", stored)

    class Built:
        def __init__(self, rows):
            self.latest_period = rows[0]["period"]

        def __len__(self):
            return 1

    monkeypatch.setattr(history_module, "from_rows", Built)
    source = source_module.SnowflakeSource()

    # Same anchor, reader waiting: the old file serves, no query.
    served = source._history(queries, warehouse, "2026-08", wait_for_warehouse=False)
    assert served.latest_period == "2026-08" and reads == []
    # The screen moved a month on: that staleness misleads, so it is read even now.
    source._history(queries, warehouse, "2026-09", wait_for_warehouse=False)
    assert reads == ["SALES_HISTORY"]
    # Nobody waiting: the expired file is re-read.
    source._history(queries, warehouse, "2026-08", wait_for_warehouse=True)
    assert reads == ["SALES_HISTORY", "SALES_HISTORY"]


def test_the_screen_only_pays_the_kpi_read_when_the_reader_refreshed():
    import inspect

    from app.routes import today as today_route

    assert "client_kpis(wait_for_warehouse=refresh)" in inspect.getsource(today_route._screen)


def test_ucfirst_raises_the_first_letter_and_leaves_names_alone():
    """`capitalize` lowered everything after the first letter, and the next event was
    printed as « singles day 11.11, china »."""
    from app.web import ucfirst

    assert ucfirst("le prochain au-delà : Singles Day 11.11, China") == (
        "Le prochain au-delà : Singles Day 11.11, China"
    )
    assert ucfirst("") == "" and ucfirst(None) == ""


def test_the_product_reading_never_waits_and_says_why_it_is_empty(monkeypatch):
    """La lecture produit suit la règle des KPI : jamais une requête sous un lecteur, la
    lecture d'hier sinon, et une note à la place d'une erreur tant que la requête n'est
    pas écrite ou pas encore lue sur cette machine."""
    from app.perf import queries, source as source_module, warehouse

    source = source_module.SnowflakeSource.__new__(source_module.SnowflakeSource)
    monkeypatch.setitem(queries.ALL, "PRODUCT_SALES", "")
    assert source.product_rows(wait_for_warehouse=True) == []
    assert "PRODUCT_SALES" in source.product_note

    monkeypatch.setitem(queries.ALL, "PRODUCT_SALES", "select 1")
    calls = []
    monkeypatch.setattr(warehouse, "rows",
                        lambda sql, params=None, label="": calls.append(label) or [("fresh",)])
    written = []
    monkeypatch.setattr(source_module, "_write_query_cache", lambda name, rows: written.append(rows))
    caches = {"fresh": None, "any": None}
    monkeypatch.setattr(source_module, "_read_query_cache",
                        lambda name, any_age=False: caches["any" if any_age else "fresh"])

    started = []
    monkeypatch.setattr(source_module, "read_behind", lambda name: started.append(name) or True)
    assert source.product_rows() == []
    assert "pas encore eu lieu" in source.product_note and calls == []
    # Jamais sous le lecteur, mais lancée derrière lui : la page se recharge quand elle atterrit.
    assert started == ["products"]

    caches["any"] = [("yesterday",)]
    assert source.product_rows() == [("yesterday",)]
    assert source.product_note == "" and calls == []

    assert source.product_rows(wait_for_warehouse=True) == [("fresh",)]
    assert calls == ["PRODUCT_SALES"] and written == [[("fresh",)]]


def test_the_product_reading_behind_the_screen_runs_once_and_writes_the_cache(monkeypatch):
    """Une lecture à la fois, une seule par vie du serveur, et le cache écrit à la fin :
    la page, qui guette l'horodatage du fichier, se recharge d'elle-même."""
    import threading

    from app.perf import queries, source as source_module, warehouse

    monkeypatch.setitem(source_module._behind, "products",
                        {"started": 0.0, "error": "", "running": False})
    monkeypatch.setitem(queries.ALL, "PRODUCT_SALES", "select 1")
    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None, label="": [("fresh",)])
    written = []
    monkeypatch.setattr(source_module, "_write_query_cache", lambda name, rows: written.append(rows))
    ran = []

    class Immediate:
        def __init__(self, target=None, name="", daemon=False):
            self.target = target

        def start(self):
            ran.append(True)
            self.target()

    monkeypatch.setattr(threading, "Thread", Immediate)

    assert source_module.read_products_behind() is True
    assert written == [[("fresh",)]] and ran == [True]
    assert source_module.products_behind_note() == ""

    # Un échec est gardé pour la page, et la lecture ne repart pas avant le délai.
    def broken(sql, params=None, label=""):
        raise RuntimeError("SQL compilation error: invalid identifier")

    monkeypatch.setattr(warehouse, "rows", broken)
    assert source_module.read_products_behind() is True
    assert "invalid identifier" in source_module.products_behind_note()
    assert source_module.read_products_behind() is False
    source_module._behind["products"]["started"] = 0.0
    assert source_module.read_products_behind() is True


def test_a_product_cache_written_by_another_query_is_not_this_reading(tmp_path, monkeypatch):
    """La fenêtre de la requête a changé un soir ; le lendemain, le cache de la veille était
    encore « du jour » et servait l'ancienne fenêtre en disant rien de neuf. L'empreinte
    de la requête voyage avec la lecture, et une autre requête ne la trouve pas."""
    from app.perf import queries, source as source_module

    monkeypatch.setattr(source_module, "_cache_path", lambda name=source_module.CACHE_FILE: tmp_path / name)
    monkeypatch.setitem(queries.ALL, "PRODUCT_SALES", "select 1")
    source_module._write_product_cache([{"scope": "LOEP"}])
    assert source_module._read_product_cache() == [{"scope": "LOEP"}]

    monkeypatch.setitem(queries.ALL, "PRODUCT_SALES", "select 2")
    assert source_module._read_product_cache() is None
    assert source_module._read_product_cache(any_age=True) is None


def test_an_expired_main_reading_is_re_read_behind_the_screen_once(monkeypatch):
    """Sans relance, une lecture expirée le restait jusqu'au réveil du fil de relecture,
    des heures ; et deux relances en même temps doublaient le temps de chacune."""
    import threading

    from app.perf import source as source_module

    started = threading.Event()
    release = threading.Event()
    calls = []

    class _Slow:
        def dataset(self, refresh=False, wait_for_warehouse=True):
            calls.append((refresh, wait_for_warehouse))
            started.set()
            release.wait(5)

    monkeypatch.setattr(source_module, "current_source", lambda: _Slow())
    monkeypatch.setitem(source_module._dataset_behind, "running", False)
    monkeypatch.setitem(source_module._dataset_behind, "error", "")

    assert source_module.read_dataset_behind() is True
    assert started.wait(5)
    assert source_module.dataset_reading() is True
    assert source_module.read_dataset_behind() is False
    release.set()
    for _ in range(100):
        if not source_module.dataset_reading():
            break
        threading.Event().wait(0.02)
    assert calls == [(True, True)]
    assert source_module.dataset_reading() is False


def test_the_reread_thread_does_not_start_a_second_main_reading(monkeypatch):
    from app.perf import reread, source as source_module

    monkeypatch.setattr(source_module, "dataset_reading", lambda: True)
    monkeypatch.setattr(source_module, "current_source",
                        lambda: (_ for _ in ()).throw(AssertionError("should not read")))

    reread.reread_all()


def test_a_main_cache_written_by_another_query_is_expired_and_not_fresh(monkeypatch):
    """Une colonne de plus dans la requête principale : la lecture d'hier se sert à qui
    attend, et se relit — elle ne passe pas pour la lecture du jour."""
    import time as _time

    from app.perf import source as source_module

    source_module._write_disk_cache([{"market": "Northland"}], _time.time(), "hier",
                                    fingerprint="ancienne")
    try:
        assert source_module._read_disk_cache(fingerprint="nouvelle") is None
        served = source_module._read_disk_cache(max_age=float("inf"))
        assert served is not None and served[0] == [{"market": "Northland"}]
        assert source_module._read_disk_cache(fingerprint="ancienne") is not None
    finally:
        source_module.cache_forget()
