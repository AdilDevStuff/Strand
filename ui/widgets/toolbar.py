"""Top navigation toolbar widget matching the sleek GitFiend dark design."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
)

from ui.theme import Theme


class Toolbar(QFrame):
    """
    Top navigation bar displaying repository pill, branch selector pill,
    sync counter badge [ ↑ ahead  ↓ behind ], and action buttons [Fetch], [Pull], [Push].
    """
    refresh_requested = Signal()
    checkout_requested = Signal(str)
    new_branch_requested = Signal(str)
    fetch_requested = Signal()
    pull_requested = Signal()
    push_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_branch: str = ""
        self.branches: Dict[str, List[str]] = {"local": [], "remote": []}
        self.ahead_count: int = 0
        self.behind_count: int = 0

        self.setFixedHeight(46)
        self.setStyleSheet(f"""
            Toolbar {{
                background-color: {Theme.BG_PRIMARY};
                border-bottom: 1px solid {Theme.BORDER_SUBTLE};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(10)

        # 1. Branch Switcher Pill Button: [⑂ Branch ⌵]
        self.btn_branch = QToolButton(self)
        self.btn_branch.setPopupMode(QToolButton.InstantPopup)
        self.btn_branch.setCursor(Qt.PointingHandCursor)
        self.btn_branch.setText("⑂  Branch ⌵")
        self.btn_branch.setStyleSheet(f"""
            QToolButton {{
                background-color: {Theme.BG_SURFACE};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: 500;
            }}
            QToolButton:hover {{
                background-color: {Theme.BG_SURFACE_HOVER};
                border-color: {Theme.ACCENT};
            }}
            QToolButton::menu-indicator {{
                image: none;
                width: 0px;
            }}
        """)
        self.branch_menu = QMenu(self.btn_branch)
        self.branch_menu.setStyleSheet(f"""
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
        self.btn_branch.setMenu(self.branch_menu)
        layout.addWidget(self.btn_branch)

        layout.addStretch()

        # 3. Sync Status Badge Pill: [ ↑ 2  ↓ 1 ]
        self.lbl_sync_badge = QLabel("↑ 0  ↓ 0", self)
        self.lbl_sync_badge.setAlignment(Qt.AlignCenter)
        self.lbl_sync_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {Theme.COLOR_ADDED_BG};
                color: {Theme.COLOR_ADDED};
                border: 1px solid #134e34;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
        """)
        layout.addWidget(self.lbl_sync_badge)

        # 4. Action Buttons: [↻ Refresh], [↓ Fetch], [⇊ Pull], [↑ Push]
        self.btn_refresh = QPushButton("↻ Refresh", self)
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setStyleSheet(self._button_style())
        self.btn_refresh.clicked.connect(self.refresh_requested)
        layout.addWidget(self.btn_refresh)

        self.btn_fetch = QPushButton("↓ Fetch", self)
        self.btn_fetch.setCursor(Qt.PointingHandCursor)
        self.btn_fetch.setStyleSheet(self._button_style())
        self.btn_fetch.clicked.connect(self.fetch_requested)
        layout.addWidget(self.btn_fetch)

        self.btn_pull = QPushButton("⇊ Pull", self)
        self.btn_pull.setCursor(Qt.PointingHandCursor)
        self.btn_pull.setStyleSheet(self._button_style())
        self.btn_pull.clicked.connect(self.pull_requested)
        layout.addWidget(self.btn_pull)

        self.btn_push = QPushButton("↑ Push", self)
        self.btn_push.setCursor(Qt.PointingHandCursor)
        self.btn_push.setStyleSheet(self._button_style())
        self.btn_push.clicked.connect(self.push_requested)
        layout.addWidget(self.btn_push)

    def _button_style(self) -> str:
        return f"""
            QPushButton {{
                background-color: {Theme.BG_SURFACE};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_DEFAULT};
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {Theme.BG_SURFACE_HOVER};
                border-color: {Theme.TEXT_MUTED};
            }}
            QPushButton:pressed {{
                background-color: {Theme.BG_SURFACE_ACTIVE};
            }}
        """

    def set_current_branch(self, branch: str) -> None:
        """Set current active branch."""
        self.current_branch = branch
        display_name = branch or "Branch"
        self.btn_branch.setText(f"⑂  {display_name} ⌵")

    @property
    def lbl_ahead_behind(self):
        return self.lbl_sync_badge

    def set_branches(self, branches: Dict[str, List[str]], current_branch: str = "") -> None:
        """Populate branch switcher menu and set active branch label."""
        if not current_branch:
            current_branch = self.current_branch
        self.branches = branches
        self.current_branch = current_branch
        display_name = current_branch or "Branch"
        self.btn_branch.setText(f"⑂  {display_name} ⌵")

        self.branch_menu.clear()
        local_branches = branches.get("local", [])
        if local_branches:
            for b in local_branches:
                action = self.branch_menu.addAction(f"⑂ {b}")
                if b == current_branch:
                    action.setText(f"● {b}")
                action.triggered.connect(lambda checked=False, target=b: self.checkout_requested.emit(target))

        remote_branches = branches.get("remote", [])
        if remote_branches:
            self.branch_menu.addSeparator()
            for rb in remote_branches:
                action = self.branch_menu.addAction(f"☁ {rb}")
                action.triggered.connect(lambda checked=False, target=rb: self.checkout_requested.emit(target))

    def set_sync_status(self, ahead: int, behind: int) -> None:
        """Update the [ ↑ ahead  ↓ behind ] badge."""
        self.ahead_count = ahead
        self.behind_count = behind
        self.lbl_sync_badge.setText(f"↑ {ahead}  ↓ {behind}")
        if ahead > 0 or behind > 0:
            self.lbl_sync_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.COLOR_ADDED_BG};
                    color: {Theme.COLOR_ADDED};
                    border: 1px solid #134e34;
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: 600;
                }}
            """)
        else:
            self.lbl_sync_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.BG_SURFACE};
                    color: {Theme.TEXT_MUTED};
                    border: 1px solid {Theme.BORDER_DEFAULT};
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: 500;
                }}
            """)
        self.btn_pull.setText(f"⇊ Pull{' ↓' + str(behind) if behind else ''}")
        self.btn_push.setText(f"↑ Push{' ↑' + str(ahead) if ahead else ''}")

    def set_loading(self, loading: bool) -> None:
        """Update enabled state of action buttons during background operations."""
        self.btn_refresh.setEnabled(not loading)
        self.btn_fetch.setEnabled(not loading)
        self.btn_pull.setEnabled(not loading)
        self.btn_push.setEnabled(not loading)
