from pathlib import Path
import json
from datetime import datetime

from PySide6 import QtWidgets
import pytest

from NanoVNASaver.Controls.LotControl import LotControl


@pytest.fixture(autouse=True)
def ensure_qapp():
    # Ensure a QApplication exists for widget construction
    app = QtWidgets.QApplication.instance()
    if app is None:
        QtWidgets.QApplication([])
    yield


def test_add_lot_creates_dir_and_json(tmp_path):
    lc = LotControl(None)
    lc.working_directory = tmp_path

    lc.add_lot("testlot", None, samples=0, create_on_disk=True)

    lot_dir = tmp_path / "testlot"
    assert lot_dir.exists() and lot_dir.is_dir()
    info_file = lot_dir / "lot.json"
    assert info_file.exists()
    with info_file.open("r", encoding="utf-8") as f:
        info = json.load(f)
    assert info["lot_name"] == "testlot"
    assert isinstance(info["samples"], int)
    # creation date should parse as ISO format
    datetime.fromisoformat(info["creation_date"])


def test_scan_populates_from_directory(tmp_path):
    # create a lot directory with lot.json
    lot_dir = tmp_path / "lotA"
    lot_dir.mkdir()
    info = {"lot_name": "lotA", "samples": 5, "creation_date": datetime.now().isoformat()}
    with (lot_dir / "lot.json").open("w", encoding="utf-8") as f:
        json.dump(info, f)

    lc = LotControl(None)
    lc.working_directory = tmp_path
    lc.scan_working_directory()

    assert "lotA" in lc.lots
    assert lc.lot_samples.get("lotA") == 5
    # table contains row with name
    found = False
    for r in range(lc.table.rowCount()):
        if lc.table.item(r, 0).text() == "lotA":
            found = True
            assert lc.table.item(r, 1).text() == "5"
    assert found
