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
import math
from dataclasses import dataclass

from PySide6 import QtGui

from ..RFTools import Datapoint
from ..SITools import log_floor_125
from .Chart import Chart
from .Frequency import FrequencyChart
from ..Formatting import format_frequency_short, format_gain

logger = logging.getLogger(__name__)


@dataclass
class TickVal:
    count: int = 0
    first: float = 0.0
    step: float = 0.0


def span2ticks(span: float, min_val: float) -> TickVal:
    span = abs(span)
    step = log_floor_125(span / 5)
    count = math.floor(span / step)
    first = math.ceil(min_val / step) * step
    if first == min_val:
        first += step
    return TickVal(count, first, step)


class LogMagChart(FrequencyChart):
    def __init__(self, name="") -> None:
        super().__init__(name)

        self.name_unit: str = "dB"

        self.minDisplayValue: int = -80
        self.maxDisplayValue: int = 10

        self.minValue: float = 0.0
        self.maxValue: float = 1.0
        self.span: float = 1.0

        self.isInverted: bool = False

    def drawValues(self, qp: QtGui.QPainter) -> None:
        if len(self.data) == 0 and len(self.reference) == 0:
            return
        self._set_start_stop()

        # Draw bands if required
        if self.bands.enabled:
            self.drawBands(qp, self.fstart, self.fstop)

        self.calc_scaling()
        self.draw_grid(qp)

        # Draw golden reference behind the current sweep (light gray)
        if getattr(self, "golden_reference", None):
            try:
                self.drawData(qp, self.golden_reference, Chart.color.golden)
            except Exception:
                pass

        # Draw any stored reference and then the current sweep on top
        self.drawData(qp, self.reference, Chart.color.reference)
        self.drawData(qp, self.data, Chart.color.sweep)
        self.drawMarkers(qp)

    def calc_scaling(self) -> None:
        if self.fixedValues:
            maxValue = self.maxDisplayValue
            minValue = self.minDisplayValue
        else:
            # Find scaling
            min_val = 100.0
            max_val = -100.0
            for d in self.data:
                logmag = self.logMag(d)
                if math.isinf(logmag):
                    continue
                max_val = max(max_val, logmag)
                min_val = min(min_val, logmag)

            # Also check min/max for the reference sweep
            for d in self.reference:
                if d.freq < self.fstart or d.freq > self.fstop:
                    continue
                logmag = self.logMag(d)
                if math.isinf(logmag):
                    continue
                max_val = max(max_val, logmag)
                min_val = min(min_val, logmag)

            # Also include golden reference sweep in scaling
            try:
                for d in self.golden_reference:
                    if d.freq < self.fstart or d.freq > self.fstop:
                        continue
                    logmag = self.logMag(d)
                    if math.isinf(logmag):
                        continue
                    max_val = max(max_val, logmag)
                    min_val = min(min_val, logmag)
            except Exception:
                # graceful if golden_reference not present
                pass

            minValue = 10 * math.floor(min_val / 10)
            maxValue = 10 * math.ceil(max_val / 10)

        self.minValue = minValue
        self.maxValue = maxValue

    def draw_grid(self, qp):
        self.span = (self.maxValue - self.minValue) or 0.01
        ticks = span2ticks(self.span, self.minValue)
        self.draw_db_lines(qp, self.maxValue, self.minValue, ticks)

        qp.setPen(QtGui.QPen(Chart.color.foreground))
        qp.drawLine(
            self.leftMargin - 5,
            self.topMargin,
            self.leftMargin + self.dim.width,
            self.topMargin,
        )
        qp.setPen(Chart.color.text)
        qp.drawText(3, self.topMargin + 4, f"{self.maxValue}")
        qp.drawText(3, self.dim.height + self.topMargin, f"{self.minValue}")
        self.drawFrequencyTicks(qp)
        self.draw_swr_markers(qp)

    def draw_db_lines(self, qp, max_value: int, min_value: int, ticks) -> None:
        for i in range(ticks.count):
            db = ticks.first + i * ticks.step
            y = self.topMargin + round(
                (max_value - db) / self.span * self.dim.height
            )
            qp.setPen(QtGui.QPen(Chart.color.foreground))
            qp.drawLine(
                self.leftMargin - 5, y, self.leftMargin + self.dim.width, y
            )
            if db > min_value and db != max_value:
                qp.setPen(QtGui.QPen(Chart.color.text))
                qp.drawText(
                    3, y + 4, f"{round(db, 1)}" if ticks.step < 1 else f"{db}"
                )

    def draw_swr_markers(self, qp) -> None:
        qp.setPen(Chart.color.swr)
        for vswr in self.swrMarkers:
            if vswr <= 1:
                continue
            logMag = 20 * math.log10((vswr - 1) / (vswr + 1))
            if self.isInverted:
                logMag = logMag * -1
            y = self.topMargin + round(
                (self.maxValue - logMag) / self.span * self.dim.height
            )
            qp.drawLine(self.leftMargin, y, self.leftMargin + self.dim.width, y)
            qp.drawText(self.leftMargin + 3, y - 1, f"VSWR: {vswr}")

    def getYPosition(self, d: Datapoint) -> int:
        logMag = self.logMag(d)
        if math.isinf(logMag):
            return self.topMargin
        return self.topMargin + int(
            (self.maxValue - logMag) / self.span * self.dim.height
        )

    def valueAtPosition(self, y) -> list[float]:
        absy = y - self.topMargin
        val = -1 * ((absy / self.dim.height * self.span) - self.maxValue)
        return [val]

    def logMag(self, p: Datapoint) -> float:
        return -p.gain if self.isInverted else p.gain

    def copy(self) -> "LogMagChart":
        new_chart: LogMagChart = super().copy()
        new_chart.isInverted = self.isInverted
        new_chart.span = self.span
        return new_chart


