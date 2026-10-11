"""Integration tests for MainWindow assembly and end-to-end daily workflow (Phase 4)."""

from __future__ import annotations

import os
import pygit2
import pytest
from PySide6.QtCore import Qt

from core.models import FileChange, FileStatus
from services.app_state import AppState
from ui.main_window import MainWindow


@pytest.fixture
def temp_git_repo(tmp_path):
    repo_dir = str(tmp_path / "main_window_repo")
    repo = pygit2.init_repository(repo_dir)
    repo.config["core.autocrlf"] = "false"
    return repo_dir


def test_main_window_initialization(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == "Strand"
    assert window.sidebar_branches is not None
    assert window.graph_view is not None
    assert window.diff_viewer is not None
    assert window.status_tree is not None
    assert window.commit_box is not None
    assert "Push" in window.btn_push.text()
    assert "Pull" in window.btn_pull.text()


def test_main_window_open_repo_and_workflow(qtbot, temp_git_repo) -> None:
    # 1. Create a repository with an initial commit
    repo = pygit2.Repository(temp_git_repo)
    sig = pygit2.Signature("Dev", "dev@example.com")
    fpath = os.path.join(temp_git_repo, "hello.txt")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("line 1\nline 2\n")
    repo.index.add("hello.txt")
    repo.index.write()
    c1 = repo.create_commit("HEAD", sig, sig, "Initial hello commit", repo.index.write_tree(), [])

    # 2. Open repository in MainWindow
    window = MainWindow(repo_path=temp_git_repo)
    qtbot.addWidget(window)
    window.show()

    # Wait for async repo initialization
    qtbot.waitUntil(lambda: len(window.graph_view.commits) == 1, timeout=4000)
    assert window.graph_view.commits[0].summary == "Initial hello commit"
    assert window.lbl_repo_name.text() == os.path.basename(temp_git_repo)
    assert window.combo_branch.currentText() == "master"

    # 3. Modify a file on disk
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("line 1\nline 2 modified\nline 3 added\n")

    window.state.refresh()
    qtbot.waitUntil(lambda: len(window.status_tree.unstaged_changes) == 1, timeout=4000)
    assert window.status_tree.unstaged_changes[0].file_path == "hello.txt"

    # 4. Select the modified file in StatusTree -> DiffViewer loads
    window.status_tree.file_selected.emit(window.status_tree.unstaged_changes[0])
    qtbot.waitUntil(lambda: len(window.diff_viewer.hunks) == 1, timeout=4000)
    assert window.diff_viewer.lbl_file_title.text() == "hello.txt"
    assert window.diff_viewer.lbl_stage_badge.text() == "UNSTAGED"

    # 5. Stage the file via StatusTree
    window.status_tree.stage_file_requested.emit("hello.txt")
    qtbot.waitUntil(lambda: len(window.status_tree.staged_changes) == 1, timeout=4000)
    assert len(window.status_tree.unstaged_changes) == 0

    # 6. Compose and submit commit in CommitBox
    window.commit_box.input_summary.setText("feat: update hello.txt content")
    qtbot.mouseClick(window.commit_box.btn_commit, Qt.LeftButton)

    # Verify new commit appears in GraphView
    qtbot.waitUntil(lambda: len(window.graph_view.commits) == 2, timeout=4000)
    assert window.graph_view.commits[0].summary == "feat: update hello.txt content"
    assert len(window.status_tree.staged_changes) == 0


def test_main_window_branch_creation(qtbot, temp_git_repo) -> None:
    repo = pygit2.Repository(temp_git_repo)
    sig = pygit2.Signature("Dev", "dev@example.com")
    fpath = os.path.join(temp_git_repo, "base.txt")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("base\n")
    repo.index.add("base.txt")
    repo.index.write()
    repo.create_commit("HEAD", sig, sig, "Base commit", repo.index.write_tree(), [])

    window = MainWindow(repo_path=temp_git_repo)
    qtbot.addWidget(window)
    window.show()

    qtbot.waitUntil(lambda: len(window.graph_view.commits) == 1, timeout=4000)

    # Create new branch
    window.state.create_branch("feature/awesome-ui")
    qtbot.waitUntil(lambda: "feature/awesome-ui" in window.state.branches.get("local", []), timeout=4000)

    # Checkout branch
    window.state.checkout_branch("feature/awesome-ui")
    qtbot.waitUntil(lambda: window.combo_branch.currentText() == "feature/awesome-ui", timeout=4000)
    assert window.state.active_branch == "feature/awesome-ui"
