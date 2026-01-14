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
from typing import TYPE_CHECKING

from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Qt

from .Control import Control

if TYPE_CHECKING:
    from ..NanoVNASaver.NanoVNASaver import NanoVNASaver as vna_app


logger = logging.getLogger(__name__)


class CalibrationControl(Control):
    """Dummy calibration control box with a red "No cal" field and a "Load calibration" button."""

    calibration_loaded = Signal(bool)

    def __init__(self, app: "vna_app"):
        super().__init__(app, "Calibration")

        # Status label: red by default and centered
        self.status_label = QtWidgets.QLabel("No cal")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumHeight(34)
        #self.status_label.setStyleSheet(
        #    "background-color: #F44336; color: white; padding: 4px; border-radius: 4px;"
        #)
        # Add the label as a full-width row
        self.layout.addRow(self.status_label)

        # Load button
        self.btn_load = QtWidgets.QPushButton("Load calibration")
        self.btn_load.setMinimumHeight(20)
        self.btn_load.clicked.connect(self.load_calibration)
        self.layout.addRow(self.btn_load)

    def load_calibration(self):
        """Dummy handler: toggles status to indicate a calibration was loaded."""
        # In a real control this would open a file dialog and load data.
        # For now we just reflect a loaded state in the UI.
        self.status_label.setText("Loaded")
        #self.status_label.setStyleSheet(
        #    "background-color: #4CAF50; color: white; padding: 4px; border-radius: 4px;"
        #)
        self.calibration_loaded.emit(True)
