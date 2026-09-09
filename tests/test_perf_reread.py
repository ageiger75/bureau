"""La relecture automatique : le serveur relit l'entrepôt quand la lecture a passé l'âge,
jamais sous un lecteur, jamais sur les données de démonstration."""

from __future__ import annotations

from app.perf import reread as R


def test_a_reading_is_due_past_its_age_or_before_the_first_one():
    hour = 3600.0
    assert R.due(6 * hour, age=7 * hour)
    assert not R.due(6 * hour, age=5 * hour)
    assert R.due(6 * hour, age=None)
    # Zéro heure : désactivé, même sans lecture.
    assert not R.due(0.0, age=None)


def test_the_thread_only_starts_in_front_of_a_warehouse_and_once(monkeypatch):
    import threading

    from app.config import settings

    monkeypatch.setattr(R, "_thread", None)
    assert R.start(max_age_hours=6.0) is False          # données de démonstration

    monkeypatch.setattr(type(settings), "reads_warehouse", property(lambda self: True))
    started = []

    class Recorded:
        def __init__(self, target=None, name="", daemon=False):
            self.daemon = daemon

        def start(self):
            started.append(self.daemon)

    monkeypatch.setattr(threading, "Thread", Recorded)
    assert R.start(max_age_hours=0.0) is False          # désactivé par le réglage
    assert R.start(max_age_hours=6.0) is True
    assert started == [True]
    assert R.start(max_age_hours=6.0) is False          # une seule fois par serveur


def test_the_reread_follows_the_refresh_order_and_waits_for_the_warehouse(monkeypatch):
    from types import SimpleNamespace

    calls = []
    fake = SimpleNamespace(
        dataset=lambda refresh=False, wait_for_warehouse=False: calls.append(("dataset", refresh, wait_for_warehouse)),
        client_kpis=lambda wait_for_warehouse=False: calls.append(("kpis", wait_for_warehouse)),
        product_rows=lambda wait_for_warehouse=False: calls.append(("products", wait_for_warehouse)),
    )
    monkeypatch.setattr(R.source, "current_source", lambda: fake)

    R.reread_all()

    assert calls == [("dataset", True, True), ("kpis", True), ("products", True)]


def test_the_age_setting_is_read_in_hours_and_zero_disables(monkeypatch):
    from app import config

    assert config._hours("", 6.0) == 6.0
    assert config._hours("12", 6.0) == 12.0
    assert config._hours("0", 6.0) == 0.0
    assert config._hours("1,5", 6.0) == 1.5
