"""Unit and integration test suite for Advanced Git Features (Phase 6).
Covers: Stash Management, 3-Way Merge Conflict Resolver, Commit Graph Search & Filtering,
History Operations (Revert/Reset) & Tags.
"""

from __future__ import annotations

import os
import pygit2
import pytest
from typing import List

from core.models import CommitNode, FileChange, FileStatus, GraphConnector
from core.git_service import GitService
from services.app_state import AppState
from ui.widgets.stash_dialog import StashDialog, StashItemWidget
from ui.widgets.conflict_resolver import ConflictResolverView, ConflictBlockWidget
from ui.widgets.graph_view import GraphView
from ui.main_window import MainWindow


@pytest.fixture
def temp_repo(tmp_path):
    repo_dir = str(tmp_path / "test_repo")
    repo = pygit2.init_repository(repo_dir)
    repo.config["user.name"] = "Developer"
    repo.config["user.email"] = "dev@example.com"
    sig = pygit2.Signature("Developer", "dev@example.com")
    fpath = os.path.join(repo_dir, "initial.txt")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("Line 1\nLine 2\n")
    repo.index.add("initial.txt")
    repo.index.write()
    tree = repo.index.write_tree()
    repo.create_commit("HEAD", sig, sig, "Initial commit", tree, [])
    return repo_dir


# -----------------------------------------------------------------------------
# 1. Stash Management Tests
# -----------------------------------------------------------------------------

def test_git_service_stashes(temp_repo) -> None:
    service = GitService(temp_repo)
    assert len(service.get_stashes()) == 0

    # Modify initial.txt and add untracked file
    fpath = os.path.join(temp_repo, "initial.txt")
    with open(fpath, "a", encoding="utf-8") as f:
        f.write("Modified line\n")

    untracked = os.path.join(temp_repo, "untracked.txt")
    with open(untracked, "w", encoding="utf-8") as f:
        f.write("Untracked content\n")

    # Save stash with untracked
    ok = service.stash_save(message="WIP work", include_untracked=True)
    assert ok is not None and "Saved" in ok

    stashes = service.get_stashes()
    assert len(stashes) == 1
    assert "WIP work" in stashes[0]["message"]
    assert not os.path.exists(untracked)  # Stashed away

    # Apply stash (keeps stash in list)
    ok = service.stash_apply(0)
    assert bool(ok)
    assert os.path.exists(untracked)
    assert len(service.get_stashes()) == 1

    # Pop stash (restores and drops)
    # First clean working directory by dropping changes
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("Line 1\nLine 2\n")
    if os.path.exists(untracked):
        os.remove(untracked)

    ok = service.stash_pop(0)
    assert bool(ok)
    assert len(service.get_stashes()) == 0

    # Save and drop test
    service.stash_save(message="Temporary stash", include_untracked=True)
    assert len(service.get_stashes()) == 1
    ok = service.stash_drop(0)
    assert bool(ok)
    assert len(service.get_stashes()) == 0


def test_stash_dialog_widget(qtbot) -> None:
    dialog = StashDialog()
    qtbot.addWidget(dialog)

    fake_stashes = [
        {"index": 0, "message": "WIP: login form", "date": "2026-10-10 12:00:00", "commit_hash": "abc1234"},
        {"index": 1, "message": "WIP: navbar redesign", "date": "2026-10-10 11:00:00", "commit_hash": "def5678"},
    ]
    dialog.set_stashes(fake_stashes)
    assert "Saved Stashes (2)" in dialog.lbl_stashes_title.text()

    # Verify signals
    pop_signals = []
    apply_signals = []
    drop_signals = []
    save_signals = []

    dialog.stash_pop_requested.connect(lambda idx: pop_signals.append(idx))
    dialog.stash_apply_requested.connect(lambda idx: apply_signals.append(idx))
    dialog.stash_drop_requested.connect(lambda idx: drop_signals.append(idx))
    dialog.stash_save_requested.connect(lambda msg, u, k: save_signals.append((msg, u, k)))

    # Find first row widget
    first_row = dialog.scroll_widget.findChildren(StashItemWidget)[0]
    first_row.pop_requested.emit(0)
    assert pop_signals == [0]

    first_row.apply_requested.emit(0)
    assert apply_signals == [0]

    first_row.drop_requested.emit(0)
    assert drop_signals == [0]

    # Save button trigger
    dialog.input_msg.setText("New stash test")
    dialog.chk_untracked.setChecked(True)
    dialog.btn_stash.click()
    assert len(save_signals) == 1
    assert save_signals[0] == ("New stash test", True, False)


# -----------------------------------------------------------------------------
# 2. Merge Conflict Resolver Tests
# -----------------------------------------------------------------------------

