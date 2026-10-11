"""Historical commit inspector showing metadata, modified files, and diff."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QClipboard, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.models import CommitNode, FileChange, FileStatus, Hunk
from ui.theme import Theme
from ui.widgets.diff_viewer import DiffViewer


class CommitFileItemWidget(QFrame):
    """File row in commit changed files list."""
    clicked = Signal(str)

    def __init__(self, change: FileChange, is_active: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.change = change
        self.is_active = is_active

        self.setCursor(Qt.PointingHandCursor)
        self._update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(8)

        # Status Badge
        lbl_status = QLabel(change.status.short_char, self)
        lbl_status.setFixedSize(18, 18)
        lbl_status.setAlignment(Qt.AlignCenter)
        color = self._get_status_color(change.status)
        lbl_status.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: #ffffff;
                font-size: 10px;
                font-weight: bold;
                border-radius: 3px;
                border: none;
            }}
        """)
        layout.addWidget(lbl_status)

        # File Path
        lbl_path = QLabel(change.display_name, self)
        lbl_path.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; background: transparent; border: none;")
        layout.addWidget(lbl_path, 1)

        # Counts (+/-)
        if change.additions > 0 or change.deletions > 0:
            lbl_counts = QLabel(f"+{change.additions} -{change.deletions}", self)
            lbl_counts.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
            layout.addWidget(lbl_counts)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.change.file_path)
        super().mousePressEvent(event)

    def set_active(self, active: bool) -> None:
        self.is_active = active
        self._update_style()

    def _update_style(self) -> None:
        bg = Theme.BG_SURFACE_ACTIVE if self.is_active else "transparent"
        self.setStyleSheet(f"""
            CommitFileItemWidget {{
                background-color: {bg};
                border-radius: 4px;
                border: none;
            }}
            CommitFileItemWidget:hover {{
                background-color: {Theme.BG_SURFACE_HOVER};
            }}
        """)

    def _get_status_color(self, status: FileStatus) -> str:
        mapping = {
            FileStatus.ADDED: Theme.COLOR_ADDED,
            FileStatus.DELETED: Theme.COLOR_DELETED,
            FileStatus.MODIFIED: Theme.COLOR_MODIFIED,
            FileStatus.UNTRACKED: Theme.COLOR_UNTRACKED,
            FileStatus.RENAMED: Theme.COLOR_RENAMED,
            FileStatus.CONFLICTED: Theme.COLOR_CONFLICT,
        }
        return mapping.get(status, Theme.TEXT_MUTED)


