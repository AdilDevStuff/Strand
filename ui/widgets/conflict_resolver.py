"""Interactive visual 3-way merge conflict resolution panel."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Theme


class ConflictBlockWidget(QFrame):
    """Visual comparison block showing 'Ours' vs 'Theirs' with resolution buttons."""
    resolved_with_block = Signal(str)  # "ours" | "theirs"

    def __init__(self, block: Dict[str, Any], block_idx: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.block = block

        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(f"""
            ConflictBlockWidget {{
                background-color: {Theme.BG_PRIMARY};
                border: 1px solid {Theme.COLOR_CONFLICT};
                border-radius: 6px;
                margin-bottom: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Header with line numbers
        hdr_layout = QHBoxLayout()
        hdr_lbl = QLabel(f"Conflict #{block_idx + 1} (Lines {block.get('start_line', '?')} - {block.get('end_line', '?')})", self)
        hdr_lbl.setStyleSheet(f"color: {Theme.COLOR_CONFLICT}; font-weight: bold; font-size: 12px;")
        hdr_layout.addWidget(hdr_lbl)
        hdr_layout.addStretch()
        layout.addLayout(hdr_layout)

        # Side-by-side or stacked content
        content_splitter = QSplitter(Qt.Horizontal, self)
        content_splitter.setHandleWidth(1)

        code_font = QFont("Consolas" if "win" in Theme.BG_PRIMARY else "Monospace", 9)
        code_font.setStyleHint(QFont.Monospace)

        # 1. Ours Pane
        ours_pane = QWidget(content_splitter)
        ours_layout = QVBoxLayout(ours_pane)
        ours_layout.setContentsMargins(0, 0, 0, 0)
        ours_layout.setSpacing(4)

        ours_hdr = QHBoxLayout()
        lbl_ours = QLabel("Ours (Current Branch)", ours_pane)
        lbl_ours.setStyleSheet(f"color: {Theme.COLOR_ADDED}; font-weight: 600; font-size: 11px;")
        ours_hdr.addWidget(lbl_ours)
        ours_hdr.addStretch()

        btn_pick_ours = QPushButton("Accept Ours", ours_pane)
        btn_pick_ours.setCursor(Qt.PointingHandCursor)
        btn_pick_ours.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.COLOR_ADDED_BG};
                color: {Theme.COLOR_ADDED};
                border: 1px solid {Theme.COLOR_ADDED};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {Theme.COLOR_ADDED};
                color: #ffffff;
            }}
        """)
        btn_pick_ours.clicked.connect(lambda: self.resolved_with_block.emit("ours"))
        ours_hdr.addWidget(btn_pick_ours)
        ours_layout.addLayout(ours_hdr)

        txt_ours = QTextEdit(ours_pane)
        txt_ours.setFont(code_font)
        txt_ours.setReadOnly(True)
        txt_ours.setPlainText(block.get("ours", ""))
        txt_ours.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.BG_SURFACE};
                color: #86efac;
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 4px;
                padding: 6px;
            }}
        """)
        ours_layout.addWidget(txt_ours)
        content_splitter.addWidget(ours_pane)

        # 2. Theirs Pane
        theirs_pane = QWidget(content_splitter)
        theirs_layout = QVBoxLayout(theirs_pane)
        theirs_layout.setContentsMargins(0, 0, 0, 0)
        theirs_layout.setSpacing(4)

        theirs_hdr = QHBoxLayout()
        lbl_theirs = QLabel("Theirs (Incoming Branch)", theirs_pane)
        lbl_theirs.setStyleSheet(f"color: {Theme.ACCENT}; font-weight: 600; font-size: 11px;")
        theirs_hdr.addWidget(lbl_theirs)
        theirs_hdr.addStretch()

        btn_pick_theirs = QPushButton("Accept Theirs", theirs_pane)
        btn_pick_theirs.setCursor(Qt.PointingHandCursor)
        btn_pick_theirs.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BG_SURFACE_ACTIVE};
                color: {Theme.ACCENT};
                border: 1px solid {Theme.ACCENT};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {Theme.ACCENT};
                color: #ffffff;
            }}
        """)
        btn_pick_theirs.clicked.connect(lambda: self.resolved_with_block.emit("theirs"))
        theirs_hdr.addWidget(btn_pick_theirs)
        theirs_layout.addLayout(theirs_hdr)

        txt_theirs = QTextEdit(theirs_pane)
        txt_theirs.setFont(code_font)
        txt_theirs.setReadOnly(True)
        txt_theirs.setPlainText(block.get("theirs", ""))
        txt_theirs.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.BG_SURFACE};
                color: #93c5fd;
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 4px;
                padding: 6px;
            }}
        """)
        theirs_layout.addWidget(txt_theirs)
        content_splitter.addWidget(theirs_pane)

        layout.addWidget(content_splitter)


