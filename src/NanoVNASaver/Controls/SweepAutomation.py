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

from PySide6 import QtCore, QtWidgets

from ..Defaults import SweepConfig, get_app_config
from ..Formatting import (
    format_frequency_inputs,
    format_frequency_short,
    format_frequency_sweep,
    parse_frequency,
)
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


class SweepAutomation(Control):
    def __init__(self, app: "vna_app"):
        super().__init__(app, "Test sequence")

        sweep_settings = self.get_settings()

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.VLine)

        input_layout = QtWidgets.QHBoxLayout()
        input_layout_l = QtWidgets.QFormLayout()
        input_layout_r = QtWidgets.QFormLayout()

        input_layout.addLayout(input_layout_l)
        input_layout.addWidget(line)
        input_layout.addLayout(input_layout_r)

        self.layout.addRow(input_layout)

        self.inputs: dict[str, FrequencyInputWidget] = {
            "Start": FrequencyInputWidget(sweep_settings.start),
            "Stop": FrequencyInputWidget(sweep_settings.end),
            "Center": FrequencyInputWidget(sweep_settings.center),
            "Span": FrequencyInputWidget(sweep_settings.span),
        }
        self.inputs["Start"].textEdited.connect(self.update_center_span)
        self.inputs["Start"].textChanged.connect(self.update_step_size)
        self.inputs["Stop"].textEdited.connect(self.update_center_span)
        self.inputs["Stop"].textChanged.connect(self.update_step_size)
        self.inputs["Center"].textEdited.connect(self.update_start_end)
        self.inputs["Span"].textEdited.connect(self.update_start_end)

        input_layout_l.addRow(QtWidgets.QLabel("Start"), self.inputs["Start"])
        input_layout_l.addRow(QtWidgets.QLabel("Stop"), self.inputs["Stop"])
        input_layout_r.addRow(QtWidgets.QLabel("Center"), self.inputs["Center"])
        input_layout_r.addRow(QtWidgets.QLabel("Span"), self.inputs["Span"])

        self.input_segments = QtWidgets.QLineEdit(sweep_settings.segments)
        self.input_segments.textEdited.connect(self.update_step_size)

        self.label_step = QtWidgets.QLabel("Hz/step")
        self.label_step.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        segment_layout = QtWidgets.QHBoxLayout()
        #segment_layout.addWidget(self.input_segments)
        #segment_layout.addWidget(self.label_step)
        #self.layout.addRow(QtWidgets.QLabel("Segments"), segment_layout)

        btn_settings_window = QtWidgets.QPushButton("Sweep settings ...")
        btn_settings_window.setFixedHeight(20)
        btn_settings_window.clicked.connect(
            lambda: self.app.display_window("sweep_settings")
        )

        self.layout.addRow(btn_settings_window)

        # --- Automation plan UI ---
        self.plan_list = QtWidgets.QListWidget()
        self.layout.addRow(self.plan_list)

        plan_btn_layout = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton("Add")
        btn_add.setFixedHeight(20)
        btn_add.clicked.connect(self.add_current)
        btn_remove = QtWidgets.QPushButton("Remove")
        btn_remove.setFixedHeight(20)
        btn_remove.clicked.connect(self.remove_selected)
        btn_load = QtWidgets.QPushButton("Load...")
        btn_load.setFixedHeight(20)
        btn_load.clicked.connect(self.load_plan)
        btn_save = QtWidgets.QPushButton("Save...")
        btn_save.setFixedHeight(20)
        btn_save.clicked.connect(self.save_plan)

        plan_btn_layout.addWidget(btn_add)
        plan_btn_layout.addWidget(btn_remove)
        plan_btn_layout.addWidget(btn_load)
        plan_btn_layout.addWidget(btn_save)
        plan_btn_layout.setContentsMargins(0, 0, 0, 0)
        plan_btn_widget = QtWidgets.QWidget()
        plan_btn_widget.setLayout(plan_btn_layout)
        self.layout.addRow(plan_btn_widget)

        # Internal state for automation
        self.plan: list[dict] = []
        self.current_plan_index = -1
        self.running_plan = False

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        #self.layout.addRow(self.progress_bar)

        self.btn_start = self._build_start_button()
        self.btn_stop = self._build_stop_button()

        # Buttons for running automation plan
        self.btn_run_plan = QtWidgets.QPushButton("Run")
        self.btn_run_plan.setFixedHeight(20)
        self.btn_run_plan.clicked.connect(self.run_plan)
        self.btn_stop_plan = QtWidgets.QPushButton("Stop")
        self.btn_stop_plan.setFixedHeight(20)
        self.btn_stop_plan.clicked.connect(self.stop_plan)
        self.btn_stop_plan.setDisabled(True)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_run_plan)
        btn_layout.addWidget(self.btn_stop_plan)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout_widget = QtWidgets.QWidget()
        btn_layout_widget.setLayout(btn_layout)
        self.layout.addRow(btn_layout_widget)

        self.inputs["Start"].textEdited.emit(self.inputs["Start"].text())
        self.inputs["Start"].textChanged.emit(self.inputs["Start"].text())

    def _build_start_button(self) -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton("Sweep")
        btn.setFixedHeight(20)
        btn.clicked.connect(self.app.sweep_start)
        btn.setShortcut(QtCore.Qt.Key.Key_Control + QtCore.Qt.Key.Key_W)
        # Will be enabled when VNA is connected
        btn.setEnabled(False)
        return btn

    def _build_stop_button(self) -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton("Stop")
        btn.setFixedHeight(20)
        btn.clicked.connect(self.app.worker.quit)
        btn.setShortcut(QtCore.Qt.Key.Key_Escape)
        btn.setDisabled(True)
        return btn

    def get_start(self) -> int:
        return self.inputs["Start"].get_freq()

    def set_start(self, start: int):
        self.inputs["Start"].setText(format_frequency_sweep(start))
        self.inputs["Start"].textEdited.emit(self.inputs["Start"].text())
        self.updated.emit(self)

    def get_end(self) -> int:
        return self.inputs["Stop"].get_freq()

    def set_end(self, end: int):
        self.inputs["Stop"].setText(format_frequency_sweep(end))
        self.inputs["Stop"].setText(format_frequency_sweep(end))
        self.inputs["Stop"].textEdited.emit(self.inputs["Stop"].text())
        self.updated.emit(self)

    def get_center(self) -> int:
        return self.inputs["Center"].get_freq()

    def set_center(self, center: int):
        self.inputs["Center"].setText(format_frequency_sweep(center))
        self.inputs["Center"].textEdited.emit(self.inputs["Center"].text())
        self.updated.emit(self)

    def get_segments(self) -> int:
        try:
            result = int(self.input_segments.text())
        except ValueError:
            result = 1
        return result

    def set_segments(self, count: int):
        self.input_segments.setText(str(count))
        self.input_segments.textEdited.emit(self.input_segments.text())
        self.updated.emit(self)

    def get_span(self) -> int:
        return self.inputs["Span"].get_freq()

    def set_span(self, span: int):
        self.inputs["Span"].setText(format_frequency_sweep(span))
        self.inputs["Span"].textEdited.emit(self.inputs["Span"].text())
        self.updated.emit(self)

    def toggle_settings(self, disabled):
        self.inputs["Start"].setDisabled(disabled)
        self.inputs["Stop"].setDisabled(disabled)
        self.inputs["Span"].setDisabled(disabled)
        self.inputs["Center"].setDisabled(disabled)
        self.input_segments.setDisabled(disabled)

    def update_center_span(self):
        fstart = self.get_start()
        fstop = self.get_end()
        fspan = fstop - fstart
        fcenter = round((fstart + fstop) / 2)
        if fspan < 0 or fstart < 0 or fstop < 0:
            return
        self.inputs["Center"].setText(fcenter)
        self.inputs["Span"].setText(fspan)
        self.update_text()
        self.update_sweep()

    def update_start_end(self):
        fcenter = self.get_center()
        fspan = self.get_span()
        if fspan < 0 or fcenter < 0:
            return
        fstart = round(fcenter - fspan / 2)
        fstop = round(fcenter + fspan / 2)
        if fstart < 0 or fstop < 0:
            return
        self.inputs["Start"].setText(fstart)
        self.inputs["Stop"].setText(fstop)
        self.update_text()
        self.update_sweep()

    def update_step_size(self):
        fspan = self.get_span()
        if fspan < 0:
            return
        segments = self.get_segments()
        if segments > 0:
            fstep = fspan / (segments * self.app.vna.datapoints - 1)
            self.label_step.setText(f"{format_frequency_short(fstep)}/step")
        self.update_sweep()

    def update_sweep(self):
        self.app.sweep.update(
            start=self.get_start(),
            end=self.get_end(),
            segments=self.get_segments(),
            points=self.app.vna.datapoints,
        )

    def update_sweep_btn(self, enabled: bool) -> None:
        self.btn_start.setEnabled(enabled)

    def get_settings(self) -> SweepConfig:
        return get_app_config().sweep_settings

    def store_settings(self) -> None:
        settings = self.get_settings()
        settings.start = self.inputs["Start"].text()
        settings.end = self.inputs["Stop"].text()
        settings.center = self.inputs["Center"].text()
        settings.span = self.inputs["Span"].text()
        settings.segments = self.input_segments.text()

    def update_text(self) -> None:
        cal_ds = self.app.calibration.dataset
        start = self.get_start()
        stop = self.get_end()
        if cal_ds.data:
            oor_text = (
                f"Out of calibration range ("
                f"{format_frequency_inputs(cal_ds.freq_min())} - "
                f"{format_frequency_inputs(cal_ds.freq_max())})"
            )
        else:
            oor_text = "No calibration data"
        self.inputs["Start"].setStyleSheet("QLineEdit {}")
        self.inputs["Stop"].setStyleSheet("QLineEdit {}")
        self.inputs["Start"].setToolTip("")
        self.inputs["Stop"].setToolTip("")
        if not cal_ds.data:
            self.inputs["Start"].setToolTip(oor_text)
            self.inputs["Start"].setStyleSheet("QLineEdit { color: red; }")
            self.inputs["Stop"].setToolTip(oor_text)
            self.inputs["Stop"].setStyleSheet("QLineEdit { color: red; }")
        else:
            if start < cal_ds.freq_min():
                self.inputs["Start"].setToolTip(oor_text)
                self.inputs["Start"].setStyleSheet("QLineEdit { color: red; }")
            if stop > cal_ds.freq_max():
                self.inputs["Stop"].setToolTip(oor_text)
                self.inputs["Stop"].setStyleSheet("QLineEdit { color: red; }")
        self.inputs["Start"].repaint()
        self.inputs["Stop"].repaint()

    # ---- Automation helpers ----
    def add_current(self) -> None:
        """Add the current sweep settings as a step in the plan."""
        step = {
            "start": self.get_start(),
            "end": self.get_end(),
            "segments": self.get_segments(),
            "points": self.app.vna.datapoints,
            "name": f"step_{len(self.plan) + 1}",
        }
        self.plan.append(step)
        self.plan_list.addItem(f"{step['name']}: {format_frequency_sweep(step['start'])}-{format_frequency_sweep(step['end'])} @ {step['points']}pts")

    def remove_selected(self) -> None:
        for it in self.plan_list.selectedItems():
            idx = self.plan_list.row(it)
            self.plan_list.takeItem(idx)
            self.plan.pop(idx)

    def load_plan(self) -> None:
        """Load a plan from a JSON file. The plan is a list of steps with keys: start,end,segments,points[,name]"""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self.app, "Load automation plan", filter="JSON Files (*.json);;All files (*)")
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8") as fh:
                import json

                plan = json.load(fh)
                if not isinstance(plan, list):
                    raise ValueError("Plan must be a list of steps")
                self.plan = plan
                self.plan_list.clear()
                for i, step in enumerate(self.plan):
                    name = step.get("name", f"step_{i+1}")
                    start = step.get("start")
                    end = step.get("end")
                    points = step.get("points", self.app.vna.datapoints)
                    self.plan_list.addItem(f"{name}: {start}-{end} @ {points}pts")
        except Exception as exc:  # keep UI stable on error
            logger.exception("Failed to load plan: %s", exc)
            self.app.showError(f"Failed to load plan: {exc}")

    def save_plan(self) -> None:
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self.app, "Save automation plan", filter="JSON Files (*.json);;All files (*)")
        if not filename:
            return
        try:
            import json

            with open(filename, "w", encoding="utf-8") as fh:
                json.dump(self.plan, fh, indent=2)
        except Exception as exc:
            logger.exception("Failed to save plan: %s", exc)
            self.app.showError(f"Failed to save plan: {exc}")

    def run_plan(self) -> None:
        """Start running the loaded plan sequentially."""
        if not self.plan:
            self.app.showError("No automation plan loaded")
            return
        if not self.app.vna.connected():
            self.app.showError("VNA not connected")
            return
        self.running_plan = True
        self.btn_run_plan.setDisabled(True)
        self.btn_stop_plan.setDisabled(False)
        self.btn_start.setDisabled(True)
        self.app.sweep_control.toggle_settings(True)

        # connect to worker finished signal
        self.app.worker.signals.finished.connect(self._on_worker_finished)
        self.current_plan_index = 0
        self._start_current_step()

    def stop_plan(self) -> None:
        """Stop ongoing plan run."""
        if not self.running_plan:
            return
        self.running_plan = False
        self.btn_run_plan.setDisabled(False)
        self.btn_stop_plan.setDisabled(True)
        self.btn_start.setDisabled(False)
        self.app.sweep_control.toggle_settings(False)
        # signal worker to stop
        self.app.worker.quit()
        try:
            self.app.worker.signals.finished.disconnect(self._on_worker_finished)
        except Exception:
            pass

    def _start_current_step(self) -> None:
        step = self.plan[self.current_plan_index]
        name = step.get("name", f"step_{self.current_plan_index + 1}")
        self.app.sweep.update(
            start=step["start"],
            end=step["end"],
            segments=step.get("segments", 1),
            points=step.get("points", self.app.vna.datapoints),
        )
        
        self.app.sweep.set_name(name)
        # start sweep; SweepWorker will emit finished when done
        self.app.sweep_start()

    def _on_worker_finished(self) -> None:
        """Handler invoked when a sweep finishes; start next or finish plan run."""
        # optional: save data automatically per-step here
        # e.g. self.app.saveData(..., source=...) or call Touchstone.save
        if not self.running_plan:
            return
        self.current_plan_index += 1
        if self.current_plan_index >= len(self.plan):
            # Done
            self.running_plan = False
            self.btn_run_plan.setDisabled(False)
            self.btn_stop_plan.setDisabled(True)
            self.btn_start.setDisabled(False)
            self.app.sweep_control.toggle_settings(False)
            try:
                self.app.worker.signals.finished.disconnect(self._on_worker_finished)
            except Exception:
                pass
            QtWidgets.QMessageBox.information(self, "Information", "Test sequnce finished")
            
            return
        # Start next
        self._start_current_step()
