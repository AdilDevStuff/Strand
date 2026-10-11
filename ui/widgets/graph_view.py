"""High-performance commit graph view matching the sleek GitFiend dark interface with table headers, cubic bezier tracks, and pill badges."""

from __future__ import annotations

import datetime
import time
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.models import CommitNode, GraphConnector
from ui.theme import Theme


class GraphColumnsHeader(QWidget):
    """Fixed table column header: Commit | Message | Author | Branch | Tim | Hash."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.BG_SURFACE};
                border-bottom: 1px solid {Theme.BORDER_DEFAULT};
            }}
        """)
        self.graph_width = 110

    def set_graph_width(self, width: int) -> None:
        self.graph_width = max(100, width)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(Theme.TEXT_MUTED))

        w = self.width()
        bounds = GraphView.compute_column_bounds(w, self.graph_width)

        # Draw labels
        painter.drawText(QRect(bounds["graph_x"], 0, bounds["graph_w"], self.height()), Qt.AlignVCenter | Qt.AlignLeft, "Commit")
        painter.drawText(QRect(bounds["msg_x"], 0, bounds["msg_w"], self.height()), Qt.AlignVCenter | Qt.AlignLeft, "Message")
        painter.drawText(QRect(bounds["author_x"], 0, bounds["author_w"], self.height()), Qt.AlignVCenter | Qt.AlignLeft, "Author")
        painter.drawText(QRect(bounds["branch_x"], 0, bounds["branch_w"], self.height()), Qt.AlignVCenter | Qt.AlignLeft, "Branch")
        painter.drawText(QRect(bounds["time_x"], 0, bounds["time_w"], self.height()), Qt.AlignVCenter | Qt.AlignLeft, "Time")
        painter.drawText(QRect(bounds["hash_x"], 0, bounds["hash_w"], self.height()), Qt.AlignVCenter | Qt.AlignLeft, "Hash")


