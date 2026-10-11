"""Main application window assembling the sleek GitFiend three-pane desktop interface."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QProcess, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.models import CommitNode, FileChange, FileStatus, Hunk
from services.app_state import AppState
from ui.theme import Theme
from ui.widgets.branch_list import BranchListWidget
from ui.widgets.commit_box import CommitBox
from ui.widgets.conflict_resolver import ConflictResolverView
from ui.widgets.diff_viewer import DiffViewer
from ui.widgets.graph_view import GraphView, HistorySection
from ui.widgets.loading_overlay import LoadingOverlay
from ui.widgets.stash_dialog import StashDialog
from ui.widgets.status_tree import StatusTree
from ui.widgets.toolbar import Toolbar


class MainWindow(QMainWindow):
    """
    Main application window implementing the attached UI design:
    - Left Activity Sidebar:
      - macOS traffic lights [🔴 🟡 🟢] + sidebar toggle [◧]
      - PROJECT: <name> ⌵
      - Branches
      - Remote branches (with active branch pill highlight)
      - Stashes
      - Tags [+]
    - Top Navigation Bar:
      - [📁 <repo> ⌵] [⑂ Branch ⌵]   [ ↑ 2  ↓ 1 ] [↓ Fetch] [⇊ Pull] [↑ Push]
    - Center Work Area:
      - Upper Pane: HistorySection (Commit Graph Table with DAG bezier curves, Author avatars, Branch pills)
      - Lower Pane (Split horizontally):
        - Left: StatusTree (Unstaged & Staged Changes with +14 -3 stats)
        - Right: DiffViewer + Floating/Docked CommitBox at bottom-right!
    """

    def __init__(
        self,
        repo_path: Optional[str] = None,
        app_state: Optional[AppState] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.state = app_state or AppState()
        self.stash_dialog = StashDialog(self)

        self.setWindowTitle("Strand")
        self.resize(1380, 860)
        self.setMinimumSize(980, 620)
        self.setStyleSheet(Theme.main_stylesheet())

        # Central Layout Structure
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._sidebar_last_width: int = 280

        # 1. Main Horizontal Splitter (Sidebar on left, Work area on right)
        self.main_h_splitter = QSplitter(Qt.Horizontal, central_widget)
        self.main_h_splitter.setHandleWidth(1)
        self.main_h_splitter.splitterMoved.connect(self._on_main_splitter_moved)

        # Left Activity Sidebar (hosting branch trees and docked CommitBox)
        self.sidebar_branches = BranchListWidget(self.main_h_splitter)
        self.sidebar_branches.setMinimumWidth(280)
        self.sidebar_branches.setMaximumWidth(450)
        self.commit_box = self.sidebar_branches.commit_box
        self.main_h_splitter.addWidget(self.sidebar_branches)

        # Floating arrow button on the left edge (middle of panel) when sidebar is collapsed
        self.btn_expand_sidebar = QPushButton("▶", central_widget)
        self.btn_expand_sidebar.setFixedSize(22, 56)
        self.btn_expand_sidebar.setCursor(Qt.PointingHandCursor)
        self.btn_expand_sidebar.setToolTip("Show sidebar (Ctrl+B)")
        self.btn_expand_sidebar.setStyleSheet(f"""
            QPushButton {{
                background-color: #1a1d24;
                color: #94a3b8;
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-left: none;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                font-size: 11px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {Theme.ACCENT};
                color: #ffffff;
                border-color: #3b82f6;
            }}
            QPushButton:pressed {{
                background-color: #1d4ed8;
            }}
        """)
        self.btn_expand_sidebar.clicked.connect(self._toggle_sidebar)
        self.btn_expand_sidebar.setVisible(False)

        # Right Main Content Container
        self.work_area = QWidget(self.main_h_splitter)
        wa_layout = QVBoxLayout(self.work_area)
        wa_layout.setContentsMargins(0, 0, 0, 0)
        wa_layout.setSpacing(0)

        # Top Navigation Bar
        self.toolbar = Toolbar(self.work_area)
        wa_layout.addWidget(self.toolbar)

        # Aliases for backward compatibility with tests
        self.btn_push = self.toolbar.btn_push
        self.btn_pull = self.toolbar.btn_pull
        class _StashesBtnProxy:
            def __init__(self, win):
                self._win = win
            def text(self) -> str:
                return f"Stashes ({len(self._win.state.stashes)})"
        self.btn_stashes = _StashesBtnProxy(self)
        self.lbl_repo_name = self.sidebar_branches.lbl_repo_name

        class _BranchComboProxy:
            def __init__(self, toolbar):
                self._toolbar = toolbar
            def currentText(self) -> str:
                return self._toolbar.current_branch
        self.combo_branch = _BranchComboProxy(self.toolbar)

        # Main Vertical Splitter: History Graph (Top) vs Changes/Diff (Bottom)
        self.center_splitter = QSplitter(Qt.Vertical, self.work_area)
        self.center_splitter.setHandleWidth(1)

        # Upper Area: Search Bar (toggleable) + History Section
        self.upper_container = QWidget(self.center_splitter)
        uc_layout = QVBoxLayout(self.upper_container)
        uc_layout.setContentsMargins(0, 0, 0, 0)
        uc_layout.setSpacing(0)

        self.search_bar = self._build_graph_search_bar()
        self.search_bar.setVisible(False)  # Hidden by default, toggled with Ctrl+F
        uc_layout.addWidget(self.search_bar)

        self.history_section = HistorySection(self.upper_container)
        self.graph_view = self.history_section.graph_view
        uc_layout.addWidget(self.history_section, 1)

        self.center_splitter.addWidget(self.upper_container)

        # Lower Area: Split Horizontally into Changes (Left) and Diff + Commit Card (Right)
        self.lower_splitter = QSplitter(Qt.Horizontal, self.center_splitter)
        self.lower_splitter.setHandleWidth(1)

        # Lower-Left: Changes Tree (Unstaged + Staged)
        self.status_tree = StatusTree(self.lower_splitter)
        self.status_tree.setMinimumWidth(220)
        self.lower_splitter.addWidget(self.status_tree)

        # Lower-Right: Diff Viewer Stack (takes full height of lower pane)
        self.diff_card_container = QWidget(self.lower_splitter)
        self.diff_card_container.setStyleSheet(f"background-color: {Theme.BG_PRIMARY};")
        dc_layout = QVBoxLayout(self.diff_card_container)
        dc_layout.setContentsMargins(0, 0, 0, 0)
        dc_layout.setSpacing(0)

        self.diff_stack = QStackedWidget(self.diff_card_container)
        self.diff_viewer = DiffViewer(self.diff_stack)
        self.conflict_resolver = ConflictResolverView(self.diff_stack)
        self.diff_stack.addWidget(self.diff_viewer)
        self.diff_stack.addWidget(self.conflict_resolver)
        dc_layout.addWidget(self.diff_stack, 1)

        self.lower_splitter.addWidget(self.diff_card_container)

        # Set default proportions: 30% changes, 70% diff viewer
        self.lower_splitter.setSizes([320, 780])

        self.center_splitter.addWidget(self.lower_splitter)

        # Set vertical split proportions: 55% History graph, 45% lower workspace
        self.center_splitter.setSizes([460, 360])

        wa_layout.addWidget(self.center_splitter, 1)
        self.main_h_splitter.addWidget(self.work_area)

        # Proportions: ~20% sidebar (matching commit box), ~80% main area
        self.main_h_splitter.setSizes([280, 1100])
        root_layout.addWidget(self.main_h_splitter, 1)

        # 3. Status Bar (Minimal)
        self.status_bar = QStatusBar(self)
        self.status_bar.setStyleSheet(f"""
            QStatusBar {{
                background-color: {Theme.BG_PRIMARY};
                color: {Theme.TEXT_MUTED};
                border-top: 1px solid {Theme.BORDER_SUBTLE};
                font-size: 11px;
                padding: 1px 10px;
            }}
        """)
        self.setStatusBar(self.status_bar)
        self.lbl_status_msg = QLabel("Ready", self.status_bar)
        self.status_bar.addWidget(self.lbl_status_msg, 1)

        self.lbl_loading_indicator = QLabel("", self.status_bar)
        self.lbl_loading_indicator.setStyleSheet(f"""
            QLabel {{
                color: #60a5fa;
                font-size: 11px;
                font-weight: 600;
                padding: 1px 8px;
                border-radius: 4px;
                background-color: rgba(37, 99, 235, 0.12);
                border: 1px solid rgba(59, 130, 246, 0.25);
            }}
        """)
        self.lbl_loading_indicator.setVisible(False)
        self.status_bar.addPermanentWidget(self.lbl_loading_indicator)

        # Global Animated Spinner Timer
        self._global_spinner_idx = 0
        self._global_spinner_timer = QTimer(self)
        self._global_spinner_timer.setInterval(80)
        self._global_spinner_timer.timeout.connect(self._on_global_spinner_tick)

        # Global Full-Window Modal Loading Overlay
        self._loading_title: str = "Processing..."
        self._loading_subtext: str = "Please wait while Git operation completes"
        self._loading_delay_timer = QTimer(self)
        self._loading_delay_timer.setSingleShot(True)
        self._loading_delay_timer.timeout.connect(self._on_loading_delay_timeout)

        self.loading_overlay = LoadingOverlay(self)
        self.loading_overlay.dismiss_requested.connect(self.stop_loading)

        self.setAcceptDrops(True)

        # Compatibility references
        self.header_bar = self.toolbar

        # Wire UI signals and reactive AppState bindings
        self._bind_state()
        self._bind_ui_events()

        # Keyboard shortcuts
        self._setup_shortcuts()

        # Open initial repository if specified
        if repo_path and os.path.isdir(repo_path):
            self.state.open_repository(repo_path)

    # -------------------------------------------------------------------------
    # Layout Builders
    # -------------------------------------------------------------------------

    def _build_graph_search_bar(self) -> QWidget:
        bar = QWidget(self)
        bar.setFixedHeight(34)
        bar.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.BG_SURFACE};
                border-bottom: 1px solid {Theme.BORDER_DEFAULT};
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        lbl_icon = QLabel("🔍", bar)
        lbl_icon.setStyleSheet("background: transparent; font-size: 11px;")
        layout.addWidget(lbl_icon)

        self.input_search = QLineEdit(bar)
        self.input_search.setPlaceholderText("Search commits by message, author, or SHA (Ctrl+F)...")
        self.input_search.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Theme.BG_INPUT};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: {Theme.ACCENT};
            }}
        """)
        self.input_search.textChanged.connect(self._on_search_query_changed)
        self.input_search.returnPressed.connect(self._on_search_next)
        layout.addWidget(self.input_search, 1)

        self.lbl_search_count = QLabel("", bar)
        self.lbl_search_count.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; background: transparent;")
        layout.addWidget(self.lbl_search_count)

        self.btn_search_prev = QPushButton("▲", bar)
        self.btn_search_prev.setFixedSize(22, 22)
        self.btn_search_prev.setToolTip("Previous match (Shift+Enter)")
        self.btn_search_prev.setStyleSheet("font-size: 9px; padding: 0;")
        self.btn_search_prev.clicked.connect(self._on_search_prev)
        layout.addWidget(self.btn_search_prev)

        self.btn_search_next = QPushButton("▼", bar)
        self.btn_search_next.setFixedSize(22, 22)
        self.btn_search_next.setToolTip("Next match (Enter)")
        self.btn_search_next.setStyleSheet("font-size: 9px; padding: 0;")
        self.btn_search_next.clicked.connect(self._on_search_next)
        layout.addWidget(self.btn_search_next)

        self.chk_search_filter = QCheckBox("Filter", bar)
        self.chk_search_filter.setToolTip("Hide non-matching commits from graph")
        self.chk_search_filter.setStyleSheet(f"color: {Theme.TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        self.chk_search_filter.toggled.connect(self._on_search_filter_toggled)
        layout.addWidget(self.chk_search_filter)

        btn_clear = QPushButton("✕", bar)
        btn_clear.setFixedSize(20, 20)
        btn_clear.setToolTip("Close search (Esc)")
        btn_clear.setStyleSheet(f"font-size: 11px; border: none; background: transparent; color: {Theme.TEXT_MUTED};")
        btn_clear.clicked.connect(self._hide_search)
        layout.addWidget(btn_clear)

        return bar

    # -------------------------------------------------------------------------
    # Reactive State Bindings
    # -------------------------------------------------------------------------

    def _bind_state(self) -> None:
        """Connect AppState signals to update UI views."""
        self.state.repo_opened.connect(self._on_repo_opened)
        self.state.repo_closed.connect(self._on_repo_closed)
        self.state.branch_changed.connect(self._on_branch_changed)
        self.state.branches_updated.connect(self._on_branches_updated)
        self.state.status_updated.connect(self.status_tree.set_changes)
        self.state.history_updated.connect(self._on_history_updated)
        self.state.diff_updated.connect(self._on_diff_updated)
        self.state.sync_status_updated.connect(self._on_sync_status_updated)
        self.state.loading_changed.connect(self._on_loading_changed)
        self.state.error_occurred.connect(self._show_error)
        self.state.operation_succeeded.connect(self._show_success)
        self.state.commit_details_loaded.connect(self._on_commit_details_loaded)
        self.state.stashes_updated.connect(self._on_stashes_updated)
        self.state.conflicts_updated.connect(self._on_conflicts_updated)
        self.state.tags_updated.connect(self.sidebar_branches.set_tags)

    def _bind_ui_events(self) -> None:
        """Connect UI widget user interactions to trigger AppState actions."""
        # Sidebar actions
        self.sidebar_branches.branch_checkout_requested.connect(self._on_checkout_requested)
        self.sidebar_branches.branch_create_requested.connect(self.state.create_branch)
        self.sidebar_branches.stash_manage_requested.connect(self._open_stash_dialog)
        self.sidebar_branches.tag_create_requested.connect(self._prompt_create_tag_general)
        self.sidebar_branches.tag_selected.connect(self._on_tag_selected)
        self.sidebar_branches.btn_toggle_sidebar.clicked.connect(self._toggle_sidebar)

        # Toolbar actions
        self.toolbar.open_repo_requested.connect(self._prompt_open_repository)
        self.toolbar.checkout_requested.connect(self._on_checkout_requested)
        self.toolbar.fetch_requested.connect(self._on_fetch_requested)
        self.toolbar.pull_requested.connect(self._on_pull_requested)
        self.toolbar.push_requested.connect(self._on_push_requested)

        # Commit graph selection and history operations
        self.graph_view.commit_selected.connect(self._on_commit_graph_selected)
        self.graph_view.revert_requested.connect(self._prompt_revert_commit)
        self.graph_view.reset_requested.connect(self._prompt_reset)
        self.graph_view.create_tag_requested.connect(self._prompt_create_tag)

        # History section buttons (Interactive commit graph, Options menu)
        self.history_section.search_toggle_requested.connect(self._toggle_search)
        self.history_section.refresh_requested.connect(self._on_refresh_requested)
        self.history_section.stashes_requested.connect(self._open_stash_dialog)
        self.history_section.create_tag_requested.connect(self._prompt_create_tag_general)
        self.history_section.terminal_requested.connect(self._open_terminal)
        self.history_section.shortcuts_requested.connect(self._show_shortcuts_dialog)

        # Stash dialog actions
        self.stash_dialog.stash_save_requested.connect(self.state.stash_save)
        self.stash_dialog.stash_pop_requested.connect(self.state.stash_pop)
        self.stash_dialog.stash_apply_requested.connect(self.state.stash_apply)
        self.stash_dialog.stash_drop_requested.connect(self.state.stash_drop)

        # Conflict resolution actions
        self.conflict_resolver.resolve_requested.connect(self._on_resolve_conflict)

        # Status tree actions
        self.status_tree.file_selected.connect(self._on_status_file_selected)
        self.status_tree.stage_file_requested.connect(self.state.stage_file)
        self.status_tree.unstage_file_requested.connect(self.state.unstage_file)
        self.status_tree.stage_all_requested.connect(self._stage_all_files)
        self.status_tree.unstage_all_requested.connect(self._unstage_all_files)

        # Diff viewer hunk triggers
        self.diff_viewer.stage_hunk_requested.connect(self.state.stage_hunk)
        self.diff_viewer.unstage_hunk_requested.connect(self.state.unstage_hunk)
        self.diff_viewer.discard_hunk_requested.connect(self.state.discard_hunk)

        # Commit box
        self.commit_box.commit_requested.connect(self._on_commit_submitted)

    def _setup_shortcuts(self) -> None:
        """Setup global window keyboard shortcuts."""
        # F5 -> Refresh
        sc_f5 = QShortcut(QKeySequence("F5"), self)
        sc_f5.activated.connect(self._on_refresh_requested)

        # Ctrl+` -> Terminal
        sc_term = QShortcut(QKeySequence("Ctrl+`"), self)
        sc_term.activated.connect(self._open_terminal)

        # Ctrl+O -> Open Repo
        sc_open = QShortcut(QKeySequence("Ctrl+O"), self)
        sc_open.activated.connect(self._prompt_open_repository)

        # Ctrl+F -> Search Commits
        sc_search = QShortcut(QKeySequence("Ctrl+F"), self)
        sc_search.activated.connect(self._focus_search)

        # Esc -> Hide Search Bar
        sc_esc = QShortcut(QKeySequence("Esc"), self)
        sc_esc.activated.connect(self._hide_search)

        # Ctrl+Shift+S -> Manage Stashes
        sc_stash = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        sc_stash.activated.connect(self._open_stash_dialog)

        # Ctrl+P -> Push
        sc_push = QShortcut(QKeySequence("Ctrl+P"), self)
        sc_push.activated.connect(self.state.push)

        # Ctrl+Shift+P -> Pull
        sc_pull = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        sc_pull.activated.connect(self.state.pull)

        # Ctrl+Shift+F -> Fetch
        sc_fetch = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        sc_fetch.activated.connect(self.state.fetch)

        # F1 -> Shortcuts Help
        sc_help = QShortcut(QKeySequence("F1"), self)
        sc_help.activated.connect(self._show_shortcuts_dialog)

        # Ctrl+B -> Toggle Sidebar
        sc_sidebar = QShortcut(QKeySequence("Ctrl+B"), self)
        sc_sidebar.activated.connect(self._toggle_sidebar)

    # -------------------------------------------------------------------------
    # Event Handlers & Layout Lifecycle
    # -------------------------------------------------------------------------

    def _toggle_sidebar(self) -> None:
        """Toggle left activity sidebar visibility with smooth restore and expand arrow."""
        is_now_visible = not self.sidebar_branches.isVisible()
        if is_now_visible:
            self.sidebar_branches.setVisible(True)
            self.btn_expand_sidebar.setVisible(False)
            target_w = getattr(self, "_sidebar_last_width", 280) or 280
            sizes = self.main_h_splitter.sizes()
            if len(sizes) >= 2 and sizes[0] < 50:
                total = sum(sizes)
                self.main_h_splitter.setSizes([target_w, max(100, total - target_w)])
        else:
            self._sidebar_last_width = max(280, self.sidebar_branches.width())
            self.sidebar_branches.setVisible(False)
            self.btn_expand_sidebar.setVisible(True)
            self._update_expand_sidebar_button_pos()

    def _on_main_splitter_moved(self, pos: int, index: int) -> None:
        """Handle dragging the main splitter to collapse or expand the sidebar."""
        if index == 1:
            if pos <= 15:
                if self.sidebar_branches.isVisible():
                    self._sidebar_last_width = 280
                    self.sidebar_branches.setVisible(False)
                    self.btn_expand_sidebar.setVisible(True)
                    self._update_expand_sidebar_button_pos()
            else:
                self._sidebar_last_width = pos
                if not self.sidebar_branches.isVisible():
                    self.sidebar_branches.setVisible(True)
                    self.btn_expand_sidebar.setVisible(False)

    def _update_expand_sidebar_button_pos(self) -> None:
        """Keep the expand arrow button vertically centered at the left edge of the central widget."""
        if hasattr(self, "btn_expand_sidebar") and self.centralWidget():
            cw = self.centralWidget()
            btn_h = self.btn_expand_sidebar.height() or 56
            y = max(0, (cw.height() - btn_h) // 2)
            self.btn_expand_sidebar.move(0, y)
            self.btn_expand_sidebar.raise_()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._update_expand_sidebar_button_pos()
        if hasattr(self, "loading_overlay") and self.loading_overlay:
            self.loading_overlay.setGeometry(0, 0, self.width(), self.height())

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self._update_expand_sidebar_button_pos()
        if hasattr(self, "loading_overlay") and self.loading_overlay:
            self.loading_overlay.setGeometry(0, 0, self.width(), self.height())

    # -------------------------------------------------------------------------
    # Central Loading Manager
    # -------------------------------------------------------------------------

    def show_loading(
        self,
        title: str = "Processing...",
        subtext: str = "Please wait while Git operation completes",
        immediate: bool = False,
    ) -> None:
        """
        Record loading operation.
        Small/normal tasks use the bottom-right corner animated badge.
        Tasks taking longer (> 600ms, e.g. large commit diffs, large repo) will activate
        the centered dimmed modal overlay.
        """
        self._loading_title = title
        self._loading_subtext = subtext
        self.lbl_loading_indicator.setVisible(True)
        self._global_spinner_timer.start()

        if immediate:
            self._loading_delay_timer.stop()
            if hasattr(self, "loading_overlay") and self.loading_overlay:
                self.loading_overlay.setGeometry(0, 0, self.width(), self.height())
                self.loading_overlay.show_loading(title, subtext)
        else:
            self._loading_delay_timer.start(600)

    def stop_loading(self) -> None:
        """Hide modal loading overlay and clear bottom-right corner indicator."""
        self._loading_delay_timer.stop()
        if hasattr(self, "loading_overlay") and self.loading_overlay:
            self.loading_overlay.hide_loading()
        self._global_spinner_timer.stop()
        self.lbl_loading_indicator.setText("")
        self.lbl_loading_indicator.setVisible(False)

    def _on_loading_delay_timeout(self) -> None:
        """Fires if an operation runs longer than 600ms, dimming app to inform user."""
        if hasattr(self, "loading_overlay") and self.loading_overlay:
            self.loading_overlay.setGeometry(0, 0, self.width(), self.height())
            self.loading_overlay.show_loading(self._loading_title, self._loading_subtext)

    def _on_loading_changed(self, is_loading: bool) -> None:
        if is_loading:
            self.lbl_loading_indicator.setVisible(True)
            self._global_spinner_timer.start()
            if not self.loading_overlay.isVisible():
                self._loading_delay_timer.start(600)
        else:
            self.stop_loading()

    def _on_global_spinner_tick(self) -> None:
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        frame = frames[self._global_spinner_idx % len(frames)]
        self._global_spinner_idx += 1
        short_action = getattr(self, "_loading_title", "Processing").replace("...", "").strip()
        self.lbl_loading_indicator.setText(f"{frame} {short_action}...")

    # -------------------------------------------------------------------------
    # Git Operation Handlers
    # -------------------------------------------------------------------------

    def _on_fetch_requested(self) -> None:
        self.show_loading(
            "Fetching from Remote...",
            "Updating remote branches, tags, and commit tracking...",
            immediate=False,
        )
        self.state.fetch()

    def _on_pull_requested(self) -> None:
        self.show_loading(
            "Pulling Latest Changes...",
            f"Fetching and merging remote changes into '{self.state.active_branch or 'current branch'}'...",
            immediate=False,
        )
        self.state.pull()

    def _on_push_requested(self) -> None:
        self.show_loading(
            "Pushing Commits...",
            f"Pushing commits on '{self.state.active_branch or 'main'}' to remote...",
            immediate=False,
        )
        self.state.push()

    def _on_checkout_requested(self, branch_name: str) -> None:
        self.show_loading(
            "Switching Branch...",
            f"Checking out '{branch_name}' and updating working files...",
            immediate=False,
        )
        self.state.checkout_branch(branch_name)

    def _on_refresh_requested(self) -> None:
        self.show_loading(
            "Refreshing Repository...",
            "Reloading commit history, status, and unstaged changes...",
            immediate=False,
        )
        self.state.refresh()

    def _stage_all_files(self) -> None:
        self.show_loading(
            "Staging Changes...",
            "Adding all unstaged modified files to the Git index...",
            immediate=False,
        )
        self.state.stage_all()

    def _unstage_all_files(self) -> None:
        self.show_loading(
            "Unstaging Changes...",
            "Removing files from the Git staging index...",
            immediate=False,
        )
        self.state.unstage_all()

    def _on_commit_submitted(self, message: str, amend: bool) -> None:
        action_name = "Amending Commit" if amend else "Creating Commit"
        self.show_loading(
            f"{action_name}...",
            f"Committing changes to '{self.state.active_branch or 'main'}'...",
            immediate=False,
        )
        self.commit_box.start_loading()
        self.lbl_status_msg.setText(f"⚡ {action_name} to '{self.state.active_branch}'...")
        self.lbl_status_msg.setStyleSheet(f"color: {Theme.ACCENT};")
        self.state.commit(message, amend=amend)

    def _prompt_open_repository(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Open Git Repository",
            os.path.expanduser("~"),
        )
        if path:
            self.show_loading(
                "Opening Repository...",
                f"Scanning Git history and repository tree at '{os.path.basename(path)}'...",
                immediate=False,
            )
            self.state.open_repository(path)

    def _on_repo_opened(self, repo_path: str) -> None:
        self.stop_loading()
        base_name = os.path.basename(repo_path)
        self.toolbar.set_repo(repo_path)
        self.sidebar_branches.set_repo_name(base_name)
        self.setWindowTitle(f"Strand - {base_name}")
        self._show_success(f"Opened repository {base_name}")

    def _on_repo_closed(self) -> None:
        self.stop_loading()
        self.toolbar.set_repo("")
        self.sidebar_branches.set_repo_name("No repository")
        self.setWindowTitle("Strand")
        self.sidebar_branches.set_branches({"local": [], "remote": []}, "")
        self.graph_view.set_commits([])
        self.diff_viewer.set_diff("", False, [])
        self.diff_stack.setCurrentWidget(self.diff_viewer)
        self.conflict_resolver.set_conflicted_file("", [])
        self._clear_search()
        self.status_tree.set_changes([], [])
        self.commit_box.clear()

    def _on_branch_changed(self, active_branch: str) -> None:
        self.sidebar_branches.set_active_branch(active_branch)
        self.commit_box.set_branch(active_branch)
        self.toolbar.set_branches(self.state.branches, active_branch)

    def _on_branches_updated(self, branches: Dict[str, List[str]]) -> None:
        self.sidebar_branches.set_branches(branches, self.state.active_branch)
        self.toolbar.set_branches(branches, self.state.active_branch)

    def _on_history_updated(self, commits: List[CommitNode]) -> None:
        self.graph_view.set_commits(commits)
        self.history_section.cols_header.set_graph_width(self.graph_view._graph_area_width())

    def _on_sync_status_updated(self, ahead: int, behind: int) -> None:
        self.toolbar.set_sync_status(ahead, behind)

    def _on_commit_graph_selected(self, commit_hash: str) -> None:
        self.show_loading(
            "Loading Commit Diffs...",
            f"Processing commit details and calculating diffs for {commit_hash[:7]}...",
            immediate=False,
        )
        self.state.select_commit(commit_hash)
        self.state.load_commit_details(commit_hash)

    def _on_commit_details_loaded(
        self,
        node: CommitNode,
        files: List[FileChange],
        hunks_by_file: Dict[str, List[Hunk]],
    ) -> None:
        self.stop_loading()
        if files:
            first_file = files[0].file_path
            hunks = hunks_by_file.get(first_file, [])
            self.diff_viewer.set_diff(first_file, is_staged=True, hunks=hunks)
        else:
            self.diff_viewer.set_diff(f"Commit {node.short_hash}", is_staged=True, hunks=[])

    def _on_diff_updated(self, file_path: str, is_staged: bool, hunks: List[Hunk]) -> None:
        self.diff_viewer.set_diff(file_path, is_staged, hunks)
        self.stop_loading()

    # -------------------------------------------------------------------------
    # Search & Filter Handlers
    # -------------------------------------------------------------------------

    def _toggle_search(self) -> None:
        if not self.search_bar.isHidden():
            self._hide_search()
        else:
            self._focus_search()

    def _focus_search(self) -> None:
        self.search_bar.setVisible(True)
        self.input_search.setFocus()
        self.input_search.selectAll()
        self.history_section.btn_graph_badge.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BG_SURFACE_ACTIVE};
                color: {Theme.ACCENT};
                border: 1px solid {Theme.ACCENT};
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
            }}
        """)

    def _hide_search(self) -> None:
        self.search_bar.setVisible(False)
        self._clear_search()
        self.history_section.btn_graph_badge.setStyleSheet(f"""
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

    def _clear_search(self) -> None:
        self.input_search.clear()
        self.lbl_search_count.setText("")
        self.graph_view.clear_filter()

    def _on_search_query_changed(self, text: str) -> None:
        query = text.strip()
        if not query:
            self.lbl_search_count.setText("")
            self.graph_view.clear_filter()
            return

        if self.chk_search_filter.isChecked():
            count = self.graph_view.filter_commits(query)
            self.lbl_search_count.setText(f"{count} match{'es' if count != 1 else ''}")
        else:
            matches = self.graph_view.search_highlight(query)
            count = len(matches)
            if count > 0:
                self.lbl_search_count.setText(f"1/{count}")
                self.graph_view.select_row(matches[0])
            else:
                self.lbl_search_count.setText("0 matches")

    def _on_search_filter_toggled(self, checked: bool) -> None:
        query = self.input_search.text().strip()
        if checked:
            count = self.graph_view.filter_commits(query)
            if query:
                self.lbl_search_count.setText(f"{count} match{'es' if count != 1 else ''}")
        else:
            self.graph_view.clear_filter()
            if query:
                matches = self.graph_view.search_highlight(query)
                count = len(matches)
                if count > 0:
                    self.lbl_search_count.setText(f"1/{count}")
                    self.graph_view.select_row(matches[0])
                else:
                    self.lbl_search_count.setText("0 matches")

    def _on_search_next(self) -> None:
        matches = self.graph_view.matching_indices
        if not matches:
            return
        curr = self.graph_view.selected_index
        next_matches = [idx for idx in matches if curr is None or idx > curr]
        target = next_matches[0] if next_matches else matches[0]
        self.graph_view.select_row(target)
        pos = matches.index(target) + 1
        self.lbl_search_count.setText(f"{pos}/{len(matches)}")

    def _on_search_prev(self) -> None:
        matches = self.graph_view.matching_indices
        if not matches:
            return
        curr = self.graph_view.selected_index
        prev_matches = [idx for idx in matches if curr is not None and idx < curr]
        target = prev_matches[-1] if prev_matches else matches[-1]
        self.graph_view.select_row(target)
        pos = matches.index(target) + 1
        self.lbl_search_count.setText(f"{pos}/{len(matches)}")

    # -------------------------------------------------------------------------
    # Stash Management Handlers
    # -------------------------------------------------------------------------

    def _open_stash_dialog(self) -> None:
        self.stash_dialog.set_stashes(self.state.stashes)
        self.stash_dialog.exec()

    def _on_stashes_updated(self, stashes: List[Dict[str, Any]]) -> None:
        self.sidebar_branches.set_stashes(len(stashes))
        if self.stash_dialog.isVisible():
            self.stash_dialog.set_stashes(stashes)

    # -------------------------------------------------------------------------
    # Conflict Resolution Handlers
    # -------------------------------------------------------------------------

    def _on_status_file_selected(self, change: FileChange) -> None:
        self.show_loading(
            "Loading File Diff...",
            f"Calculating diff for '{change.file_path}'...",
            immediate=False,
        )
        if change.status == FileStatus.CONFLICTED:
            blocks = []
            if self.state.git_service:
                blocks = self.state.git_service.parse_conflict_blocks(change.file_path)
            self.conflict_resolver.set_conflicted_file(change.file_path, blocks)
            self.diff_stack.setCurrentWidget(self.conflict_resolver)
            self.stop_loading()
        else:
            self.diff_stack.setCurrentWidget(self.diff_viewer)
            self.state.select_file(change)

    def _on_resolve_conflict(self, file_path: str, strategy: str) -> None:
        self.state.resolve_conflict(file_path, strategy)

    def _on_conflicts_updated(self, conflicted_files: List[str]) -> None:
        if self.conflict_resolver.file_path and self.conflict_resolver.file_path not in conflicted_files:
            self.diff_stack.setCurrentWidget(self.diff_viewer)
            self.conflict_resolver.set_conflicted_file("", [])

    # -------------------------------------------------------------------------
    # History Actions (Revert, Reset, Tags) Prompts
    # -------------------------------------------------------------------------

    def _prompt_revert_commit(self, commit_hash: str) -> None:
        reply = QMessageBox.question(
            self,
            "Revert Commit",
            f"Are you sure you want to revert commit {commit_hash[:7]}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.state.revert_commit(commit_hash)

    def _prompt_reset(self, commit_hash: str, mode: str) -> None:
        reply = QMessageBox.question(
            f"Reset ({mode.title()})",
            f"Are you sure you want to perform a {mode.upper()} reset to {commit_hash[:7]}?\n"
            f"{'WARNING: Any uncommitted changes will be permanently discarded!' if mode == 'hard' else ''}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.state.reset(commit_hash, mode)

    def _prompt_create_tag(self, commit_hash: str) -> None:
        tag_name, ok = QInputDialog.getText(
            self,
            "Create Tag",
            f"Tag name for commit {commit_hash[:7]}:",
        )
        if ok and tag_name.strip():
            self.state.create_tag(tag_name.strip(), commit_hash)

    def _prompt_create_tag_general(self) -> None:
        head_commit = self.graph_view.get_selected_commit()
        commit_hash = head_commit.hash if head_commit else "HEAD"
        self._prompt_create_tag(commit_hash)

    def _on_tag_selected(self, tag_name: str) -> None:
        # Search or highlight tag
        self.graph_view.filter_commits(tag_name)

    def _open_terminal(self) -> None:
        cwd = self.state.current_repo_path or os.path.expanduser("~")
        if platform.system() == "Windows":
            cmd = f'start powershell.exe -NoExit -Command "Set-Location \'{cwd}\'"'
            subprocess.Popen(cmd, shell=True)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-a", "Terminal", cwd])
        else:
            terminals = [
                os.environ.get("TERMINAL"),
                "konsole",
                "gnome-terminal",
                "alacritty",
                "kitty",
                "xfce4-terminal",
                "x-terminal-emulator",
                "xterm",
            ]
            term_bin = next((t for t in terminals if t and shutil.which(t)), None)
            if term_bin:
                try:
                    subprocess.Popen([term_bin], cwd=cwd)
                except Exception as ex:
                    self._show_error(f"Failed to open terminal: {ex}")
            else:
                self._show_error("No supported terminal emulator found.")

    def _show_error(self, message: str) -> None:
        self.stop_loading()
        self.commit_box.stop_loading_error(message)
        self.lbl_status_msg.setText(f"✕ Error: {message}")
        self.lbl_status_msg.setStyleSheet(f"color: {Theme.COLOR_DELETED};")

    def _show_success(self, message: str) -> None:
        self.stop_loading()
        if "Committed" in message:
            short_hash = message.split()[-1] if len(message.split()) > 1 else ""
            self.commit_box.stop_loading_success(short_hash)
        self.lbl_status_msg.setText(f"✓ {message}")
        self.lbl_status_msg.setStyleSheet(f"color: {Theme.COLOR_ADDED};")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and os.path.isdir(url.toLocalFile()):
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                folder = url.toLocalFile()
                if os.path.isdir(folder):
                    self.state.open_repository(folder)
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)

    def closeEvent(self, event) -> None:
        if hasattr(self, "state") and self.state is not None:
            self.state.close_repository()
        super().closeEvent(event)

    def _show_shortcuts_dialog(self) -> None:
        QMessageBox.information(
            self,
            "Strand Keyboard Shortcuts",
            "<h3>Keyboard Shortcuts</h3>"
            "<ul>"
            "<li><b>F5</b>: Refresh repository status</li>"
            "<li><b>Ctrl+O</b>: Open local repository</li>"
            "<li><b>Ctrl+F</b>: Search & filter commit graph</li>"
            "<li><b>Ctrl+Shift+S</b>: Manage saved stashes</li>"
            "<li><b>Ctrl+`</b>: Open terminal at repository root</li>"
            "<li><b>Ctrl+P</b>: Push commits to remote</li>"
            "<li><b>Ctrl+Shift+P</b>: Pull commits from remote</li>"
            "<li><b>Ctrl+Shift+F</b>: Fetch refs from remote</li>"
            "<li><b>Ctrl+Enter</b> (in Commit Box): Commit staged changes</li>"
            "<li><b>F1</b>: Show this shortcuts help</li>"
            "</ul>",
        )
