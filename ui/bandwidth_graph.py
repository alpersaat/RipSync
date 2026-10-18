from collections import deque
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen, QLinearGradient, QFont
from PyQt6.QtWidgets import QWidget

from ui.styles import format_speed, T


class BandwidthGraphWidget(QWidget):
    """
    Sleek, lightweight real-time bandwidth sparkline graph.
    Visualizes download speed history over the last 30-40 seconds.
    Designed to fit seamlessly in the status bar or toolbar.
    """
    def __init__(self, max_samples: int = 40, parent=None):
        super().__init__(parent)
        self.max_samples = max_samples
        self.history = deque([0.0] * self.max_samples, maxlen=self.max_samples)
        self.current_speed = 0.0
        self.max_speed = 0.0

        self.setFixedSize(140, 26)
        self.setToolTip("Canlı İndirme Hızı Dalgalanma Grafiği (Son 40 sn)")

    def add_speed_sample(self, speed_bps: float):
        """Append a new speed sample (in bytes per second) and trigger repaint."""
        val = max(0.0, float(speed_bps))
        self.history.append(val)
        self.current_speed = val
        self.max_speed = max(self.history)
        self.update()

    def reset(self):
        """Reset the graph history to 0."""
        self.history = deque([0.0] * self.max_samples, maxlen=self.max_samples)
        self.current_speed = 0.0
        self.max_speed = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background rounded card
        bg_color = QColor(T['code_bg'])
        border_color = QColor(T['bg_hover'])
        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(0, 0, w - 1, h - 1, 4, 4)

        if not self.history:
            return

        # Determine scale: minimum scale ceiling is 256 KB/s
        ceiling = max(256 * 1024.0, self.max_speed * 1.15)
        samples = list(self.history)
        n = len(samples)
        if n < 2:
            return

        step_x = (w - 4) / float(n - 1)
        pad_bottom = 2.0
        pad_top = 3.0
        avail_h = h - pad_bottom - pad_top

        # Compute points
        points = []
        for i, val in enumerate(samples):
            x = 2.0 + (i * step_x)
            ratio = min(1.0, max(0.0, val / ceiling))
            y = (h - pad_bottom) - (ratio * avail_h)
            points.append(QPointF(x, y))

        # Build path for fill
        fill_path = QPainterPath()
        fill_path.moveTo(points[0].x(), h - pad_bottom)
        for pt in points:
            fill_path.lineTo(pt)
        fill_path.lineTo(points[-1].x(), h - pad_bottom)
        fill_path.closeSubpath()

        # Gradient fill
        gradient = QLinearGradient(0, pad_top, 0, h - pad_bottom)
        gradient.setColorAt(0.0, QColor(122, 162, 247, 100))  # TokyoNight Blue
        gradient.setColorAt(1.0, QColor(122, 162, 247, 5))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(fill_path)

        # Stroke line path
        line_path = QPainterPath()
        line_path.moveTo(points[0])
        for pt in points[1:]:
            line_path.lineTo(pt)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(T['accent']), 1.4))
        painter.drawPath(line_path)

        # Draw peak text overlay if active
        if self.max_speed > 1024:
            painter.setPen(QColor(169, 177, 214, 180))
            f = QFont("Segoe UI", 7)
            painter.setFont(f)
            peak_str = format_speed(self.max_speed)
            painter.drawText(6, 11, f"⚡ {peak_str}")