class CommitDetailView(QWidget):
    """
    Historical commit inspector displaying full commit metadata,
    changed files list, and diff viewing for each modified file.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.commit_node: Optional[CommitNode] = None
        self.file_changes: List[FileChange] = []
        self.hunks_by_file: Dict[str, List[Hunk]] = {}
        self.selected_file: Optional[str] = None
        self._file_widgets: List[CommitFileItemWidget] = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header Metadata Card
        self.header_frame = QFrame(self)
        self.header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_SURFACE};
                border-bottom: 1px solid {Theme.BORDER_DEFAULT};
            }}
        """)
        h_layout = QVBoxLayout(self.header_frame)
        h_layout.setContentsMargins(16, 12, 16, 12)
        h_layout.setSpacing(8)

        # Top line: Short hash + Copy button + Author + Date
        top_row = QWidget(self.header_frame)
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        self.lbl_hash = QLabel("Commit: -", top_row)
        font_mono = QFont("Consolas" if "win" in Theme.BG_PRIMARY else "Monospace", 10)
        font_mono.setStyleHint(QFont.Monospace)
        self.lbl_hash.setFont(font_mono)
        self.lbl_hash.setStyleSheet(f"color: {Theme.ACCENT}; font-weight: bold; border: none;")
        top_layout.addWidget(self.lbl_hash)

        self.btn_copy_hash = QPushButton("Copy", top_row)
        self.btn_copy_hash.setCursor(Qt.PointingHandCursor)
        self.btn_copy_hash.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BG_SURFACE_ACTIVE};
                color: {Theme.TEXT_SECONDARY};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 3px;
                padding: 1px 6px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                color: {Theme.TEXT_PRIMARY};
            }}
        """)
        self.btn_copy_hash.clicked.connect(self._copy_hash)
        top_layout.addWidget(self.btn_copy_hash)

        top_layout.addStretch()

        self.lbl_author_date = QLabel("", top_row)
        self.lbl_author_date.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 12px; border: none;")
        top_layout.addWidget(self.lbl_author_date)

        h_layout.addWidget(top_row)

        # Commit message
        self.lbl_message = QLabel("No commit selected", self.header_frame)
        self.lbl_message.setWordWrap(True)
        self.lbl_message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_message.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; font-size: 13px; font-weight: 500; border: none;")
        h_layout.addWidget(self.lbl_message)

        main_layout.addWidget(self.header_frame)

        # 2. Splitter for Files List and Diff View
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Theme.BORDER_SUBTLE};
            }}
        """)

        # Left side of splitter: changed files list
        files_container = QWidget(self.splitter)
        files_layout = QVBoxLayout(files_container)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(0)

        # Files list header
        files_header = QWidget(files_container)
        files_header.setStyleSheet(f"background-color: {Theme.BG_PRIMARY}; border-bottom: 1px solid {Theme.BORDER_SUBTLE};")
        fh_layout = QHBoxLayout(files_header)
        fh_layout.setContentsMargins(12, 6, 12, 6)

        self.lbl_files_count = QLabel("Changed Files (0)", files_header)
        self.lbl_files_count.setStyleSheet(f"color: {Theme.TEXT_SECONDARY}; font-size: 11px; font-weight: 600; border: none;")
        fh_layout.addWidget(self.lbl_files_count)
        files_layout.addWidget(files_header)

        # Files scroll area
        self.files_scroll = QScrollArea(files_container)
        self.files_scroll.setWidgetResizable(True)
        self.files_scroll.setStyleSheet(f"background-color: {Theme.BG_PRIMARY}; border: none;")

        self.files_list_widget = QWidget()
        self.files_list_widget.setStyleSheet(f"background-color: {Theme.BG_PRIMARY};")
        self.files_list_layout = QVBoxLayout(self.files_list_widget)
        self.files_list_layout.setContentsMargins(8, 8, 8, 8)
        self.files_list_layout.setSpacing(2)
        self.files_list_layout.setAlignment(Qt.AlignTop)

        self.files_scroll.setWidget(self.files_list_widget)
        files_layout.addWidget(self.files_scroll)

        self.splitter.addWidget(files_container)

        # Right side of splitter: Diff viewer for the selected file
        self.diff_viewer = DiffViewer(self.splitter)
        self.splitter.addWidget(self.diff_viewer)

        # Set initial splitter proportions (220px files, remainder diff)
        self.splitter.setSizes([220, 500])

        main_layout.addWidget(self.splitter, 1)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def set_commit_details(
        self,
        node: CommitNode,
        file_changes: List[FileChange],
        hunks_by_file: Dict[str, List[Hunk]],
    ) -> None:
        """Populate metadata card, file changes, and diffs for historical commit."""
        self.commit_node = node
        self.file_changes = file_changes
        self.hunks_by_file = hunks_by_file
        self.selected_file = None
        self._file_widgets.clear()

        # Update metadata header
        self.lbl_hash.setText(f"Commit: {node.short_hash}")
        self.lbl_author_date.setText(f"{node.author} • {node.datetime_str}")
        self.lbl_message.setText(node.message.strip() or "No commit message")

        # Update files count
        self.lbl_files_count.setText(f"Changed Files ({len(file_changes)})")

        # Clear existing file rows
        while self.files_list_layout.count() > 0:
            item = self.files_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Populate file items
        for change in file_changes:
            item_widget = CommitFileItemWidget(change, is_active=False, parent=self.files_list_widget)
            item_widget.clicked.connect(self._on_file_clicked)
            self.files_list_layout.addWidget(item_widget)
            self._file_widgets.append(item_widget)

        # Select first file if available
        if file_changes:
            first_path = file_changes[0].file_path
            self._on_file_clicked(first_path)
        else:
            self.diff_viewer.set_diff("", False, [])

    def clear(self) -> None:
        """Reset inspector to empty state."""
        self.commit_node = None
        self.file_changes = []
        self.hunks_by_file = {}
        self.selected_file = None
        self._file_widgets.clear()

        self.lbl_hash.setText("Commit: -")
        self.lbl_author_date.setText("")
        self.lbl_message.setText("No commit selected")
        self.lbl_files_count.setText("Changed Files (0)")

        while self.files_list_layout.count() > 0:
            item = self.files_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.diff_viewer.set_diff("", False, [])

    # -------------------------------------------------------------------------
    # Private Event Handlers
    # -------------------------------------------------------------------------

    def _on_file_clicked(self, file_path: str) -> None:
        self.selected_file = file_path
        for w in self._file_widgets:
            w.set_active(w.change.file_path == file_path)

        hunks = self.hunks_by_file.get(file_path, [])
        self.diff_viewer.set_diff(file_path, is_staged=True, hunks=hunks)

    def _copy_hash(self) -> None:
        if self.commit_node:
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(self.commit_node.hash)
            self.btn_copy_hash.setText("Copied!")
            self.btn_copy_hash.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.COLOR_ADDED_BG};
                    color: {Theme.COLOR_ADDED};
                    border: 1px solid {Theme.COLOR_ADDED};
                    border-radius: 3px;
                    padding: 1px 6px;
                    font-size: 10px;
                }}
            """)
