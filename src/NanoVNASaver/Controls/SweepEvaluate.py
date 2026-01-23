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

        btn_golden= QtWidgets.QPushButton("Test golden sample")
        btn_golden.setFixedHeight(40)
        btn_golden_set= QtWidgets.QPushButton("Set as reference")
        btn_golden_set.setFixedHeight(40)
        middle_top_row = QtWidgets.QVBoxLayout()

        middle_top_row.addWidget(self.golden_title)
        middle_top_row.addWidget(self.golden_label)
        
        middle_bot_row = QtWidgets.QHBoxLayout()
        middle_bot_row.addWidget(btn_golden)
        middle_bot_row.addWidget(btn_golden_set)

        middle_column.addRow(middle_top_row)
        middle_column.addRow(middle_bot_row)


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
            QtWidgets.QMessageBox.warning(self, "Error", "Failed to load test spec")
            return
        self.spec = spec
        self.spec_label.setText(str(Path(path).name))
        self.populate_table()
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
        text, ok = QtWidgets.QInputDialog.getText(self, "Serial number", "Enter serial number:")
        if not ok:
            return
        serial = str(text).strip()
        if not serial:
            QtWidgets.QMessageBox.warning(self, "Invalid serial", "No serial number entered")
            return
        self.current_serial = serial
        logger.debug("Serial entered: %s", self.current_serial)
        try:
            self.app.sweep_start()
        except Exception:
            logger.exception("Failed to start sweep")

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

            # PCB lot field
            try:
                pcb_text = ""
                if hasattr(self.app, "lot_control") and hasattr(self.app.lot_control, "pcb_lot_field"):
                    pcb_text = str(self.app.lot_control.pcb_lot_field.text()).strip()
                pcb_ok = bool(pcb_text)
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

