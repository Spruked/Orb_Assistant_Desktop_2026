import sys
import math
import os
from collections import deque
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QGraphicsDropShadowEffect,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
)
from PySide6.QtCore import Qt, QTimer, QPoint, Signal, QObject, QThread, QRect, QPointF
from PySide6.QtGui import (
    QColor,
    QPainter,
    QBrush,
    QPen,
    QFont,
    QCursor,
    QRadialGradient,
)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orb_controller import SF_ORB_Controller
from gravity_field_2d import EpistemicGravityField2D


class CognitiveWorker(QObject):
    """Background thread for cognitive processing"""

    pulse_signal = Signal(dict)

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.running = True
        self.last_pos = QPoint(0, 0)
        self.last_time = 0

    def process_cursor(self, pos):
        if not self.running:
            return

        # Calculate velocity
        current_time = os.times().system
        dx = pos.x() - self.last_pos.x()
        dy = pos.y() - self.last_pos.y()
        dt = current_time - self.last_time if self.last_time > 0 else 0.016
        velocity = math.sqrt(dx * dx + dy * dy) / max(dt, 0.001)

        self.last_pos = pos
        self.last_time = current_time

        stimulus = {
            "type": "cursor_movement",
            "coordinates": [pos.x(), pos.y()],
            "velocity": min(velocity, 50.0),  # Cap velocity
            "intent": "navigation",
        }

        thought = self.controller.cognitively_emerge(stimulus)
        if thought:
            self.pulse_signal.emit(thought.pulse())


