from PySide6 import QtWidgets

from NanoVNASaver.Controls.SweepEvaluate import SweepEvaluate
from NanoVNASaver.Touchstone import Touchstone
from NanoVNASaver.RFTools import Datapoint


def test_worker_init_called_on_test(monkeypatch):
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])

    class FakeWorker:
        def __init__(self):
            self.init_called = False
            self.rawData11 = [Datapoint(900000000, 1.0, 0.0)]
            self.signals = type("S", (), {"updated": type("E", (), {"emit": lambda *a, **k: None})()})()

        def init_data(self):
            self.init_called = True
            # simulate clearing of internal buffers
            self.rawData11 = []

    class FakeApp:
        pass

    fake_app = FakeApp()
    # Start with non-empty Touchstone data
    fake_app.data = Touchstone()
    fake_app.ref_data = Touchstone()

    # Attach fake worker with pre-filled rawData11
    fake_worker = FakeWorker()
    fake_app.worker = fake_worker

    se = SweepEvaluate(fake_app)

    # stub input dialog and sweep_start
    monkeypatch.setattr(QtWidgets.QInputDialog, 'getText', lambda *a, **k: ("SN1", True))
    called = {'started': False}

    def fake_start():
        called['started'] = True

    fake_app.sweep_start = fake_start

    # precondition
    assert fake_worker.rawData11 != []

    # Call handler
    se._on_test_button_clicked()

    # worker.init_data should have been called and rawData11 cleared
    assert fake_worker.init_called is True
    assert fake_worker.rawData11 == []
    assert called['started'] is True
