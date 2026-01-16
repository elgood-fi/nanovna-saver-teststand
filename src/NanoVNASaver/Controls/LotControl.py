#  NanoVNASaver
#
#  A python program to view and export Touchstone data from a NanoVNA
#  Copyright (C) 2019, 2020  Rune B. Broberg
#  Copyright (C) 2020,2021 NanoVNA-Saver Authors
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional
import json
from datetime import datetime
from ..Touchstone import Touchstone

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices

from .Control import Control

if TYPE_CHECKING:
    from ..NanoVNASaver.NanoVNASaver import NanoVNASaver as vna_app


logger = logging.getLogger(__name__)


class LotControl(Control):
    """Dummy Lot control with a path field, serial label and a scrollable list of serials and statuses."""

    lot_changed = Signal(bool)

    def __init__(self, app: "vna_app"):
        super().__init__(app, "Lot control")

        # Internal state
        self.current_lot_path: Path | None = None
        self.current_lot_name: str | None = None
        self.lot_counter = 1
        self.lots: dict[str, str] = {}
        self.lot_samples: dict[str, int] = {}
        self.highlighted_row: int | None = None
        # PCB lot field state: True if the PCB Lot text field is empty
        self.pcb_lot_empty: bool = True

        # Working directory for new lots / defaults
        self.working_directory: Path = Path.cwd()

        # Lot label: plain text showing current lot (default "No lot")
        self.lot_label = QtWidgets.QLabel("No lot")
        self.lot_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lot_label.setMinimumHeight(24)
        self.lot_label.setAlignment(Qt.AlignCenter)
        #self.golden_label.setMinimumHeight(34)
        self.lot_label.setStyleSheet(
            "padding: 1px; border-radius: 4px; border: 2px solid #666; font-size: 18px;"
        )
        self.layout.addRow(QtWidgets.QLabel("Current lot"))
        self.layout.addRow(self.lot_label)  # spacer
        # Samples label: plain numeric display for the currently selected lot
        self.samples_label = QtWidgets.QLabel("0")
        self.samples_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.samples_label.setMinimumHeight(24)
        self.layout.addRow("Samples:", self.samples_label)

        # Current serial label
        self.serial_label = QtWidgets.QLabel("#N/A")
        self.layout.addRow("Current serial:", self.serial_label)

        # PCB Lot input field
        self.pcb_lot_field = QtWidgets.QLineEdit()
        self.pcb_lot_field.setPlaceholderText("Enter PCB lot number")
        self.pcb_lot_field.setMinimumHeight(24)
        self.layout.addRow("PCB Lot:", self.pcb_lot_field)
        # Ensure internal state tracks the field (default is empty)
        self.pcb_lot_empty = True
        self.pcb_lot_field.textChanged.connect(self._on_pcb_lot_changed)

        # Table for lots (Lot name + number of samples)
        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Lot", "Samples"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(150)
        self.layout.addRow(self.table)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()

        self.btn_select = QtWidgets.QPushButton("Select")
        self.btn_select.setMinimumHeight(20)
        self.btn_select.setEnabled(False)
        self.btn_select.clicked.connect(self.select_lot)
        btn_layout.addWidget(self.btn_select)

        self.btn_new = QtWidgets.QPushButton("New lot")
        self.btn_new.setMinimumHeight(20)
        self.btn_new.clicked.connect(self.new_lot)
        btn_layout.addWidget(self.btn_new)

        self.btn_open = QtWidgets.QPushButton("Directory")
        self.btn_open.setMinimumHeight(20)
        # Directory now prompts to change the working directory; always enabled
        self.btn_open.setEnabled(True)
        self.btn_open.clicked.connect(self.open_directory)
        btn_layout.addWidget(self.btn_open)

        self.layout.addRow(btn_layout)

        

        # Connect click handler (highlighting). Selection will be performed with the Select button
        self.table.itemClicked.connect(self._on_item_clicked)

        # Scan the working directory for existing lot directories
        try:
            self.scan_working_directory()
        except Exception:
            logger.exception("Failed scanning working directory")

    def set_lot_selected(self, lot_name: str, path: str) -> None:
        """Set the selected lot and update UI state."""
        self.current_lot_name = lot_name
        self.current_lot_path = Path(path)
        self.lot_label.setText(lot_name)
        # Update samples display for selected lot
        samples = self.lot_samples.get(lot_name, 0)
        self.samples_label.setText(f"{samples}")
        self.serial_label.setText("#N/A")
        # Clear PCB lot field when selecting a lot
        if hasattr(self, "pcb_lot_field"):
            self.pcb_lot_field.setText("")
        self.pcb_lot_empty = True
        self.btn_open.setEnabled(True)
        self.btn_select.setEnabled(False)
        # visually select the row
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).text() == lot_name:
                self.table.selectRow(r)
                break
        self.lot_changed.emit(True)

    def new_lot(self) -> None:
        """Prompt for a new lot name and add it to the list."""
        default_name = f"lot_{self.lot_counter:03d}"
        name, ok = QtWidgets.QInputDialog.getText(
            self, "New lot", "Lot name:", QtWidgets.QLineEdit.Normal, default_name
        )
        if not ok or not name:
            return
        self.lot_counter += 1
        # create on disk in working_directory
        self.add_lot(name, None, samples=0, create_on_disk=True)
        # Highlight the newly added lot (does not yet select it)
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).text() == name:
                self.table.setCurrentCell(r, 0)
                self.highlighted_row = r
                self.btn_select.setEnabled(True)
                break

    def select_lot(self) -> None:
        """Select the currently highlighted lot (finalize selection)."""
        if self.highlighted_row is None:
            return
        lot_name = self.table.item(self.highlighted_row, 0).text()
        lot_path = self.lots.get(lot_name, str(self.working_directory / lot_name))
        # refresh samples from disk if present
        lot_dir = Path(lot_path)
        info_file = lot_dir / "lot.json"
        if info_file.exists():
            try:
                with info_file.open("r", encoding="utf-8") as f:
                    info = json.load(f)
                samples = int(info.get("samples", 0))
                self.lot_samples[lot_name] = samples
            except Exception:
                logger.exception("Failed reading lot info for %s", lot_name)
        self.set_lot_selected(lot_name, lot_path)

    def open_directory(self) -> None:
        """Prompt the user to change the working directory for lots and scan it."""
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select working directory", str(self.working_directory)
        )
        if not dir_path:
            return
        self.working_directory = Path(dir_path)
        logger.info("Working directory changed to %s", self.working_directory)
        # Rescan working directory for lot directories
        try:
            self.scan_working_directory()
        except Exception:
            logger.exception("Failed scanning new working directory")
        QtWidgets.QMessageBox.information(
            self, "Working directory",
            f"Working directory set to:\n{self.working_directory}"
        )

    def scan_working_directory(self) -> None:
        """Scan the working directory for lot directories and populate the table.

        A lot directory is a subdirectory that contains a JSON file with keys:
        - "lot_name" (must match the directory name)
        - "samples" (int)
        - "creation_date" (ISO datetime string)
        """
        # Clear current lists and table
        self.lots.clear()
        self.lot_samples.clear()
        self.table.setRowCount(0)

        if not self.working_directory.exists():
            return

        for child in sorted(self.working_directory.iterdir()):
            if not child.is_dir():
                continue
            # look for json files inside child
            info_file = None
            for candidate in child.glob("*.json"):
                try:
                    with candidate.open("r", encoding="utf-8") as f:
                        info = json.load(f)
                    # validate
                    if (
                        isinstance(info, dict)
                        and info.get("lot_name") == child.name
                        and "samples" in info
                        and "creation_date" in info
                    ):
                        info_file = candidate
                        samples = int(info.get("samples", 0))
                        # add lot without creating on disk
                        self.add_lot(child.name, str(child), samples=samples, create_on_disk=False)
                        break
                except Exception:
                    logger.exception("Invalid lot json at %s", candidate)
                    continue

    def add_lot(self, lot_name: str, path: str | None = None, *, samples: int = 0, create_on_disk: bool = True) -> None:
        """Add a lot entry to the table (name + sample count).

        If create_on_disk is True, this will create a directory in self.working_directory
        and write a `lot.json` file with the lot metadata (if it does not already exist).
        """
        # Determine directory
        lot_dir = Path(path) if path else (self.working_directory / lot_name)
        if create_on_disk:
            try:
                lot_dir.mkdir(parents=True, exist_ok=True)
                info_file = lot_dir / f"{lot_name}.json"
                if not info_file.exists():
                    info = {
                        "lot_name": lot_name,
                        "samples": int(samples),
                        "creation_date": datetime.now().isoformat(),
                    }
                    with info_file.open("w", encoding="utf-8") as f:
                        json.dump(info, f, indent=2)
                else:
                    # read existing info
                    try:
                        with info_file.open("r", encoding="utf-8") as f:
                            existing = json.load(f)
                        samples = int(existing.get("samples", samples))
                    except Exception:
                        logger.exception("Failed reading existing lot info %s", info_file)
            except Exception:
                logger.exception("Failed to create lot directory %s", lot_dir)

        # If already present, update sample count and path
        if lot_name in self.lots:
            self.lots[lot_name] = str(lot_dir)
            self.lot_samples[lot_name] = int(samples)
            # update table row for samples
            for r in range(self.table.rowCount()):
                if self.table.item(r, 0).text() == lot_name:
                    self.table.item(r, 1).setText(str(self.lot_samples[lot_name]))
                    break
            return

        # otherwise insert new row
        row = self.table.rowCount()
        self.table.insertRow(row)
        name_item = QtWidgets.QTableWidgetItem(lot_name)
        name_item.setFlags(name_item.flags() ^ QtCore.Qt.ItemIsEditable)
        self.table.setItem(row, 0, name_item)

        self.lots[lot_name] = str(lot_dir)
        self.lot_samples[lot_name] = int(samples)
        samples_item = QtWidgets.QTableWidgetItem(str(self.lot_samples[lot_name]))
        samples_item.setFlags(samples_item.flags() ^ QtCore.Qt.ItemIsEditable)
        self.table.setItem(row, 1, samples_item)

    def _on_pcb_lot_changed(self, text: str) -> None:
        """Update internal state tracking whether PCB Lot field is empty."""
        self.pcb_lot_empty = (text.strip() == "")

    def _on_item_clicked(self, item: QtWidgets.QTableWidgetItem) -> None:
        # store the highlighted row, but do not finalize selection until user presses Select
        self.highlighted_row = item.row()
        self.btn_select.setEnabled(True)


