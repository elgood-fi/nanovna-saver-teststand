from pathlib import Path
import json

from PySide6 import QtWidgets

from NanoVNASaver.Controls.SweepEvaluate import SweepEvaluate
from NanoVNASaver.Controls.LotControl import LotControl
from NanoVNASaver.TestSpec import TestSpec, TestPoint
from NanoVNASaver.Touchstone import Touchstone
from NanoVNASaver.RFTools import Datapoint


def test_autosave_on_evaluate(tmp_path):
    # Ensure a QApplication exists for widget construction
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])

    # Minimal fake app with Touchstone data
    class FakeApp:
        pass

    fake_app = FakeApp()
    fake_app.data = Touchstone()
    # populate s11 with a single datapoint so evaluation finds samples
    fake_app.data.s11 = [Datapoint(900000000, 0.5, 0.0)]
    # also include S21 so we can save S2P files
    fake_app.data.s21 = [Datapoint(900000000, 0.2, 0.0)]

    se = SweepEvaluate(fake_app)
    lc = LotControl(fake_app)

    # Prepare lot directory and selection
    lot_dir = tmp_path / "lotA"
    lot_dir.mkdir()
    lc.current_lot_name = "lotA"
    lc.current_lot_path = lot_dir

    # Connect signal
    se.results_ready.connect(lc.save_results_for_latest)

    # Prepare a simple spec with one test point matching the datapoint freq
    tp = TestPoint(name="t", parameter="S11", frequency=900000000, span=0, limit_db=-30.0, direction="over")
    se.spec = TestSpec(sweep={}, tests=[tp])
    se.current_serial = "SN1"

    # Run evaluation -> should emit and create TestData
    se.evaluate()

    # Call save with the new TestData object
    lc.save_results_for_latest(se.test_data)

    # Verify files saved under lot/<serial>/<id>/
    td = se.test_data
    sample_dir = lot_dir / td.serial / td.id
    assert sample_dir.exists(), "Expected sample directory to exist"

    s1p_files = list(sample_dir.glob("*.s1p"))
    s2p_files = list(sample_dir.glob("*.s2p"))
    results_files = list(sample_dir.glob(f"results_{td.serial}_{td.id}.json"))

    assert len(s1p_files) == 1, "Expected one .s1p file saved in sample dir"
    assert len(s2p_files) == 1, "Expected one .s2p file saved in sample dir"
    assert len(results_files) == 1, "Expected one results json in sample dir"

    # Verify the results JSON contains serial and id
    with results_files[0].open("r", encoding="utf-8") as f:
        jd = json.load(f)
    assert jd.get("serial") == td.serial
    assert jd.get("id") == td.id

    # Verify lot.json sample count updated
    info_file = lot_dir / "lot.json"
    assert info_file.exists()
    with info_file.open("r", encoding="utf-8") as f:
        info = json.load(f)
    assert info.get("samples", 0) == 1