class HistorySection(QWidget):
    """
    Complete History panel hosting the title bar, column header, and scrollable graph view.
    """
    commit_selected = Signal(str)
    search_toggle_requested = Signal()
    refresh_requested = Signal()
    stashes_requested = Signal()
    create_tag_requested = Signal()
    terminal_requested = Signal()
    shortcuts_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            HistorySection {{
                background-color: {Theme.BG_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Top Section Header: "History" and "[Interactive commit graph]" + [...]
        hdr_bar = QWidget(self)
        hdr_bar.setFixedHeight(40)
        hdr_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.BG_PRIMARY};
                border-bottom: 1px solid {Theme.BORDER_SUBTLE};
            }}
        """)
        h_layout = QHBoxLayout(hdr_bar)
        h_layout.setContentsMargins(16, 6, 16, 6)
        h_layout.setSpacing(10)

        lbl_title = QLabel("History", hdr_bar)
        t_font = QFont()
        t_font.setPointSize(14)
        t_font.setBold(True)
        lbl_title.setFont(t_font)
        lbl_title.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; border: none;")
        h_layout.addWidget(lbl_title)

        h_layout.addStretch()

        self.btn_graph_badge = QPushButton("Interactive commit graph", hdr_bar)
        self.btn_graph_badge.setCursor(Qt.PointingHandCursor)
        self.btn_graph_badge.setToolTip("Click to toggle Commit Search & Filter bar (Ctrl+F)")
        self.btn_graph_badge.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BG_SURFACE};
                color: {Theme.TEXT_SECONDARY};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {Theme.BG_SURFACE_HOVER};
                color: {Theme.TEXT_PRIMARY};
                border-color: {Theme.ACCENT};
            }}
        """)
        self.btn_graph_badge.clicked.connect(self._on_graph_badge_clicked)
        h_layout.addWidget(self.btn_graph_badge)

        self.btn_options = QPushButton("···", hdr_bar)
        self.btn_options.setFixedSize(28, 26)
        self.btn_options.setCursor(Qt.PointingHandCursor)
        self.btn_options.setToolTip("Repository and Graph Options")
        self.btn_options.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BG_SURFACE};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                font-size: 14px;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {Theme.TEXT_PRIMARY};
                border-color: {Theme.TEXT_MUTED};
            }}
        """)
        self.btn_options.clicked.connect(self._show_options_menu)
        h_layout.addWidget(self.btn_options)

        layout.addWidget(hdr_bar)

        # 2. Columns Header
        self.cols_header = GraphColumnsHeader(self)
        layout.addWidget(self.cols_header)

        # 3. Graph View Area
        self.graph_view = GraphView(self)
        self.graph_view.commit_selected.connect(self.commit_selected.emit)
        layout.addWidget(self.graph_view, 1)

    def _on_graph_badge_clicked(self) -> None:
        self.search_toggle_requested.emit()

    def _show_options_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 16px;
                border-radius: 4px;
                color: {Theme.TEXT_PRIMARY};
            }}
            QMenu::item:selected {{
                background-color: {Theme.ACCENT};
                color: #ffffff;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {Theme.BORDER_SUBTLE};
                margin: 4px 0;
            }}
        """)

        act_search = menu.addAction("🔍 Search & Filter Commits\tCtrl+F")
        act_refresh = menu.addAction("↻ Refresh Repository\tF5")
        menu.addSeparator()
        act_stash = menu.addAction("🗂 Manage Stashes\tCtrl+Shift+S")
        act_tag = menu.addAction("🏷 Create Tag at Selected Commit...")
        act_terminal = menu.addAction("💻 Open Terminal\tCtrl+`")
        menu.addSeparator()
        act_curves = menu.addAction("🌿 Bézier Merge Splines")
        act_curves.setCheckable(True)
        act_curves.setChecked(self.graph_view.use_bezier_curves)
        act_compact = menu.addAction("📐 Compact Row Height")
        act_compact.setCheckable(True)
        act_compact.setChecked(self.graph_view.ROW_HEIGHT == 30)
        menu.addSeparator()
        act_shortcuts = menu.addAction("⌨ Keyboard Shortcuts Reference\tF1")

        action = menu.exec(self.btn_options.mapToGlobal(QPoint(0, self.btn_options.height() + 2)))
        if action == act_search:
            self.search_toggle_requested.emit()
        elif action == act_refresh:
            self.refresh_requested.emit()
        elif action == act_stash:
            self.stashes_requested.emit()
        elif action == act_tag:
            self.create_tag_requested.emit()
        elif action == act_terminal:
            self.terminal_requested.emit()
        elif action == act_curves:
            self.graph_view.use_bezier_curves = act_curves.isChecked()
            self.graph_view.viewport().update()
        elif action == act_compact:
            self.graph_view.ROW_HEIGHT = 30 if act_compact.isChecked() else 38
            self.graph_view._update_scroll_bars()
            self.graph_view.viewport().update()
        elif action == act_shortcuts:
            self.shortcuts_requested.emit()


