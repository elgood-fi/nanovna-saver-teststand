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


def test_scan_loads_checksum(tmp_path: Path):
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])

    class FakeApp:
        pass

    fake_app = FakeApp()
    lc = LotControl(fake_app)
    # prepare an existing lot directory with a checksum in its JSON
    lot_dir = tmp_path / "lotZ"
    lot_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "lot_name": "lotZ",
        "samples": 0,
        "creation_date": "2020-01-01T00:00:00",
        "checksum": "deadbeef",
    }
    info_file = lot_dir / "lotZ.json"
    with info_file.open("w", encoding="utf-8") as f:
        import json

        json.dump(info, f)

    lc.working_directory = tmp_path
    lc.scan_working_directory()

    assert lc.lot_checksum.get("lotZ") == "deadbeef"


def test_select_lot_loads_checksum(tmp_path: Path):
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])

    class FakeApp:
        pass

    fake_app = FakeApp()
    lc = LotControl(fake_app)
    # prepare an existing lot directory with a checksum in its JSON
    lot_dir = tmp_path / "lotA"
    lot_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "lot_name": "lotA",
        "samples": 3,
        "creation_date": "2020-01-01T00:00:00",
        "checksum": "cafebabe",
        "units": [],
    }
    info_file = lot_dir / "lotA.json"
    with info_file.open("w", encoding="utf-8") as f:
        import json

        json.dump(info, f)

    lc.working_directory = tmp_path
    lc.scan_working_directory()

    # Find the row for lotA and highlight it
    found_row = None
    for r in range(lc.table.rowCount()):
        if lc.table.item(r, 0).text() == "lotA":
            found_row = r
            break
    assert found_row is not None
    lc.highlighted_row = found_row

    # trigger selection which should load checksum as well
    lc.select_lot()
    assert lc.current_lot_name == "lotA"
    assert lc.lot_checksum.get("lotA") == "cafebabe"


def test_save_results_preserves_lot_checksum(tmp_path: Path):
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])

    class FakeApp:
        pass

    fake_app = FakeApp()
    lc = LotControl(fake_app)
    # prepare an existing lot directory with a checksum in its JSON
    lot_dir = tmp_path / "lotS"
    lot_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "lot_name": "lotS",
        "samples": 0,
        "creation_date": "2020-01-01T00:00:00",
        "checksum": "beefcafe",
        "units": [],
    }
    info_file = lot_dir / "lotS.json"
    with info_file.open("w", encoding="utf-8") as f:
        import json

        json.dump(info, f)

    lc.working_directory = tmp_path
    lc.scan_working_directory()

    # highlight and select
    found_row = None
    for r in range(lc.table.rowCount()):
        if lc.table.item(r, 0).text() == "lotS":
            found_row = r
            break
    assert found_row is not None
    lc.highlighted_row = found_row
    lc.select_lot()

    from NanoVNASaver.TestSpec import TestPoint, TestResult, TestData
    tp = TestPoint(name="T", parameter="S11", frequency=1000000, span=1000, limit_db=-10, direction="under")
    tr = TestResult(tp=tp, passed=True, min=-9.5, max=-9.0, failing=[], samples=1)
    td = TestData(serial="SN1", id="tid-1", meta=None, passed=True, pcb_lot=None, results=[tr])

    # Ensure app has data for FilesWindow export (a minimal dummy)
    fake_app.data = True
    lc.app = fake_app
    lc.save_results_for_latest(td)

    # read lot json and verify checksum preserved
    with info_file.open("r", encoding="utf-8") as f:
        import json

        info2 = json.load(f)
    assert info2.get("checksum") == "beefcafe"
