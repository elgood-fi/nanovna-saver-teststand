from pathlib import Path

import pytest

from NanoVNASaver.Controls.LotControl import save_s1p, save_s2p
from NanoVNASaver.Touchstone import Touchstone
from NanoVNASaver.RFTools import Datapoint


def make_simple_touchstone():
    t = Touchstone()
    # make a couple of datapoints for s11
    t.s11 = [Datapoint(1000000, 1.0, 0.0), Datapoint(2000000, 0.5, -0.1)]
    return t


def test_save_s1p_creates_file(tmp_path):
    t = make_simple_touchstone()
    out = save_s1p(t, tmp_path, "mytest")
    assert Path(out).exists()
    with open(out, encoding="utf-8") as f:
        data = f.read()
    assert data == t.saves(1)


def test_save_s2p_requires_s21(tmp_path):
    t = make_simple_touchstone()
    with pytest.raises(ValueError):
        save_s2p(t, tmp_path, "mytest")


def test_save_s2p_creates_file(tmp_path):
    t = make_simple_touchstone()
    # create matching s21 datapoints
    t.s21 = [Datapoint(1000000, 0.0, 0.0), Datapoint(2000000, 0.0, 0.0)]
    out = save_s2p(t, tmp_path, "both")
    assert Path(out).exists()
    with open(out, encoding="utf-8") as f:
        data = f.read()
    assert data == t.saves(4)
