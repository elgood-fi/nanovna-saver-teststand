from pathlib import Path
import json

from PySide6 import QtWidgets

from NanoVNASaver.Controls.LotControl import LotControl
from NanoVNASaver.Touchstone import Touchstone
from NanoVNASaver.RFTools import Datapoint


class SimpleTD:
    pass


def test_unit_counts_and_transitions(tmp_path):
    # Ensure a QApplication exists for widget construction
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])

    class FakeApp:
        pass

    fake_app = FakeApp()
    fake_app.data = Touchstone()
    # populate s11 and s21 so export succeeds
    fake_app.data.s11 = [Datapoint(900000000, 0.5, 0.0)]
    fake_app.data.s21 = [Datapoint(900000000, 0.2, 0.0)]

    lc = LotControl(fake_app)

    # Prepare lot directory and selection
    lot_dir = tmp_path / "lotB"
    lot_dir.mkdir()
    lc.current_lot_name = "lotB"
    lc.current_lot_path = lot_dir

    # 1) Save a failing result for SNX -> should be added as failed
    td1 = SimpleTD()
    td1.serial = "SNX"
    td1.id = "id1"
    td1.passed = False
    td1.results = []

    lc.save_results_for_latest(td1)

    info_file = lot_dir / "lotB.json"
    assert info_file.exists()
    with info_file.open("r", encoding="utf-8") as f:
        info = json.load(f)
    assert info.get("passed_units") == 0
    assert info.get("failed_units") == 1
    units = info.get("units")
    assert any(u[0] == "SNX" and u[1] is False for u in units)
    assert abs(info.get("yield", 0.0) - 0.0) < 1e-6
    keys = list(info.keys())
    assert keys[-1] == "units"

    # 2) Save a passing result for SNX -> should update entry from false to true

    # 2) Save a passing result for SNX -> should update entry from false to true
    td2 = SimpleTD()
    td2.serial = "SNX"
    td2.id = "id2"
    td2.passed = True
    td2.results = []

    lc.save_results_for_latest(td2)

    with info_file.open("r", encoding="utf-8") as f:
        info = json.load(f)
    assert info.get("passed_units") == 1
    assert info.get("failed_units") == 0
    units = info.get("units")
    assert any(u[0] == "SNX" and u[1] is True for u in units)
    assert abs(info.get("yield", 0.0) - 1.0) < 1e-6
    keys = list(info.keys())
    assert keys[-1] == "units"

    # 3) Save a failing result for SNX after it's already passed -> should flip to failing
    td3 = SimpleTD()
    td3.serial = "SNX"
    td3.id = "id3"
    td3.passed = False
    td3.results = []

    lc.save_results_for_latest(td3)

    with info_file.open("r", encoding="utf-8") as f:
        info = json.load(f)
    # Expect transition: passed -> fail
    assert info.get("passed_units") == 0
    assert info.get("failed_units") == 1
    units = info.get("units")
    assert any(u[0] == "SNX" and u[1] is False for u in units)
    assert abs(info.get("yield", 0.0) - 0.0) < 1e-6
