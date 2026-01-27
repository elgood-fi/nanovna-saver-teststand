from pathlib import Path
from PySide6 import QtWidgets

from NanoVNASaver.Controls.LotControl import LotControl


def test_lot_checksum_on_create(tmp_path: Path):
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])

    class FakeApp:
        pass

    fake_app = FakeApp()
    # Provide a SweepEvaluate-like object with test_checksum
    fake_app.sweep_evaluate = type("X", (), {"test_checksum": "deadbeef"})()

    lc = LotControl(fake_app)
    lc.working_directory = tmp_path

    # Create a new lot on disk
    lc.add_lot("lotX", None, samples=0, passed=0, failed=0, create_on_disk=True)

    info_file = tmp_path / "lotX" / "lotX.json"
    assert info_file.exists()
    with info_file.open("r", encoding="utf-8") as f:
        import json

        info = json.load(f)
    assert info.get("checksum") == "deadbeef"
    assert lc.lot_checksum.get("lotX") == "deadbeef"


def test_lot_checksum_none_when_not_set(tmp_path: Path):
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])

    class FakeApp:
        pass

    fake_app = FakeApp()
    # No sweep_evaluate present on fake_app

    lc = LotControl(fake_app)
    lc.working_directory = tmp_path

    lc.add_lot("lotY", None, samples=0, passed=0, failed=0, create_on_disk=True)
    info_file = tmp_path / "lotY" / "lotY.json"
    assert info_file.exists()
    with info_file.open("r", encoding="utf-8") as f:
        import json

        info = json.load(f)
    assert info.get("checksum") is None
    assert lc.lot_checksum.get("lotY") is None
