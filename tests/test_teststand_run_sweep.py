from NanoVNASaver.TestStand import NanoVNASaver, TestSpec, TestPoint


def test_evaluate_starts_sweep(monkeypatch):
    app = NanoVNASaver(no_save_config=True, no_load_config=True)
    # create a simple spec with sweep
    spec = TestSpec(sweep={"start": 1000, "stop": 2000, "points": 11, "segments": 1}, tests=[])
    app.test_spec = spec

    called = {}

    def fake_sweep_start():
        called["started"] = True

    monkeypatch.setattr(app, "sweep_start", fake_sweep_start)
    # Ensure initial sweep params different
    assert app.sweep.start != 1000 or app.sweep.end != 2000

    app.evaluate_test_points()

    assert getattr(app, "_test_pending", False) is True
    # sweep_start should have been called
    assert called.get("started", False) is True
    # sweep parameters should have been updated
    assert app.sweep.start == 1000
    assert app.sweep.end == 2000