# Helper functions for saving touchstone files directly in this module
def _unique_filename(directory: Path, base: str, ext: str) -> Path:
    """Return a non-existing filename in ``directory`` with extension ``ext``.

    If ``base.ext`` exists, appends a numeric suffix before the extension,
    e.g. ``base-1.ext``, ``base-2.ext`` etc.
    """
    directory.mkdir(parents=True, exist_ok=True)
    cand = directory / f"{base}.{ext}"
    i = 1
    while cand.exists():
        cand = directory / f"{base}-{i}.{ext}"
        i += 1
    return cand


def save_s1p(ts: Touchstone, directory: Path, base_name: Optional[str] = "touchstone") -> Path:
    """Save a Touchstone object as a 1-port file (.s1p) in ``directory``.

    Args:
        ts: Touchstone instance containing S11 data.
        directory: Directory to write the file into. Will be created if missing.
        base_name: Base name for the file (without extension). Defaults to "touchstone".

    Returns:
        Path to the written file.

    Raises:
        ValueError: if S11 data is empty.
        IOError: on file write errors.
    """
    if not ts.s11:
        raise ValueError("No S11 data to save as S1P")
    filename = _unique_filename(Path(directory), base_name, "s1p")
    ts.filename = str(filename)
    ts.save(1)
    logger.info("Saved S1P to %s", filename)
    return filename


def save_s2p(ts: Touchstone, directory: Path, base_name: Optional[str] = "touchstone") -> Path:
    """Save a Touchstone object as a 2-port file (.s2p) in ``directory``.

    Args:
        ts: Touchstone instance containing S11 and S21 data.
        directory: Directory to write the file into. Will be created if missing.
        base_name: Base name for the file (without extension). Defaults to "touchstone".

    Returns:
        Path to the written file.

    Raises:
        ValueError: if S11 or S21 data is empty.
        IOError: on file write errors.
    """
    if not ts.s11:
        raise ValueError("No S11 data to save as S2P")
    if not ts.s21:
        raise ValueError("No S21 data to save as S2P")
    filename = _unique_filename(Path(directory), base_name, "s2p")
    ts.filename = str(filename)
    ts.save(4)
    logger.info("Saved S2P to %s", filename)
    return filename