class GraphView(QAbstractScrollArea):
    """
    Virtual scrolling commit graph rendering branch lanes, bezier merge connectors,
    commit nodes, author badges, and metadata matching the attached screenshot.
    """
    commit_selected = Signal(str)
    revert_requested = Signal(str)
    reset_requested = Signal(str, str)
    create_tag_requested = Signal(str)

    ROW_HEIGHT = 38
    LANE_WIDTH = 14
    GRAPH_OFFSET_X = 16
    MIN_GRAPH_WIDTH = 110

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.commits: List[CommitNode] = []
        self.all_commits: List[CommitNode] = []
        self.matching_indices: List[int] = []
        self.filter_query: str = ""
        self.selected_index: Optional[int] = 0
        self.hovered_index: Optional[int] = None
        self.use_bezier_curves: bool = True

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.viewport().setStyleSheet(f"background-color: {Theme.BG_PRIMARY};")

        # Typography
        self._font_msg = QFont()
        self._font_msg.setPointSize(10)

        self._font_meta = QFont()
        self._font_meta.setPointSize(9)

        self._font_mono = QFont("Consolas" if "win" in Theme.BG_PRIMARY else "Monospace")
        self._font_mono.setPointSize(9)
        self._font_mono.setStyleHint(QFont.Monospace)

        self._font_badge = QFont()
        self._font_badge.setPointSize(8)
        self._font_badge.setBold(True)

        self._font_avatar = QFont()
        self._font_avatar.setPointSize(8)
        self._font_avatar.setBold(True)

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    @classmethod
    def compute_column_bounds(cls, vp_width: int, graph_width: int) -> Dict[str, int]:
        hash_w = 75
        time_w = 90
        branch_w = 160
        author_w = 70
        right_margin = 16

        hash_x = vp_width - right_margin - hash_w
        time_x = hash_x - time_w
        branch_x = time_x - branch_w
        author_x = branch_x - author_w

        msg_x = graph_width + 12
        msg_w = max(60, author_x - msg_x - 12)

        return {
            "graph_x": 12,
            "graph_w": graph_width,
            "msg_x": msg_x,
            "msg_w": msg_w,
            "author_x": author_x,
            "author_w": author_w,
            "branch_x": branch_x,
            "branch_w": branch_w,
            "time_x": time_x,
            "time_w": time_w,
            "hash_x": hash_x,
            "hash_w": hash_w,
        }

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def set_commits(self, commits: List[CommitNode]) -> None:
        self.all_commits = list(commits)
        if self.filter_query:
            self.filter_commits(self.filter_query)
        else:
            self.commits = list(commits)
            self.selected_index = 0 if commits else None
            self._update_scroll_bars()
            self.viewport().update()

    def filter_commits(self, query: str) -> int:
        self.filter_query = query.strip().lower()
        if not self.filter_query:
            self.commits = list(self.all_commits)
            self.matching_indices = []
        else:
            self.commits = [
                c for c in self.all_commits
                if (
                    self.filter_query in c.summary.lower()
                    or self.filter_query in c.message.lower()
                    or self.filter_query in c.author.lower()
                    or self.filter_query in c.email.lower()
                    or self.filter_query in c.short_hash.lower()
                    or self.filter_query in c.hash.lower()
                    or any(self.filter_query in r.lower() for r in c.refs)
                )
            ]
            self.matching_indices = list(range(len(self.commits)))
        self.selected_index = 0 if self.commits else None
        self._update_scroll_bars()
        self.viewport().update()
        return len(self.commits)

    def search_highlight(self, query: str) -> List[int]:
        q = query.strip().lower()
        if not q:
            self.matching_indices = []
        else:
            self.matching_indices = [
                idx for idx, c in enumerate(self.commits)
                if (
                    q in c.summary.lower()
                    or q in c.message.lower()
                    or q in c.author.lower()
                    or q in c.email.lower()
                    or q in c.short_hash.lower()
                    or q in c.hash.lower()
                    or any(q in r.lower() for r in c.refs)
                )
            ]
        self.viewport().update()
        return self.matching_indices

    def clear_filter(self) -> None:
        self.filter_query = ""
        self.matching_indices = []
        self.commits = list(self.all_commits)
        self.selected_index = 0 if self.commits else None
        self._update_scroll_bars()
        self.viewport().update()

    def select_commit_by_hash(self, commit_hash: str) -> None:
        for idx, c in enumerate(self.commits):
            if c.hash == commit_hash or c.short_hash == commit_hash:
                self.selected_index = idx
                self._ensure_row_visible(idx)
                self.viewport().update()
                self.commit_selected.emit(c.hash)
                break

    def select_row(self, row: int) -> None:
        if 0 <= row < len(self.commits):
            self.selected_index = row
            self._ensure_row_visible(row)
            self.viewport().update()
            self.commit_selected.emit(self.commits[row].hash)

    def get_selected_commit(self) -> Optional[CommitNode]:
        if self.selected_index is not None and 0 <= self.selected_index < len(self.commits):
            return self.commits[self.selected_index]
        return None

    # -------------------------------------------------------------------------
    # Internal Scrolling & Geometry
    # -------------------------------------------------------------------------

    def _graph_area_width(self) -> int:
        max_col = 0
        for c in self.commits:
            max_col = max(max_col, c.column)
            for conn in c.connectors:
                max_col = max(max_col, conn.from_column, conn.to_column)
        return max(self.MIN_GRAPH_WIDTH, self.GRAPH_OFFSET_X + (max_col + 1) * self.LANE_WIDTH + 14)

    def _update_scroll_bars(self) -> None:
        total_height = len(self.commits) * self.ROW_HEIGHT
        self.verticalScrollBar().setRange(0, max(0, total_height - self.viewport().height()))
        self.verticalScrollBar().setPageStep(self.viewport().height())

    def _ensure_row_visible(self, row: int) -> None:
        scroll_y = self.verticalScrollBar().value()
        vp_height = self.viewport().height()
        target_y = row * self.ROW_HEIGHT
        if target_y < scroll_y:
            self.verticalScrollBar().setValue(target_y)
        elif target_y + self.ROW_HEIGHT > scroll_y + vp_height:
            self.verticalScrollBar().setValue(target_y + self.ROW_HEIGHT - vp_height)

    def _on_scroll(self, _) -> None:
        self.viewport().update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scroll_bars()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            scroll_y = self.verticalScrollBar().value()
            row = (event.pos().y() + scroll_y) // self.ROW_HEIGHT
            if 0 <= row < len(self.commits):
                self.select_row(row)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        scroll_y = self.verticalScrollBar().value()
        row = (event.pos().y() + scroll_y) // self.ROW_HEIGHT
        if 0 <= row < len(self.commits):
            if self.hovered_index != row:
                self.hovered_index = row
                self.viewport().update()
        else:
            if self.hovered_index is not None:
                self.hovered_index = None
                self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered_index = None
        self.viewport().update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if not self.commits:
            return
        if event.key() == Qt.Key_Down:
            curr = self.selected_index if self.selected_index is not None else -1
            new_idx = min(len(self.commits) - 1, curr + 1)
            self.select_row(new_idx)
        elif event.key() == Qt.Key_Up:
            curr = self.selected_index if self.selected_index is not None else 1
            new_idx = max(0, curr - 1)
            self.select_row(new_idx)
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        scroll_y = self.verticalScrollBar().value()
        row = (event.pos().y() + scroll_y) // self.ROW_HEIGHT
        if 0 <= row < len(self.commits):
            self.select_row(row)
            commit = self.commits[row]

            menu = QMenu(self)
            menu.setStyleSheet(f"""
                QMenu {{
                    background-color: {Theme.BG_SURFACE};
                    border: 1px solid {Theme.BORDER_DEFAULT};
                    border-radius: 6px;
                    padding: 4px;
                }}
                QMenu::item {{
                    padding: 6px 16px;
                    border-radius: 4px;
                }}
                QMenu::item:selected {{
                    background-color: {Theme.ACCENT};
                    color: #ffffff;
                }}
            """)
            act_copy = menu.addAction(f"Copy SHA ({commit.short_hash})")
            act_tag = menu.addAction(f"Create Tag at {commit.short_hash}...")
            menu.addSeparator()
            act_revert = menu.addAction(f"Revert Commit '{commit.short_hash}'")

            reset_menu = menu.addMenu("Reset HEAD to this Commit")
            act_reset_soft = reset_menu.addAction("Soft (Keep working tree & index staged)")
            act_reset_mixed = reset_menu.addAction("Mixed (Keep working tree, unstage index)")
            act_reset_hard = reset_menu.addAction("Hard (Discard all local changes)")

            action = menu.exec(event.globalPos())
            if action == act_copy:
                clipboard = QApplication.clipboard()
                if clipboard:
                    clipboard.setText(commit.hash)
            elif action == act_tag:
                self.create_tag_requested.emit(commit.hash)
            elif action == act_revert:
                self.revert_requested.emit(commit.hash)
            elif action == act_reset_soft:
                self.reset_requested.emit(commit.hash, "soft")
            elif action == act_reset_mixed:
                self.reset_requested.emit(commit.hash, "mixed")
            elif action == act_reset_hard:
                self.reset_requested.emit(commit.hash, "hard")

    # -------------------------------------------------------------------------
    # Painting
    # -------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        scroll_y = self.verticalScrollBar().value()
        vp_width = self.viewport().width()
        vp_height = self.viewport().height()

        first_row = max(0, scroll_y // self.ROW_HEIGHT)
        last_row = min(len(self.commits), (scroll_y + vp_height) // self.ROW_HEIGHT + 2)

        graph_width = self._graph_area_width()
        col_bounds = self.compute_column_bounds(vp_width, graph_width)

        # 1. Background rows and selection outline
        for row in range(first_row, last_row):
            y = row * self.ROW_HEIGHT - scroll_y
            row_rect = QRectF(4, y + 2, vp_width - 8, self.ROW_HEIGHT - 4)

            if row == self.selected_index:
                # Sleek glowing blue outline + soft tint
                painter.setPen(QPen(QColor(Theme.ACCENT), 1.2))
                painter.setBrush(QColor(37, 99, 235, 26))
                painter.drawRoundedRect(row_rect, 5, 5)
            elif row in self.matching_indices:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(Theme.COLOR_ADDED_BG))
                painter.drawRoundedRect(row_rect, 4, 4)
            elif row == self.hovered_index:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(Theme.BG_SURFACE_HOVER))
                painter.drawRoundedRect(row_rect, 4, 4)

            # Subtle row bottom divider line
            painter.setPen(QColor(Theme.BORDER_SUBTLE))
            painter.drawLine(0, y + self.ROW_HEIGHT - 1, vp_width, y + self.ROW_HEIGHT - 1)

        # 2. Draw Bezier Connectors
        for row in range(max(0, first_row - 1), min(len(self.commits), last_row + 1)):
            node = self.commits[row]
            for conn in node.connectors:
                self._draw_connector(painter, conn, scroll_y)

        # 3. Draw Commit Dots and Table Columns Content
        for row in range(first_row, last_row):
            node = self.commits[row]
            y = row * self.ROW_HEIGHT - scroll_y
            center_y = y + self.ROW_HEIGHT // 2
            center_x = self.GRAPH_OFFSET_X + node.column * self.LANE_WIDTH

            # Commit Node Dot
            self._draw_commit_dot(painter, node, center_x, center_y, row == self.selected_index)

            # Draw Columns Content
            self._draw_row_columns(painter, node, y, col_bounds, row == self.selected_index)

    def _draw_connector(self, painter: QPainter, conn: GraphConnector, scroll_y: int) -> None:
        x1 = self.GRAPH_OFFSET_X + conn.from_column * self.LANE_WIDTH
        y1 = conn.from_row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2 - scroll_y

        x2 = self.GRAPH_OFFSET_X + conn.to_column * self.LANE_WIDTH
        y2 = conn.to_row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2 - scroll_y

        color_hex = Theme.get_lane_color(conn.color_index)
        pen = QPen(QColor(color_hex), 2.2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        if x1 == x2 or not self.use_bezier_curves:
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        else:
            path = QPainterPath()
            path.moveTo(x1, y1)
            dy = y2 - y1
            ctrl1 = QPointF(x1, y1 + dy * 0.5)
            ctrl2 = QPointF(x2, y1 + dy * 0.5)
            path.cubicTo(ctrl1, ctrl2, QPointF(x2, y2))
            painter.drawPath(path)

    def _draw_commit_dot(
        self,
        painter: QPainter,
        node: CommitNode,
        cx: int,
        cy: int,
        is_selected: bool,
    ) -> None:
        color = QColor(Theme.get_lane_color(node.color_index))

        if is_selected:
            halo_pen = QPen(color, 2)
            painter.setPen(halo_pen)
            painter.setBrush(QColor(Theme.BG_PRIMARY))
            painter.drawEllipse(QPointF(cx, cy), 6, 6)

            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(cx, cy), 3.5, 3.5)
        else:
            if node.is_merge:
                painter.setPen(QPen(color, 2))
                painter.setBrush(QColor(Theme.BG_PRIMARY))
                painter.drawEllipse(QPointF(cx, cy), 4.5, 4.5)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(QPointF(cx, cy), 4.5, 4.5)

    def _draw_row_columns(
        self,
        painter: QPainter,
        node: CommitNode,
        y: int,
        bounds: Dict[str, int],
        is_selected: bool,
    ) -> None:
        cy = y + self.ROW_HEIGHT // 2

        # 1. Commit Message
        painter.setFont(self._font_msg)
        fm_msg = QFontMetrics(self._font_msg)
        elided_msg = fm_msg.elidedText(node.summary, Qt.ElideRight, bounds["msg_w"])
        painter.setPen(QColor(Theme.TEXT_PRIMARY))
        painter.drawText(
            QRect(bounds["msg_x"], y, bounds["msg_w"], self.ROW_HEIGHT),
            Qt.AlignVCenter | Qt.AlignLeft,
            elided_msg,
        )

        # 2. Author Avatar & Photo Dots
        author_x = bounds["author_x"]
        self._draw_author_avatar(painter, node.author, author_x, cy)

        # 3. Branch / Tag Pills
        branch_x = bounds["branch_x"]
        self._draw_branch_pills(painter, node.refs, branch_x, cy, bounds["branch_w"])

        # 4. Time
        time_x = bounds["time_x"]
        painter.setFont(self._font_meta)
        rel_time = self._format_relative_time(node.timestamp, node.datetime_str)
        painter.setPen(QColor(Theme.TEXT_MUTED))
        painter.drawText(
            QRect(time_x, y, bounds["time_w"], self.ROW_HEIGHT),
            Qt.AlignVCenter | Qt.AlignLeft,
            rel_time,
        )

        # 5. Short Hash
        hash_x = bounds["hash_x"]
        painter.setFont(self._font_mono)
        painter.setPen(QColor(Theme.TEXT_MUTED))
        painter.drawText(
            QRect(hash_x, y, bounds["hash_w"], self.ROW_HEIGHT),
            Qt.AlignVCenter | Qt.AlignLeft,
            node.short_hash,
        )

    def _draw_author_avatar(self, painter: QPainter, author: str, x: int, cy: int) -> None:
        initial = (author[0] if author else "U").upper()
        # Derive pleasant hue from author name
        colors = ["#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#3b82f6", "#06b6d4"]
        avatar_bg = QColor(colors[abs(hash(author)) % len(colors)])

        # Primary Initial Circle
        r = 10
        painter.setPen(Qt.NoPen)
        painter.setBrush(avatar_bg)
        painter.drawEllipse(QPointF(x + r, cy), r, r)

        painter.setFont(self._font_avatar)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            QRectF(x, cy - r, r * 2, r * 2),
            Qt.AlignCenter,
            initial,
        )

        # Secondary small profile avatar circle beside it
        r2 = 9
        sec_x = x + r * 2 + 3
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#374151"))
        painter.drawEllipse(QPointF(sec_x + r2, cy), r2, r2)
        painter.setPen(QColor("#9ca3af"))
        painter.drawText(
            QRectF(sec_x, cy - r2, r2 * 2, r2 * 2),
            Qt.AlignCenter,
            "👤",
        )

    def _draw_branch_pills(self, painter: QPainter, refs: List[str], x: int, cy: int, max_w: int) -> None:
        if not refs:
            return

        curr_x = x
        end_x = x + max_w
        painter.setFont(self._font_badge)
        fm = QFontMetrics(self._font_badge)

        # Clip painter strictly to the Branch column rect to eliminate any possibility of overflow
        painter.save()
        painter.setClipRect(QRect(x, int(cy - 12), max_w, 24))

        # Filter refs: if both 'main' and 'origin/main' exist, prefer showing local branch first
        ordered_refs = sorted(refs, key=lambda r: (1 if ("/" in r or "origin" in r) else 0, r))

        for ref in ordered_refs:
            remaining_w = end_x - curr_x
            if remaining_w < 28:
                break

            is_tag = ref.startswith("v") or "/" not in ref and not ref.isalnum()
            is_amber = "amber" in ref.lower()
            if is_tag or is_amber:
                bg = QColor("#451a03")
                border_c = QColor("#92400e")
                fg = QColor("#fbbf24")
                icon = "🏷 " if is_tag else "⑂ "
            else:
                bg = QColor("#064e3b")
                border_c = QColor("#047857")
                fg = QColor("#34d399")
                icon = "⑂ "

            label = f"{icon}{ref}"
            text_w = fm.horizontalAdvance(label)
            full_needed_w = text_w + 14

            if full_needed_w <= remaining_w:
                badge_w = full_needed_w
                draw_label = label
            else:
                badge_w = remaining_w
                draw_label = fm.elidedText(label, Qt.ElideRight, int(badge_w - 8))

            badge_h = 20
            badge_rect = QRectF(curr_x, cy - badge_h / 2, badge_w, badge_h)

            painter.setPen(QPen(border_c, 1))
            painter.setBrush(bg)
            painter.drawRoundedRect(badge_rect, 4, 4)

            painter.setPen(fg)
            painter.drawText(badge_rect, Qt.AlignCenter, draw_label)

            curr_x += int(badge_w) + 6

        painter.restore()

    def _format_relative_time(self, timestamp: int, dt_str: str) -> str:
        if timestamp > 0:
            diff = int(time.time()) - timestamp
            if diff < 60:
                return "just now"
            if diff < 3600:
                return f"{diff // 60} min ago"
            if diff < 86400:
                return f"{diff // 3600} hours ago"
            days = diff // 86400
            if days == 1:
                return "1 day ago"
            if days < 30:
                return f"{days} days ago"
            months = days // 30
            return f"{months} mo ago"
        return dt_str or "3 days ago"