class ConflictResolverView(QWidget):
    """
    Main 3-way merge conflict resolution panel.
    Displays file conflict banners and allows batch or block-level conflict resolution.
    """
    resolve_requested = Signal(str, str)  # (file_path, strategy: "ours" | "theirs" | "mark_resolved")

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.file_path: str = ""
        self.conflict_blocks: List[Dict[str, Any]] = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top Action & Banner Bar
        self.header_frame = QFrame(self)
        self.header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_SURFACE};
                border-bottom: 1px solid {Theme.BORDER_DEFAULT};
            }}
        """)
        hdr_layout = QHBoxLayout(self.header_frame)
        hdr_layout.setContentsMargins(16, 10, 16, 10)
        hdr_layout.setSpacing(12)

        self.lbl_title = QLabel("Merge Conflict Resolver", self.header_frame)
        self.lbl_title.setStyleSheet(f"font-weight: 700; color: {Theme.COLOR_CONFLICT}; font-size: 13px;")
        hdr_layout.addWidget(self.lbl_title)

        self.lbl_file = QLabel("No conflicted file selected", self.header_frame)
        self.lbl_file.setStyleSheet(f"color: {Theme.TEXT_SECONDARY}; font-size: 12px;")
        hdr_layout.addWidget(self.lbl_file)

        hdr_layout.addStretch()

        # Batch Actions
        self.btn_accept_all_ours = QPushButton("Use All Ours", self.header_frame)
        self.btn_accept_all_ours.setCursor(Qt.PointingHandCursor)
        self.btn_accept_all_ours.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.COLOR_ADDED_BG};
                color: {Theme.COLOR_ADDED};
                border: 1px solid {Theme.COLOR_ADDED};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {Theme.COLOR_ADDED};
                color: #ffffff;
            }}
        """)
        self.btn_accept_all_ours.clicked.connect(lambda: self._on_resolve("ours"))
        hdr_layout.addWidget(self.btn_accept_all_ours)

        self.btn_accept_all_theirs = QPushButton("Use All Theirs", self.header_frame)
        self.btn_accept_all_theirs.setCursor(Qt.PointingHandCursor)
        self.btn_accept_all_theirs.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BG_SURFACE_ACTIVE};
                color: {Theme.ACCENT};
                border: 1px solid {Theme.ACCENT};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {Theme.ACCENT};
                color: #ffffff;
            }}
        """)
        self.btn_accept_all_theirs.clicked.connect(lambda: self._on_resolve("theirs"))
        hdr_layout.addWidget(self.btn_accept_all_theirs)

        self.btn_mark_resolved = QPushButton("Mark Resolved", self.header_frame)
        self.btn_mark_resolved.setCursor(Qt.PointingHandCursor)
        self.btn_mark_resolved.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {Theme.ACCENT_HOVER};
            }}
        """)
        self.btn_mark_resolved.clicked.connect(lambda: self._on_resolve("mark_resolved"))
        hdr_layout.addWidget(self.btn_mark_resolved)

        main_layout.addWidget(self.header_frame)

        # Scroll area for blocks
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"QScrollArea {{ background-color: {Theme.BG_PRIMARY}; border: none; }}")

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet(f"background-color: {Theme.BG_PRIMARY};")
        self.blocks_layout = QVBoxLayout(self.scroll_content)
        self.blocks_layout.setContentsMargins(16, 16, 16, 16)
        self.blocks_layout.setSpacing(12)
        self.blocks_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area, 1)

    def set_conflicted_file(self, file_path: str, blocks: List[Dict[str, Any]]) -> None:
        """Populate view with parsed conflict blocks for the given file."""
        self.file_path = file_path
        self.conflict_blocks = blocks

        self.lbl_file.setText(file_path if file_path else "No conflicted file selected")
        has_file = bool(file_path)
        self.btn_accept_all_ours.setEnabled(has_file)
        self.btn_accept_all_theirs.setEnabled(has_file)
        self.btn_mark_resolved.setEnabled(has_file)

        # Clear existing block widgets
        while self.blocks_layout.count() > 0:
            item = self.blocks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not blocks:
            empty_lbl = QLabel("No active conflict markers detected in this file.", self.scroll_content)
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 13px; margin-top: 40px;")
            self.blocks_layout.addWidget(empty_lbl)
            return

        for idx, block in enumerate(blocks):
            w = ConflictBlockWidget(block, idx, self.scroll_content)
            w.resolved_with_block.connect(lambda strategy: self._on_resolve(strategy))
            self.blocks_layout.addWidget(w)

    def _on_resolve(self, strategy: str) -> None:
        if self.file_path:
            self.resolve_requested.emit(self.file_path, strategy)