def test_git_service_conflict_parsing_and_resolution(temp_repo) -> None:
    service = GitService(temp_repo)

    # Write a file with standard Git conflict markers
    conflict_path = os.path.join(temp_repo, "conflict.txt")
    conflict_content = (
        "Header line\n"
        "<<<<<<< HEAD\n"
        "Ours line 1\n"
        "Ours line 2\n"
        "=======\n"
        "Theirs line A\n"
        ">>>>>>> feature-branch\n"
        "Footer line\n"
    )
    with open(conflict_path, "w", encoding="utf-8") as f:
        f.write(conflict_content)

    blocks = service.parse_conflict_blocks("conflict.txt")
    assert len(blocks) == 1
    assert "Ours line 1\nOurs line 2" in blocks[0]["ours"]
    assert "Theirs line A" in blocks[0]["theirs"]
    assert blocks[0]["start_line"] == 2
    assert blocks[0]["end_line"] == 7

    # Resolve choosing "ours"
    service.resolve_conflict("conflict.txt", "ours")
    with open(conflict_path, "r", encoding="utf-8") as f:
        resolved = f.read()
    assert "Ours line 1" in resolved
    assert "Theirs line A" not in resolved
    assert "<<<<<<<" not in resolved
    assert "=======" not in resolved
    assert ">>>>>>>" not in resolved
    assert "Header line" in resolved
    assert "Footer line" in resolved

    # Re-introduce conflict and resolve choosing "theirs"
    with open(conflict_path, "w", encoding="utf-8") as f:
        f.write(conflict_content)
    service.resolve_conflict("conflict.txt", "theirs")
    with open(conflict_path, "r", encoding="utf-8") as f:
        resolved = f.read()
    assert "Theirs line A" in resolved
    assert "Ours line 1" not in resolved
    assert "<<<<<<<" not in resolved

    # Mark resolved strategy
    with open(conflict_path, "w", encoding="utf-8") as f:
        f.write("Manually fixed line\n")
    service.resolve_conflict("conflict.txt", "mark_resolved")
    changes = service.get_status()
    # Verified staged
    assert any(c.file_path == "conflict.txt" and c.is_staged for c in changes)


def test_conflict_resolver_widget(qtbot) -> None:
    view = ConflictResolverView()
    qtbot.addWidget(view)

    blocks = [
        {
            "start_line": 5,
            "end_line": 12,
            "ours": "def compute():\n    return 42\n",
            "theirs": "def compute():\n    return 100\n",
        }
    ]
    view.set_conflicted_file("calc.py", blocks)
    assert view.lbl_file.text() == "calc.py"
    assert view.blocks_layout.count() == 1

    signals = []
    view.resolve_requested.connect(lambda f, s: signals.append((f, s)))

    # Click batch buttons
    view.btn_accept_all_ours.click()
    assert len(signals) == 1
    assert signals[-1] == ("calc.py", "ours")

    view.btn_accept_all_theirs.click()
    assert len(signals) == 2
    assert signals[-1] == ("calc.py", "theirs")

    view.btn_mark_resolved.click()
    assert len(signals) == 3
    assert signals[-1] == ("calc.py", "mark_resolved")

    # Block-level widget button
    block_widget = view.findChildren(ConflictBlockWidget)[0]
    block_widget.resolved_with_block.emit("ours")
    assert len(signals) == 4
    assert signals[-1] == ("calc.py", "ours")


# -----------------------------------------------------------------------------
# 3. Commit Graph Search & Filtering Tests
# -----------------------------------------------------------------------------

def test_graph_view_search_and_filter(qtbot) -> None:
    view = GraphView()
    qtbot.addWidget(view)

    c1 = CommitNode(
        hash="1111111111111111111111111111111111111111",
        short_hash="1111111",
        summary="feat: initial user login",
        message="feat: initial user login\n\nFull description",
        author="Alice",
        email="alice@test.com",
        timestamp=1000,
        column=0,
    )
    c2 = CommitNode(
        hash="2222222222222222222222222222222222222222",
        short_hash="2222222",
        summary="fix: null pointer in auth handler",
        message="fix: null pointer in auth handler",
        author="Bob",
        email="bob@test.com",
        timestamp=2000,
        column=0,
    )
    c3 = CommitNode(
        hash="3333333333333333333333333333333333333333",
        short_hash="3333333",
        summary="docs: update installation instructions",
        message="docs: update installation instructions",
        author="Charlie",
        email="charlie@test.com",
        timestamp=3000,
        column=0,
    )
    c4 = CommitNode(
        hash="4444444444444444444444444444444444444444",
        short_hash="4444444",
        summary="fix: another bug fix in payments",
        message="fix: another bug fix in payments",
        author="Alice",
        email="alice@test.com",
        timestamp=4000,
        column=0,
    )

    commits = [c4, c3, c2, c1]
    view.set_commits(commits)
    assert len(view.commits) == 4

    # Search highlighting (does not hide rows)
    matches = view.search_highlight("fix")
    assert matches == [0, 2]  # c4 and c2 contain 'fix'
    assert len(view.commits) == 4

    # Filter mode (hides non-matching rows)
    count = view.filter_commits("Alice")
    assert count == 2
    assert len(view.commits) == 2
    assert view.commits[0].author == "Alice"
    assert view.commits[1].author == "Alice"

    # Clear filter restores full list
    view.clear_filter()
    assert len(view.commits) == 4
    assert len(view.matching_indices) == 0

    # Select row helper
    selected_hashes = []
    view.commit_selected.connect(lambda h: selected_hashes.append(h))
    view.select_row(2)
    assert view.selected_index == 2
    assert selected_hashes == [c2.hash]


