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
from typing import TYPE_CHECKING

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

        # Lot label: plain text showing current lot (default "No lot")
        self.lot_label = QtWidgets.QLabel("No lot")
        self.lot_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lot_label.setMinimumHeight(24)
        self.layout.addRow("Current lot:", self.lot_label)

        # Samples label: plain numeric display for the currently selected lot
        self.samples_label = QtWidgets.QLabel("Samples: 0")
        self.samples_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.samples_label.setMinimumHeight(24)
        self.layout.addRow("Samples:", self.samples_label)

        # Current serial label
        self.serial_label = QtWidgets.QLabel("#N/A")
        self.layout.addRow("Current serial:", self.serial_label)

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
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self.open_directory)
        btn_layout.addWidget(self.btn_open)

        self.layout.addRow(btn_layout)

        

        # Connect click handler (highlighting). Selection will be performed with the Select button
        self.table.itemClicked.connect(self._on_item_clicked)

    def set_lot_selected(self, lot_name: str, path: str) -> None:
        """Set the selected lot and update UI state."""
        self.current_lot_name = lot_name
        self.current_lot_path = Path(path)
        self.lot_label.setText(lot_name)
        # Update samples display for selected lot
        samples = self.lot_samples.get(lot_name, 0)
        self.samples_label.setText(f"Samples: {samples}")
        self.serial_label.setText("#N/A")
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
        lot_path = str(Path.cwd() / name)
        self.add_lot(name, lot_path)
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
        lot_path = self.lots.get(lot_name, str(Path.cwd() / lot_name))
        self.set_lot_selected(lot_name, lot_path)

    def open_directory(self) -> None:
        """Open the lot directory in the OS file browser."""
        if not self.current_lot_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_lot_path)))

    def add_lot(self, lot_name: str, path: str) -> None:
        """Add a lot entry to the table (name + sample count)."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        name_item = QtWidgets.QTableWidgetItem(lot_name)
        name_item.setFlags(name_item.flags() ^ QtCore.Qt.ItemIsEditable)
        self.table.setItem(row, 0, name_item)

        # default samples is zero
        self.lots[lot_name] = path
        self.lot_samples[lot_name] = 0
        samples_item = QtWidgets.QTableWidgetItem(str(0))
        samples_item.setFlags(samples_item.flags() ^ QtCore.Qt.ItemIsEditable)
        self.table.setItem(row, 1, samples_item)

    def _on_item_clicked(self, item: QtWidgets.QTableWidgetItem) -> None:
        # store the highlighted row, but do not finalize selection until user presses Select
        self.highlighted_row = item.row()
        self.btn_select.setEnabled(True)
