from PySide6 import QtWidgets

from NanoVNASaver.Controls.SweepEvaluate import SweepEvaluate
from NanoVNASaver.Touchstone import Touchstone
from NanoVNASaver.RFTools import Datapoint


def test_touchstone_cleared_before_test(monkeypatch):
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])

    class FakeApp:
        pass

    fake_app = FakeApp()
    # Start with non-empty Touchstone data
    fake_app.data = Touchstone()
    fake_app.data.s11 = [Datapoint(900000000, 0.5, 0.0)]
    fake_app.ref_data = Touchstone()

    se = SweepEvaluate(fake_app)

    # stub input dialog and sweep_start
    monkeypatch.setattr(QtWidgets.QInputDialog, 'getText', lambda *a, **k: ("SN1", True))
    called = {'started': False}

    def fake_start():
        called['started'] = True

    fake_app.sweep_start = fake_start

    # Call handler
    se._on_test_button_clicked()

    # Touchstone data should have been reset to empty
    assert fake_app.data.s11 == []
    assert isinstance(fake_app.data, Touchstone)
    assert called['started'] is True
