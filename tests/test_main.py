"""Tests for CLI entry point, argument parsing, application lifecycle, and packaging (Phase 5)."""

from __future__ import annotations

import io
import os
import sys
from unittest.mock import MagicMock, patch
import pygit2
import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from main import (
    __version__,
    create_parser,
    main,
    print_version_info,
    resolve_repository_path,
)
from services.app_state import AppState
from ui.main_window import MainWindow


def test_cli_parser_defaults():
    parser = create_parser()
    args = parser.parse_args([])
    assert args.repo_path is None
    assert args.version is False
    assert args.software_rendering is False
    assert args.log_level == "INFO"


def test_cli_parser_custom_args():
    parser = create_parser()
    args = parser.parse_args(["/path/to/my/repo", "--version", "--software-rendering", "--log-level", "DEBUG"])
    assert args.repo_path == "/path/to/my/repo"
    assert args.version is True
    assert args.software_rendering is True
    assert args.log_level == "DEBUG"


def test_print_version_info(capsys):
    print_version_info()
    captured = capsys.readouterr()
    assert "Strand" in captured.out
    assert f"v{__version__}" in captured.out
    assert "PySide6 (Qt)" in captured.out
    assert "pygit2 (libgit2)" in captured.out


def test_resolve_repository_path(tmp_path):
    repo_dir = str(tmp_path / "valid_git_repo")
    repo = pygit2.init_repository(repo_dir)

    # 1. Resolving the repo path directly
    resolved = resolve_repository_path(repo_dir)
    assert resolved == os.path.abspath(repo_dir)

    # 2. Resolving a nested directory inside the repo
    sub_dir = os.path.join(repo_dir, "nested", "deep", "folder")
    os.makedirs(sub_dir)
    resolved_nested = resolve_repository_path(sub_dir)
    assert resolved_nested == os.path.abspath(repo_dir)

    # 3. Non-existent path returns None or valid fallback
    resolved_none = resolve_repository_path(str(tmp_path / "non_existent_folder_xyz"))
    assert resolved_none is None or not os.path.exists(resolved_none)


def test_main_cli_version_flag(capsys):
    ret = main(["--version"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Strand" in captured.out


def test_main_cli_with_repo_launch(qtbot, tmp_path):
    repo_dir = str(tmp_path / "cli_launch_repo")
    repo = pygit2.init_repository(repo_dir)
    repo.config["core.autocrlf"] = "false"

    # Run main with path, ensure it runs without error (app already exists under qtbot)
    ret = main([repo_dir, "--log-level", "DEBUG"])
    assert ret == 0


def test_main_cli_without_repo_starts_on_home_screen(qtbot, monkeypatch, tmp_path):
    repo_dir = str(tmp_path / "working_directory_repo")
    pygit2.init_repository(repo_dir)
    monkeypatch.chdir(repo_dir)
    open_repository = MagicMock()
    monkeypatch.setattr(AppState, "open_repository", open_repository)

    ret = main([])

    assert ret == 0
    open_repository.assert_not_called()


def test_main_window_close_event_cleanup(qtbot, tmp_path):
    repo_dir = str(tmp_path / "close_test_repo")
    pygit2.init_repository(repo_dir)

    state = AppState()
    window = MainWindow(app_state=state)
    qtbot.addWidget(window)
    window.show()

    state.open_repository(repo_dir)
    qtbot.waitUntil(lambda: state.current_repo_path is not None, timeout=3000)

    # Close window and verify repository is closed cleanly
    window.close()
    assert state.current_repo_path is None
    assert state.git_service is None


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_main_window_drag_and_drop_event(qtbot, tmp_path):
    repo_dir = str(tmp_path / "drag_drop_repo")
    pygit2.init_repository(repo_dir)

    state = AppState()
    window = MainWindow(app_state=state)
    qtbot.addWidget(window)
    window.show()

    # Simulate drag enter with folder URL
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(repo_dir)])
    drag_event = QDragEnterEvent(
        QPoint(100, 100),
        Qt.CopyAction,
        mime,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    window.dragEnterEvent(drag_event)
    assert drag_event.isAccepted()

    # Simulate drop event
    drop_event = QDropEvent(
        QPoint(100, 100),
        Qt.CopyAction,
        mime,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    window.dropEvent(drop_event)
    assert drop_event.isAccepted()

    # Verify state opened dropped repo
    qtbot.waitUntil(lambda: state.current_repo_path == os.path.abspath(repo_dir), timeout=3000)
    assert window.sidebar_branches.repository_paths == [os.path.abspath(repo_dir)]


def test_main_window_shortcuts_dialog(qtbot, monkeypatch):
    dialog_called = False

    def mock_information(*args, **kwargs):
        nonlocal dialog_called
        dialog_called = True

    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", mock_information)

    window = MainWindow()
    qtbot.addWidget(window)
    window._show_shortcuts_dialog()
    assert dialog_called is True
