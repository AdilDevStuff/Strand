"""Unit and GUI component test suite for Custom UI Components (Phase 3)."""

from __future__ import annotations

import sys
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QPushButton

from core.models import CommitNode, DiffLine, DiffLineType, FileChange, FileStatus, GraphConnector, Hunk
from ui.widgets.graph_view import GraphView
from ui.widgets.diff_viewer import DiffViewer, HunkWidget
from ui.widgets.status_tree import StatusTree, FileRowWidget
from ui.widgets.commit_box import CommitBox


# -----------------------------------------------------------------------------
# Test GraphView
# -----------------------------------------------------------------------------

def test_graph_view_set_commits_and_selection(qapp, qtbot) -> None:
    c1 = CommitNode(
        hash="aaa111",
        short_hash="aaa111",
        author="Alice",
        email="a@example.com",
        timestamp=1000,
        datetime_str="2026-01-01 10:00",
        parent_hashes=[],
        message="Initial commit",
        summary="Initial commit",
        column=0,
        row=1,
    )
    c2 = CommitNode(
        hash="bbb222",
        short_hash="bbb222",
        author="Bob",
        email="b@example.com",
        timestamp=2000,
        datetime_str="2026-01-01 11:00",
        parent_hashes=["aaa111"],
        message="Second commit",
        summary="Second commit",
        column=0,
        row=0,
        connectors=[
            GraphConnector(from_column=0, to_column=0, from_row=0, to_row=1, color_index=0)
        ],
    )

    view = GraphView()
    qtbot.addWidget(view)
    view.resize(600, 400)
    view.show()

    view.set_commits([c2, c1])
    assert len(view.commits) == 2
    assert view.selected_index == 0
    assert view.get_selected_commit() == c2

    # Select by hash
    selected_hashes = []
    view.commit_selected.connect(lambda h: selected_hashes.append(h))

    view.select_commit_by_hash("aaa111")
    assert view.selected_index == 1
    assert view.get_selected_commit() == c1
    assert selected_hashes == ["aaa111"]

    # Keyboard navigation: Key_Up selects row 0
    qtbot.keyClick(view, Qt.Key_Up)
    assert view.selected_index == 0
    assert selected_hashes[-1] == "bbb222"

    # Repaint verification
    view.viewport().repaint()


# -----------------------------------------------------------------------------
# Test DiffViewer
# -----------------------------------------------------------------------------

def test_diff_viewer_unstaged_actions(qapp, qtbot) -> None:
    viewer = DiffViewer()
    qtbot.addWidget(viewer)
    viewer.resize(600, 400)
    viewer.show()

    hunk = Hunk(
        file_path="src/main.py",
        header="@@ -1,2 +1,3 @@",
        old_start=1,
        old_lines=2,
        new_start=1,
        new_lines=3,
        lines=[
            DiffLine(DiffLineType.CONTEXT, "import sys", 1, 1),
            DiffLine(DiffLineType.DELETION, "print('old')", 2, None),
            DiffLine(DiffLineType.ADDITION, "print('new')", None, 2),
            DiffLine(DiffLineType.ADDITION, "print('more')", None, 3),
        ],
        is_staged=False,
    )

    staged_requests = []
    discard_requests = []
    viewer.stage_hunk_requested.connect(lambda h: staged_requests.append(h))
    viewer.discard_hunk_requested.connect(lambda h: discard_requests.append(h))

    viewer.set_diff("src/main.py", is_staged=False, hunks=[hunk])

    assert viewer.lbl_file_title.text() == "src/main.py"
    assert viewer.lbl_stage_badge.text() == "UNSTAGED"

    # Verify embedded HunkWidget was added
    hunk_widgets = viewer.findChildren(HunkWidget)
    assert len(hunk_widgets) == 1
    hw = hunk_widgets[0]

    # Find buttons on HunkWidget
    btns = hw.findChildren(QPushButton)
    btn_stage = next(b for b in btns if "Stage" in b.text())
    btn_discard = next(b for b in btns if "Discard" in b.text())

    qtbot.mouseClick(btn_stage, Qt.LeftButton)
    assert len(staged_requests) == 1
    assert staged_requests[0] == hunk

    qtbot.mouseClick(btn_discard, Qt.LeftButton)
    assert len(discard_requests) == 1
    assert discard_requests[0] == hunk