class FloatingOrb(QWidget):
    def __init__(self):
        super().__init__()
        self.controller = SF_ORB_Controller()

        # Window setup
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(120, 120)

        # Position
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())

        # State
        self.current_pos = self.pos()
        # Single source of truth for target position (top-left corner of the widget)
        self.target_pos = self.pos()

        # Cognitive state
        self.cognitive_mode = "GUARD"
        self.glow_intensity = 0.5
        self.predictive_offset = QPoint(0, 0)
        self.necessity_vector = (0.0, 0.0)
        self.jump_active = False
        self.field_density = 0
        self.edge_cutter_active = False
        self.purge_phase = 0
        self.proc_time_ms = 0.0
        self.latency_samples = deque(maxlen=40)

        # Gravity / Proprioception
        self.gravity_field = EpistemicGravityField2D()
        self.gravity_pressure = 0.0
        self.nav_vector = None  # [x, y] from controller
        self.sine_phase = 0.0  # Phase for sine-based jitter

        # Mode colors
        self.colors = {
            "GUARD": QColor(0, 128, 128),  # Teal
            "GUARD-HABIT": QColor(64, 160, 100),  # Teal-Green
            "HABIT": QColor(255, 191, 0),  # Amber
            "INTUITION-JUMP": QColor(143, 0, 255),  # Violet
        }
        self.current_color = self.colors["GUARD"]
        self.pulse_phase = 0

        # Setup worker thread
        self.worker_thread = QThread()
        self.worker = CognitiveWorker(self.controller)
        self.worker.moveToThread(self.worker_thread)
        self.worker.pulse_signal.connect(self.handle_pulse)

        # Timers
        self.track_timer = QTimer()
        self.track_timer.timeout.connect(self.track_cursor)
        self.track_timer.start(16)  # 60fps tracking

        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(16)

        self.cognitive_timer = QTimer()
        self.cognitive_timer.timeout.connect(self.process_cognition)
        self.cognitive_timer.start(100)  # 10Hz cognition

        self.last_cursor = QCursor.pos()
        self.setup_ui()
        self.worker_thread.start()

    def setup_ui(self):
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(30)
        self.shadow.setColor(self.current_color)
        self.shadow.setOffset(0, 0)
        self.setGraphicsEffect(self.shadow)

        self.hud = QLabel(self)
        self.hud.setGeometry(10, 45, 100, 30)
        self.hud.setStyleSheet("""
            color: white; 
            background: rgba(0,0,0,0.7); 
            border-radius: 15px; 
            padding: 5px;
            font-weight: bold;
        """)
        self.hud.setFont(QFont("Consolas", 9))
        self.hud.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hud.setText("GUARD")
        self.hud.hide()

    def track_cursor(self):
        self.last_cursor = QCursor.pos()

    def process_cognition(self):
        if self.worker_thread.isRunning():
            self.worker.process_cursor(self.last_cursor)

    def handle_pulse(self, pulse):
        mode = pulse.get("cognitive_mode", "GUARD")
        self.cognitive_mode = mode
        self.glow_intensity = pulse.get("glow_intensity", 0.5)
        self.field_density = pulse.get("field_density", 0)
        self.proc_time_ms = pulse.get("proc_time_ms", 0.0)
        self.edge_cutter_active = pulse.get("edge_cutter_active", False)

        # Update Epistemic Gravity Field
        gravity_stats = pulse.get("gravity_stats", {})
        self.gravity_pressure = self.gravity_field.update_from_pulse(gravity_stats)
        self.nav_vector = pulse.get("navigation_vector", None)

        # Handle Humean prediction
        if mode in ["HABIT", "GUARD-HABIT"]:
            pred = pulse.get("predictive_intent", {})
            if pred and "target" in pred:
                quad = pred["target"]
                offsets = {
                    "NW": (-60, -60),
                    "NE": (60, -60),
                    "SW": (-60, 60),
                    "SE": (60, 60),
                }
                off = offsets.get(quad, (0, 0))
                self.predictive_offset = QPoint(off[0], off[1])
            else:
                self.predictive_offset = QPoint(0, 0)
        else:
            self.predictive_offset = QPoint(0, 0)

        # Handle Spinozan jump
        if mode == "INTUITION-JUMP":
            jump_vec = pulse.get("jump_vector", [0, 0])
            if jump_vec and abs(jump_vec[0]) > 0.01:
                screen = QApplication.primaryScreen().geometry()
                center = screen.center()
                # Map normalized vector to screen space (200px range)
                target_x = center.x() + jump_vec[0] * 200 - 60
                target_y = center.y() + jump_vec[1] * 200 - 60
                self.target_pos = QPoint(int(target_x), int(target_y))
                self.jump_active = True
            self.pulse_phase = 0  # Reset pulse for shockwave
        else:
            self.jump_active = False
            # Navigation Vector Handling (Stability First)
            if self.nav_vector:
                # Clamp nav_vector magnitude to avoid wild swings
                vx, vy = self.nav_vector[0], self.nav_vector[1]
                mag = math.sqrt(vx * vx + vy * vy)
                max_speed = 3.0  # Cap the push from the field
                if mag > max_speed:
                    scale = max_speed / mag
                    vx *= scale
                    vy *= scale

                # Apply vector to current position to find target
                # Logic: target = current + vec * 40 (pixels lookahead)
                target_offset = QPoint(int(vx * 40), int(vy * 40))
                raw_target = self.current_pos + target_offset
            else:
                # Classic behavior: follow cursor with prediction
                # Anchor: Top-Left (pos) is cursor - (60,60) to center orb on cursor
                raw_target = self.last_cursor + self.predictive_offset - QPoint(60, 60)

            # Screen Clamping with Margin
            screen = QApplication.primaryScreen().geometry()
            margin = 20
            # Orb size is 120x120 approx
            min_x = screen.left() + margin
            max_x = screen.right() - 120 - margin
            min_y = screen.top() + margin
            max_y = screen.bottom() - 120 - margin

            clamped_x = max(min_x, min(raw_target.x(), max_x))
            clamped_y = max(min_y, min(raw_target.y(), max_y))

            self.target_pos = QPoint(int(clamped_x), int(clamped_y))

        self.hud.setText(f"{mode}\n{self.glow_intensity:.2f}")
        self.update()

    def update_animation(self):
        # Color lerp
        target_color = self.colors.get(self.cognitive_mode, self.colors["GUARD"])
        r = (
            self.current_color.red()
            + (target_color.red() - self.current_color.red()) * 0.1
        )
        g = (
            self.current_color.green()
            + (target_color.green() - self.current_color.green()) * 0.1
        )
        b = (
            self.current_color.blue()
            + (target_color.blue() - self.current_color.blue()) * 0.1
        )
        self.current_color = QColor(int(r), int(g), int(b))

        # Shadow/glow
        self.shadow.setColor(self.current_color)
        base_blur = 20
        blur = base_blur + (60 * self.glow_intensity)
        self.shadow.setBlurRadius(int(blur))

        # Position handling
        if self.jump_active:
            # Spinozan snap (instant)
            self.current_pos = self.target_pos
        else:
            # Smoother lerp for stability
            if self.cognitive_mode == "HABIT":
                speed = 0.12  # Slightly reduced for stability
            else:
                speed = 0.06  # Very smooth following

            # Sine-based "breathing" noise instead of random jitter
            self.sine_phase += 0.1
            noise_amp = 0
            if self.gravity_pressure > 0.001:
                # Pressure controls amplitude of the sine wave
                noise_amp = self.gravity_pressure * 5.0  # pixels

            sine_x = math.sin(self.sine_phase) * noise_amp
            sine_y = math.cos(self.sine_phase * 0.7) * noise_amp

            new_x = (
                self.current_pos.x()
                + (self.target_pos.x() - self.current_pos.x()) * speed
                + sine_x
            )
            new_y = (
                self.current_pos.y()
                + (self.target_pos.y() - self.current_pos.y()) * speed
                + sine_y
            )

            self.current_pos = QPoint(int(new_x), int(new_y))

        self.move(self.current_pos)

        # Pulse phase for intuition shockwave
        if self.cognitive_mode == "INTUITION-JUMP":
            self.pulse_phase = (self.pulse_phase + 2) % 30
        elif self.edge_cutter_active:
            # Purge shockwave runs longer and independent of jump
            self.purge_phase = min(self.purge_phase + 3, 120)
        else:
            self.purge_phase = max(self.purge_phase - 4, 0)

        # Track latency samples for sparkline
        self.latency_samples.append(float(self.proc_time_ms))

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Purge shockwave effect when edge-cutter is active
        if self.purge_phase > 0:
            alpha = max(0, 180 - self.purge_phase)
            radius = 60 + self.purge_phase * 1.5
            shock_color = QColor(238, 130, 238, alpha)
            painter.setBrush(QBrush(QColor(238, 130, 238, max(10, alpha // 3))))
            painter.setPen(QPen(shock_color, 3))
            painter.drawEllipse(
                int(60 - radius / 2), int(60 - radius / 2), int(radius), int(radius)
            )

        # Shockwave effect for Intuition-Jump
        if self.cognitive_mode == "INTUITION-JUMP" and self.pulse_phase > 0:
            alpha = int(255 * (1 - self.pulse_phase / 30))
            pulse_color = QColor(
                self.current_color.red(),
                self.current_color.green(),
                self.current_color.blue(),
                alpha,
            )
            painter.setBrush(QBrush(pulse_color))
            painter.setPen(Qt.PenStyle.NoPen)
            radius = 60 + self.pulse_phase * 3
            painter.drawEllipse(
                int(60 - radius / 2), int(60 - radius / 2), radius, radius
            )

        # Main orb with gradient
        gradient = QRadialGradient(60, 60, 50)
        gradient.setColorAt(0, self.current_color.lighter(150))
        gradient.setColorAt(0.7, self.current_color)
        gradient.setColorAt(1, self.current_color.darker(120))

        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(10, 10, 100, 100)

        # Inner core
        painter.setBrush(QBrush(QColor(255, 255, 255, 100)))
        painter.drawEllipse(30, 30, 60, 60)

        # Density ring (maps 0-1000 to arc) and hysteresis band (650-800)
        density_ratio = min(max(self.field_density / 1000.0, 0.0), 1.0)
        painter.setPen(QPen(QColor(0, 200, 200), 4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(6, 6, 108, 108, 90 * 16, -int(density_ratio * 360 * 16))

        trigger, release = 800, 650
        band_start = release / 1000.0 * 360.0
        band_span = (trigger - release) / 1000.0 * 360.0
        painter.setPen(QPen(QColor(120, 220, 120, 180), 3))
        painter.drawArc(
            10, 10, 100, 100, int((90 - band_start) * 16), -int(band_span * 16)
        )

        # Latency sparkline (bottom area)
        if self.latency_samples:
            samples = list(self.latency_samples)
            max_latency = max(max(samples), 1.0)
            w = 80
            h = 30
            x0 = 20
            y0 = 90
            pts = []
            for i, val in enumerate(samples):
                x = x0 + (i / max(1, len(samples) - 1)) * w
                y = y0 + h - min(h, (val / max_latency) * h)
                pts.append(QPointF(x, y))
            painter.setPen(QPen(QColor(255, 90, 90), 2))
            painter.drawPolyline(pts)

        # Mode indicator ring
        if self.cognitive_mode == "HABIT":
            painter.setPen(QPen(self.colors["HABIT"], 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(5, 5, 110, 110)

        # Gravity Entropy Field visualization (Subtle background distortion)
        if self.gravity_pressure > 0.01:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 0, 0, int(self.gravity_pressure * 30))))
            painter.drawEllipse(50, 50, 20, 20)  # Red dot in center if high entropy

    def enterEvent(self, event):
        self.hud.show()

    def leaveEvent(self, event):
        self.hud.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPos() - self.drag_pos)
            self.current_pos = self.pos()
            self.target_pos = self.pos()
            event.accept()

    def closeEvent(self, event):
        self.worker.running = False
        self.worker_thread.quit()
        self.worker_thread.wait()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    orb = FloatingOrb()
    orb.show()

    print("SF-ORB Interface Active (Gravity Enabled)")
    print("Visual Modes:")
    print("  Teal (Guard)     = Deductive validation, rigid following")
    print("  Amber (Habit)    = Inductive prediction, leads cursor")
    print("  Violet (Jump)    = Spinozan necessity, instant snap + shockwave")
    print("  Red Core         = High Epistemic Entropy (Instability)")
    print("\nDrag to move | Hover for HUD | Watch it learn...")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
