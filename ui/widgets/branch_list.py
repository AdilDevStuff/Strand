"""Left navigation sidebar matching the GitFiend dark design with branches, remotes, stashes, and tags."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Theme
from ui.widgets.commit_box import CommitBox


class BranchListWidget(QWidget):
    """
    Left activity sidebar matching the attached UI design:
    - macOS traffic lights [🔴 🟡 🟢] + sidebar collapse toggle [◧]
    - PROJECT: <name> ⌵
    - Branches list
    - Remote branches (with active branch pill highlight)
    - Stashes
    - Tags (with [+] create button)
    """
    branch_checkout_requested = Signal(str)
    branch_create_requested = Signal(str)
    stash_manage_requested = Signal()
    tag_create_requested = Signal()
    tag_selected = Signal(str)
    open_repo_requested = Signal()
    repository_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.repo_name: str = "web-app"
        self.repository_paths: List[str] = []
        self.active_branch: str = ""
        self.branches_data: Dict[str, List[str]] = {"local": [], "remote": []}
        self.tags_data: List[Any] = []
        self.stashes_count: int = 0

        self.setStyleSheet(f"""
            BranchListWidget {{
                background-color: {Theme.BG_SIDEBAR};
                border-right: 1px solid {Theme.BORDER_SUBTLE};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        # 1. Top Window Controls Bar: [🔴 🟡 🟢] and [◧]
        ctrl_bar = QWidget(self)
        ctrl_layout = QHBoxLayout(ctrl_bar)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        for color_hex in (Theme.COLOR_TRAFFIC_RED, Theme.COLOR_TRAFFIC_YELLOW, Theme.COLOR_TRAFFIC_GREEN):
            dot = QLabel(ctrl_bar)
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"""
                QLabel {{
                    background-color: {color_hex};
                    border-radius: 6px;
                }}
            """)
            ctrl_layout.addWidget(dot)

        ctrl_layout.addStretch()

        self.btn_toggle_sidebar = QPushButton("◧", ctrl_bar)
        self.btn_toggle_sidebar.setFixedSize(22, 22)
        self.btn_toggle_sidebar.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_sidebar.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Theme.TEXT_MUTED};
                border: none;
                font-size: 13px;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {Theme.TEXT_PRIMARY};
            }}
        """)
        ctrl_layout.addWidget(self.btn_toggle_sidebar)
        layout.addWidget(ctrl_bar)

        # 2. PROJECT: <name> ⌵ Header
        proj_bar = QWidget(self)
        proj_layout = QHBoxLayout(proj_bar)
        proj_layout.setContentsMargins(0, 4, 0, 4)
        proj_layout.setSpacing(6)

        self.lbl_project_prefix = QLabel("PROJECT:", proj_bar)
        self.lbl_project_prefix.setStyleSheet(f"""
            color: {Theme.TEXT_MUTED};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
        """)
        proj_layout.addWidget(self.lbl_project_prefix)

        self.btn_project = QToolButton(proj_bar)
        self.btn_project.setText(self.repo_name)
        self.btn_project.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_project.setPopupMode(QToolButton.InstantPopup)
        self.btn_project.setCursor(Qt.PointingHandCursor)
        self.btn_project.setStyleSheet(f"""
            QToolButton {{
                color: {Theme.TEXT_PRIMARY};
                font-size: 12px;
                font-weight: 600;
                border: none;
                padding: 0;
            }}
            QToolButton:hover {{ color: {Theme.ACCENT}; }}
        """)
        self.project_menu = QMenu(self.btn_project)
        self.btn_project.setMenu(self.project_menu)
        self.lbl_project_name = self.btn_project
        self.lbl_repo_name = self.lbl_project_name
        proj_layout.addWidget(self.btn_project)

        proj_layout.addStretch()

        lbl_proj_chevron = QLabel("⌵", proj_bar)
        lbl_proj_chevron.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        proj_layout.addWidget(lbl_proj_chevron)

        layout.addWidget(proj_bar)

        # 3. Tree Widget with Custom Styled Items
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: transparent;
                color: {Theme.TEXT_PRIMARY};
                border: none;
                font-size: 12px;
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 5px 8px;
                border-radius: 6px;
                margin-bottom: 2px;
            }}
            QTreeWidget::item:hover {{
                background-color: {Theme.BG_SURFACE_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: {Theme.BG_SURFACE_ACTIVE};
                color: #ffffff;
            }}
        """)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        layout.addWidget(self.tree, 1)

        # 4. Docked Commit Box in sidebar bottom
        self.commit_box = CommitBox(self)
        layout.addWidget(self.commit_box)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def set_repo_name(self, name: str) -> None:
        """Update displayed project name."""
        self.repo_name = name or "No repository"
        self.btn_project.setText(self.repo_name)

    def set_repositories(self, paths: List[str], active_path: str = "") -> None:
        """Populate the project dropdown with repositories opened in this window."""
        self.repository_paths = list(dict.fromkeys(paths))
        self.project_menu.clear()
        unique_paths = self.repository_paths
        active_normalized = os.path.abspath(active_path.replace("\\", "/")) if active_path else ""
        for path in unique_paths:
            display_path = os.path.abspath(path.replace("\\", "/"))
            action = self.project_menu.addAction(os.path.basename(display_path))
            action.setToolTip(path)
            action.setCheckable(True)
            action.setChecked(display_path == active_normalized)
            action.triggered.connect(
                lambda checked=False, selected=path: self.repository_selected.emit(selected)
            )
        if unique_paths:
            self.project_menu.addSeparator()
        open_action = self.project_menu.addAction("Open Repository…")
        open_action.triggered.connect(self.open_repo_requested)

    def set_branches(self, branches: Dict[str, List[str]], active_branch: str) -> None:
        """Update local and remote branches."""
        self.branches_data = branches
        self.active_branch = active_branch
        self._rebuild_tree()

    def set_active_branch(self, active_branch: str) -> None:
        """Update active branch."""
        self.active_branch = active_branch
        self._rebuild_tree()

    def set_tags(self, tags: List[Any]) -> None:
        """Update list of tags."""
        self.tags_data = tags
        self._rebuild_tree()

    def set_stashes(self, count: int) -> None:
        """Update stashes count."""
        self.stashes_count = count
        self._rebuild_tree()

    # -------------------------------------------------------------------------
    # Tree Construction
    # -------------------------------------------------------------------------

    def _rebuild_tree(self) -> None:
        self.tree.clear()

        # Section: Branches
        local_branches = self.branches_data.get("local", [])
        sec_branches = QTreeWidgetItem(self.tree)
        sec_branches.setText(0, "Branches")
        sec_branches.setFlags(Qt.ItemIsEnabled)
        sec_branches.setFont(0, self._section_font())
        sec_branches.setForeground(0, QColor(Theme.TEXT_MUTED))
        sec_branches.setExpanded(True)

        for b in local_branches:
            item = QTreeWidgetItem(sec_branches)
            is_active = (b == self.active_branch)
            prefix = "● " if is_active else "⑂ "
            item.setText(0, f"{prefix}{b}")
            item.setData(0, Qt.UserRole, ("branch", b))
            if is_active:
                item.setForeground(0, QColor(Theme.COLOR_ADDED))
                item.setBackground(0, QColor("#142721"))
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            else:
                item.setForeground(0, QColor(Theme.TEXT_PRIMARY))

        # Section: Remote branches ⌵
        remote_branches = self.branches_data.get("remote", [])
        sec_remote = QTreeWidgetItem(self.tree)
        sec_remote.setText(0, "Remote branches  ⌵")
        sec_remote.setFlags(Qt.ItemIsEnabled)
        sec_remote.setFont(0, self._section_font())
        sec_remote.setForeground(0, QColor(Theme.TEXT_MUTED))
        sec_remote.setExpanded(True)

        for rb in remote_branches:
            item = QTreeWidgetItem(sec_remote)
            # Remove remote name prefix like 'origin/' for display if desired or keep
            clean_name = rb.split("/", 1)[-1] if "/" in rb else rb
            is_active = (clean_name == self.active_branch)
            prefix = "● " if is_active else "   "
            item.setText(0, f"{prefix}{clean_name}")
            item.setData(0, Qt.UserRole, ("remote", rb))
            if is_active:
                item.setForeground(0, QColor(Theme.COLOR_ADDED))
                item.setBackground(0, QColor("#142721"))
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            else:
                item.setForeground(0, QColor(Theme.TEXT_SECONDARY))

        # Section: Stashes
        sec_stashes = QTreeWidgetItem(self.tree)
        stash_label = f"Stashes ({self.stashes_count})" if self.stashes_count else "Stashes"
        sec_stashes.setText(0, stash_label)
        sec_stashes.setData(0, Qt.UserRole, ("action", "stashes"))
        sec_stashes.setFont(0, self._section_font())
        sec_stashes.setForeground(0, QColor(Theme.TEXT_MUTED))

        # Section: Tags with [+]
        sec_tags = QTreeWidgetItem(self.tree)
        sec_tags.setText(0, "Tags               +")
        sec_tags.setData(0, Qt.UserRole, ("action", "new_tag"))
        sec_tags.setFont(0, self._section_font())
        sec_tags.setForeground(0, QColor(Theme.TEXT_MUTED))
        sec_tags.setExpanded(True)

        if self.tags_data:
            for t in self.tags_data:
                tag_name = t.get("name") if isinstance(t, dict) else str(t)
                item = QTreeWidgetItem(sec_tags)
                item.setText(0, f"🏷 {tag_name}")
                item.setData(0, Qt.UserRole, ("tag", tag_name))
                item.setForeground(0, QColor(Theme.TEXT_SECONDARY))

    def _section_font(self) -> QFont:
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        return font

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, val = data
        if kind == "action" and val == "stashes":
            self.stash_manage_requested.emit()
        elif kind == "action" and val == "new_tag":
            self.tag_create_requested.emit()
        elif kind == "tag":
            self.tag_selected.emit(val)

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, val = data
        if kind in ("branch", "remote"):
            self.branch_checkout_requested.emit(val)