def test_diff_viewer_staged_actions(qapp, qtbot) -> None:
    viewer = DiffViewer()
    qtbot.addWidget(viewer)

    hunk = Hunk(
        file_path="src/test.py",
        header="@@ -1,1 +1,2 @@",
        old_start=1,
        old_lines=1,
        new_start=1,
        new_lines=2,
        lines=[
            DiffLine(DiffLineType.CONTEXT, "def test():", 1, 1),
            DiffLine(DiffLineType.ADDITION, "    pass", None, 2),
        ],
        is_staged=True,
    )

    unstage_requests = []
    viewer.unstage_hunk_requested.connect(lambda h: unstage_requests.append(h))

    viewer.set_diff("src/test.py", is_staged=True, hunks=[hunk])

    assert viewer.lbl_stage_badge.text() == "STAGED"

    hunk_widgets = viewer.findChildren(HunkWidget)
    assert len(hunk_widgets) == 1
    hw = hunk_widgets[0]

    btn_unstage = next(b for b in hw.findChildren(QPushButton) if "Unstage" in b.text())
    qtbot.mouseClick(btn_unstage, Qt.LeftButton)

    assert len(unstage_requests) == 1
    assert unstage_requests[0] == hunk


# -----------------------------------------------------------------------------
# Test StatusTree
# -----------------------------------------------------------------------------

def test_status_tree_interactions(qapp, qtbot) -> None:
    tree = StatusTree()
    qtbot.addWidget(tree)
    tree.resize(300, 500)
    tree.show()

    staged_change = FileChange("staged_file.txt", FileStatus.ADDED, is_staged=True)
    unstaged_change = FileChange("modified_file.py", FileStatus.MODIFIED, is_staged=False)

    tree.set_changes([staged_change], [unstaged_change])

    assert "Staged Changes (1)" in tree.lbl_staged_title.text()
    assert "Unstaged Changes (1)" in tree.lbl_unstaged_title.text()

    # Selection emission
    selected_files = []
    tree.file_selected.connect(lambda f: selected_files.append(f))

    row_widgets = tree.findChildren(FileRowWidget)
    assert len(row_widgets) == 2

    # Click on unstaged row
    qtbot.mouseClick(row_widgets[1], Qt.LeftButton)
    assert len(selected_files) == 1
    assert selected_files[0].file_path == "modified_file.py"

    # Action buttons: Stage All / Unstage All
    stage_all_called = []
    unstage_all_called = []
    tree.stage_all_requested.connect(lambda: stage_all_called.append(True))
    tree.unstage_all_requested.connect(lambda: unstage_all_called.append(True))

    qtbot.mouseClick(tree.btn_stage_all, Qt.LeftButton)
    assert stage_all_called == [True]

    qtbot.mouseClick(tree.btn_unstage_all, Qt.LeftButton)
    assert unstage_all_called == [True]


# -----------------------------------------------------------------------------
# Test CommitBox
# -----------------------------------------------------------------------------

def test_commit_box_submission_and_shortcuts(qapp, qtbot) -> None:
    box = CommitBox()
    qtbot.addWidget(box)
    box.show()

    assert not box.btn_commit.isEnabled()

    commits_emitted = []
    amends_emitted = []
    box.commit_requested.connect(lambda msg, amend: commits_emitted.append((msg, amend)))
    box.amend_toggled.connect(lambda chk: amends_emitted.append(chk))

    # Typing summary enables commit button
    box.input_summary.setText("feat: add graph rendering")
    assert box.btn_commit.isEnabled()
    assert box.get_commit_message() == "feat: add graph rendering"

    # Click Commit
    qtbot.mouseClick(box.btn_commit, Qt.LeftButton)
    assert commits_emitted == [("feat: add graph rendering", False)]

    # Amend toggle
    qtbot.mouseClick(box.chk_amend, Qt.LeftButton)
    assert box.is_amend
    assert amends_emitted == [True]
    assert box.btn_commit.text() == "Amend Commit"

    # Extended description
    box.input_desc.setPlainText("Closes #42\nDetails here.")
    full_msg = box.get_commit_message()
    assert "feat: add graph rendering\n\nCloses #42\nDetails here." == full_msg

    # Submit with amend
    qtbot.mouseClick(box.btn_commit, Qt.LeftButton)
    assert commits_emitted[-1] == (full_msg, True)

    # Clear inputs
    box.clear()
    assert box.input_summary.text() == ""
    assert box.input_desc.toPlainText() == ""
    assert not box.is_amend
    assert not box.btn_commit.isEnabled()
