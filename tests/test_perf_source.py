

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
