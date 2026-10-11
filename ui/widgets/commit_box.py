"""Elevated floating commit card widget with lively animated loading states."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Theme


class CommitDescriptionEdit(QPlainTextEdit):
    """Text edit capturing Ctrl+Enter / Cmd+Enter to commit."""
    submit_triggered = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier):
                self.submit_triggered.emit()
                return
        super().keyPressEvent(event)


class CommitBox(QFrame):
    """
    Elevated card panel featuring commit title, multi-line description,
    lively animated progress bars, spinner frames, and a prominent commit action button.
    """
    commit_requested = Signal(str, bool)  # (message, is_amend)
    amend_toggled = Signal(bool)

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_branch: str = "main"
        self._is_loading: bool = False
        self._spinner_idx: int = 0

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            CommitBox {{
                background-color: {Theme.BG_CARD};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        # 1. Top Animated Indeterminate Progress Bar (Hidden when idle)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)  # Animated indeterminate bouncing glow
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: transparent;
                border-radius: 1px;
                height: 3px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563eb, stop:0.5 #60a5fa, stop:1 #2563eb);
                border-radius: 1px;
            }}
        """)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 2. Summary Input Line
        self.input_summary = QLineEdit(self)
        self.input_summary.setPlaceholderText("Type Commit Message")
        self.input_summary.setStyleSheet(f"""
            QLineEdit {{
                font-weight: 500;
                font-size: 12px;
                padding: 6px 10px;
                background-color: {Theme.BG_INPUT};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                color: {Theme.TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {Theme.BORDER_FOCUS};
            }}
            QLineEdit:disabled {{
                background-color: #0c0d10;
                color: {Theme.TEXT_MUTED};
            }}
        """)
        self.input_summary.returnPressed.connect(self._on_summary_return)
        layout.addWidget(self.input_summary)

        # 3. Extended Description
        self.input_desc = CommitDescriptionEdit(self)
        self.input_desc.setPlaceholderText("Commit Description")
        self.input_desc.setFixedHeight(54)
        self.input_desc.setStyleSheet(f"""
            QPlainTextEdit {{
                font-size: 11px;
                padding: 6px 10px;
                background-color: {Theme.BG_INPUT};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                color: {Theme.TEXT_PRIMARY};
            }}
            QPlainTextEdit:focus {{
                border-color: {Theme.BORDER_FOCUS};
            }}
            QPlainTextEdit:disabled {{
                background-color: #0c0d10;
                color: {Theme.TEXT_MUTED};
            }}
        """)
        self.input_desc.submit_triggered.connect(self._on_submit)
        layout.addWidget(self.input_desc)

        # 4. Status Notification Banner (Visible during loading or feedback)
        self.lbl_status = QLabel(self)
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setFixedHeight(18)
        self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #60a5fa;")
        self.lbl_status.setVisible(False)
        layout.addWidget(self.lbl_status)

        # 5. Full-Width Primary Commit Button: [Commit to main (Ctrl+Enter)]
        self.btn_commit = QPushButton(f"Commit to {self.current_branch} (Ctrl+Enter)", self)
        self.btn_commit.setObjectName("primaryButton")
        self.btn_commit.setCursor(Qt.PointingHandCursor)
        self._apply_normal_button_style()
        self.btn_commit.clicked.connect(self._on_submit)
        layout.addWidget(self.btn_commit)

        # Animation Timer for lively spinner ticks (every 80ms)
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._on_spinner_tick)

    # -------------------------------------------------------------------------
    # Lively Loading API
    # -------------------------------------------------------------------------

    def start_loading(self) -> None:
        """Trigger lively animated loading state when a commit is initiated."""
        self._is_loading = True
        self._spinner_idx = 0

        # Show animated pulsing progress bar
        self.progress_bar.setVisible(True)

        # Disable input fields to prevent modification during commit
        self.input_summary.setEnabled(False)
        self.input_desc.setEnabled(False)
        self.btn_commit.setEnabled(False)

        # Show active status message
        self.lbl_status.setText(f"⚡ Creating commit to '{self.current_branch}'...")
        self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #60a5fa;")
        self.lbl_status.setVisible(True)

        # Button loading style with glowing border
        self.btn_commit.setStyleSheet(f"""
            QPushButton#primaryButton {{
                background-color: #1e3a8a;
                color: #93c5fd;
                border: 1px solid #3b82f6;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 8px 14px;
            }}
        """)

        # Start lively spinner immediately
        self._on_spinner_tick()
        self._timer.start()

    def stop_loading_success(self, short_hash: str = "") -> None:
        """Display energetic success feedback and transition back smoothly."""
        self._is_loading = False
        self._timer.stop()
        self.progress_bar.setVisible(False)

        hash_display = f" {short_hash}" if short_hash else ""

        # Status badge success
        self.lbl_status.setText(f"✓ Successfully committed{hash_display} to '{self.current_branch}'!")
        self.lbl_status.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {Theme.COLOR_ADDED};")
        self.lbl_status.setVisible(True)

        # Button success flash
        self.btn_commit.setText(f"✓ Committed{hash_display}!")
        self.btn_commit.setStyleSheet(f"""
            QPushButton#primaryButton {{
                background-color: {Theme.COLOR_ADDED};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 8px 14px;
            }}
        """)

        # Clear inputs
        self.input_summary.clear()
        self.input_desc.clear()
        self.input_summary.setEnabled(True)
        self.input_desc.setEnabled(True)

        # Smoothly reset button to normal after 1.5 seconds
        QTimer.singleShot(1500, self._reset_to_idle)

    def stop_loading_error(self, error_message: str = "") -> None:
        """Display error feedback and re-enable inputs."""
        self._is_loading = False
        self._timer.stop()
        self.progress_bar.setVisible(False)

        self.lbl_status.setText(f"✕ {error_message[:45]}" if error_message else "✕ Commit failed")
        self.lbl_status.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {Theme.COLOR_DELETED};")
        self.lbl_status.setVisible(True)

        self.input_summary.setEnabled(True)
        self.input_desc.setEnabled(True)
        self.btn_commit.setEnabled(True)

        self._reset_to_idle()

    def _reset_to_idle(self) -> None:
        self.lbl_status.setVisible(False)
        self._apply_normal_button_style()
        self.btn_commit.setText(f"Commit to {self.current_branch} (Ctrl+Enter)")
        self.btn_commit.setEnabled(True)

    def _on_spinner_tick(self) -> None:
        frame = self.SPINNER_FRAMES[self._spinner_idx % len(self.SPINNER_FRAMES)]
        self._spinner_idx += 1
        self.btn_commit.setText(f"{frame}  Committing to {self.current_branch}...")

    def _apply_normal_button_style(self) -> None:
        self.btn_commit.setStyleSheet(f"""
            QPushButton#primaryButton {{
                background-color: {Theme.ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 8px 14px;
            }}
            QPushButton#primaryButton:hover {{
                background-color: {Theme.ACCENT_HOVER};
            }}
            QPushButton#primaryButton:disabled {{
                background-color: #1e3a5f;
                color: #64748b;
            }}
        """)

    # -------------------------------------------------------------------------
    # Standard Controls
    # -------------------------------------------------------------------------

    def set_branch(self, branch_name: str) -> None:
        self.current_branch = branch_name or "main"
        if not self._is_loading:
            self.btn_commit.setText(f"Commit to {self.current_branch} (Ctrl+Enter)")

    def set_has_staged_changes(self, has_staged: bool) -> None:
        if not self._is_loading:
            self.btn_commit.setEnabled(True)

    def clear(self) -> None:
        self.input_summary.clear()
        self.input_desc.clear()

    def set_amend_data(self, summary: str, body: str) -> None:
        self.input_summary.setText(summary)
        self.input_desc.setPlainText(body)

    def _on_summary_return(self) -> None:
        if self.input_desc.toPlainText().strip():
            self._on_submit()
        else:
            self.input_desc.setFocus()

    def _on_submit(self) -> None:
        if self._is_loading:
            return
        summary = self.input_summary.text().strip()
        if not summary:
            summary = self.input_summary.placeholderText() or "Update"
        desc = self.input_desc.toPlainText().strip()
        full_msg = f"{summary}\n\n{desc}" if desc else summary
        self.commit_requested.emit(full_msg, False)
