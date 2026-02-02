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
import uuid
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtCore import Qt
from pathlib import Path

from ..Defaults import SweepConfig, get_app_config
from ..Formatting import format_frequency, format_gain
from ..Formatting import (
    format_frequency_inputs,
    format_frequency_short,
    format_frequency_sweep,
    parse_frequency,
)
from ..Charts import LogMagChart, LogMagTest
from .Control import Control

if TYPE_CHECKING:
    from ..NanoVNASaver.NanoVNASaver import NanoVNASaver as vna_app

logger = logging.getLogger(__name__)


class FrequencyInputWidget(QtWidgets.QLineEdit):
    def __init__(self, text=""):
        super().__init__(text)
        self.nextFrequency = -1
        self.previousFrequency = -1
        self.setFixedHeight(20)
        self.setMinimumWidth(60)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

    def setText(self, text: str) -> None:
        super().setText(format_frequency_inputs(text))

    def get_freq(self) -> int:
        return parse_frequency(self.text())


class SweepEvaluate(Control):
    """Widget to load a JSON test spec and evaluate sweeps against it."""

    # Signal emitted with the latest results (list of TestResult)
    results_ready = QtCore.Signal(object)

    def __init__(self, app: "vna_app"):
        super().__init__(app, "Test configuration")

        

        # Override base Control width so widget expands to parent width
        # (Control sets a small maximum width by default)
        self.setMaximumWidth(16777215)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)

        self.spec = None
        # Holds the latest evaluation results as a list of TestResult dataclass instances
        self.latest_result = None

        self.test_data = None
        # MD5 checksum of the loaded test spec file, or None if no spec loaded
        self.test_checksum: str | None = None

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        # Make the bar thicker and display the percentage centered over the bar
        self.progress_bar.setFixedHeight(14)
        # Ensure percentage text is visible and in percent format
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setTextVisible(True)
        # Try to center text using API (may not exist on all bindings)
        try:
            self.progress_bar.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        except Exception:
            pass
        # Style for a thicker rounded bar and colored chunk
        self.progress_bar.setStyleSheet(
            "QProgressBar {"
            "  border: 1px solid #999;"
            "  border-radius: 4px;"
            "  background: #f0f0f0;"
            "  padding: 0px;"
            "}"
            "QProgressBar::chunk {"
            "  background-color: #3daee9;"
            "  border-radius: 4px;"
            "  margin: 0px;"
            "}"
        )
        

        # Overall status panel shown above the progress bar
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setFixedHeight(80)
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        font = self.status_label.font()
        font.setBold(True)
        self.status_label.setFont(font)
        self._testing = False
        self._last_result_state = None
        self.current_serial = None
        # yellow = ready/testing default
        self._set_status_style("Ready", "#FFD54F", "black")

        self.layout.addRow(self.status_label)

        self.layout.addRow(self.progress_bar)

        # Create charts for S11 Return Loss and S21 Insertion Loss
        # Use LogMagTest so the charts can render TestSpec markers
        self.s11_chart = LogMagTest("S11 Return Loss")
        self.s21_chart = LogMagTest("S21 Insertion Loss")

        # If a golden reference already exists on the application, show it
        try:
            if hasattr(self.app, "golden_ref_data") and self.app.golden_ref_data:
                self.s11_chart.setGoldenReference(self.app.golden_ref_data.s11)
                self.s21_chart.setGoldenReference(self.app.golden_ref_data.s21)
                # Update label to reflect presence
                try:
                    self.golden_label.setText("Golden reference loaded")
                except Exception:
                    pass
        except Exception:
            logger.exception("Failed to initialize golden reference on charts")
    
        # Create a horizontal layout for the charts arranged side by side
        charts_layout = QtWidgets.QHBoxLayout()
        charts_layout.addWidget(self.s11_chart)
        charts_layout.addWidget(self.s21_chart)
        self.layout.addRow(charts_layout)

        # Connect to worker signals to reflect testing state
        try:
            self.app.worker.signals.updated.connect(self._on_worker_updated)
            self.app.worker.signals.finished.connect(self._on_worker_finished)
        except Exception:
            # If worker or signals not available yet, ignore
            pass

        # Connect to other controls (if present) so button state can be kept up-to-date
        try:
            # Update when PCB lot field changes
            if hasattr(self.app, "lot_control") and hasattr(self.app.lot_control, "pcb_lot_field"):
                self.app.lot_control.pcb_lot_field.textChanged.connect(self.update_test_button_state)
            # Update when a PCB lot is explicitly set via the 'Set' button
            if hasattr(self.app, "lot_control") and hasattr(self.app.lot_control, "pcb_lot_changed"):
                self.app.lot_control.pcb_lot_changed.connect(self.update_test_button_state)
            # Update when lot selection changes
            if hasattr(self.app, "lot_control") and hasattr(self.app.lot_control, "lot_changed"):
                self.app.lot_control.lot_changed.connect(self.update_test_button_state)
        except Exception:
            pass
        try:
            # Update when calibration is loaded
            if hasattr(self.app, "calibration_control"):
                self.app.calibration_control.calibration_loaded.connect(self.update_test_button_state)
        except Exception:
            pass
        try:
            # If serial control already exists, update when connection state changes
            if hasattr(self.app, "serial_control"):
                self.app.serial_control.connected.connect(self.update_test_button_state)
        except Exception:
            pass

        # Initial state update
        try:
            self.update_test_button_state()
        except Exception:
            pass

        # Install event filter to allow Enter/Return key to act as an alias for the Test button
        try:
            self.installEventFilter(self)
        except Exception:
            pass

        # Top row: spec path + load button
        #path_layout = QtWidgets.QHBoxLayout()
        #left_column = QtWidgets.QVBoxLayout()
        #right_column = QtWidgets.QVBoxLayout()
        #self.spec_label = QtWidgets.QLabel("No program loaded")
        #self.spec_label.setWordWrap(True)
        #btn_load = QtWidgets.QPushButton("Load program...")
        #btn_load.setFixedHeight(40)
        #btn_load.clicked.connect(self.load_spec_dialog)
        #left_column.addWidget(self.spec_label)
        #left_column.addWidget(btn_load)
        #path_layout.addLayout(left_column)
        #path_layout.addLayout(right_column)
        #self.layout.addRow(path_layout)

        # Options row
        opts_layout = QtWidgets.QHBoxLayout()
        #self.auto_eval = QtWidgets.QCheckBox("Auto evaluate on sweep finished")
        #btn_apply = QtWidgets.QPushButton("Apply sweep settings")
        #btn_apply.setFixedHeight(40)
        #btn_apply.clicked.connect(self.apply_sweep_settings)
        #btn_eval = QtWidgets.QPushButton("Evaluate now")
        #btn_eval.setFixedHeight(40)
        #btn_eval.clicked.connect(self.evaluate)
        #btn_save = QtWidgets.QPushButton("Save results...")
        #btn_save.setFixedHeight(40)
        #btn_save.clicked.connect(self.save_results)
        left_column = QtWidgets.QVBoxLayout() 
        # Keep a reference to the Test button so we can enable/disable it from state changes
        self.btn_test = QtWidgets.QPushButton("Test")
        self.btn_test.setMinimumHeight(90)
        self.btn_test.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )
        #btn_test.setFixedWidth(350)
        self.btn_test.clicked.connect(self._on_test_button_clicked)
        self.btn_test.setEnabled(False)
        left_column.addWidget(self.btn_test)
        #btn_test.clicked.connect(self.on_run_sequence_btn)
        middle_column = QtWidgets.QFormLayout()
        self.golden_title = QtWidgets.QLabel("Golden sample")
        self.golden_label = QtWidgets.QLabel("N/A")
        self.golden_label.setAlignment(Qt.AlignCenter)
        #self.golden_label.setMinimumHeight(34)
        self.golden_label.setStyleSheet(
            "padding: 1px; border-radius: 4px; border: 2px solid #666;"
        )
        # Add the label as a full-width row
        status_display = QtWidgets.QFormLayout() 
        status_spacer = QtWidgets.QSpacerItem(200, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        status_display.addItem(status_spacer)
        
        '''
        status_title = QtWidgets.QLabel("Test configuration status")
        status_display.addRow(status_title)

        conn_row = QtWidgets.QHBoxLayout()
        conn_indicator = QtWidgets.QLabel("Not connected")
        conn_indicator.setStyleSheet(
            "background-color: #F44336; color: white; padding: 1px; border-radius: 4px;"
        )
        connection = QtWidgets.QLabel("Connection")
        conn_row.addWidget(connection)
        conn_row.addWidget(conn_indicator)
        status_display.addRow(conn_row) 
        

        cal_row = QtWidgets.QHBoxLayout()
        cal_indicator = QtWidgets.QLabel("Calibration not loaded")
        cal_indicator.setStyleSheet(
            "background-color: #F44336; color: white; padding: 1px; border-radius: 4px;"
        )
        calibration = QtWidgets.QLabel("Calibration")
        cal_row.addWidget(calibration)
        cal_row.addWidget(cal_indicator)
        status_display.addRow(cal_row) 
        '''

        self.btn_golden = QtWidgets.QPushButton("Test golden sample")
        self.btn_golden.setFixedHeight(40)
        # Disable until prerequisites are met (same behavior as Test button)
        self.btn_golden.setEnabled(False)
        # 'Set as reference' disabled until a golden candidate exists
        self.btn_golden_set = QtWidgets.QPushButton("Set as reference")
        self.btn_golden_set.setFixedHeight(40)
        self.btn_golden_set.setEnabled(False)
        middle_top_row = QtWidgets.QVBoxLayout()

        middle_top_row.addWidget(self.golden_title)
        middle_top_row.addWidget(self.golden_label)
        
        middle_bot_row = QtWidgets.QHBoxLayout()
        middle_bot_row.addWidget(self.btn_golden)
        middle_bot_row.addWidget(self.btn_golden_set)

        middle_column.addRow(middle_top_row)
        middle_column.addRow(middle_bot_row)

        # Golden sample flow state
        self._golden_mode = False  # Set True when a golden sample test is started
        self._golden_candidate_available = False
        self._last_golden_s11 = None
        self._last_golden_s21 = None

        # Wire up golden buttons
        try:
            self.btn_golden.clicked.connect(self._on_test_golden_clicked)
        except Exception:
            pass
        self.btn_golden_set.clicked.connect(self._on_set_golden_clicked) 


        right_column = QtWidgets.QFormLayout()
        self.spec_title = QtWidgets.QLabel("Test program")
        self.spec_label = QtWidgets.QLabel("No program loaded")
        self.spec_label.setWordWrap(True)
        self.spec_label.setStyleSheet(
            "padding: 1px; border-radius: 4px; border: 2px solid #666;"
        )
        self.spec_label.setAlignment(Qt.AlignCenter)

        right_top_row = QtWidgets.QVBoxLayout()
        right_top_row.addWidget(self.spec_title)
        right_top_row.addWidget(self.spec_label)

        btn_load = QtWidgets.QPushButton("Load program...")
        btn_load.setFixedHeight(40)
        btn_load.clicked.connect(self.load_spec_dialog)

        right_bottom_row = QtWidgets.QHBoxLayout()
        right_bottom_row.addWidget(btn_load)


        right_column.addRow(right_top_row)
        right_column.addRow(right_bottom_row)
        
        test_layout = QtWidgets.QHBoxLayout()
        
        test_layout.addLayout(middle_column)
        test_layout.addLayout(right_column)
        test_layout.addLayout(status_display)
        test_layout.addLayout(left_column)

        #test_layout.addWidget(self.progress_bar)

        #opts_layout.addWidget(self.auto_eval)
        #opts_layout.addWidget(btn_apply)
        #opts_layout.addWidget(btn_eval)
        #opts_layout.addWidget(btn_save)
        self.layout.addRow(opts_layout)

        # Results table
        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "Status",
            "Name",
            "Param",
            "Freq",
            "Span",
            "Limit dB",
            "Dir",
            "Min",
            "Max",
        ])
        #"Failing count",
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        # Allow table to expand to fill available space
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.layout.addRow(self.table)

        self.layout.addRow(test_layout)

    def load_spec_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open test spec", "", "JSON files (*.json);;All files (*)"
        )
        if path:
            self.load_spec(path)
            self.apply_sweep_settings()

    def load_spec(self, path: str):
        from ..TestSpec import parse_test_spec

        spec = parse_test_spec(path)
        if spec is None:
            # ensure checksum is cleared if loading failed
            self.test_checksum = None
            QtWidgets.QMessageBox.warning(self, "Error", "Failed to load test spec")
            return
        self.spec = spec
        sweep = self.spec.sweep
        start = int(sweep.get("start", 0)) if sweep else 0
        stop = int(sweep.get("stop", 0)) if sweep else 0
        points = int(sweep.get("points", self.app.sweep.points)) if sweep else self.app.sweep.points
        segments = int(sweep.get("segments", self.app.sweep.segments)) if sweep else self.app.sweep.segments
        # compute md5 checksum of the file and store
        try:
            import hashlib as _hashlib

            with open(path, "rb") as _f:
                self.test_checksum = _hashlib.md5(_f.read()).hexdigest()
        except Exception:
            self.test_checksum = None
        self.spec_label.setText(f"{str(Path(path).name)} - {self.test_checksum[:8] if self.test_checksum else 'no checksum'}: [{format_frequency_short(start)} - {format_frequency_short(stop)}]  [{points}*{segments} = {points*segments} pts]")
        self.populate_table()
        self.app.updateTitle()
        # Pass filtered spec to the charts so they can draw markers for their
        # respective parameters (s11/s21)
        from ..TestSpec import TestSpec as _TS

        s11_tests = [t for t in spec.tests if t.parameter.lower() == "s11"]
        s21_tests = [t for t in spec.tests if t.parameter.lower() == "s21"]
        try:
            self.s11_chart.setTestSpec(_TS(sweep=spec.sweep, tests=s11_tests))
        except Exception:
            self.s11_chart.setTestSpec(None)
        try:
            self.s21_chart.setTestSpec(_TS(sweep=spec.sweep, tests=s21_tests))
        except Exception:
            self.s21_chart.setTestSpec(None)

        # Update Test button state whenever a spec is loaded
        try:
            self.update_test_button_state()
        except Exception:
            pass

    def populate_table(self):
        self.table.setRowCount(0)
        if not self.spec:
            return
        for tp in self.spec.tests:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem("N/A"))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(tp.name))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(tp.parameter))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(format_frequency(tp.frequency)))
            self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(format_frequency(tp.span)))
            self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(str(tp.limit_db)))
            self.table.setItem(row, 6, QtWidgets.QTableWidgetItem(tp.direction))
            self.table.setItem(row, 7, QtWidgets.QTableWidgetItem(""))
            self.table.setItem(row, 8, QtWidgets.QTableWidgetItem(""))
            #self.table.setItem(row, 9, QtWidgets.QTableWidgetItem("0"))

    def evaluate(self):
        if not self.spec:
            QtWidgets.QMessageBox.information(self, "Info", "No spec loaded")
            return
        s11 = self.app.data.s11 if self.app.data and self.app.data.s11 else []
        s21 = self.app.data.s21 if self.app.data and self.app.data.s21 else []
        if not s11 and not s21:
            QtWidgets.QMessageBox.information(self, "Info", "No sweep data available to evaluate")
            return
        
        # Update charts with current data
        self.s11_chart.setData(s11)
        self.s21_chart.setData(s21)
        
        from ..TestSpec import evaluate_testspec
        from ..TestSpec import TestResult, TestData

        results = evaluate_testspec(s11, s21, self.spec)
        # create TestResult instances for the latest run (keep compatibility with dict results)
        try:

            test_results = []
            for tp, res in zip(self.spec.tests, results):
                test_results.append(
                    TestResult(
                        tp=tp,
                        passed=bool(res.get("pass", False)),
                        min=res.get("min"),
                        max=res.get("max"),
                        failing=res.get("failing", []),
                        samples=res.get("samples", 0),
                    )
                )
            self.latest_result = test_results
            

        except Exception as e:
            # If dataclass import or construction fails for any reason, clear latest_result
            print(f"error: {e}")
            self.latest_result = None

        
        # update table rows
        overall_pass = True
        for row, res in enumerate(results):
            status_item = QtWidgets.QTableWidgetItem("PASS" if res["pass"] else "FAIL")
            status_item.setForeground(QtGui.QColor(20, 20, 20))
            if res["pass"]:
                status_item.setBackground(QtGui.QColor(100, 255, 100))
            else:
                status_item.setBackground(QtGui.QColor(255, 100, 100))
            self.table.setItem(row, 0, status_item)
            self.table.setItem(row, 7, QtWidgets.QTableWidgetItem(format_gain(res["min"]) if res["min"] is not None else ""))
            self.table.setItem(row, 8, QtWidgets.QTableWidgetItem(format_gain(res["max"]) if res["max"] is not None else ""))
            #self.table.setItem(row, 9, QtWidgets.QTableWidgetItem(str(len(res.get("failing", [])))))
            if not res["pass"]:
                overall_pass = False

        self.test_data = TestData(
            serial=self.current_serial or "NOSERIAL",
            id=str(uuid.uuid4()),
            meta="test_run",
            passed= overall_pass,
            pcb_lot="",
            results=self.latest_result
        )   
        # If this test was run as a golden candidate, store the raw sweep data for later promotion
        if getattr(self, "_golden_mode", False):
            try:
                self._last_golden_s11 = list(s11)
                self._last_golden_s21 = list(s21)
                self._last_golden_pass = overall_pass
                self._golden_candidate_available = True
                # Update label to indicate a golden candidate is available
                self.golden_label.setText(f"Candidate: {self.current_serial} - {'PASS' if overall_pass else 'FAIL'}")
                # Enable 'Set as reference' button now that a candidate exists
                try:
                    self.btn_golden_set.setEnabled(True)
                except Exception:
                    pass
            except Exception:
                logger.exception("Failed storing golden candidate")
            finally:
                # Clear golden mode - candidate has been produced
                self._golden_mode = False

        # Update overall status panel based on results
        if overall_pass:
            self._last_result_state = "PASS"
            self._set_status_style("PASS", "#4CAF50", "white")
        else:
            self._last_result_state = "FAIL"
            self._set_status_style("FAIL", "#F44336", "white")

        print(self.latest_result)
        try:
            print("Emitting results_ready from evaluate")
            self.results_ready.emit(self.test_data)
        except Exception:
            logger.exception("Failed to emit results_ready")

    def apply_sweep_settings(self):
        if not self.spec:
            QtWidgets.QMessageBox.information(self, "Info", "No spec loaded")
            return
        sweep = self.spec.sweep
        start = int(sweep.get("start", 0)) if sweep else 0
        stop = int(sweep.get("stop", 0)) if sweep else 0
        points = int(sweep.get("points", self.app.sweep.points)) if sweep else self.app.sweep.points
        segments = int(sweep.get("segments", self.app.sweep.segments)) if sweep else self.app.sweep.segments
        if start <= 0 or stop <= 0 or stop <= start:
            QtWidgets.QMessageBox.warning(self, "Error", "Invalid sweep settings in spec")
            return
        self.app.sweep.update(start=start, end=stop, segments=segments, points=points)
        # update sweep control UI
        span = stop - start
        try:
            self.app.sweep_control.set_start(start)
            self.app.sweep_control.set_end(stop)
            self.app.sweep_control.set_span(span)
            self.app.sweep_control.set_segments(segments)
           
        except Exception:
            # Non-fatal if UI not present
            logger.exception("Could not update sweep control UI")

    def save_results(self):
        if not self.spec:
            QtWidgets.QMessageBox.information(self, "Info", "No spec loaded")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save results", "", "JSON files (*.json);;All files (*)")
        if not path:
            return
        # gather results from table
        results = []
        for r in range(self.table.rowCount()):
            results.append({
                "status": self.table.item(r, 0).text() if self.table.item(r, 0) else "",
                "name": self.table.item(r, 1).text() if self.table.item(r, 1) else "",
                "parameter": self.table.item(r, 2).text() if self.table.item(r, 2) else "",
                "freq": self.table.item(r, 3).text() if self.table.item(r, 3) else "",
                "min": self.table.item(r, 7).text() if self.table.item(r, 7) else "",
                "max": self.table.item(r, 8).text() if self.table.item(r, 8) else "",
            })
            #"failing_count": self.table.item(r, 9).text() if self.table.item(r, 9) else "0",
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"spec": self.spec.sweep, "results": results}, f, indent=2)

    def _on_test_button_clicked(self):
        # Before prompting, check test spec checksum against the selected lot's checksum
        try:
            se_checksum = getattr(self, "test_checksum", None)
            lot_checksum = None
            try:
                if hasattr(self.app, "lot_control"):
                    lot_name = getattr(self.app.lot_control, "current_lot_name", None)
                    if lot_name:
                        lot_checksum = self.app.lot_control.lot_checksum.get(lot_name)
            except Exception:
                lot_checksum = None
            if se_checksum != lot_checksum:
                QtWidgets.QMessageBox.warning(self, "Warning", "Warning! Uncrecognized test configuration checksum detected!")
        except Exception:
            # if anything goes wrong, we still proceed to prompt for serial
            logger.exception("Failed checking test spec checksum against lot checksum")

        text, ok = QtWidgets.QInputDialog.getText(self, "Serial number", "Enter serial number:")
        if not ok:
            return
        serial = str(text).strip()
        if not serial:
            QtWidgets.QMessageBox.warning(self, "Invalid serial", "No serial number entered")
            return
        self.current_serial = serial
        logger.debug("Serial entered: %s", self.current_serial)
        # Reset touchstone data to a clean initial state before starting a test
        try:
            from ..Touchstone import Touchstone
            try:
                self.app.data = Touchstone()
            except Exception:
                # If assignment fails for some reason, log and continue
                logger.exception("Failed resetting app.data to new Touchstone")
            try:
                self.app.ref_data = Touchstone()
            except Exception:
                logger.exception("Failed resetting app.ref_data to new Touchstone")
            # Emit an update signal if available so UI can react to cleared data
            try:
                # Reinitialize worker internal buffers to avoid old data being
                # pushed back into the UI when the first segment completes.
                if hasattr(self.app, 'worker'):
                    try:
                        self.app.worker.init_data()
                    except Exception:
                        logger.exception("Failed resetting worker data before test")
                if hasattr(self.app, 'worker') and hasattr(self.app.worker, 'signals'):
                    self.app.worker.signals.updated.emit()
            except Exception:
                # not critical
                logger.debug("Could not emit worker updated signal after clearing touchstone data")
        except Exception:
            logger.exception("Error while re-initializing Touchstone data before test")
        try:
            self.app.sweep_start()
        except Exception:
            logger.exception("Failed to start sweep")

    def _on_test_golden_clicked(self):
        """Start a test intended for the golden sample. After the test finishes the
        result can be saved as the golden reference by pressing "Set as reference".
        """
        self._golden_mode = True
        self.golden_label.setText("Waiting for golden test...")
        # Ensure 'Set as reference' is disabled until a candidate is produced
        try:
            self.btn_golden_set.setEnabled(False)
        except Exception:
            pass
        # Reuse the normal test flow (prompts for serial etc.)
        self._on_test_button_clicked()

    def _on_set_golden_clicked(self):
        """Persist the last golden candidate sweep as the golden reference and
        update charts to display it behind current sweeps."""
        if not self._golden_candidate_available:
            QtWidgets.QMessageBox.information(self, "Info", "No golden sample result available to set as reference")
            return
        try:
            import datetime
            from ..Touchstone import Touchstone
            # Ensure app has a golden_ref_data holder
            try:
                self.app.golden_ref_data = getattr(self.app, "golden_ref_data", None) or Touchstone()
            except Exception:
                self.app.golden_ref_data = Touchstone()
            # Store the last golden candidate into the app-level golden reference
            self.app.golden_ref_data.s11 = list(self._last_golden_s11)
            self.app.golden_ref_data.s21 = list(self._last_golden_s21)
            # Update the golden label with serial and pass state
            status = "PASS" if self._last_golden_pass else "FAIL"
            self.golden_label.setText(f"{self.current_serial} - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            # Push to charts
            try:
                self.s11_chart.setGoldenReference(self.app.golden_ref_data.s11)
                self.s21_chart.setGoldenReference(self.app.golden_ref_data.s21)
            except Exception:
                logger.exception("Failed to update charts with golden reference")
            QtWidgets.QMessageBox.information(self, "Golden set", "Golden sample saved as reference")
            # Candidate consumed: disable the button until a new golden test is run
            self._golden_candidate_available = False
            try:
                self.btn_golden_set.setEnabled(False)
            except Exception:
                pass
        except Exception:
            logger.exception("Failed setting golden reference")

    def update_test_button_state(self, *args) -> None:
        """Enable the Test button only when all preconditions are met:
        - PCB lot field is non-empty
        - a calibration file is loaded (1-port valid)
        - a test specification is loaded
        - the NanoVNA device is connected
        """
        try:
            pcb_ok = False
            spec_ok = False
            cal_ok = False
            vna_ok = False
            lot_ok = False

            # PCB lot set via the 'Set' button (must have been explicitly set)
            try:
                pcb_ok = False
                if hasattr(self.app, "lot_control"):
                    pcb_ok = getattr(self.app.lot_control, "pcb_lot_value", None) is not None
            except Exception:
                pcb_ok = False

            # Spec loaded
            spec_ok = bool(self.spec)

            # Calibration loaded
            try:
                cal_ok = bool(self.app.calibration and self.app.calibration.isValid1Port())
            except Exception:
                cal_ok = False

            # VNA connected
            try:
                vna_ok = bool(self.app.vna and self.app.vna.connected())
            except Exception:
                vna_ok = False

            # Lot selected
            try:
                lot_ok = bool(hasattr(self.app, "lot_control") and getattr(self.app.lot_control, "current_lot_name", None))
            except Exception:
                lot_ok = False

            enabled = pcb_ok and spec_ok and cal_ok and vna_ok and lot_ok
            # Set tooltip for user guidance
            if not enabled:
                reasons = []
                if not pcb_ok:
                    reasons.append("PCB lot not set")
                if not lot_ok:
                    reasons.append("No lot selected")
                if not spec_ok:
                    reasons.append("No test program loaded")
                if not cal_ok:
                    reasons.append("Calibration not loaded")
                if not vna_ok:
                    reasons.append("Device not connected")
                tooltip = "; ".join(reasons)
            else:
                tooltip = "Ready to test"

            try:
                self.btn_test.setEnabled(enabled)
                self.btn_test.setToolTip(tooltip)
            except Exception:
                pass
            try:
                # Mirror Test button behavior for the golden test button when available
                if hasattr(self, 'btn_golden'):
                    self.btn_golden.setEnabled(enabled)
                    self.btn_golden.setToolTip(tooltip)
            except Exception:
                pass
        except Exception:
            logger.exception("Failed to update Test button state")

    def _set_status_style(self, text: str, bg_color: str, fg_color: str) -> None:
        # Simple stylesheet based status update
        try:
            self.status_label.setText(text)
            self.status_label.setStyleSheet(
                f"background-color: {bg_color}; color: {fg_color}; border: 1px solid #666; font-size: 36px; border-radius: 4px;"
            )
        except Exception:
            pass

    def eventFilter(self, obj, event):
        """Intercept key press events and treat Enter/Return as alias for the Test button."""
        try:
            # Use QtCore event type and key constants
            if event.type() == QtCore.QEvent.KeyPress:
                key = event.key()
                if key in (Qt.Key_Return, Qt.Key_Enter):
                    # Only trigger test if button is enabled
                    try:
                        if getattr(self, "btn_test", None) and self.btn_test.isEnabled():
                            # Call same handler as button click
                            self._on_test_button_clicked()
                            return True
                    except Exception:
                        pass
        except Exception:
            logger.exception("eventFilter error")
        # fall back to default processing
        return super().eventFilter(obj, event)

    def _on_worker_updated(self):
        # Called frequently while sweeping; show Testing when worker is active
        try:
            pct = float(getattr(self.app.worker, "percentage", 0.0))
        except Exception:
            pct = 0.0
        if 0.0 < pct < 100.0:
            if not self._testing:
                self._testing = True
                self._last_result_state = None
                self._set_status_style("Testing", "#FFD54F", "black")

    def _on_worker_finished(self):
        # Sweep finished; clear testing flag. If no evaluation result exists, show Ready
        self._testing = False
        if self._last_result_state is None:
            self._set_status_style("Ready", "#FFD54F", "black")
        else:
            pass
            #self.results_ready.emit(self.latest_result)
            #print("Emitted results_ready from worker finished")

