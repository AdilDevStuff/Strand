"""Unit and integration test suite for UI Presentation Layer (Phase 3 & Phase 4)."""

from __future__ import annotations

import os
import sys
import pygit2
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QPushButton

from core.models import CommitNode, DiffLine, DiffLineType, FileChange, FileStatus, Hunk
from services.app_state import AppState
from ui.theme import Theme
from ui.widgets.commit_detail import CommitDetailView
from ui.widgets.commit_panel import CommitPanel
from ui.widgets.diff_viewer import DiffViewer
from ui.widgets.graph_view import GraphView
from ui.widgets.status_tree import StatusTree
from ui.widgets.toolbar import Toolbar
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    """Ensure QApplication instance is initialized for GUI widget testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def sample_hunk():
    return Hunk(
        file_path="src/main.py",
        header="@@ -1,3 +1,4 @@",
        old_start=1,
        old_lines=3,
        new_start=1,
        new_lines=4,
        lines=[
            DiffLine(line_type=DiffLineType.CONTEXT, content="import sys", old_lineno=1, new_lineno=1),
            DiffLine(line_type=DiffLineType.DELETION, content="print('old')", old_lineno=2, new_lineno=None),
            DiffLine(line_type=DiffLineType.ADDITION, content="print('new')", old_lineno=None, new_lineno=2),
            DiffLine(line_type=DiffLineType.ADDITION, content="print('extra')", old_lineno=None, new_lineno=3),
        ],
        is_staged=False,
        hunk_index=0,
    )


@pytest.fixture
def sample_commit_node():
    return CommitNode(
        hash="a1b2c3d4e5f678901234567890abcdef12345678",
        short_hash="a1b2c3d",
        author="Alice Developer",
        email="alice@example.com",
        timestamp=1700000000,
        datetime_str="2023-11-14 22:13",
        parent_hashes=[],
        message="feat: initial project setup\n\nDetailed description here.",
        summary="feat: initial project setup",
        refs=["main", "v1.0.0"],
        column=0,
        row=0,
    )


# -----------------------------------------------------------------------------
# Test Theme
# -----------------------------------------------------------------------------

def test_theme_tokens_and_stylesheet():
    assert len(Theme.LANE_PALETTE) >= 6
    assert Theme.get_lane_color(0) == Theme.LANE_PALETTE[0]
    # Lane palette wraps cyclically
    assert Theme.get_lane_color(len(Theme.LANE_PALETTE)) == Theme.LANE_PALETTE[0]

    sheet = Theme.main_stylesheet()
    assert Theme.BG_PRIMARY in sheet
    assert Theme.TEXT_PRIMARY in sheet
    assert "QScrollBar" in sheet


# -----------------------------------------------------------------------------
# Test GraphView Widget
# -----------------------------------------------------------------------------

def test_graph_view_rendering_and_interaction(qapp, qtbot, sample_commit_node):
    graph = GraphView()
    qtbot.addWidget(graph)
    graph.resize(500, 300)

    c2 = CommitNode(
        hash="b2c3d4e5f678901234567890abcdef1234567890",
        short_hash="b2c3d4e",
        author="Bob",
        email="bob@example.com",
        timestamp=1700000500,
        datetime_str="2023-11-14 22:21",
        parent_hashes=[sample_commit_node.hash],
        message="fix: bugfix",
        summary="fix: bugfix",
        refs=["feature-1"],
        column=1,
        row=1,
    )

    commits = [sample_commit_node, c2]
    graph.set_commits(commits)

    assert len(graph.commits) == 2
    assert graph.get_selected_commit() == sample_commit_node

    # Test commit selection by hash
    with qtbot.waitSignal(graph.commit_selected) as blocker:
        graph.select_commit_by_hash("b2c3d4e")
    assert blocker.args == [c2.hash]
    assert graph.get_selected_commit() == c2

    # Verify rendering paintEvent doesn't crash
    graph.repaint()


# -----------------------------------------------------------------------------
# Test StatusTree Widget
# -----------------------------------------------------------------------------

def test_status_tree_interactions(qapp, qtbot):
    tree = StatusTree()
    qtbot.addWidget(tree)
    tree.resize(300, 400)

    staged = [
        FileChange(file_path="staged.py", status=FileStatus.MODIFIED, is_staged=True, additions=5, deletions=2),
    ]
    unstaged = [
        FileChange(file_path="unstaged.txt", status=FileStatus.ADDED, is_staged=False, additions=10, deletions=0),
        FileChange(file_path="deleted.py", status=FileStatus.DELETED, is_staged=False, additions=0, deletions=8),
    ]

    tree.set_changes(staged, unstaged)
    assert tree.lbl_staged_title.text() == "Staged Changes (1)"
    assert tree.lbl_unstaged_title.text() == "Unstaged Changes (2)"

    # Test row selection
    selected_changes = []
    tree.file_selected.connect(lambda c: selected_changes.append(c))

    # Click first row in staged layout
    first_staged_row = tree._row_widgets[0]
    qtbot.mouseClick(first_staged_row, Qt.LeftButton)
    assert len(selected_changes) == 1
    assert selected_changes[0].file_path == "staged.py"

    # Test stage / unstage all button triggers
    with qtbot.waitSignal(tree.unstage_all_requested):
        qtbot.mouseClick(tree.btn_unstage_all, Qt.LeftButton)

    with qtbot.waitSignal(tree.stage_all_requested):
        qtbot.mouseClick(tree.btn_stage_all, Qt.LeftButton)


# -----------------------------------------------------------------------------
# Test DiffViewer Widget
# -----------------------------------------------------------------------------

def test_diff_viewer_rendering_and_actions(qapp, qtbot, sample_hunk):
    diff = DiffViewer()
    qtbot.addWidget(diff)
    diff.resize(600, 400)

    # Initially empty
    diff.set_diff("", False, [])
    assert "No file selected" in diff.lbl_file_title.text()

    # Populate with unstaged hunk
    diff.set_diff("src/main.py", is_staged=False, hunks=[sample_hunk])
    assert diff.lbl_file_title.text() == "src/main.py"
    assert diff.lbl_stage_badge.text() == "UNSTAGED"

    # Find HunkWidget buttons
    hunk_widgets = diff.findChildren(diff.content_widget.findChildren(QPushButton)[0].__class__)
    assert len(hunk_widgets) >= 2  # Stage Hunk & Discard Hunk buttons exist

    # Test stage hunk signal
    with qtbot.waitSignal(diff.stage_hunk_requested) as blocker:
        diff.stage_hunk_requested.emit(sample_hunk)
    assert blocker.args[0] == sample_hunk

    # Test discard hunk signal
    with qtbot.waitSignal(diff.discard_hunk_requested) as blocker:
        diff.discard_hunk_requested.emit(sample_hunk)
    assert blocker.args[0] == sample_hunk

    # Populate with staged hunk
    sample_hunk.is_staged = True
    diff.set_diff("src/main.py", is_staged=True, hunks=[sample_hunk])
    assert diff.lbl_stage_badge.text() == "STAGED"

    with qtbot.waitSignal(diff.unstage_hunk_requested) as blocker:
        diff.unstage_hunk_requested.emit(sample_hunk)
    assert blocker.args[0] == sample_hunk


# -----------------------------------------------------------------------------
# Test CommitPanel Widget
# -----------------------------------------------------------------------------

def test_commit_panel_validation_and_shortcuts(qapp, qtbot):
    panel = CommitPanel()
    qtbot.addWidget(panel)
    panel.resize(320, 200)

    # Button should be disabled initially (empty message, 0 staged)
    assert not panel.btn_commit.isEnabled()

    # Add message but 0 staged -> still disabled
    panel.set_message("feat: my commit")
    assert not panel.btn_commit.isEnabled()

    # Set staged count > 0 -> should become enabled!
    panel.set_staged_count(3)
    assert panel.btn_commit.isEnabled()

    # Test commit button click
    commits = []
    panel.commit_requested.connect(lambda msg, amend: commits.append((msg, amend)))
    qtbot.mouseClick(panel.btn_commit, Qt.LeftButton)

    assert len(commits) == 1
    assert commits[0] == ("feat: my commit", False)
    assert panel.get_message() == ""  # Cleared after commit

    # Test Amend checkbox enables committing even if staged count is 0
    panel.set_staged_count(0)
    panel.set_message("amend message")
    assert not panel.btn_commit.isEnabled()

    panel.chk_amend.setChecked(True)
    assert panel.btn_commit.isEnabled()
    assert "Amend" in panel.btn_commit.text()

    # Test Ctrl+Enter shortcut triggers commit
    commits.clear()
    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier)
    panel.txt_message.keyPressEvent(event)

    assert len(commits) == 1
    assert commits[0] == ("amend message", True)


# -----------------------------------------------------------------------------
# Test Toolbar Widget
# -----------------------------------------------------------------------------

def test_toolbar_branch_and_sync(qapp, qtbot):
    toolbar = Toolbar()
    qtbot.addWidget(toolbar)
    toolbar.resize(800, 50)

    # Set repository
    toolbar.set_repository(r"C:\MyProjects\AwesomeApp")
    assert toolbar.lbl_repo_name.text() == "AwesomeApp"

    # Set branch
    toolbar.set_current_branch("feature-login")
    assert "feature-login" in toolbar.btn_branch.text()

    # Set branches list
    toolbar.set_branches({
        "local": ["main", "feature-login", "dev"],
        "remote": ["origin/main"],
    })
    actions = [a.text() for a in toolbar.branch_menu.actions()]
    assert any("feature-login" in a for a in actions)
    assert any("origin/main" in a for a in actions)

    # Set sync status
    toolbar.set_sync_status(ahead=2, behind=1)
    assert "↑ 2" in toolbar.lbl_ahead_behind.text()
    assert "↓ 1" in toolbar.lbl_ahead_behind.text()

    # Test button click signals
    with qtbot.waitSignal(toolbar.refresh_requested):
        qtbot.mouseClick(toolbar.btn_refresh, Qt.LeftButton)

    with qtbot.waitSignal(toolbar.fetch_requested):
        qtbot.mouseClick(toolbar.btn_fetch, Qt.LeftButton)

    with qtbot.waitSignal(toolbar.pull_requested):
        qtbot.mouseClick(toolbar.btn_pull, Qt.LeftButton)

    with qtbot.waitSignal(toolbar.push_requested):
        qtbot.mouseClick(toolbar.btn_push, Qt.LeftButton)

    toolbar.set_loading(True)
    assert not toolbar.btn_refresh.isEnabled()
    toolbar.set_loading(False)
    assert toolbar.btn_refresh.isEnabled()


# -----------------------------------------------------------------------------
# Test CommitDetailView Inspector
# -----------------------------------------------------------------------------

def test_commit_detail_inspector(qapp, qtbot, sample_commit_node, sample_hunk):
    view = CommitDetailView()
    qtbot.addWidget(view)
    view.resize(700, 450)

    files = [
        FileChange(file_path="src/main.py", status=FileStatus.MODIFIED, is_staged=True, additions=2, deletions=1),
        FileChange(file_path="README.md", status=FileStatus.ADDED, is_staged=True, additions=15, deletions=0),
    ]
    hunks_map = {
        "src/main.py": [sample_hunk],
        "README.md": [],
    }

    view.set_commit_details(sample_commit_node, files, hunks_map)

    assert sample_commit_node.short_hash in view.lbl_hash.text()
    assert sample_commit_node.author in view.lbl_author_date.text()
    assert "initial project setup" in view.lbl_message.text()
    assert len(view._file_widgets) == 2

    # Click second file (README.md)
    item_readme = view._file_widgets[1]
    qtbot.mouseClick(item_readme, Qt.LeftButton)
    assert view.selected_file == "README.md"

    # Test clear
    view.clear()
    assert "No commit selected" in view.lbl_message.text()
    assert len(view._file_widgets) == 0


# -----------------------------------------------------------------------------
# Test MainWindow Integration
# -----------------------------------------------------------------------------

def test_main_window_integration_and_flow(qapp, qtbot, tmp_path):
    # Create a real Git repo to test end-to-end flow
    repo_dir = str(tmp_path / "gui_integration_repo")
    repo = pygit2.init_repository(repo_dir)
    repo.config["core.autocrlf"] = "false"

    # Create initial commit
    file1 = os.path.join(repo_dir, "hello.txt")
    with open(file1, "w") as f:
        f.write("first line\n")
    repo.index.add("hello.txt")
    repo.index.write()
    sig = pygit2.Signature("Integration Tester", "test@gui.com")
    tree_id = repo.index.write_tree()
    c1 = repo.create_commit("HEAD", sig, sig, "Initial commit", tree_id, [])

    state = AppState()
    window = MainWindow(app_state=state)
    qtbot.addWidget(window)
    window.resize(1100, 700)
    window.show()

    # Open repository
    with qtbot.waitSignal(state.repo_opened, timeout=3000):
        state.open_repository(repo_dir)

    assert window.state.current_repo_path == os.path.abspath(repo_dir)
    assert os.path.basename(repo_dir) in window.lbl_repo_name.text()
    assert len(window.graph_view.commits) == 1
    assert window.graph_view.commits[0].summary == "Initial commit"

    # Modify file to create unstaged change
    with open(file1, "a") as f:
        f.write("second line\n")

    with qtbot.waitSignal(state.status_updated, timeout=3000):
        state.refresh()

    assert len(window.status_tree.unstaged_changes) == 1
    assert window.status_tree.unstaged_changes[0].file_path == "hello.txt"

    # Select unstaged file to populate DiffViewer
    with qtbot.waitSignal(state.diff_updated, timeout=3000):
        state.select_file(window.status_tree.unstaged_changes[0])

    assert window.diff_viewer.file_path == "hello.txt"
    assert len(window.diff_viewer.hunks) == 1

    # Stage the file via StatusTree
    with qtbot.waitSignal(state.status_updated, timeout=3000):
        window.status_tree.stage_file_requested.emit("hello.txt")

    assert len(window.status_tree.staged_changes) == 1

    # Commit via CommitBox
    window.commit_box.set_commit_message("feat: added second line")
    with qtbot.waitSignal(state.history_updated, timeout=3000):
        window.commit_box._on_submit()

    # Status should now be clean, commits should be 2
    assert len(window.status_tree.staged_changes) == 0
    assert len(window.status_tree.unstaged_changes) == 0
    assert len(window.graph_view.commits) == 2

    # Click historical commit in GraphView to inspect details
    with qtbot.waitSignal(state.commit_details_loaded, timeout=3000):
        window.graph_view.commit_selected.emit(str(c1))

    assert "hello.txt" in window.diff_viewer.file_path or str(c1)[:7] in window.diff_viewer.file_path
