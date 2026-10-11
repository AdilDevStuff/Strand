"""Interactive Stash management dialog and panel."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Theme


class StashItemWidget(QFrame):
    """A single stash row with Pop, Apply, and Drop buttons."""
    pop_requested = Signal(int)
    apply_requested = Signal(int)
    drop_requested = Signal(int)

    def __init__(self, stash: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.stash = stash
        self.index = stash.get("index", 0)

        self.setStyleSheet(f"""
            StashItemWidget {{
                background-color: {Theme.BG_PRIMARY};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 6px;
            }}
            StashItemWidget:hover {{
                border-color: {Theme.BORDER_FOCUS};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Stash index badge
        lbl_idx = QLabel(f"stash@{{{self.index}}}", self)
        lbl_idx.setStyleSheet(f"""
            QLabel {{
                color: {Theme.ACCENT};
                background-color: {Theme.BG_SURFACE_ACTIVE};
                font-family: Consolas, Monospace;
                font-weight: bold;
                font-size: 11px;
                padding: 2px 6px;
                border-radius: 3px;
            }}
        """)
        layout.addWidget(lbl_idx)

        # Message and date
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        lbl_msg = QLabel(stash.get("message", "WIP"), self)
        lbl_msg.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; font-weight: 500; font-size: 12px;")
        info_col.addWidget(lbl_msg)

        lbl_date = QLabel(stash.get("date", ""), self)
        lbl_date.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 10px;")
        info_col.addWidget(lbl_date)

        layout.addLayout(info_col, 1)

        # Action Buttons
        btn_pop = QPushButton("Pop", self)
        btn_pop.setCursor(Qt.PointingHandCursor)
        btn_pop.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BG_SURFACE_ACTIVE};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {Theme.ACCENT};
                color: #ffffff;
            }}
        """)
        btn_pop.clicked.connect(lambda: self.pop_requested.emit(self.index))
        layout.addWidget(btn_pop)

        btn_apply = QPushButton("Apply", self)
        btn_apply.setCursor(Qt.PointingHandCursor)
        btn_apply.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BG_SURFACE_ACTIVE};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                border-color: {Theme.ACCENT};
                color: #ffffff;
            }}
        """)
        btn_apply.clicked.connect(lambda: self.apply_requested.emit(self.index))
        layout.addWidget(btn_apply)

        btn_drop = QPushButton("Drop", self)
        btn_drop.setCursor(Qt.PointingHandCursor)
        btn_drop.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Theme.COLOR_DELETED};
                border: 1px solid {Theme.COLOR_DELETED};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {Theme.COLOR_DELETED};
                color: #ffffff;
            }}
        """)
        btn_drop.clicked.connect(lambda: self.drop_requested.emit(self.index))
        layout.addWidget(btn_drop)


class StashDialog(QDialog):
    """Modal or modeless dialog managing repository stashes."""
    stash_save_requested = Signal(str, bool, bool)  # (msg, include_untracked, keep_index)
    stash_pop_requested = Signal(int)
    stash_apply_requested = Signal(int)
    stash_drop_requested = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Git Stashes")
        self.resize(560, 420)
        self.setStyleSheet(Theme.main_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Create Stash Box
        create_frame = QFrame(self)
        create_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        c_layout = QVBoxLayout(create_frame)
        c_layout.setSpacing(8)

        lbl_hdr = QLabel("Stash Current Changes", create_frame)
        lbl_hdr.setStyleSheet(f"font-weight: 600; color: {Theme.TEXT_PRIMARY}; font-size: 12px;")
        c_layout.addWidget(lbl_hdr)

        self.input_msg = QLineEdit(create_frame)
        self.input_msg.setPlaceholderText("Optional stash message...")
        self.input_msg.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Theme.BG_INPUT};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
            }}
        """)
        c_layout.addWidget(self.input_msg)

        opts_row = QHBoxLayout()
        self.chk_untracked = QCheckBox("Include untracked files (-u)", create_frame)
        self.chk_untracked.setStyleSheet(f"color: {Theme.TEXT_SECONDARY}; font-size: 11px;")
        opts_row.addWidget(self.chk_untracked)

        self.chk_keep_index = QCheckBox("Keep index staged", create_frame)
        self.chk_keep_index.setStyleSheet(f"color: {Theme.TEXT_SECONDARY}; font-size: 11px;")
        opts_row.addWidget(self.chk_keep_index)

        opts_row.addStretch()

        self.btn_stash = QPushButton("Stash Changes", create_frame)
        self.btn_stash.setCursor(Qt.PointingHandCursor)
        self.btn_stash.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 5px 14px;
                font-weight: 600;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Theme.ACCENT_HOVER};
            }}
        """)
        self.btn_stash.clicked.connect(self._on_save_stash)
        opts_row.addWidget(self.btn_stash)

        c_layout.addLayout(opts_row)
        layout.addWidget(create_frame)

        # 2. Existing Stashes List
        self.lbl_stashes_title = QLabel("Saved Stashes (0)", self)
        self.lbl_stashes_title.setStyleSheet(f"font-weight: 600; color: {Theme.TEXT_PRIMARY}; font-size: 12px;")
        layout.addWidget(self.lbl_stashes_title)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(6)
        self.scroll_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.scroll_widget)
        layout.addWidget(self.scroll_area, 1)

    def set_stashes(self, stashes: List[Dict[str, Any]]) -> None:
        """Update stashes list in UI."""
        self.lbl_stashes_title.setText(f"Saved Stashes ({len(stashes)})")

        while self.scroll_layout.count() > 0:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not stashes:
            empty = QLabel("No stashes saved in this repository.", self.scroll_widget)
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 12px; margin-top: 30px;")
            self.scroll_layout.addWidget(empty)
            return

        for stash in stashes:
            row = StashItemWidget(stash, self.scroll_widget)
            row.pop_requested.connect(self.stash_pop_requested)
            row.apply_requested.connect(self.stash_apply_requested)
            row.drop_requested.connect(self.stash_drop_requested)
            self.scroll_layout.addWidget(row)

    def _on_save_stash(self) -> None:
        msg = self.input_msg.text().strip()
        include_u = self.chk_untracked.isChecked()
        keep_idx = self.chk_keep_index.isChecked()
        self.stash_save_requested.emit(msg, include_u, keep_idx)
        self.input_msg.clear()
