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
import contextlib
import logging
import threading
from time import localtime, strftime

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QWidget

from .About import VERSION
from .Calibration import Calibration
from .Charts import (
    CapacitanceChart,
    CombinedLogMagChart,
    GroupDelayChart,
    InductanceChart,
    LogMagChart,
    MagnitudeChart,
    MagnitudeZChart,
    MagnitudeZSeriesChart,
    MagnitudeZShuntChart,
    PermeabilityChart,
    PhaseChart,
    PolarChart,
    QualityFactorChart,
    RealImaginaryMuChart,
    RealImaginaryZChart,
    RealImaginaryZSeriesChart,
    RealImaginaryZShuntChart,
    SmithChart,
    SParameterChart,
    TDRChart,
    VSWRChart,
)
from .Charts.Chart import Chart
from .Controls.MarkerControl import MarkerControl
from .Controls.SerialControl import SerialControl
from .Controls.SweepControl import SweepControl
from .Defaults import APP_SETTINGS, AppSettings, get_app_config
from .Formatting import format_frequency, format_gain, format_vswr
from .Hardware.Hardware import Interface
from .Hardware.VNA import VNA
from .Marker.Delta import DeltaMarker
from .Marker.Widget import Marker
from .RFTools import corr_att_data
from .Settings.Bands import BandsModel
from .Settings.Sweep import Sweep
from .SweepWorker import SweepWorker
from .Touchstone import Touchstone
from .Windows import (
    AboutWindow,
    AnalysisWindow,
    CalibrationWindow,
    DeviceSettingsWindow,
    DisplaySettingsWindow,
    FilesWindow,
    SweepSettingsWindow,
    TDRWindow,
)
from .Windows.ui import get_window_icon

logger = logging.getLogger(__name__)

WORKING_KILL_TIME_MS = 10 * 1000


class Communicate(QObject):
    data_available = QtCore.Signal()


