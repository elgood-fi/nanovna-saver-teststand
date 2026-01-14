from NanoVNASaver.TestSpec import parse_test_spec, evaluate_test_point, evaluate_testspec, TestPoint, TestSpec
from NanoVNASaver.RFTools import Datapoint
from pathlib import Path


def dp_with_gain(freq, gain_db):
    mag = 10 ** (gain_db / 20.0)
    return Datapoint(freq, mag, 0.0)


def test_parse_test_spec_found():
    p = Path("test_spec.json")
    spec = parse_test_spec(str(p))
    assert spec is not None
    assert isinstance(spec.tests, list)
    assert "sweep" in spec.sweep


def test_evaluate_point_over_pass():
    data = [dp_with_gain(995, 6.0), dp_with_gain(1000, 6.0), dp_with_gain(1005, 6.0)]
    tp = TestPoint(name="T1", parameter="s21", frequency=1000, span=20, limit_db=5.0, direction="over")
    r = evaluate_test_point(data, tp)
    assert r["pass"] is True
    assert r["min"] >= 5.0


def test_evaluate_point_under_pass():
    data = [dp_with_gain(49990, -6.0), dp_with_gain(50000, -6.0), dp_with_gain(50010, -6.0)]
    tp = TestPoint(name="T2", parameter="s11", frequency=50000, span=40, limit_db=-3.0, direction="under")
    r = evaluate_test_point(data, tp)
    assert r["pass"] is True
    assert r["max"] <= -3.0


def test_evaluate_testspec_mixed():
    s11 = [dp_with_gain(1000, -20.0), dp_with_gain(2000, -20.0)]
    s21 = [dp_with_gain(1000, -1.0), dp_with_gain(2000, -10.0)]
    spec = TestSpec(sweep={}, tests=[
        TestPoint(name="P1", parameter="s21", frequency=1000, span=10, limit_db=-3.0, direction="over"),
        TestPoint(name="P2", parameter="s21", frequency=2000, span=10, limit_db=-5.0, direction="under"),
    ])
    results = evaluate_testspec(s11, s21, spec)
    assert len(results) == 2
    assert results[0]["pass"] is True
    assert results[1]["pass"] is False
