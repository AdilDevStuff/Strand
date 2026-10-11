"""Unit and integration test suite for Core Git Engine & Data Models (Phase 1)."""

from __future__ import annotations

import os
import pygit2
import pytest

from core.models import (
    CommitNode,
    DiffLine,
    DiffLineType,
    FileChange,
    FileStatus,
    GraphConnector,
    Hunk,
)
from core.git_service import GitService, find_git_executable
from core.graph_builder import GraphBuilder


# -----------------------------------------------------------------------------
# Test Models
# -----------------------------------------------------------------------------

def test_file_status_short_chars() -> None:
    assert FileStatus.MODIFIED.short_char == "M"
    assert FileStatus.ADDED.short_char == "A"
    assert FileStatus.DELETED.short_char == "D"
    assert FileStatus.UNTRACKED.short_char == "U"
    assert FileStatus.RENAMED.short_char == "R"


def test_hunk_patch_generation() -> None:
    lines = [
        DiffLine(DiffLineType.CONTEXT, "line1"),
        DiffLine(DiffLineType.DELETION, "old_line"),
        DiffLine(DiffLineType.ADDITION, "new_line"),
        DiffLine(DiffLineType.CONTEXT, "line2"),
    ]
    hunk = Hunk(
        file_path="src/main.py",
        header="@@ -1,3 +1,3 @@",
        old_start=1,
        old_lines=3,
        new_start=1,
        new_lines=3,
        lines=lines,
    )

    assert hunk.additions_count == 1
    assert hunk.deletions_count == 1

    patch = hunk.to_patch(reverse=False)
    assert "--- a/src/main.py" in patch
    assert "+++ b/src/main.py" in patch
    assert "@@ -1,3 +1,3 @@" in patch
    assert " line1" in patch
    assert "-old_line" in patch
    assert "+new_line" in patch

    # Reverse patch
    rev_patch = hunk.to_patch(reverse=True)
    assert "--- a/src/main.py" in rev_patch
    assert "+++ b/src/main.py" in rev_patch
    assert "@@ -1,3 +1,3 @@" in rev_patch
    assert "+old_line" in rev_patch
    assert "-new_line" in rev_patch


# -----------------------------------------------------------------------------
# Test GitService against real temporary repository
# -----------------------------------------------------------------------------

@pytest.fixture
def temp_repo(tmp_path):
    repo_dir = str(tmp_path / "test_repo")
    pygit2.init_repository(repo_dir)
    return repo_dir


def test_git_service_empty_repo_status_and_commit(temp_repo) -> None:
    service = GitService(temp_repo)
    assert service.is_empty
    assert service.get_current_branch() == "master"
    assert len(service.get_status()) == 0

    # Create a new untracked file
    test_file = os.path.join(temp_repo, "hello.txt")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("Hello World\nLine 2\n")

    changes = service.get_status()
    assert len(changes) == 1
    assert changes[0].file_path == "hello.txt"
    assert changes[0].status == FileStatus.UNTRACKED
    assert not changes[0].is_staged

    # Get diff of untracked file
    diff_hunks = service.get_diff("hello.txt", staged=False)
    assert len(diff_hunks) == 1
    assert diff_hunks[0].new_lines == 2
    assert diff_hunks[0].lines[0].line_type == DiffLineType.ADDITION

    # Stage the file
    service.stage_file("hello.txt")
    changes = service.get_status()
    assert len(changes) == 1
    assert changes[0].file_path == "hello.txt"
    assert changes[0].status == FileStatus.ADDED
    assert changes[0].is_staged

    # Commit the staged file
    commit_hash = service.commit("Initial test commit")
    assert len(commit_hash) == 40
    assert not service.is_empty
    assert len(service.get_status()) == 0


def test_git_service_stage_and_unstage_file(temp_repo) -> None:
    service = GitService(temp_repo)
    file_path = os.path.join(temp_repo, "app.py")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("print('v1')\n")

    service.stage_file("app.py")
    service.commit("Initial commit")

    # Modify file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("print('v2')\n")

    changes = service.get_status()
    assert len(changes) == 1
    assert changes[0].status == FileStatus.MODIFIED
    assert not changes[0].is_staged

    # Stage modification
    service.stage_file("app.py")
    changes = service.get_status()
    assert len(changes) == 1
    assert changes[0].status == FileStatus.MODIFIED
    assert changes[0].is_staged

    # Unstage modification
    service.unstage_file("app.py")
    changes = service.get_status()
    assert len(changes) == 1
    assert changes[0].status == FileStatus.MODIFIED
    assert not changes[0].is_staged