# -----------------------------------------------------------------------------
# 4. History Operations (Revert/Reset) & Tags Tests
# -----------------------------------------------------------------------------

def test_git_service_tags(temp_repo) -> None:
    service = GitService(temp_repo)
    assert len(service.get_tags()) == 0

    # Create lightweight tag
    service.create_tag("v0.1.0")

    # Create annotated tag with message
    service.create_tag("v1.0.0", message="Stable release v1.0")

    tags = service.get_tags()
    assert len(tags) == 2
    tag_names = [t["name"] for t in tags]
    assert "v0.1.0" in tag_names
    assert "v1.0.0" in tag_names

    # Delete tag
    service.delete_tag("v0.1.0")
    tags = service.get_tags()
    assert len(tags) == 1
    assert tags[0]["name"] == "v1.0.0"


def test_git_service_revert_and_reset(temp_repo) -> None:
    service = GitService(temp_repo)
    repo = pygit2.Repository(temp_repo)
    sig = pygit2.Signature("Dev", "dev@example.com")

    # Create a 2nd commit that adds a file
    f2 = os.path.join(temp_repo, "feature.txt")
    with open(f2, "w", encoding="utf-8") as f:
        f.write("Feature content\n")
    repo.index.add("feature.txt")
    repo.index.write()
    c2 = repo.create_commit("HEAD", sig, sig, "Add feature", repo.index.write_tree(), [repo.head.target])

    history = service.get_commit_history()
    assert len(history) == 2

    # Revert 2nd commit
    res = service.revert_commit(str(c2))
    assert res is not None
    history = service.get_commit_history()
    assert len(history) == 3
    assert "Revert" in history[0].summary

    # Reset HEAD~1 mixed
    res = service.reset("HEAD~1", mode="mixed")
    assert res is not None
    history = service.get_commit_history()
    assert len(history) == 2


# -----------------------------------------------------------------------------
# 5. AppState Reactive Integration
# -----------------------------------------------------------------------------

def test_app_state_advanced_git_flow(qtbot, temp_repo) -> None:
    state = AppState()
    state.open_repository(temp_repo)
    qtbot.waitUntil(lambda: state.git_service is not None, timeout=4000)

    # 1. Stash flow
    fpath = os.path.join(temp_repo, "initial.txt")
    with open(fpath, "a", encoding="utf-8") as f:
        f.write("Stash flow line\n")

    stashes_received = []
    state.stashes_updated.connect(lambda s: stashes_received.append(s))

    state.stash_save(message="AppState stash test")
    qtbot.waitUntil(lambda: len(state.stashes) == 1, timeout=4000)
    assert "AppState stash test" in state.stashes[0]["message"]

    state.stash_pop(0)
    qtbot.waitUntil(lambda: len(state.stashes) == 0, timeout=4000)

    # 2. Tag flow
    tags_received = []
    state.tags_updated.connect(lambda t: tags_received.append(t))

    state.create_tag("v2.0.0", message="Release 2.0")
    qtbot.waitUntil(lambda: len(state.tags) == 1, timeout=4000)
    assert state.tags[0]["name"] == "v2.0.0"

    state.delete_tag("v2.0.0")
    qtbot.waitUntil(lambda: len(state.tags) == 0, timeout=4000)


# -----------------------------------------------------------------------------
# 6. MainWindow Phase 6 UI Integration
# -----------------------------------------------------------------------------

def test_main_window_phase6_search_and_stashes(qtbot, temp_repo) -> None:
    # Add a second commit to temp_repo
    repo = pygit2.Repository(temp_repo)
    sig = pygit2.Signature("Dev", "dev@example.com")
    f2 = os.path.join(temp_repo, "extra.txt")
    with open(f2, "w", encoding="utf-8") as f:
        f.write("Extra content\n")
    repo.index.add("extra.txt")
    repo.index.write()
    repo.create_commit("HEAD", sig, sig, "feat: implement payment gateway", repo.index.write_tree(), [repo.head.target])

    window = MainWindow(repo_path=temp_repo)
    qtbot.addWidget(window)
    window.show()

    qtbot.waitUntil(lambda: len(window.graph_view.commits) == 2, timeout=4000)

    # 1. Search Bar interaction
    window.input_search.setText("payment")
    qtbot.waitUntil(lambda: "1 match" in window.lbl_search_count.text() or "1/1" in window.lbl_search_count.text(), timeout=3000)

    # Toggle filter
    window.chk_search_filter.setChecked(True)
    assert len(window.graph_view.commits) == 1
    assert "payment" in window.graph_view.commits[0].summary

    window.chk_search_filter.setChecked(False)
    assert len(window.graph_view.commits) == 2

    # Clear search
    window._clear_search()
    assert window.input_search.text() == ""
    assert window.lbl_search_count.text() == ""

    # 2. Stash Dialog accessibility
    assert window.btn_stashes.text() == "Stashes (0)"
