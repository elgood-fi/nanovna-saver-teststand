from PySide6 import QtWidgets

from NanoVNASaver.Controls.SweepEvaluate import SweepEvaluate
from NanoVNASaver.Controls.LotControl import LotControl


def test_warning_shown_on_checksum_mismatch(monkeypatch):
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])

    class FakeApp:
        pass

    fake_app = FakeApp()
    # attach required components
    se = SweepEvaluate(fake_app)
    lc = LotControl(fake_app)
    fake_app.sweep_evaluate = se
    fake_app.lot_control = lc

    # simulate a lot selected with checksum 'aaa'
    lc.current_lot_name = 'lotA'
    lc.lot_checksum['lotA'] = 'aaa'

    # set a different checksum on the loaded spec
    se.test_checksum = 'bbb'

    # intercept QMessageBox.warning
    called = {}

    def fake_warning(parent, title, text):
        called['title'] = title
        called['text'] = text

    monkeypatch.setattr(QtWidgets.QMessageBox, 'warning', lambda *a, **k: fake_warning(*a, **k))
    # stub input dialog to not block
    monkeypatch.setattr(QtWidgets.QInputDialog, 'getText', lambda *a, **k: ("SN1", True))
    # stub sweep_start to record call
    called['sweep_started'] = False

    def fake_start():
        called['sweep_started'] = True

    fake_app.sweep_start = fake_start

    # Call the handler
    se._on_test_button_clicked()

    assert called.get('text') == "Warning! Uncrecognized test configuration checksum detected!"
    # And sweep should still be started
    assert called['sweep_started'] is True