def test_git_service_hunk_operations(temp_repo) -> None:
    service = GitService(temp_repo)
    file_path = os.path.join(temp_repo, "lines.txt")
    with open(file_path, "wb") as f:
        f.write(b"line 1\nline 2\nline 3\n")

    service.stage_file("lines.txt")
    service.commit("Base commit")

    # Create modified line
    with open(file_path, "wb") as f:
        f.write(b"line 1\nline 2 MODIFIED\nline 3\n")

    diff_hunks = service.get_diff("lines.txt", staged=False)
    assert len(diff_hunks) == 1
    hunk = diff_hunks[0]
    assert hunk.old_start == 1
    assert hunk.new_start == 1

    # Stage this single hunk
    service.stage_hunk(hunk)

    staged_changes = [c for c in service.get_status() if c.is_staged]
    assert len(staged_changes) == 1
    assert staged_changes[0].file_path == "lines.txt"

    # Unstage this hunk
    service.unstage_hunk(hunk)
    staged_changes = [c for c in service.get_status() if c.is_staged]
    assert len(staged_changes) == 0

    # Discard hunk in working directory
    service.discard_hunk(hunk)
    with open(file_path, "rb") as f:
        content = f.read()
    assert b"line 2 MODIFIED" not in content
    assert "line 2" in content.decode("utf-8")


