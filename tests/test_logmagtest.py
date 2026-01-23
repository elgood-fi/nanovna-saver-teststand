from NanoVNASaver.Charts import LogMagTest
from NanoVNASaver.TestSpec import TestPoint, TestSpec
from NanoVNASaver.RFTools import Datapoint


def make_data(start=1000, stop=2000, step=100):
    data = []
    for f in range(start, stop + 1, step):
        # use unit magnitude (0 dB) for simplicity
        data.append(Datapoint(f, 1.0, 0.0))
    return data


def test_compute_test_marker_positions_and_y_values():
    chart = LogMagTest("Test")
    data = make_data()
    chart.setData(data)
    chart.fixedValues = True
    chart.minDisplayValue = -10
    chart.maxDisplayValue = 10
    # Establish start/stop and scaling
    chart._set_start_stop()
    chart.calc_scaling()

    tp = TestPoint(name="T1", parameter="s21", frequency=1500, span=200, limit_db=-3.0, direction="under")
    geom = chart.compute_test_marker(tp)

    expected_left = chart.getXPosition(Datapoint(1400, 0, 0))
    expected_right = chart.getXPosition(Datapoint(1600, 0, 0))
    assert geom["x_left"] == expected_left
    assert geom["x_right"] == expected_right

    # expect x_mid to be the center (match position at 1500)
    expected_mid = chart.getXPosition(Datapoint(1500, 0, 0))
    assert geom["x_mid"] == expected_mid

    # non-inverted: value should be the raw limit_db (-3.0)
    value = -3.0
    expected_y = chart.topMargin + round((chart.maxValue - value) / chart.span * chart.dim.height)
    assert geom["y"] == expected_y
    assert geom["direction"] == "under"

    # For "under" the vertical line should start at the top margin
    assert geom["line_start_y"] == chart.topMargin


def test_limit_y_value_respects_inversion():
    chart = LogMagTest("TestInv")
    data = make_data()
    chart.setData(data)
    chart.fixedValues = True
    chart.minDisplayValue = -10
    chart.maxDisplayValue = 10
    chart._set_start_stop()
    chart.calc_scaling()

    tp = TestPoint(name="T2", parameter="s11", frequency=1500, span=200, limit_db=-3.0, direction="over")

    # not inverted
    geom = chart.compute_test_marker(tp)
    val_not_inv = -3.0
    expected_y_not_inv = chart.topMargin + round((chart.maxValue - val_not_inv) / chart.span * chart.dim.height)
    assert geom["y"] == expected_y_not_inv

    # For "over" the vertical line should start at the bottom of the chart
    assert geom["line_start_y"] == chart.topMargin + chart.dim.height

    # set inversion and re-evaluate
    chart.isInverted = True
    geom_inv = chart.compute_test_marker(tp)
    # inverted value is -limit_db (i.e., 3.0)
    val_inv = 3.0
    expected_y_inv = chart.topMargin + round((chart.maxValue - val_inv) / chart.span * chart.dim.height)
    assert geom_inv["y"] == expected_y_inv
    assert geom_inv["direction"] == "over"
    # line start should still be bottom for "over"
    assert geom_inv["line_start_y"] == chart.topMargin + chart.dim.height