class NanoVNASaver(QWidget):
    version = VERSION
    scale_factor = 1.0

    def __init__(self) -> None:
        super().__init__()
        self.setWindowIcon(get_window_icon())
        self.version = VERSION
        self.baseTitle = f"Filter test stand (NanoVNASaver version: {self.version})"
        self.setWindowTitle(self.baseTitle)

        # Minimal windows dict so display_window works
        self.windows: dict[str, QtWidgets.QDialog] = {
            "about": AboutWindow(self),
        }

        # Top-level layout for the test UI
        main_layout = QtWidgets.QVBoxLayout()
        self.setLayout(main_layout)

        # Create test panel: two columns
        test_widget = QtWidgets.QWidget()
        test_layout = QtWidgets.QHBoxLayout()
        test_widget.setLayout(test_layout)

        # Left column
        left_col = QtWidgets.QVBoxLayout()
        btn_load_cal = QtWidgets.QPushButton("Load calibration file")
        btn_load_cal.setMinimumHeight(48)
        btn_load_cal.clicked.connect(lambda: self.display_window("about"))

        cal_file_name = QtWidgets.QLabel("No calibration file loaded")

        btn_res_folder = QtWidgets.QPushButton("Open test results folder")
        btn_res_folder.setMinimumHeight(28)
        btn_res_folder.clicked.connect(lambda: self.display_window("about"))

        btn_log = QtWidgets.QPushButton("Display test log")
        btn_log.setMinimumHeight(28)
        btn_log.clicked.connect(lambda: self.display_window("about"))
        
        

        lbl_start = QtWidgets.QLabel("Start frequency")
        inp_start = QtWidgets.QLineEdit()
        inp_start.setPlaceholderText("Start (Hz)")

        lbl_end = QtWidgets.QLabel("End frequency")
        inp_end = QtWidgets.QLineEdit()
        inp_end.setPlaceholderText("End (Hz)")

        lbl_points = QtWidgets.QLabel("Number of measurement points")
        inp_points = QtWidgets.QLineEdit()
        inp_points.setPlaceholderText("5")

        left_col.addWidget(btn_load_cal)
        left_col.addWidget(cal_file_name)
        left_col.addSpacing(8)
        left_col.addWidget(lbl_start)
        left_col.addWidget(inp_start)
        left_col.addWidget(lbl_end)
        left_col.addWidget(inp_end)
        left_col.addWidget(lbl_points)
        left_col.addWidget(inp_points)
        left_col.addSpacing(8)
        left_col.addWidget(btn_res_folder)
        left_col.addWidget(btn_log)
        left_col.addStretch(1)

        left_widget = QtWidgets.QWidget()
        left_widget.setLayout(left_col)
        left_widget.setMinimumWidth(200)

        # Right column
        right_col = QtWidgets.QVBoxLayout()
        
        sample_id = QtWidgets.QLabel("Sample #0000001")
        sample_id.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        sample_id.setStyleSheet("""
        QLabel {
        color: black;
        font-size: 18px;
        padding: 10px;
        }
        """)

        

        status = QtWidgets.QLabel("PASS")
        status.setStyleSheet("""
        QLabel {
        color: green;
        font-size: 56px;
        padding: 10px;
        }
        """)
        status.setMinimumHeight(80)
        #status.setMinimumWidth(260)
        status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        btn_test = QtWidgets.QPushButton("Test")
        btn_test.setMinimumHeight(80)
        btn_test.clicked.connect(lambda: self.display_window("about"))

        test_sequence = QtWidgets.QListWidget()
        #placeholder test log
        test_sequence.addItem("Reading calibration file... OK")
        test_sequence.addItem("Measuring point #1 ... OK")
        test_sequence.addItem("Measuring point #2 ... OK")
        test_sequence.addItem("Measuring point #3 ... OK")
        test_sequence.addItem("Measuring point #4 ... OK")
        test_sequence.addItem("Measuring point #5 ... OK")
        test_sequence.addItem("Writing result file ... OK")
        test_sequence.addItem("Printing label... OK")
        success = QtWidgets.QListWidgetItem("Success! All tests passed.")
        success.setForeground(QtGui.QBrush(QtGui.QColor("Green")))
        test_sequence.addItem(success)
        test_sequence.setMinimumHeight(200)
 

        right_col.addWidget(sample_id)
        right_col.addWidget(status)
        right_col.addWidget(test_sequence)
        right_col.addWidget(btn_test)
        right_col.addStretch(1)

        right_widget = QtWidgets.QWidget()
        right_widget.setLayout(right_col)

        test_layout.addWidget(left_widget)
        test_layout.addWidget(right_widget)
        test_layout.setStretch(0, 0)
        test_layout.setStretch(1, 1)
    

        main_layout.addWidget(test_widget)

        '''
        # Full-width placeholder row under the two columns
        placeholder = QtWidgets.QLabel("placeholder")
        placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        
        # Give it a bit of vertical presence
        placeholder.setMinimumHeight(30)
        main_layout.addWidget(placeholder)
        '''

    def auto_connect(
        self,
    ):  # connect if there is exactly one detected serial device
        if self.serial_control.inp_port.count() == 1:
            self.serial_control.connect_device()

    def _sweep_control(self, start: bool = True) -> None:
        self.sweep_control.progress_bar.setValue(0 if start else 100)
        self.sweep_control.btn_start.setDisabled(start)
        self.sweep_control.btn_stop.setDisabled(not start)
        self.sweep_control.toggle_settings(start)

    def sweep_start(self):
        # Run the device data update
        if not self.vna.connected():
            return
        self._sweep_control(start=True)

        for m in self.markers:
            m.resetLabels()
        self.s11_min_rl_label.setText("")
        self.s11_min_swr_label.setText("")
        self.s21_min_gain_label.setText("")
        self.s21_max_gain_label.setText("")
        self.tdr_result_label.setText("")

        logger.debug("Starting worker thread")
        self.worker.start()
        # TODO: Rewrite to make worker a qrunnable with worker signals
        # https://www.pythonguis.com/tutorials/multithreading-pyqt6-applications-qthreadpool/
        # self.threadpool.start(self.worker)

    def saveData(self, data, data21, source=None):
        with self.dataLock:
            self.data.s11 = data
            self.data.s21 = data21
            if self.s21att > 0:
                self.data.s21 = corr_att_data(self.data.s21, self.s21att)
        if source is not None:
            self.sweepSource = source
        else:
            time = strftime("%Y-%m-%d %H:%M:%S", localtime())
            name = self.sweep.properties.name or "nanovna"
            self.sweepSource = f"{name}_{time}"

    def markerUpdated(self, marker: Marker):
        with self.dataLock:
            marker.findLocation(self.data.s11)
            marker.resetLabels()
            marker.updateLabels(self.data.s11, self.data.s21)
            for c in self.subscribing_charts:
                c.update()
        if not self.delta_marker_layout.isHidden():
            m1 = self.markers[0]
            m2 = None
            if self.marker_ref:
                if self.ref_data:
                    m2 = Marker("Reference")
                    m2.location = self.markers[0].location
                    m2.resetLabels()
                    m2.updateLabels(self.ref_data.s11, self.ref_data.s21)
                else:
                    logger.warning("No reference data for marker")

            elif Marker.count() >= 2:
                m2 = self.markers[1]

            if m2 is None:
                logger.error("No data for delta, missing marker or reference")
            else:
                self.delta_marker.set_markers(m1, m2)
                self.delta_marker.resetLabels()
                with contextlib.suppress(IndexError):
                    self.delta_marker.updateLabels()

    def dataUpdated(self):
        with self.dataLock:
            s11 = self.data.s11[:]
            s21 = self.data.s21[:]

        for m in self.markers:
            m.resetLabels()
            m.updateLabels(s11, s21)

        for c in self.s11charts:
            c.setData(s11)

        for c in self.s21charts:
            c.setData(s21)

        for c in self.combinedCharts:
            c.setCombinedData(s11, s21)

        self.sweep_control.progress_bar.setValue(int(self.worker.percentage))
        self.windows["tdr"].updateTDR()

        if s11:
            min_vswr = min(s11, key=lambda data: data.vswr)
            self.s11_min_swr_label.setText(
                f"{format_vswr(min_vswr.vswr)} @"
                f" {format_frequency(min_vswr.freq)}"
            )
            self.s11_min_rl_label.setText(format_gain(min_vswr.gain))
        else:
            self.s11_min_swr_label.setText("")
            self.s11_min_rl_label.setText("")

        if s21:
            min_gain = min(s21, key=lambda data: data.gain)
            max_gain = max(s21, key=lambda data: data.gain)
            self.s21_min_gain_label.setText(
                f"{format_gain(min_gain.gain)}"
                f" @ {format_frequency(min_gain.freq)}"
            )
            self.s21_max_gain_label.setText(
                f"{format_gain(max_gain.gain)}"
                f" @ {format_frequency(max_gain.freq)}"
            )
        else:
            self.s21_min_gain_label.setText("")
            self.s21_max_gain_label.setText("")

        self.updateTitle()
        self.communicate.data_available.emit()

    def sweepFinished(self):
        self._sweep_control(start=False)

        for marker in self.markers:
            marker.frequencyInput.textEdited.emit(marker.frequencyInput.text())

    def setReference(self, s11=None, s21=None, source=None):
        if not s11:
            with self.dataLock:
                s11 = self.data.s11[:]
                s21 = self.data.s21[:]

        self.ref_data.s11 = s11
        for c in self.s11charts:
            c.setReference(s11)

        self.ref_data.s21 = s21
        for c in self.s21charts:
            c.setReference(s21)

        for c in self.combinedCharts:
            c.setCombinedReference(s11, s21)

        self.btnResetReference.setDisabled(False)

        self.referenceSource = source or self.sweepSource
        self.updateTitle()

    def updateTitle(self):
        insert = "("
        if self.sweepSource != "":
            insert += (
                f"Sweep: {self.sweepSource} @ {len(self.data.s11)} points"
                f"{', ' if self.referenceSource else ''}"
            )
        if self.referenceSource != "":
            insert += (
                f"Reference: {self.referenceSource} @"
                f" {len(self.ref_data.s11)} points"
            )
        insert += ")"
        title = f"{self.baseTitle} {insert or ''}"
        self.setWindowTitle(title)

    def resetReference(self):
        self.ref_data = Touchstone()
        self.referenceSource = ""
        self.updateTitle()
        for c in self.subscribing_charts:
            c.resetReference()
        self.btnResetReference.setDisabled(True)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(1100, 400)

    def display_window(self, name):
        self.windows[name].show()
        QtWidgets.QApplication.setActiveWindow(self.windows[name])

    def showError(self, text):
        QtWidgets.QMessageBox.warning(self, "Error", text)

    def showSweepError(self):
        self.showError(self.worker.error_message)
        with contextlib.suppress(IOError):
            self.vna.flushSerialBuffers()  # Remove any left-over data
            self.vna.reconnect()  # try reconnection
        self.sweepFinished()

    def popoutChart(self, chart: Chart):
        logger.debug("Requested popout for chart: %s", chart.name)
        new_chart = self.copyChart(chart)
        new_chart.isPopout = True
        new_chart.show()
        new_chart.setWindowTitle(new_chart.name)
        new_chart.setWindowIcon(get_window_icon())

    def copyChart(self, chart: Chart):
        new_chart = chart.copy()
        self.subscribing_charts.append(new_chart)
        if chart in self.s11charts:
            self.s11charts.append(new_chart)
        if chart in self.s21charts:
            self.s21charts.append(new_chart)
        if chart in self.combinedCharts:
            self.combinedCharts.append(new_chart)
        new_chart.popout_requested.connect(self.popoutChart)
        return new_chart

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        self.worker.quit()
        self.worker.wait(WORKING_KILL_TIME_MS)
        for marker in self.markers:
            marker.update_settings()
        self.settings.sync()
        self.bands.saveSettings()
        self.threadpool.waitForDone(2500)

        app_config = get_app_config()
        app_config.chart.marker_count = Marker.count()
        app_config.gui.window_width = self.width()
        app_config.gui.window_height = self.height()
        app_config.gui.splitter_sizes = self.splitter.saveState()

        self.sweep_control.store_settings()

        self.settings.store_config()

        # Dosconnect connected devices and release serial port
        self.serial_control.disconnect_device()

        a0.accept()

    def changeFont(self, font: QtGui.QFont) -> None:
        qf_new = QtGui.QFontMetricsF(font)
        normal_font = QtGui.QFont(font)
        normal_font.setPointSize(8)
        qf_normal = QtGui.QFontMetricsF(normal_font)
        # Characters we would normally display
        standard_string = "0.123456789 0.123456789 MHz \N{OHM SIGN}"
        new_width = qf_new.horizontalAdvance(standard_string)
        old_width = qf_normal.horizontalAdvance(standard_string)
        self.scale_factor = new_width / old_width
        logger.debug(
            "New font width: %f, normal font: %f, factor: %f",
            new_width,
            old_width,
            self.scale_factor,
        )
        # TODO: Update all the fixed widths to account for the scaling
        for m in self.markers:
            m.get_data_layout().setFont(font)
            m.setScale(self.scale_factor)

    def update_sweep_title(self):
        for c in self.subscribing_charts:
            c.setSweepTitle(self.sweep.properties.name)
