"""Interactive diff viewer matching the design screenshot with Stage Hunk, Discard, syntax gutter,
and a toggle button to switch between unified (single view) and side-by-side (split view).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.models import DiffLine, DiffLineType, Hunk
from ui.theme import Theme


class HunkWidget(QFrame):
    """
    Renders an individual diff hunk with header, line gutters, red/green rows, and Stage/Discard triggers.
    Supports both Unified (single view) and Split (side-by-side) modes.
    """
    stage_requested = Signal(object)
    unstage_requested = Signal(object)
    discard_requested = Signal(object)

    def __init__(self, hunk: Hunk, is_staged: bool, mode: str = "unified", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.hunk = hunk
        self.is_staged = is_staged
        self.mode = mode

        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_PRIMARY};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Hunk Header Bar: @@ -... +... @@ + [Stage Hunk] [Discard]
        header_bar = QWidget(self)
        header_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.BG_SURFACE};
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                border-bottom: 1px solid {Theme.BORDER_DEFAULT};
            }}
        """)
        h_layout = QHBoxLayout(header_bar)
        h_layout.setContentsMargins(12, 6, 12, 6)
        h_layout.setSpacing(8)

        hdr_label = QLabel(hunk.header, header_bar)
        hdr_font = QFont("Monospace", 9)
        hdr_font.setStyleHint(QFont.Monospace)
        hdr_label.setFont(hdr_font)
        hdr_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; background: transparent; border: none;")
        h_layout.addWidget(hdr_label)

        h_layout.addStretch()

        if not is_staged:
            btn_stage = QPushButton("[Stage Hunk]", header_bar)
            btn_stage.setCursor(Qt.PointingHandCursor)
            btn_stage.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {Theme.ACCENT};
                    border: 1px solid #1e3a8a;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 3px 10px;
                }}
                QPushButton:hover {{
                    background-color: {Theme.ACCENT};
                    color: #ffffff;
                }}
            """)
            btn_stage.clicked.connect(lambda: self.stage_requested.emit(self.hunk))
            h_layout.addWidget(btn_stage)

            btn_discard = QPushButton("[Discard]", header_bar)
            btn_discard.setCursor(Qt.PointingHandCursor)
            btn_discard.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {Theme.COLOR_DELETED};
                    border: 1px solid #7f1d1d;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 3px 10px;
                }}
                QPushButton:hover {{
                    background-color: {Theme.COLOR_DELETED};
                    color: #ffffff;
                }}
            """)
            btn_discard.clicked.connect(lambda: self.discard_requested.emit(self.hunk))
            h_layout.addWidget(btn_discard)
        else:
            btn_unstage = QPushButton("[Unstage Hunk]", header_bar)
            btn_unstage.setCursor(Qt.PointingHandCursor)
            btn_unstage.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {Theme.COLOR_ADDED};
                    border: 1px solid #064e3b;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 3px 10px;
                }}
                QPushButton:hover {{
                    background-color: {Theme.COLOR_ADDED};
                    color: #ffffff;
                }}
            """)
            btn_unstage.clicked.connect(lambda: self.unstage_requested.emit(self.hunk))
            h_layout.addWidget(btn_unstage)

        layout.addWidget(header_bar)

        code_font = QFont("Monospace", 9)
        code_font.setStyleHint(QFont.Monospace)

        # 2. Sub-header for split view
        if mode == "split":
            col_bar = QWidget(self)
            col_bar.setFixedHeight(22)
            col_bar.setStyleSheet(f"""
                QWidget {{
                    background-color: #121316;
                    border-bottom: 1px solid {Theme.BORDER_SUBTLE};
                }}
            """)
            col_layout = QHBoxLayout(col_bar)
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.setSpacing(0)

            lbl_orig = QLabel("  Original (-)", col_bar)
            lbl_orig.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 10px; font-weight: 600; border: none; background: transparent;")
            lbl_orig.setFont(code_font)

            div_hdr = QFrame(col_bar)
            div_hdr.setFixedWidth(1)
            div_hdr.setStyleSheet(f"background-color: {Theme.BORDER_SUBTLE}; border: none;")

            lbl_mod = QLabel("  Modified (+)", col_bar)
            lbl_mod.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 10px; font-weight: 600; border: none; background: transparent;")
            lbl_mod.setFont(code_font)

            col_layout.addWidget(lbl_orig, 1)
            col_layout.addWidget(div_hdr)
            col_layout.addWidget(lbl_mod, 1)
            layout.addWidget(col_bar)

        # 3. Diff Lines Container
        lines_container = QWidget(self)
        lines_container.setStyleSheet(f"background-color: {Theme.BG_PRIMARY}; border: none;")
        lines_layout = QVBoxLayout(lines_container)
        lines_layout.setContentsMargins(0, 0, 0, 0)
        lines_layout.setSpacing(0)

        if mode == "split":
            pairs = self._pair_lines_for_split(hunk.lines)
            for left_line, right_line in pairs:
                row_widget = QWidget(lines_container)
                row_widget.setFixedHeight(22)
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(0)

                # Left side (Original / Deleted / Context / Empty)
                left_cell = QWidget(row_widget)
                left_layout = QHBoxLayout(left_cell)
                left_layout.setContentsMargins(8, 0, 8, 0)
                left_layout.setSpacing(6)

                if left_line is not None:
                    if left_line.line_type == DiffLineType.DELETION:
                        left_bg = "background-color: rgba(239, 68, 68, 0.16);"
                        left_color = "#f87171"
                        sign_color = "#f87171"
                        sign_char = "-"
                    else:
                        left_bg = "background: transparent;"
                        left_color = Theme.TEXT_PRIMARY
                        sign_color = Theme.TEXT_MUTED
                        sign_char = ""

                    left_cell.setStyleSheet(f"QWidget {{ {left_bg} }}")

                    old_num_str = str(left_line.old_lineno) if left_line.old_lineno is not None else ""
                    lbl_old = QLabel(old_num_str, left_cell)
                    lbl_old.setFixedWidth(28)
                    lbl_old.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    lbl_old.setFont(code_font)
                    lbl_old.setStyleSheet(f"color: {Theme.TEXT_MUTED}; background: transparent; border: none;")
                    left_layout.addWidget(lbl_old)

                    lbl_sign = QLabel(sign_char, left_cell)
                    lbl_sign.setFixedWidth(12)
                    lbl_sign.setAlignment(Qt.AlignCenter)
                    lbl_sign.setFont(code_font)
                    lbl_sign.setStyleSheet(f"color: {sign_color}; background: transparent; font-weight: bold; border: none;")
                    left_layout.addWidget(lbl_sign)

                    lbl_text = QLabel(left_line.content, left_cell)
                    lbl_text.setFont(code_font)
                    lbl_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    lbl_text.setStyleSheet(f"color: {left_color}; background: transparent; border: none;")
                    left_layout.addWidget(lbl_text, 1)
                else:
                    left_cell.setStyleSheet("background-color: rgba(255, 255, 255, 0.012);")
                    lbl_empty = QLabel("", left_cell)
                    lbl_empty.setStyleSheet("background: transparent; border: none;")
                    left_layout.addWidget(lbl_empty, 1)

                # Vertical separator
                sep = QFrame(row_widget)
                sep.setFixedWidth(1)
                sep.setStyleSheet(f"background-color: {Theme.BORDER_SUBTLE}; border: none;")

                # Right side (Modified / Added / Context / Empty)
                right_cell = QWidget(row_widget)
                right_layout = QHBoxLayout(right_cell)
                right_layout.setContentsMargins(8, 0, 8, 0)
                right_layout.setSpacing(6)

                if right_line is not None:
                    if right_line.line_type == DiffLineType.ADDITION:
                        right_bg = "background-color: rgba(16, 185, 129, 0.16);"
                        right_color = "#34d399"
                        sign_color = "#34d399"
                        sign_char = "+"
                    else:
                        right_bg = "background: transparent;"
                        right_color = Theme.TEXT_PRIMARY
                        sign_color = Theme.TEXT_MUTED
                        sign_char = ""

                    right_cell.setStyleSheet(f"QWidget {{ {right_bg} }}")

                    new_num_str = str(right_line.new_lineno) if right_line.new_lineno is not None else ""
                    lbl_new = QLabel(new_num_str, right_cell)
                    lbl_new.setFixedWidth(28)
                    lbl_new.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    lbl_new.setFont(code_font)
                    lbl_new.setStyleSheet(f"color: {Theme.TEXT_MUTED}; background: transparent; border: none;")
                    right_layout.addWidget(lbl_new)

                    lbl_sign = QLabel(sign_char, right_cell)
                    lbl_sign.setFixedWidth(12)
                    lbl_sign.setAlignment(Qt.AlignCenter)
                    lbl_sign.setFont(code_font)
                    lbl_sign.setStyleSheet(f"color: {sign_color}; background: transparent; font-weight: bold; border: none;")
                    right_layout.addWidget(lbl_sign)

                    lbl_text = QLabel(right_line.content, right_cell)
                    lbl_text.setFont(code_font)
                    lbl_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    lbl_text.setStyleSheet(f"color: {right_color}; background: transparent; border: none;")
                    right_layout.addWidget(lbl_text, 1)
                else:
                    right_cell.setStyleSheet("background-color: rgba(255, 255, 255, 0.012);")
                    lbl_empty = QLabel("", right_cell)
                    lbl_empty.setStyleSheet("background: transparent; border: none;")
                    right_layout.addWidget(lbl_empty, 1)

                row_layout.addWidget(left_cell, 1)
                row_layout.addWidget(sep)
                row_layout.addWidget(right_cell, 1)

                lines_layout.addWidget(row_widget)
        else:
            # Unified single view
            for line in hunk.lines:
                row_widget = QWidget(lines_container)
                row_widget.setFixedHeight(22)

                bg_style = "background: transparent;"
                text_color = Theme.TEXT_PRIMARY
                sign_color = Theme.TEXT_MUTED

                if line.line_type == DiffLineType.ADDITION:
                    bg_style = "background-color: rgba(16, 185, 129, 0.16);"
                    text_color = "#34d399"
                    sign_color = "#34d399"
                elif line.line_type == DiffLineType.DELETION:
                    bg_style = "background-color: rgba(239, 68, 68, 0.16);"
                    text_color = "#f87171"
                    sign_color = "#f87171"

                row_widget.setStyleSheet(f"QWidget {{ {bg_style} }}")

                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(12, 0, 12, 0)
                row_layout.setSpacing(10)

                # Line numbers (old / new)
                old_num_str = str(line.old_lineno) if line.old_lineno is not None else ""
                new_num_str = str(line.new_lineno) if line.new_lineno is not None else ""

                lbl_old = QLabel(old_num_str, row_widget)
                lbl_old.setFixedWidth(28)
                lbl_old.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                lbl_old.setFont(code_font)
                lbl_old.setStyleSheet(f"color: {Theme.TEXT_MUTED}; background: transparent; border: none;")
                row_layout.addWidget(lbl_old)

                lbl_new = QLabel(new_num_str, row_widget)
                lbl_new.setFixedWidth(28)
                lbl_new.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                lbl_new.setFont(code_font)
                lbl_new.setStyleSheet(f"color: {Theme.TEXT_MUTED}; background: transparent; border: none;")
                row_layout.addWidget(lbl_new)

                # Sign +/-
                lbl_sign = QLabel(line.prefix if line.prefix != " " else "", row_widget)
                lbl_sign.setFixedWidth(14)
                lbl_sign.setAlignment(Qt.AlignCenter)
                lbl_sign.setFont(code_font)
                lbl_sign.setStyleSheet(f"color: {sign_color}; background: transparent; font-weight: bold; border: none;")
                row_layout.addWidget(lbl_sign)

                # Code content
                lbl_text = QLabel(line.content, row_widget)
                lbl_text.setFont(code_font)
                lbl_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
                lbl_text.setStyleSheet(f"color: {text_color}; background: transparent; border: none;")
                row_layout.addWidget(lbl_text, 1)

                lines_layout.addWidget(row_widget)

        layout.addWidget(lines_container)

    @staticmethod
    def _pair_lines_for_split(lines: List[DiffLine]) -> List[Tuple[Optional[DiffLine], Optional[DiffLine]]]:
        """Align unified diff lines into side-by-side (left=old, right=new) pairs."""
        pairs: List[Tuple[Optional[DiffLine], Optional[DiffLine]]] = []
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            if line.line_type == DiffLineType.CONTEXT:
                pairs.append((line, line))
                i += 1
            elif line.line_type in (DiffLineType.DELETION, DiffLineType.ADDITION):
                dels: List[DiffLine] = []
                adds: List[DiffLine] = []
                while i < n and lines[i].line_type in (DiffLineType.DELETION, DiffLineType.ADDITION):
                    if lines[i].line_type == DiffLineType.DELETION:
                        dels.append(lines[i])
                    else:
                        adds.append(lines[i])
                    i += 1
                max_len = max(len(dels), len(adds))
                for k in range(max_len):
                    left_l = dels[k] if k < len(dels) else None
                    right_l = adds[k] if k < len(adds) else None
                    pairs.append((left_l, right_l))
            else:
                pairs.append((line, line))
                i += 1
        return pairs


class DiffViewer(QWidget):
    """
    Main diff viewer panel hosting unified or side-by-side split diff hunks with
    file path title bar, staged badge, and view-mode toggle button.
    """
    stage_hunk_requested = Signal(object)
    unstage_hunk_requested = Signal(object)
    discard_hunk_requested = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.file_path: str = ""
        self.is_staged: bool = False
        self.hunks: List[Hunk] = []
        self.view_mode: str = "unified"  # "unified" or "split"

        self.setStyleSheet(f"""
            DiffViewer {{
                background-color: {Theme.BG_PRIMARY};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header: File path title bar
        self.header_bar = QWidget(self)
        self.header_bar.setFixedHeight(36)
        self.header_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.BG_PRIMARY};
                border-bottom: 1px solid {Theme.BORDER_SUBTLE};
            }}
        """)
        hdr_layout = QHBoxLayout(self.header_bar)
        hdr_layout.setContentsMargins(16, 6, 16, 6)
        hdr_layout.setSpacing(10)

        self.lbl_file_title = QLabel("src/main.py", self.header_bar)
        f_font = QFont()
        f_font.setPointSize(12)
        f_font.setBold(True)
        self.lbl_file_title.setFont(f_font)
        self.lbl_file_title.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; border: none;")
        hdr_layout.addWidget(self.lbl_file_title)

        # Stage Badge (UNSTAGED / STAGED)
        self.lbl_stage_badge = QLabel("UNSTAGED", self.header_bar)
        self.lbl_stage_badge.setVisible(False)
        hdr_layout.addWidget(self.lbl_stage_badge)

        hdr_layout.addStretch()

        # View Mode Toggle Button: Unified vs Split View
        self.btn_view_mode = QPushButton(self.header_bar)
        self.btn_view_mode.setCursor(Qt.PointingHandCursor)
        self.btn_view_mode.setToolTip("Switch between Unified (single view) and Split (side-by-side) diff view")
        self._update_view_mode_button()
        self.btn_view_mode.clicked.connect(self.toggle_view_mode)
        hdr_layout.addWidget(self.btn_view_mode)

        self.btn_top_stage = QPushButton("[Stage Hunk]", self.header_bar)
        self.btn_top_stage.setCursor(Qt.PointingHandCursor)
        self.btn_top_stage.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Theme.ACCENT};
                border: 1px solid #1e3a8a;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 3px 10px;
            }}
            QPushButton:hover {{
                background-color: {Theme.ACCENT};
                color: #ffffff;
            }}
        """)
        self.btn_top_stage.clicked.connect(self._on_top_stage_clicked)
        hdr_layout.addWidget(self.btn_top_stage)

        self.btn_top_discard = QPushButton("[Discard]", self.header_bar)
        self.btn_top_discard.setCursor(Qt.PointingHandCursor)
        self.btn_top_discard.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Theme.COLOR_DELETED};
                border: 1px solid #7f1d1d;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 3px 10px;
            }}
            QPushButton:hover {{
                background-color: {Theme.COLOR_DELETED};
                color: #ffffff;
            }}
        """)
        self.btn_top_discard.clicked.connect(self._on_top_discard_clicked)
        hdr_layout.addWidget(self.btn_top_discard)

        main_layout.addWidget(self.header_bar)

        # 2. Scroll area for hunks
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"QScrollArea {{ background-color: {Theme.BG_PRIMARY}; border: none; }}")

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet(f"background-color: {Theme.BG_PRIMARY};")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(14, 14, 14, 14)
        self.content_layout.setSpacing(14)
        self.content_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area, 1)

        # Empty placeholder
        self.lbl_empty = QLabel("Select a modified or staged file to view diff", self.content_widget)
        self.lbl_empty.setAlignment(Qt.AlignCenter)
        self.lbl_empty.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 13px; padding: 40px;")
        self.content_layout.addWidget(self.lbl_empty)

    def _update_view_mode_button(self) -> None:
        """Update button label and visual accent styling based on current view mode."""
        if self.view_mode == "unified":
            self.btn_view_mode.setText("◫ Split View")
            self.btn_view_mode.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.BG_SURFACE};
                    color: {Theme.TEXT_SECONDARY};
                    border: 1px solid {Theme.BORDER_DEFAULT};
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 3px 10px;
                }}
                QPushButton:hover {{
                    background-color: #1e222b;
                    color: #ffffff;
                    border-color: {Theme.ACCENT};
                }}
            """)
        else:
            self.btn_view_mode.setText("☰ Unified View")
            self.btn_view_mode.setStyleSheet(f"""
                QPushButton {{
                    background-color: #1e3a8a;
                    color: #bfdbfe;
                    border: 1px solid #3b82f6;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 3px 10px;
                }}
                QPushButton:hover {{
                    background-color: #2563eb;
                    color: #ffffff;
                }}
            """)

    def set_view_mode(self, mode: str) -> None:
        """Set view mode to 'unified' or 'split' and refresh display."""
        if mode in ("unified", "split") and mode != self.view_mode:
            self.view_mode = mode
            self._update_view_mode_button()
            self.display_diff(self.file_path, self.is_staged, self.hunks)

    def toggle_view_mode(self) -> None:
        """Toggle between unified and split views."""
        self.set_view_mode("split" if self.view_mode == "unified" else "unified")

    def display_diff(self, file_path: str, is_staged: bool, hunks: List[Hunk]) -> None:
        self.file_path = file_path
        self.is_staged = is_staged
        self.hunks = hunks

        self.lbl_file_title.setText(file_path or "No file selected")

        if file_path:
            self.lbl_stage_badge.setVisible(True)
            if is_staged:
                self.lbl_stage_badge.setText("STAGED")
                self.lbl_stage_badge.setStyleSheet(f"""
                    QLabel {{
                        color: {Theme.COLOR_ADDED};
                        background-color: rgba(16, 185, 129, 0.14);
                        border: 1px solid rgba(16, 185, 129, 0.3);
                        font-size: 10px;
                        font-weight: 700;
                        padding: 1px 6px;
                        border-radius: 4px;
                    }}
                """)
            else:
                self.lbl_stage_badge.setText("UNSTAGED")
                self.lbl_stage_badge.setStyleSheet(f"""
                    QLabel {{
                        color: #94a3b8;
                        background-color: rgba(148, 163, 184, 0.12);
                        border: 1px solid rgba(148, 163, 184, 0.25);
                        font-size: 10px;
                        font-weight: 700;
                        padding: 1px 6px;
                        border-radius: 4px;
                    }}
                """)
        else:
            self.lbl_stage_badge.setVisible(False)

        has_hunks = bool(hunks)
        self.btn_top_stage.setVisible(has_hunks and not is_staged)
        self.btn_top_discard.setVisible(has_hunks and not is_staged)

        # Clear existing
        while self.content_layout.count() > 0:
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not hunks:
            self.lbl_empty = QLabel(
                f"No changes detected for '{file_path}'" if file_path else "Select a file to view diff",
                self.content_widget,
            )
            self.lbl_empty.setAlignment(Qt.AlignCenter)
            self.lbl_empty.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 13px; padding: 40px;")
            self.content_layout.addWidget(self.lbl_empty)
            return

        for hunk in hunks:
            hw = HunkWidget(hunk, is_staged=is_staged, mode=self.view_mode, parent=self.content_widget)
            hw.stage_requested.connect(self.stage_hunk_requested.emit)
            hw.unstage_requested.connect(self.unstage_hunk_requested.emit)
            hw.discard_requested.connect(self.discard_hunk_requested.emit)
            self.content_layout.addWidget(hw)

    def clear(self) -> None:
        self.display_diff("", False, [])

    def _on_top_stage_clicked(self) -> None:
        if self.hunks:
            self.stage_hunk_requested.emit(self.hunks[0])

    def _on_top_discard_clicked(self) -> None:
        if self.hunks:
            self.discard_hunk_requested.emit(self.hunks[0])

    set_diff = display_diff