def test_git_service_branches_and_checkout(temp_repo) -> None:
    service = GitService(temp_repo)
    file_path = os.path.join(temp_repo, "file.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("content\n")
    service.stage_file("file.txt")
    c1 = service.commit("First commit")

    # Create branch
    branch_ref = service.repo.create_branch("feature-login", service.repo[c1])
    branches = service.get_branches()
    assert "feature-login" in branches["local"]
    assert "master" in branches["local"]

    # Checkout branch
    service.checkout("feature-login")
    assert service.get_current_branch() == "feature-login"

    # Checkout back
    service.checkout("master")
    assert service.get_current_branch() == "master"


def test_git_service_commit_history(temp_repo) -> None:
    service = GitService(temp_repo)
    file_path = os.path.join(temp_repo, "file.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("1\n")
    service.stage_file("file.txt")
    c1 = service.commit("Commit one")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("2\n")
    service.stage_file("file.txt")
    c2 = service.commit("Commit two")

    history = service.get_commit_history()
    assert len(history) == 2
    assert history[0].hash == c2
    assert history[0].summary == "Commit two"
    assert history[1].hash == c1
    assert history[1].summary == "Commit one"


# -----------------------------------------------------------------------------
# Test GraphBuilder with topological sorting and merge lanes
# -----------------------------------------------------------------------------

def test_graph_builder_linear_history() -> None:
    c1 = CommitNode(
        hash="1111111",
        short_hash="1111111",
        author="Dev",
        email="dev@example.com",
        timestamp=100,
        datetime_str="2026-01-01 10:00",
        parent_hashes=[],
        message="Initial",
        summary="Initial",
    )
    c2 = CommitNode(
        hash="2222222",
        short_hash="2222222",
        author="Dev",
        email="dev@example.com",
        timestamp=200,
        datetime_str="2026-01-01 11:00",
        parent_hashes=["1111111"],
        message="Update",
        summary="Update",
    )

    builder = GraphBuilder()
    graph = builder.build([c2, c1])
    assert len(graph) == 2
    assert graph[0].hash == "2222222"
    assert graph[0].row == 0
    assert graph[0].column == 0
    assert len(graph[0].connectors) == 1
    assert graph[0].connectors[0].to_row == 1
    assert graph[0].connectors[0].to_column == 0
    assert not graph[0].connectors[0].is_merge

    assert graph[1].hash == "1111111"
    assert graph[1].row == 1
    assert graph[1].column == 0
    assert len(graph[1].connectors) == 0


def test_graph_builder_branch_and_merge() -> None:
    r"""
    DAG structure:
    c_merge (parents: c_main, c_feat)
       |          \
     c_main      c_feat
       \          /
         c_root
    """
    c_root = CommitNode(
        hash="root",
        short_hash="root",
        author="Dev",
        email="dev@example.com",
        timestamp=100,
        datetime_str="2026-01-01 10:00",
        parent_hashes=[],
        message="Root",
        summary="Root",
    )
    c_main = CommitNode(
        hash="main1",
        short_hash="main1",
        author="Dev",
        email="dev@example.com",
        timestamp=200,
        datetime_str="2026-01-01 11:00",
        parent_hashes=["root"],
        message="Main work",
        summary="Main work",
    )
    c_feat = CommitNode(
        hash="feat1",
        short_hash="feat1",
        author="Dev",
        email="dev@example.com",
        timestamp=300,
        datetime_str="2026-01-01 12:00",
        parent_hashes=["root"],
        message="Feature work",
        summary="Feature work",
    )
    c_merge = CommitNode(
        hash="merge",
        short_hash="merge",
        author="Dev",
        email="dev@example.com",
        timestamp=400,
        datetime_str="2026-01-01 13:00",
        parent_hashes=["main1", "feat1"],
        message="Merge branch feature",
        summary="Merge branch feature",
    )

    builder = GraphBuilder()
    graph = builder.build([c_root, c_feat, c_main, c_merge])

    assert len(graph) == 4
    # Topological order puts merge at row 0
    assert graph[0].hash == "merge"
    assert graph[0].row == 0
    assert graph[0].column == 0

    # Merge node should have 2 connectors
    assert len(graph[0].connectors) == 2
    # First parent connection
    assert not graph[0].connectors[0].is_merge
    # Second parent merge connection
    assert graph[0].connectors[1].is_merge
    assert graph[0].connectors[1].to_column > 0

    # Ensure root is the last commit at row 3
    assert graph[3].hash == "root"
    assert graph[3].row == 3


def test_git_service_simultaneous_staged_and_unstaged(temp_repo) -> None:
    service = GitService(temp_repo)
    file_path = os.path.join(temp_repo, "dual.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("base content\n")
    service.stage_file("dual.txt")
    service.commit("Base commit")

    # Change 1: stage it
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("base content\nstaged addition\n")
    service.stage_file("dual.txt")

    # Change 2: unstaged modification in working tree
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("base content\nstaged addition\nunstaged addition\n")

    changes = service.get_status()
    # Expect 2 changes: one staged, one unstaged
    assert len(changes) == 2
    staged = [c for c in changes if c.is_staged]
    unstaged = [c for c in changes if not c.is_staged]
    assert len(staged) == 1
    assert staged[0].status == FileStatus.MODIFIED
    assert len(unstaged) == 1
    assert unstaged[0].status == FileStatus.MODIFIED


def test_git_service_amend_commit(temp_repo) -> None:
    service = GitService(temp_repo)
    file_path = os.path.join(temp_repo, "file.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("v1\n")
    service.stage_file("file.txt")
    c1 = service.commit("Commit initial")

    # Amend with new message and file update
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("v2\n")
    service.stage_file("file.txt")
    c_amended = service.commit("Commit initial amended", amend=True)

    history = service.get_commit_history()
    assert len(history) == 1
    assert history[0].hash == c_amended
    assert history[0].summary == "Commit initial amended"


def test_git_service_deleted_file(temp_repo) -> None:
    service = GitService(temp_repo)
    file_path = os.path.join(temp_repo, "to_delete.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("content\n")
    service.stage_file("to_delete.txt")
    service.commit("Add file to delete")

    # Delete from disk
    os.remove(file_path)
    changes = service.get_status()
    assert len(changes) == 1
    assert changes[0].status == FileStatus.DELETED
    assert not changes[0].is_staged

    # Stage deletion
    service.stage_file("to_delete.txt")
    changes = service.get_status()
    assert len(changes) == 1
    assert changes[0].status == FileStatus.DELETED
    assert changes[0].is_staged

    # Unstage deletion
    service.unstage_file("to_delete.txt")
    changes = service.get_status()
    assert len(changes) == 1
    assert not changes[0].is_staged


def test_graph_builder_complex_lanes_recycling() -> None:
    """
    Test column lane recycling when multiple branches terminate.
    """
    c0 = CommitNode("c0", "c0", "Dev", "d@t", 10, "2026-01-01", [], "Root", "Root")
    c1 = CommitNode("c1", "c1", "Dev", "d@t", 20, "2026-01-01", ["c0"], "Branch 1", "Branch 1")
    c2 = CommitNode("c2", "c2", "Dev", "d@t", 30, "2026-01-01", ["c0"], "Branch 2", "Branch 2")
    c3 = CommitNode("c3", "c3", "Dev", "d@t", 40, "2026-01-01", ["c0"], "Branch 3", "Branch 3")

    builder = GraphBuilder()
    graph = builder.build([c0, c1, c2, c3])
    assert len(graph) == 4
    # All branches connect back to c0
    root_node = next(n for n in graph if n.hash == "c0")
    assert root_node.row == 3
    assert root_node.column == 0

