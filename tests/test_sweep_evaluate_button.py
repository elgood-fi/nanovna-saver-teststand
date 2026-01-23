from PySide6 import QtWidgets

from NanoVNASaver.Controls.SweepEvaluate import SweepEvaluate
from NanoVNASaver.TestSpec import TestSpec


def ensure_qapp():
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])


class FakeCal:
    def __init__(self, valid=False):
        self._valid = valid

    def isValid1Port(self):
        return self._valid


class FakeVNA:
    def __init__(self, connected=False):
        self._connected = connected

    def connected(self):
        return self._connected


class FakeLot:
    def __init__(self):
        self.pcb_lot_field = QtWidgets.QLineEdit()
        # Simulate currently selected lot name (None when not selected)
        self.current_lot_name = None


def test_test_button_disabled_when_lot_not_selected_even_if_others_ok():
    ensure_qapp()
    app = FakeApp(cal_valid=True, vna_connected=True)

    se = SweepEvaluate(app)

    # PCB lot set, spec loaded, cal valid, vna connected, but no lot selected -> disabled
    app.lot_control.pcb_lot_field.setText("LOT-1")
    se.spec = TestSpec(sweep={}, tests=[])
    app.lot_control.current_lot_name = None

    se.update_test_button_state()
    assert not se.btn_test.isEnabled()


class FakeApp:
    def __init__(self, cal_valid=False, vna_connected=False):
        self.calibration = FakeCal(cal_valid)
        self.vna = FakeVNA(vna_connected)
        self.lot_control = FakeLot()
        # other attributes referenced by SweepEvaluate are optional and handled by try/except


def test_test_button_disabled_when_missing_conditions():
    ensure_qapp()
    app = FakeApp(cal_valid=False, vna_connected=False)

    se = SweepEvaluate(app)

    # No spec loaded, pcb lot empty, calibration invalid, device disconnected -> disabled
    se.update_test_button_state()
    assert not se.btn_test.isEnabled()


def test_test_button_enabled_when_all_conditions_met():
    ensure_qapp()
    app = FakeApp(cal_valid=True, vna_connected=True)

    se = SweepEvaluate(app)

    # Set pcb lot
    app.lot_control.pcb_lot_field.setText("LOT-123")
    # Load a dummy spec
    se.spec = TestSpec(sweep={}, tests=[])

    se.update_test_button_state()
    assert se.btn_test.isEnabled()


def test_load_spec_assigns_tests_to_charts(tmp_path):
    ensure_qapp()
    app = FakeApp(cal_valid=True, vna_connected=True)
    se = SweepEvaluate(app)

    spec = {
        "sweep": {},
        "tests": [
            {"name": "P1", "parameter": "s11", "frequency": 1000, "span": 10, "limit_db": -3.0, "direction": "under"},
            {"name": "P2", "parameter": "s21", "frequency": 2000, "span": 20, "limit_db": -5.0, "direction": "over"},
        ],
    }
    p = tmp_path / "spec.json"
    p.write_text(__import__("json").dumps(spec))

    se.load_spec(str(p))
    # s11 chart should receive only s11 tests
    assert se.s11_chart.testspec is not None
    assert len(se.s11_chart.testspec.tests) == 1
    assert se.s11_chart.testspec.tests[0].parameter.lower() == "s11"

    assert se.s21_chart.testspec is not None
    assert len(se.s21_chart.testspec.tests) == 1
    assert se.s21_chart.testspec.tests[0].parameter.lower() == "s21"
