"""Full-window modal loading overlay dimming the application with a centered animated card."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Theme


class CircularSpinner(QWidget):
    """Smooth 40 FPS rotating circular spinner with glowing accent arc."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(50, 50)
        self.angle: float = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(25)  # ~40 FPS
        self.timer.timeout.connect(self._rotate)

    def start(self) -> None:
        self.angle = 0.0
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def _rotate(self) -> None:
        self.angle = (self.angle + 8) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(6, 6, 38, 38)

        # Background track ring
        pen_track = QPen(QColor(36, 40, 52), 3.5)
        painter.setPen(pen_track)
        painter.drawArc(rect, 0, 360 * 16)

        # Active spinning arc with rounded caps
        pen_arc = QPen(QColor(59, 130, 246), 3.5)
        pen_arc.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_arc)
        painter.drawArc(rect, -int(self.angle * 16), 110 * 16)


class LoadingOverlay(QWidget):
    """
    Translucent full-window overlay that dims the entire application and displays
    a centered elevated card with animated circular spinner, title, and progress.
    """
    dismiss_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        # Main overlay layout centering the card
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setAlignment(Qt.AlignCenter)

        # Elevated Centered Card
        self.card = QFrame(self)
        self.card.setObjectName("loadingCard")
        self.card.setFixedWidth(320)
        self.card.setStyleSheet(f"""
            QFrame#loadingCard {{
                background-color: {Theme.BG_CARD};
                border: 1px solid #2b303c;
                border-radius: 12px;
            }}
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(14)
        card_layout.setAlignment(Qt.AlignCenter)

        # 1. Circular animated spinner (centered)
        spinner_row = QHBoxLayout()
        spinner_row.setAlignment(Qt.AlignCenter)
        self.spinner = CircularSpinner(self.card)
        spinner_row.addWidget(self.spinner)
        card_layout.addLayout(spinner_row)

        # 2. Main title text
        self.lbl_title = QLabel("Processing...", self.card)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        t_font = QFont()
        t_font.setPointSize(13)
        t_font.setBold(True)
        self.lbl_title.setFont(t_font)
        self.lbl_title.setStyleSheet("color: #f8fafc; background: transparent; border: none;")
        card_layout.addWidget(self.lbl_title)

        # 3. Subtitle / Hint text
        self.lbl_subtext = QLabel("Please wait while Git operation completes", self.card)
        self.lbl_subtext.setAlignment(Qt.AlignCenter)
        self.lbl_subtext.setWordWrap(True)
        self.lbl_subtext.setStyleSheet("color: #94a3b8; font-size: 11px; background: transparent; border: none;")
        card_layout.addWidget(self.lbl_subtext)

        # 4. Indeterminate animated gradient progress bar
        self.progress_bar = QProgressBar(self.card)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {{
                border: none;
                background-color: #20242e;
                border-radius: 1px;
                height: 3px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563eb, stop:0.5 #60a5fa, stop:1 #2563eb);
                border-radius: 1px;
            }}
        """)
        card_layout.addWidget(self.progress_bar)

        # 5. Dismiss button (appears if an operation takes longer than 6 seconds)
        self.btn_dismiss = QPushButton("Dismiss (Cancel Wait)", self.card)
        self.btn_dismiss.setCursor(Qt.PointingHandCursor)
        self.btn_dismiss.setStyleSheet(f"""
            QPushButton {{
                background-color: #1a1d24;
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                font-size: 11px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{
                background-color: #262a34;
                color: #ffffff;
            }}
        """)
        self.btn_dismiss.setVisible(False)
        self.btn_dismiss.clicked.connect(self._on_dismiss_clicked)
        card_layout.addWidget(self.btn_dismiss)

        main_layout.addWidget(self.card)

        # Timer to reveal dismiss button after 6 seconds of waiting
        self._stuck_timer = QTimer(self)
        self._stuck_timer.setSingleShot(True)
        self._stuck_timer.setInterval(6000)
        self._stuck_timer.timeout.connect(self._on_stuck_timeout)

        self.hide()

    def show_loading(self, title: str = "Processing...", subtext: str = "Please wait while Git operation completes") -> None:
        """Show full overlay, dimming app and animating spinner."""
        self.lbl_title.setText(title)
        self.lbl_subtext.setText(subtext)
        self.btn_dismiss.setVisible(False)
        self.spinner.start()
        self._stuck_timer.start()

        if self.parentWidget():
            self.setGeometry(0, 0, self.parentWidget().width(), self.parentWidget().height())
        self.raise_()
        self.show()

    def hide_loading(self) -> None:
        """Hide overlay and stop spinner."""
        self._stuck_timer.stop()
        self.spinner.stop()
        self.hide()

    def _on_stuck_timeout(self) -> None:
        """If operation is taking long, show dismiss button."""
        self.lbl_subtext.setText("This operation is taking longer than usual...")
        self.btn_dismiss.setVisible(True)

    def _on_dismiss_clicked(self) -> None:
        self.hide_loading()
        self.dismiss_requested.emit()

    def paintEvent(self, event) -> None:
        """Draw translucent dimming background covering the full application."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 12, 16, 185))

    def mousePressEvent(self, event) -> None:
        event.accept()  # Block clicks through overlay

    def mouseReleaseEvent(self, event) -> None:
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        event.accept()

    def wheelEvent(self, event) -> None:
        event.accept()
