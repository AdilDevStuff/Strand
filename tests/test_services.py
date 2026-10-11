"""Unit and integration test suite for Asynchronous Bridge & State Management (Phase 2)."""

from __future__ import annotations

import os
import sys
import time
import pygit2
import pytest
from PySide6.QtCore import QCoreApplication

from core.models import FileChange, FileStatus, Hunk
from services.git_worker import GitTaskRunnable, GitWorkerThread, run_async
from services.repo_watcher import RepoWatcher
from services.app_state import AppState


@pytest.fixture
def temp_git_repo(tmp_path):
    repo_dir = str(tmp_path / "service_test_repo")
    repo = pygit2.init_repository(repo_dir)
    repo.config["core.autocrlf"] = "false"
    return repo_dir


# -----------------------------------------------------------------------------
# Test GitWorker & Async Runner
# -----------------------------------------------------------------------------

def test_git_task_runnable_success(qapp, qtbot) -> None:
    def compute(a, b):
        return a + b

    runnable = GitTaskRunnable(compute, 10, 32)
    results = []
    finished = []

    runnable.signals.result.connect(lambda res: results.append(res))
    runnable.signals.finished.connect(lambda: finished.append(True))

    runnable.run()

    assert results == [42]
    assert finished == [True]


def test_git_task_runnable_error(qapp, qtbot) -> None:
    def fail_fn():
        raise ValueError("Invalid Git ref")

    runnable = GitTaskRunnable(fail_fn)
    errors = []
    finished = []

    runnable.signals.error.connect(lambda err: errors.append(err))
    runnable.signals.finished.connect(lambda: finished.append(True))

    runnable.run()

    assert len(errors) == 1
    assert "ValueError: Invalid Git ref" in errors[0]
    assert finished == [True]


def test_run_async_dispatch(qapp, qtbot) -> None:
    def worker_action():
        time.sleep(0.05)
        return "async_success"

    results = []
    runnable = run_async(worker_action, on_success=lambda r: results.append(r))
    with qtbot.waitSignal(runnable.signals.finished, timeout=2000):
        pass

    assert results == ["async_success"]


def test_git_worker_thread_stream(qapp, qtbot, tmp_path) -> None:
    cmd = [sys.executable, "-c", "import sys; print('LINE_ONE'); print('LINE_TWO')"]
    worker = GitWorkerThread(cmd=cmd, cwd=str(tmp_path))

    lines = []
    worker.line_received.connect(lambda l: lines.append(l))

    with qtbot.waitSignal(worker.finished, timeout=3000):
        worker.start()

    assert "LINE_ONE" in lines
    assert "LINE_TWO" in lines


def test_git_worker_thread_cancellation(qapp, qtbot, tmp_path) -> None:
    # Command that sleeps
    cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
    worker = GitWorkerThread(cmd=cmd, cwd=str(tmp_path))

    errors = []
    worker.error.connect(lambda e: errors.append(e))

    worker.start()
    qtbot.wait(100)
    worker.cancel()

    with qtbot.waitSignal(worker.finished, timeout=2000):
        pass

    assert any("cancelled" in err.lower() for err in errors)


# -----------------------------------------------------------------------------
# Test RepoWatcher
# -----------------------------------------------------------------------------

def test_repo_watcher_debounce(qapp, qtbot, temp_git_repo) -> None:
    watcher = RepoWatcher(temp_git_repo, debounce_ms=50)

    changed_events = []
    watcher.repository_changed.connect(lambda: changed_events.append(True))

    # Touch a file in the repo
    test_file = os.path.join(temp_git_repo, "sample.txt")
    with open(test_file, "w") as f:
        f.write("content 1\n")

    # Rapid writes within debounce window
    with open(test_file, "w") as f:
        f.write("content 2\n")

    # Wait for debounced signal
    qtbot.waitUntil(lambda: len(changed_events) > 0, timeout=2000)
    assert len(changed_events) >= 1

    watcher.unwatch()


def test_repo_watcher_pause_resume(qapp, qtbot, temp_git_repo) -> None:
    watcher = RepoWatcher(temp_git_repo, debounce_ms=50)
    changed_events = []
    watcher.repository_changed.connect(lambda: changed_events.append(True))

    watcher.pause()
    test_file = os.path.join(temp_git_repo, "paused.txt")
    with open(test_file, "w") as f:
        f.write("ignore me\n")

    # Wait to verify nothing fired while paused
    qtbot.wait(150)
    assert len(changed_events) == 0

    # Resume and test that events resume
    watcher.resume()
    watcher.unwatch()


# -----------------------------------------------------------------------------
# Test AppState Reactive Store
# -----------------------------------------------------------------------------

def test_app_state_open_and_close(qapp, qtbot, temp_git_repo) -> None:
    state = AppState()
    opened_paths = []
    state.repo_opened.connect(lambda p: opened_paths.append(p))

    state.open_repository(temp_git_repo)
    qtbot.waitUntil(lambda: len(opened_paths) == 1, timeout=3000)

    assert state.current_repo_path == os.path.abspath(temp_git_repo)
    assert state.active_branch == "master"
    assert state.git_service is not None

    # Close repo
    closed_signals = []
    state.repo_closed.connect(lambda: closed_signals.append(True))
    state.close_repository()

    assert closed_signals == [True]
    assert state.current_repo_path is None
    assert state.git_service is None


