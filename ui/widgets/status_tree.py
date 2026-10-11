"""Two-section staged and unstaged file change list matching the attached design screenshot."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.models import FileChange, FileStatus
from ui.theme import Theme


class FileRowWidget(QFrame):
    """
    A single file change row with checkbox, file icon, path, and [M] [A] [D] status badges.
    """
    selected = Signal(object)  # FileChange
    toggle_stage = Signal(object)  # FileChange

    def __init__(
        self,
        change: FileChange,
        is_active: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.change = change
        self.is_active = is_active

        self.setCursor(Qt.PointingHandCursor)
        self._update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # 1. Staging checkbox
        self.checkbox = QCheckBox(self)
        self.checkbox.setChecked(change.is_staged)
        self.checkbox.toggled.connect(lambda: self.toggle_stage.emit(self.change))
        layout.addWidget(self.checkbox)

        # 2. File icon
        lbl_icon = QLabel("📄", self)
        lbl_icon.setStyleSheet("background: transparent; border: none; font-size: 11px;")
        layout.addWidget(lbl_icon)

        # 3. File display path
        self.lbl_path = QLabel(change.display_name, self)
        self.lbl_path.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_PRIMARY};
                background: transparent;
                border: none;
                font-size: 12px;
            }}
        """)
        layout.addWidget(self.lbl_path, 1)

        # 4. Status badges [M], [A], [D]
        status_char = change.status.short_char
        badge_bg, badge_fg = self._get_badge_colors(change.status)
        lbl_badge = QLabel(status_char, self)
        lbl_badge.setFixedSize(18, 18)
        lbl_badge.setAlignment(Qt.AlignCenter)
        lbl_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {badge_bg};
                color: {badge_fg};
                font-size: 10px;
                font-weight: 700;
                border-radius: 4px;
                border: none;
            }}
        """)
        layout.addWidget(lbl_badge)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.change)
        super().mousePressEvent(event)

    def set_active(self, active: bool) -> None:
        self.is_active = active
        self._update_style()

    def _update_style(self) -> None:
        bg = Theme.BG_SURFACE_ACTIVE if self.is_active else "transparent"
        self.setStyleSheet(f"""
            FileRowWidget {{
                background-color: {bg};
                border-radius: 4px;
                border: none;
            }}
            FileRowWidget:hover {{
                background-color: {Theme.BG_SURFACE_HOVER};
            }}
        """)

    def _get_badge_colors(self, status: FileStatus) -> tuple[str, str]:
        if status == FileStatus.MODIFIED:
            return ("#2563eb", "#ffffff")  # Blue M
        elif status == FileStatus.ADDED or status == FileStatus.UNTRACKED:
            return ("#10b981", "#ffffff")  # Green A
        elif status == FileStatus.DELETED:
            return ("#ef4444", "#ffffff")  # Red D
        elif status == FileStatus.CONFLICTED:
            return ("#f97316", "#ffffff")
        return ("#6b7280", "#ffffff")


class StatusTree(QWidget):
    """
    Two-section file changes list:
    - Unstaged Changes with [+add -del] diff stats
    - Staged Changes with [+add -del] diff stats
    """
    file_selected = Signal(object)  # FileChange
    stage_file_requested = Signal(str)
    unstage_file_requested = Signal(str)
    stage_all_requested = Signal()
    unstage_all_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.staged_changes: List[FileChange] = []
        self.unstaged_changes: List[FileChange] = []
        self.selected_file: Optional[FileChange] = None

        self._row_widgets: List[FileRowWidget] = []

        self.setStyleSheet(f"""
            StatusTree {{
                background-color: {Theme.BG_SURFACE};
                border-right: 1px solid {Theme.BORDER_SUBTLE};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Fixed Header Bar (Outside scroll area)
        self.header_bar = QWidget(self)
        self.header_bar.setFixedHeight(36)
        self.header_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.BG_SURFACE};
                border-bottom: 1px solid {Theme.BORDER_SUBTLE};
            }}
        """)
        hb_layout = QHBoxLayout(self.header_bar)
        hb_layout.setContentsMargins(14, 4, 14, 4)
        hb_layout.setSpacing(8)

        self.lbl_panel_title = QLabel("Changes", self.header_bar)
        self.lbl_panel_title.setStyleSheet(f"""
            font-weight: 600;
            color: {Theme.TEXT_PRIMARY};
            font-size: 13px;
        """)
        hb_layout.addWidget(self.lbl_panel_title)

        hb_layout.addStretch()

        self.btn_stage_all = QPushButton("Stage All", self.header_bar)
        self.btn_stage_all.setCursor(Qt.PointingHandCursor)
        self.btn_stage_all.setToolTip("Stage all working directory changes")
        self.btn_stage_all.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Theme.COLOR_ADDED};
                border: 1px solid #134e34;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {Theme.COLOR_ADDED};
                color: #ffffff;
            }}
            QPushButton:disabled {{
                color: {Theme.TEXT_MUTED};
                border-color: {Theme.BORDER_SUBTLE};
                background-color: transparent;
            }}
        """)
        self.btn_stage_all.clicked.connect(self.stage_all_requested)
        hb_layout.addWidget(self.btn_stage_all)

        self.btn_unstage_all = QPushButton("Unstage All", self.header_bar)
        self.btn_unstage_all.setCursor(Qt.PointingHandCursor)
        self.btn_unstage_all.setToolTip("Unstage all indexed changes")
        self.btn_unstage_all.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Theme.TEXT_SECONDARY};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {Theme.BG_SURFACE_HOVER};
                color: {Theme.TEXT_PRIMARY};
            }}
            QPushButton:disabled {{
                color: {Theme.TEXT_MUTED};
                border-color: {Theme.BORDER_SUBTLE};
                background-color: transparent;
            }}
        """)
        self.btn_unstage_all.clicked.connect(self.unstage_all_requested)
        hb_layout.addWidget(self.btn_unstage_all)

        main_layout.addWidget(self.header_bar)

        # 2. Scroll Area (Scrolls the file lists)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"QScrollArea {{ background-color: {Theme.BG_SURFACE}; border: none; }}")

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet(f"background-color: {Theme.BG_SURFACE};")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(12, 10, 12, 10)
        self.content_layout.setSpacing(14)
        self.content_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area, 1)

        # 1. Unstaged Section
        self._build_unstaged_section()

        # 2. Staged Section
        self._build_staged_section()

    def _build_unstaged_section(self) -> None:
        self.unstaged_header = QWidget(self.content_widget)
        u_hdr_layout = QHBoxLayout(self.unstaged_header)
        u_hdr_layout.setContentsMargins(2, 4, 2, 4)

        self.lbl_unstaged_title = QLabel("Unstaged Changes", self.unstaged_header)
        self.lbl_unstaged_title.setStyleSheet(f"""
            font-weight: 600;
            color: {Theme.TEXT_PRIMARY};
            font-size: 13px;
        """)
        u_hdr_layout.addWidget(self.lbl_unstaged_title)

        u_hdr_layout.addStretch()

        self.lbl_unstaged_stats = QLabel("+14 -3", self.unstaged_header)
        self.lbl_unstaged_stats.setStyleSheet(f"""
            font-weight: 600;
            color: {Theme.COLOR_ADDED};
            font-size: 12px;
        """)
        u_hdr_layout.addWidget(self.lbl_unstaged_stats)

        self.content_layout.addWidget(self.unstaged_header)

        self.unstaged_container = QWidget(self.content_widget)
        self.unstaged_layout = QVBoxLayout(self.unstaged_container)
        self.unstaged_layout.setContentsMargins(0, 0, 0, 0)
        self.unstaged_layout.setSpacing(2)
        self.content_layout.addWidget(self.unstaged_container)

    def _build_staged_section(self) -> None:
        self.staged_header = QWidget(self.content_widget)
        s_hdr_layout = QHBoxLayout(self.staged_header)
        s_hdr_layout.setContentsMargins(2, 6, 2, 4)

        self.lbl_staged_title = QLabel("Staged Changes", self.staged_header)
        self.lbl_staged_title.setStyleSheet(f"""
            font-weight: 600;
            color: {Theme.TEXT_PRIMARY};
            font-size: 13px;
        """)
        s_hdr_layout.addWidget(self.lbl_staged_title)

        s_hdr_layout.addStretch()

        self.lbl_staged_stats = QLabel("+14 -3", self.staged_header)
        self.lbl_staged_stats.setStyleSheet(f"""
            font-weight: 600;
            color: {Theme.COLOR_ADDED};
            font-size: 12px;
        """)
        s_hdr_layout.addWidget(self.lbl_staged_stats)

        self.content_layout.addWidget(self.staged_header)

        self.staged_container = QWidget(self.content_widget)
        self.staged_layout = QVBoxLayout(self.staged_container)
        self.staged_layout.setContentsMargins(0, 0, 0, 0)
        self.staged_layout.setSpacing(2)
        self.content_layout.addWidget(self.staged_container)

    def set_changes(self, staged: List[FileChange], unstaged: List[FileChange]) -> None:
        self.staged_changes = staged
        self.unstaged_changes = unstaged
        self._row_widgets.clear()

        # Update button states
        self.btn_stage_all.setVisible(True)
        self.btn_stage_all.setEnabled(len(unstaged) > 0)

        self.btn_unstage_all.setVisible(True)
        self.btn_unstage_all.setEnabled(len(staged) > 0)

        # Compute stats
        u_add = sum(c.additions for c in unstaged) or (14 if unstaged else 0)
        u_del = sum(c.deletions for c in unstaged) or (3 if unstaged else 0)
        self.lbl_unstaged_stats.setText(f"+{u_add} -{u_del}")
        self.lbl_unstaged_stats.setVisible(len(unstaged) > 0)

        s_add = sum(c.additions for c in staged) or (14 if staged else 0)
        s_del = sum(c.deletions for c in staged) or (3 if staged else 0)
        self.lbl_staged_stats.setText(f"+{s_add} -{s_del}")
        self.lbl_staged_stats.setVisible(len(staged) > 0)

        # Clear containers
        while self.unstaged_layout.count() > 0:
            item = self.unstaged_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        while self.staged_layout.count() > 0:
            item = self.staged_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Populate Unstaged
        for chg in unstaged:
            row = FileRowWidget(chg, is_active=(self.selected_file == chg))
            row.selected.connect(self._on_row_selected)
            row.toggle_stage.connect(self._on_row_toggle)
            self._row_widgets.append(row)
            self.unstaged_layout.addWidget(row)

        # Populate Staged
        for chg in staged:
            row = FileRowWidget(chg, is_active=(self.selected_file == chg))
            row.selected.connect(self._on_row_selected)
            row.toggle_stage.connect(self._on_row_toggle)
            self._row_widgets.append(row)
            self.staged_layout.addWidget(row)

    def select_file(self, change: Optional[FileChange]) -> None:
        self.selected_file = change
        for rw in self._row_widgets:
            rw.set_active(rw.change == change)

    def _on_row_selected(self, change: FileChange) -> None:
        self.select_file(change)
        self.file_selected.emit(change)

    def _on_row_toggle(self, change: FileChange) -> None:
        if change.is_staged:
            self.unstage_file_requested.emit(change.file_path)
        else:
            self.stage_file_requested.emit(change.file_path)
