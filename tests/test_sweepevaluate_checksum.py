from pathlib import Path
import hashlib
from PySide6 import QtWidgets

from NanoVNASaver.Controls.SweepEvaluate import SweepEvaluate


def test_test_checksum(tmp_path: Path):
    # Ensure a QApplication exists for widget construction
    app_qt = QtWidgets.QApplication.instance()
    if app_qt is None:
        QtWidgets.QApplication([])

    class FakeApp:
        pass

    fake_app = FakeApp()
    se = SweepEvaluate(fake_app)

    # Create a minimal valid test spec JSON file
    spec_file = tmp_path / "spec.json"
    spec_content = '{"sweep": {}, "tests": [], "meta": {"id": "t1"}}'
    spec_file.write_text(spec_content, encoding="utf-8")

    # Load spec and verify checksum
    se.load_spec(str(spec_file))
    with spec_file.open("rb") as f:
        expected = hashlib.md5(f.read()).hexdigest()
    assert se.test_checksum == expected

    # Loading a missing/invalid spec should clear checksum
    missing = tmp_path / "does_not_exist.json"
    se.load_spec(str(missing))
    assert se.test_checksum is None