def test_app_state_stage_and_commit_flow(qapp, qtbot, temp_git_repo) -> None:
    state = AppState()
    state.open_repository(temp_git_repo)
    qtbot.waitUntil(lambda: state.git_service is not None, timeout=3000)

    # 1. Create a file
    fpath = os.path.join(temp_git_repo, "code.py")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("print('hello')\n")

    # Refresh state to pick up new file
    state.refresh()
    qtbot.waitUntil(lambda: len(state.unstaged_files) == 1, timeout=3000)
    assert state.unstaged_files[0].file_path == "code.py"

    # Select the file and verify diff is loaded
    state.select_file(state.unstaged_files[0])
    qtbot.waitUntil(lambda: len(state.active_diff) > 0, timeout=3000)
    assert len(state.active_diff) == 1
    assert state.active_diff[0].new_lines == 1

    # 2. Stage the file
    state.stage_file("code.py")
    qtbot.waitUntil(lambda: len(state.staged_files) == 1 and len(state.unstaged_files) == 0, timeout=3000)

    # 3. Commit staged changes
    history_events = []
    state.history_updated.connect(lambda hist: history_events.append(hist))

    state.commit("Add code.py")
    qtbot.waitUntil(lambda: len(state.commits) == 1, timeout=3000)
    assert state.commits[0].summary == "Add code.py"
    assert len(state.staged_files) == 0

    state.close_repository()


def test_app_state_checkout_branch(qapp, qtbot, temp_git_repo) -> None:
    state = AppState()
    state.open_repository(temp_git_repo)
    qtbot.waitUntil(lambda: state.git_service is not None, timeout=3000)

    # Make initial commit
    fpath = os.path.join(temp_git_repo, "readme.md")
    with open(fpath, "w") as f:
        f.write("readme\n")
    state.stage_file("readme.md")
    state.commit("Initial commit")
    qtbot.waitUntil(lambda: len(state.commits) == 1, timeout=3000)

    # Create new branch
    c_tip = state.git_service.repo[state.commits[0].hash]
    state.git_service.repo.create_branch("develop", c_tip)

    # Checkout new branch
    state.checkout_branch("develop")
    qtbot.waitUntil(lambda: state.active_branch == "develop", timeout=3000)
    assert state.active_branch == "develop"

    state.close_repository()


def test_app_state_unstage_and_discard(qapp, qtbot, temp_git_repo) -> None:
    state = AppState()
    state.open_repository(temp_git_repo)
    qtbot.waitUntil(lambda: state.git_service is not None, timeout=3000)

    # Base commit
    fpath = os.path.join(temp_git_repo, "data.txt")
    with open(fpath, "wb") as f:
        f.write(b"base\n")
    state.stage_file("data.txt")
    qtbot.waitUntil(lambda: len(state.staged_files) == 1, timeout=3000)
    state.commit("Base commit")
    qtbot.waitUntil(lambda: len(state.commits) == 1, timeout=3000)

    # Modify file
    with open(fpath, "wb") as f:
        f.write(b"base\nmodified\n")
    state.refresh()
    qtbot.waitUntil(lambda: len(state.unstaged_files) == 1, timeout=3000)

    # Stage file
    state.stage_file("data.txt")
    qtbot.waitUntil(lambda: len(state.staged_files) == 1, timeout=3000)

    # Unstage file
    state.unstage_file("data.txt")
    qtbot.waitUntil(lambda: len(state.unstaged_files) == 1 and len(state.staged_files) == 0, timeout=3000)

    # Select file, get hunk, discard hunk
    state.select_file(state.unstaged_files[0])
    qtbot.waitUntil(lambda: len(state.active_diff) > 0, timeout=3000)
    hunk = state.active_diff[0]

    state.discard_hunk(hunk)
    qtbot.waitUntil(lambda: len(state.unstaged_files) == 0, timeout=3000)

    with open(fpath, "rb") as f:
        content = f.read()
    assert b"modified" not in content

    state.close_repository()


def test_app_state_select_commit(qapp, qtbot, temp_git_repo) -> None:
    state = AppState()
    state.open_repository(temp_git_repo)
    qtbot.waitUntil(lambda: state.git_service is not None, timeout=3000)

    fpath = os.path.join(temp_git_repo, "c.txt")
    with open(fpath, "w") as f:
        f.write("commit test\n")
    state.stage_file("c.txt")
    qtbot.waitUntil(lambda: len(state.staged_files) == 1, timeout=3000)
    state.commit("Commit test message")
    qtbot.waitUntil(lambda: len(state.commits) == 1, timeout=3000)

    # Select by hash
    state.select_commit(state.commits[0].hash)
    assert state.selected_commit is not None
    assert state.selected_commit.hash == state.commits[0].hash

    # Deselect
    state.select_commit(None)
    assert state.selected_commit is None

    state.close_repository()


def test_app_state_invalid_repo_error(qapp, qtbot, tmp_path) -> None:
    state = AppState()
    errors = []
    state.error_occurred.connect(lambda err: errors.append(err))

    non_existent = str(tmp_path / "does_not_exist")
    state.open_repository(non_existent)

    assert len(errors) == 1
    assert "does not exist" in errors[0].lower()

