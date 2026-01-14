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

        # Lot label: plain text showing current lot (default "No lot")
        self.path_label = QtWidgets.QLabel("No lot")
        self.path_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.path_label.setMinimumHeight(24)
        self.layout.addRow("Current lot:", self.path_label)

        # Current serial label
        self.serial_label = QtWidgets.QLabel("#N/A")
        self.layout.addRow("Current serial:", self.serial_label)

        # Table for lots
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

        self.btn_continue = QtWidgets.QPushButton("Continue lot")
        self.btn_continue.setMinimumHeight(20)
        self.btn_continue.setEnabled(False)
        self.btn_continue.clicked.connect(self.continue_lot)
        btn_layout.addWidget(self.btn_continue)

        self.btn_new = QtWidgets.QPushButton("New lot")
        self.btn_new.setMinimumHeight(20)
        self.btn_new.clicked.connect(self.new_lot)
        btn_layout.addWidget(self.btn_new)

        self.btn_open = QtWidgets.QPushButton("Open directory")
        self.btn_open.setMinimumHeight(20)
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self.open_directory)
        btn_layout.addWidget(self.btn_open)

        self.layout.addRow(btn_layout)

        # Internal state
        self.current_lot_path: Path | None = None
        self.current_lot_name: str | None = None
        self.lot_counter = 1

        # Connect selection change handler
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

    def set_lot_selected(self, lot_name: str, path: str) -> None:
        """Set the selected lot and update UI state."""
        self.current_lot_name = lot_name
        self.current_lot_path = Path(path)
        self.path_label.setText(lot_name)
        self.serial_label.setText("#N/A")
        self.btn_open.setEnabled(True)
        self.btn_continue.setEnabled(True)
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
        # Select the newly added lot
        # find the row we just added
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).text() == name:
                self.table.selectRow(r)
                break

    def continue_lot(self) -> None:
        """Continue work with the currently selected lot."""
        if not self.current_lot_path:
            return
        logger.info("Continuing lot %s at %s", self.current_lot_name, self.current_lot_path)

    def open_directory(self) -> None:
        """Open the lot directory in the OS file browser."""
        if not self.current_lot_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_lot_path)))

    def add_lot(self, lot_name: str, path: str) -> None:
        """Add a lot entry to the table (name + path)."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        name_item = QtWidgets.QTableWidgetItem(lot_name)
        name_item.setFlags(name_item.flags() ^ QtCore.Qt.ItemIsEditable)
        self.table.setItem(row, 0, name_item)

        path_item = QtWidgets.QTableWidgetItem(path)
        path_item.setFlags(path_item.flags() ^ QtCore.Qt.ItemIsEditable)
        self.table.setItem(row, 1, path_item)

    def _on_selection_changed(self) -> None:
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        lot_name = self.table.item(row, 0).text()
        lot_path = self.table.item(row, 1).text()
        self.set_lot_selected(lot_name, lot_path)
