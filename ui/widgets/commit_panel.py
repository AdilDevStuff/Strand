"""Commit message input panel with validation, amend support, and shortcuts."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Theme


class CommitMessageEdit(QPlainTextEdit):
    """Multiline editor that catches Ctrl+Enter or Cmd+Enter to commit."""
    submit_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Commit summary (required)\n\nDescription (optional)...")
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Theme.BG_INPUT};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 8px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
                selection-background-color: {Theme.ACCENT};
            }}
            QPlainTextEdit:focus {{
                border: 1px solid {Theme.BORDER_FOCUS};
            }}
        """)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier):
                event.accept()
                self.submit_requested.emit()
                return
        super().keyPressEvent(event)


class CommitPanel(QFrame):
    """
    GitFiend-inspired commit box with message editor, amend toggle,
    staged changes counter, and commit dispatch.
    """
    commit_requested = Signal(str, bool)  # (message, amend)
    amend_toggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.staged_count: int = 0
        self.current_branch: str = "master"

        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(f"""
            CommitPanel {{
                background-color: {Theme.BG_SURFACE};
                border-top: 1px solid {Theme.BORDER_DEFAULT};
                padding: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # Header Row
        hdr_widget = QWidget(self)
        hdr_layout = QHBoxLayout(hdr_widget)
        hdr_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_title = QLabel("Commit Changes", hdr_widget)
        self.lbl_title.setStyleSheet(f"font-weight: 600; color: {Theme.TEXT_PRIMARY}; font-size: 13px;")
        hdr_layout.addWidget(self.lbl_title)

        self.lbl_staged_badge = QLabel("0 staged", hdr_widget)
        self.lbl_staged_badge.setStyleSheet(f"""
            QLabel {{
                color: {Theme.COLOR_ADDED};
                background-color: {Theme.COLOR_ADDED_BG};
                font-size: 11px;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 4px;
            }}
        """)
        hdr_layout.addWidget(self.lbl_staged_badge)
        hdr_layout.addStretch()

        layout.addWidget(hdr_widget)

        # Editor
        self.txt_message = CommitMessageEdit(self)
        self.txt_message.setFixedHeight(85)
        self.txt_message.textChanged.connect(self._validate_input)
        self.txt_message.submit_requested.connect(self._on_commit_clicked)
        layout.addWidget(self.txt_message)

        # Footer Row (Amend Checkbox + Commit Button)
        footer_widget = QWidget(self)
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        self.chk_amend = QCheckBox("Amend", footer_widget)
        self.chk_amend.setStyleSheet(f"""
            QCheckBox {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 12px;
            }}
            QCheckBox:hover {{
                color: {Theme.TEXT_PRIMARY};
            }}
        """)
        self.chk_amend.toggled.connect(self._on_amend_toggled)
        footer_layout.addWidget(self.chk_amend)

        footer_layout.addStretch()

        self.btn_commit = QPushButton("Commit", footer_widget)
        self.btn_commit.setCursor(Qt.PointingHandCursor)
        self.btn_commit.setEnabled(False)
        self.btn_commit.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.ACCENT};
                color: #ffffff;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 14px;
                border-radius: 5px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {Theme.ACCENT_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {Theme.BG_SURFACE_ACTIVE};
                color: {Theme.TEXT_MUTED};
            }}
        """)
        self.btn_commit.clicked.connect(self._on_commit_clicked)
        footer_layout.addWidget(self.btn_commit)

        layout.addWidget(footer_widget)

    # -------------------------------------------------------------------------
    # Public State Setters
    # -------------------------------------------------------------------------

    def set_staged_count(self, count: int) -> None:
        """Update staged count badge and re-validate."""
        self.staged_count = count
        self.lbl_staged_badge.setText(f"{count} staged")
        if count > 0:
            self.lbl_staged_badge.setStyleSheet(f"""
                QLabel {{
                    color: {Theme.COLOR_ADDED};
                    background-color: {Theme.COLOR_ADDED_BG};
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px 6px;
                    border-radius: 4px;
                }}
            """)
        else:
            self.lbl_staged_badge.setStyleSheet(f"""
                QLabel {{
                    color: {Theme.TEXT_MUTED};
                    background-color: {Theme.BG_PRIMARY};
                    font-size: 11px;
                    font-weight: normal;
                    padding: 2px 6px;
                    border-radius: 4px;
                }}
            """)
        self._validate_input()

    def set_current_branch(self, branch: str) -> None:
        """Update commit button label with branch name."""
        self.current_branch = branch or "master"
        self._update_button_label()

    def set_message(self, text: str) -> None:
        """Set commit message programmatically."""
        self.txt_message.setPlainText(text)
        self._validate_input()

    def get_message(self) -> str:
        """Return current commit message text."""
        return self.txt_message.toPlainText().strip()

    def clear_message(self) -> None:
        """Clear commit message text."""
        self.txt_message.clear()
        self._validate_input()

    # -------------------------------------------------------------------------
    # Validation & Actions
    # -------------------------------------------------------------------------

    def _update_button_label(self) -> None:
        amend_prefix = "Amend & " if self.chk_amend.isChecked() else ""
        branch_str = f" to {self.current_branch}" if self.current_branch else ""
        self.btn_commit.setText(f"{amend_prefix}Commit{branch_str}")

    def _validate_input(self) -> None:
        has_message = bool(self.txt_message.toPlainText().strip())
        is_amend = self.chk_amend.isChecked()
        can_commit = has_message and (self.staged_count > 0 or is_amend)
        self.btn_commit.setEnabled(can_commit)

    def _on_amend_toggled(self, checked: bool) -> None:
        self._update_button_label()
        self._validate_input()
        self.amend_toggled.emit(checked)

    def _on_commit_clicked(self) -> None:
        msg = self.get_message()
        if not msg:
            return
        is_amend = self.chk_amend.isChecked()
        if self.staged_count > 0 or is_amend:
            self.commit_requested.emit(msg, is_amend)
            self.clear_message()
            if is_amend:
                self.chk_amend.setChecked(False)
