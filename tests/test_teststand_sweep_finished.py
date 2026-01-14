from NanoVNASaver.TestStand import NanoVNASaver, TestSpec, TestPoint
from NanoVNASaver.RFTools import Datapoint


def dp_with_gain(freq, gain_db):
    mag = 10 ** (gain_db / 20.0)
    return Datapoint(freq, mag, 0.0)


def test_sweep_finished_runs_evaluation():
    app = NanoVNASaver(no_save_config=True, no_load_config=True)
    # create a spec with a single test point
    spec = TestSpec(sweep={}, tests=[TestPoint(name='P1', parameter='s21', frequency=1000, span=10, limit_db=-3.0, direction='over')])
    app.test_spec = spec
    # populate s21 with sample points that pass
    app.data.s21 = [dp_with_gain(995, -6.0), dp_with_gain(1000, -6.0), dp_with_gain(1005, -6.0)]

    app._test_pending = True
    app.sweepFinished()

    assert getattr(app, "_test_pending", False) is False
    assert len(app.test_results) == 1
    assert app.test_results[0]['pass'] is True