class LogMagTest(LogMagChart):
    """Log magnitude chart that can render test-spec limit markers.

    The chart is passed a TestSpec and will draw a limit marker for each
    TestPoint in the spec. The marker width is determined by the TestPoint
    span (frequency span in Hz) and the vertical position corresponds to
    the TestPoint.limit_db converted to the chart's value-space (respecting
    inversion via `isInverted`).

    Direction semantics:
    - "under": draw a box with top removed (open-top 'U')
    - "over": draw a box with bottom removed (open-bottom '^')
    """

    def __init__(self, name: str = "") -> None:
        super().__init__(name)
        self.testspec = None

    def setTestSpec(self, spec) -> None:
        self.testspec = spec
        self.update()

    def compute_test_marker(self, tp):
        """Compute marker geometry for a TestPoint.

        Returns a dict with x_left, x_right, y (pixel coordinates) and direction.
        This method is intentionally public so unit tests can assert geometry
        without relying on actual painting.
        """
        # Frequency span to x coordinates
        low = tp.frequency - tp.span // 2
        high = tp.frequency + tp.span // 2
        x_left = max(self.leftMargin, self.getXPosition(Datapoint(low, 0, 0)))
        x_right = min(
            self.leftMargin + self.dim.width,
            self.getXPosition(Datapoint(high, 0, 0)),
        )
        x_mid = int((x_left + x_right) // 2)

        # Convert limit_db to chart value-space (respecting inversion)
        value = -tp.limit_db if self.isInverted else tp.limit_db
        # Guard against zero span
        span = self.span or 1e-9
        y = self.topMargin + round((self.maxValue - value) / span * self.dim.height)

        # Determine vertical line start depending on direction: "under" -> line from top, "over" -> line from bottom
        if (tp.direction or "over").lower() == "under":
            line_start_y = self.topMargin
        else:
            line_start_y = self.topMargin + self.dim.height

        return {
            "x_left": int(x_left),
            "x_right": int(x_right),
            "x_mid": int(x_mid),
            "y": int(y),
            "line_start_y": int(line_start_y),
            "direction": tp.direction,
            "tp": tp,
        }

    def drawValues(self, qp: QtGui.QPainter) -> None:
        # Let the parent draw everything else first
        super().drawValues(qp)

        if not self.testspec:
            return

        qp.setPen(QtGui.QPen(Chart.color.text, 2))
        # marker_height controls arrowhead size
        for tp in self.testspec.tests:
            geom = self.compute_test_marker(tp)
            xl = geom["x_left"]
            xr = geom["x_right"]
            xm = geom["x_mid"]
            y = geom["y"]
            line_start = geom["line_start_y"]
            direction = (geom["direction"] or "over").lower()

            # Draw the vertical line from top or bottom up to the arrow tip
            qp.drawLine(xm, line_start, xm, y)

            # Arrowhead size: base on span width but keep reasonable limits
            head_w = max(6, int((xr - xl) / 4))
            head_h = max(5, int(head_w / 2))

            if direction == "under":
                # Arrow points downwards: draw two lines forming a V pointing down at (xm, y)
                qp.drawLine(xm - head_w, y - head_h, xm, y)
                qp.drawLine(xm + head_w, y - head_h, xm, y)
            else:
                # "over" or default: arrow points upwards
                qp.drawLine(xm - head_w, y + head_h, xm, y)
                qp.drawLine(xm + head_w, y + head_h, xm, y)

            # Optionally label with the test name
            try:
                qp.drawText(xl + 10, y - 15, tp.name)
                qp.drawText(xl + 10, y , f"{format_gain(tp.limit_db)}")
                qp.drawText(xl + 10, y + 15, f"{format_frequency_short(tp.span)}")
            except Exception:
                # Fallback: ignore drawing errors (keeps tests headless-friendly)
                pass

