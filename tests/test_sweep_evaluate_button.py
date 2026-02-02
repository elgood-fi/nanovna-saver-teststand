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
        # Simulate an explicitly set PCB lot value (None until 'Set' is used)
        self.pcb_lot_value = None
        # Simulate currently selected lot name (None when not selected)
        self.current_lot_name = None
        # Minimal signal-like helper so tests can emulate emission
        class _Sig:
            def __init__(self):
                self._cbs = []
            def connect(self, cb):
                self._cbs.append(cb)
            def emit(self):
                for cb in list(self._cbs):
                    try:
                        cb()
                    except Exception:
                        pass
        self.pcb_lot_changed = _Sig()


def test_test_button_disabled_when_lot_not_selected_even_if_others_ok():
    ensure_qapp()
    app = FakeApp(cal_valid=True, vna_connected=True)

    se = SweepEvaluate(app)

    # PCB lot set, spec loaded, cal valid, vna connected, but no lot selected -> disabled
    app.lot_control.pcb_lot_value = "LOT-1"
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

    # Set pcb lot (must be explicitly set via 'Set')
    app.lot_control.pcb_lot_value = "LOT-123"
    # Load a dummy spec
    se.spec = TestSpec(sweep={}, tests=[])

    se.update_test_button_state()
    assert se.btn_test.isEnabled()


def test_enter_key_triggers_test_button(monkeypatch):
    ensure_qapp()
    app = FakeApp(cal_valid=True, vna_connected=True)
    se = SweepEvaluate(app)

    # Ensure button is enabled
    app.lot_control.pcb_lot_value = "LOT-1"
    se.spec = TestSpec(sweep={}, tests=[])
    se.update_test_button_state()
    assert se.btn_test.isEnabled()

    # Replace the handler with a simple marker so the dialog isn't shown
    called = {"ok": False}

    def fake_start():
        called["ok"] = True

    monkeypatch.setattr(se, "_on_test_button_clicked", fake_start)

    # Send Return key event to the widget
    evt = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, Qt.Key_Return, QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(se, evt)
    QtWidgets.QApplication.processEvents()

    assert called["ok"] is True


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


def test_pcb_lot_set_signal_enables_button():
    ensure_qapp()
    app = FakeApp(cal_valid=True, vna_connected=True)
    se = SweepEvaluate(app)

    # Spec loaded and lot selected, but pcb not explicitly set -> disabled
    se.spec = TestSpec(sweep={}, tests=[])
    app.lot_control.current_lot_name = "lot1"
    app.lot_control.pcb_lot_value = None
    se.update_test_button_state()
    assert not se.btn_test.isEnabled()

    # Now set the value and emit the signal that the control would emit when pressing 'Set'
    app.lot_control.pcb_lot_value = "LOTX"
    app.lot_control.pcb_lot_changed.emit()
    assert se.btn_test.isEnabled()
