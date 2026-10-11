"""Central reactive state store for the Git client application."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from PySide6.QtCore import QObject, QThreadPool, Signal

from core.git_service import GitService
from core.graph_builder import GraphBuilder
from core.models import CommitNode, FileChange, FileStatus, Hunk
from services.git_worker import GitTaskRunnable, run_async
from services.repo_watcher import RepoWatcher


class AppState(QObject):
    """
    Reactive central application store tracking repository state,
    active branch, staged/unstaged changes, selected commit, diff, and sync status.
    All disk I/O and Git computations run asynchronously off the main thread.
    """

    # Signals
    repo_opened = Signal(str)
    repo_closed = Signal()
    branch_changed = Signal(str)
    branches_updated = Signal(dict)
    status_updated = Signal(list, list)  # (staged_files, unstaged_files)
    history_updated = Signal(list)  # (commits: List[CommitNode])
    diff_updated = Signal(str, bool, list)  # (file_path, is_staged, List[Hunk])
    commit_selected_changed = Signal(object)  # (Optional[CommitNode])
    file_selected_changed = Signal(object)  # (Optional[FileChange])
    sync_status_updated = Signal(int, int)  # (ahead, behind)
    loading_changed = Signal(bool)
    error_occurred = Signal(str)
    operation_succeeded = Signal(str)
    commit_details_loaded = Signal(object, list, dict)  # (CommitNode, List[FileChange], Dict[str, List[Hunk]])
    stashes_updated = Signal(list)  # (stashes: List[Dict[str, Any]])
    tags_updated = Signal(list)  # (tags: List[Dict[str, str]])
    conflicts_updated = Signal(list)  # (conflicted_files: List[str])

    def __init__(
        self,
        thread_pool: Optional[QThreadPool] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        if thread_pool is not None:
            self.thread_pool = thread_pool
        else:
            self.thread_pool = QThreadPool(self)
            self.thread_pool.setMaxThreadCount(1)
        self.graph_builder = GraphBuilder()
        self.watcher = RepoWatcher(parent=self)
        self.watcher.repository_changed.connect(self._on_external_repo_change)

        # Reactive State Properties
        self.current_repo_path: Optional[str] = None
        self.git_service: Optional[GitService] = None
        self.active_branch: str = ""
        self.staged_files: List[FileChange] = []
        self.unstaged_files: List[FileChange] = []
        self.commits: List[CommitNode] = []
        self.branches: Dict[str, List[str]] = {"local": [], "remote": []}
        self.stashes: List[Dict[str, Any]] = []
        self.tags: List[Dict[str, str]] = []
        self.conflicted_files: List[str] = []
        self.selected_commit: Optional[CommitNode] = None
        self.selected_file: Optional[FileChange] = None
        self.active_diff: List[Hunk] = []
        self.ahead_count: int = 0
        self.behind_count: int = 0
        self.is_loading: bool = False

    # -------------------------------------------------------------------------
    # Repository Management
    # -------------------------------------------------------------------------

    def open_repository(self, path: str) -> None:
        """Open and initialize a repository path asynchronously."""
        if not path or not os.path.exists(path):
            self.error_occurred.emit(f"Directory does not exist: {path}")
            return

        def _do_open():
            service = GitService(path)
            branch = service.get_current_branch()
            branches = service.get_branches()
            status_list = service.get_status()
            staged = [c for c in status_list if c.is_staged]
            unstaged = [c for c in status_list if not c.is_staged]
            history = service.get_commit_history()
            graph = self.graph_builder.build(history)
            ahead, behind = service.get_remote_sync_status()
            stashes = service.get_stashes()
            tags = service.get_tags()
            conflicts = service.get_conflicted_files()
            return service, branch, branches, staged, unstaged, graph, ahead, behind, stashes, tags, conflicts

        def _on_success(payload):
            service, branch, branches, staged, unstaged, graph, ahead, behind, stashes, tags, conflicts = payload
            self.current_repo_path = os.path.abspath(path)
            self.git_service = service
            self.active_branch = branch
            self.branches = branches
            self.staged_files = staged
            self.unstaged_files = unstaged
            self.commits = graph
            self.ahead_count = ahead
            self.behind_count = behind
            self.stashes = stashes
            self.tags = tags
            self.conflicted_files = conflicts
            self.selected_commit = graph[0] if graph else None
            self.selected_file = None
            self.active_diff = []

            # Watch repository for disk mutations
            self.watcher.watch(self.current_repo_path)

            self.repo_opened.emit(self.current_repo_path)
            self.branch_changed.emit(self.active_branch)
            self.branches_updated.emit(self.branches)
            self.status_updated.emit(self.staged_files, self.unstaged_files)
            self.history_updated.emit(self.commits)
            self.sync_status_updated.emit(self.ahead_count, self.behind_count)
            self.stashes_updated.emit(self.stashes)
            self.tags_updated.emit(self.tags)
            self.conflicts_updated.emit(self.conflicted_files)
            self.commit_selected_changed.emit(self.selected_commit)
            self.file_selected_changed.emit(None)
            self.diff_updated.emit("", False, [])

        self._execute_async(_do_open, on_success=_on_success)

    def close_repository(self) -> None:
        """Close current repository and reset state."""
        self.watcher.unwatch()
        self.current_repo_path = None
        self.git_service = None
        self.active_branch = ""
        self.staged_files = []
        self.unstaged_files = []
        self.commits = []
        self.branches = {"local": [], "remote": []}
        self.stashes = []
        self.tags = []
        self.conflicted_files = []
        self.selected_commit = None
        self.selected_file = None
        self.active_diff = []
        self.ahead_count = 0
        self.behind_count = 0

        self.repo_closed.emit()
        self.status_updated.emit([], [])
        self.stashes_updated.emit([])
        self.tags_updated.emit([])
        self.conflicts_updated.emit([])
        self.history_updated.emit([])
        self.file_selected_changed.emit(None)
        self.diff_updated.emit("", False, [])

    # -------------------------------------------------------------------------
    # State Refresh
    # -------------------------------------------------------------------------

    def refresh(self) -> None:
        """Asynchronously refresh status, commits, branches, and active diff."""
        if not self.git_service:
            return

        sel_file = self.selected_file

        def _do_refresh():
            service = self.git_service
            assert service is not None
            branch = service.get_current_branch()
            branches = service.get_branches()
            status_list = service.get_status()
            staged = [c for c in status_list if c.is_staged]
            unstaged = [c for c in status_list if not c.is_staged]
            history = service.get_commit_history()
            graph = self.graph_builder.build(history)
            ahead, behind = service.get_remote_sync_status()
            stashes = service.get_stashes()
            tags = service.get_tags()
            conflicts = service.get_conflicted_files()

            diff_hunks: List[Hunk] = []
            if sel_file:
                diff_hunks = service.get_diff(sel_file.file_path, sel_file.is_staged)

            return branch, branches, staged, unstaged, graph, ahead, behind, diff_hunks, stashes, tags, conflicts

        def _on_success(payload):
            branch, branches, staged, unstaged, graph, ahead, behind, diff_hunks, stashes, tags, conflicts = payload
            self.active_branch = branch
            self.branches = branches
            self.staged_files = staged
            self.unstaged_files = unstaged
            self.commits = graph
            self.ahead_count = ahead
            self.behind_count = behind
            self.stashes = stashes
            self.tags = tags
            self.conflicted_files = conflicts

            self.branch_changed.emit(self.active_branch)
            self.branches_updated.emit(self.branches)
            self.status_updated.emit(self.staged_files, self.unstaged_files)
            self.history_updated.emit(self.commits)
            self.sync_status_updated.emit(self.ahead_count, self.behind_count)
            self.stashes_updated.emit(self.stashes)
            self.tags_updated.emit(self.tags)
            self.conflicts_updated.emit(self.conflicted_files)

            if sel_file:
                self.active_diff = diff_hunks
                self.diff_updated.emit(sel_file.file_path, sel_file.is_staged, self.active_diff)

        self._execute_async(_do_refresh, on_success=_on_success)

    def _on_external_repo_change(self) -> None:
        """Triggered by RepoWatcher when changes occur on disk."""
        self.refresh()

    # -------------------------------------------------------------------------
    # Selection Management
    # -------------------------------------------------------------------------

    def select_file(
        self,
        change: Union[FileChange, str, None],
        is_staged: bool = False,
    ) -> None:
        """Select a file change and load its diff asynchronously."""
        if isinstance(change, str):
            file_obj: Optional[FileChange] = FileChange(
                file_path=change,
                status=FileStatus.MODIFIED,
                is_staged=is_staged,
            )
        else:
            file_obj = change

        self.selected_file = file_obj
        self.file_selected_changed.emit(file_obj)

        if file_obj is None or not self.git_service:
            self.active_diff = []
            self.diff_updated.emit("", False, [])
            return

        def _fetch_diff():
            assert self.git_service is not None
            return self.git_service.get_diff(file_obj.file_path, file_obj.is_staged)

        def _on_success(hunks: List[Hunk]):
            self.active_diff = hunks
            self.diff_updated.emit(file_obj.file_path, file_obj.is_staged, hunks)

        self._execute_async(_fetch_diff, on_success=_on_success)

    def select_commit(self, commit: Union[CommitNode, str, None]) -> None:
        """Set the currently highlighted commit node."""
        if commit is None:
            self.selected_commit = None
        elif isinstance(commit, CommitNode):
            self.selected_commit = commit
        elif isinstance(commit, str):
            self.selected_commit = next(
                (c for c in self.commits if c.hash == commit or c.short_hash == commit),
                None,
            )
        self.commit_selected_changed.emit(self.selected_commit)

    # -------------------------------------------------------------------------
    # Git Actions (Stage, Unstage, Discard, Commit, Checkout)
    # -------------------------------------------------------------------------

    def stage_file(self, path: str) -> None:
        """Stage an entire file asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.stage_file(path)

        def _done(_):
            if self.selected_file and self.selected_file.file_path == path:
                self.selected_file = FileChange(path, self.selected_file.status, is_staged=True)
                self.file_selected_changed.emit(self.selected_file)
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def unstage_file(self, path: str) -> None:
        """Unstage an entire file asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.unstage_file(path)

        def _done(_):
            if self.selected_file and self.selected_file.file_path == path:
                self.selected_file = FileChange(path, self.selected_file.status, is_staged=False)
                self.file_selected_changed.emit(self.selected_file)
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def stage_hunk(self, hunk: Hunk) -> None:
        """Stage a single hunk asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.stage_hunk(hunk)

        def _done(_):
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def unstage_hunk(self, hunk: Hunk) -> None:
        """Unstage a single hunk asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.unstage_hunk(hunk)

        def _done(_):
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def discard_hunk(self, hunk: Hunk) -> None:
        """Discard a single hunk in the working tree asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.discard_hunk(hunk)

        def _done(_):
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def commit(self, message: str, amend: bool = False) -> None:
        """Create or amend a commit asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            return self.git_service.commit(message, amend=amend)

        def _done(commit_hash: str):
            self.operation_succeeded.emit(f"Committed {commit_hash[:7]}")
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def checkout_branch(self, branch_name: str) -> None:
        """Checkout a branch asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.checkout(branch_name)

        def _done(_):
            self.operation_succeeded.emit(f"Switched to branch {branch_name}")
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def stage_all(self) -> None:
        """Stage all modified, untracked, and deleted files asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.stage_all()

        def _done(_):
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def unstage_all(self) -> None:
        """Unstage all files back to HEAD asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.unstage_all()

        def _done(_):
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def create_branch(self, branch_name: str) -> None:
        """Create a new branch asynchronously and refresh."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.create_branch(branch_name)

        def _done(_):
            self.operation_succeeded.emit(f"Created branch '{branch_name}'")
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def load_commit_details(self, commit_hash: str) -> None:
        """Inspect a historical commit and emit commit_details_loaded asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            return self.git_service.get_commit_details(commit_hash)

        def _done(payload):
            node, files, hunks = payload
            if node:
                self.commit_details_loaded.emit(node, files, hunks)

        self._execute_async(_action, on_success=_done)

    def push(self) -> None:
        """Push commits to origin asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            return self.git_service.push()

        def _done(out: str):
            self.operation_succeeded.emit("Pushed commits successfully")
            self.refresh()

        self._execute_async(_action, on_success=_done)

    def pull(self) -> None:
        """Pull commits from origin asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            return self.git_service.pull()

        def _done(out: str):
            self.operation_succeeded.emit("Pulled commits successfully")
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def fetch(self) -> None:
        """Fetch commits from origin asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            return self.git_service.fetch()

        def _done(out: str):
            self.operation_succeeded.emit("Fetched latest refs successfully")
            self.refresh()

        self._execute_async(_action, on_success=_done)

    # -------------------------------------------------------------------------
    # Stash Actions
    # -------------------------------------------------------------------------

    def stash_save(self, message: str = "", include_untracked: bool = False, keep_index: bool = False) -> None:
        """Stash working tree changes asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            return self.git_service.stash_save(message, include_untracked, keep_index)

        def _done(res: str):
            self.operation_succeeded.emit(f"Saved stash: {res}")
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def stash_pop(self, index: int = 0) -> None:
        """Pop stash asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            return self.git_service.stash_pop(index)

        def _done(res: str):
            self.operation_succeeded.emit(f"Applied and dropped stash@{{{index}}}")
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def stash_apply(self, index: int = 0) -> None:
        """Apply stash asynchronously without dropping."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            return self.git_service.stash_apply(index)

        def _done(res: str):
            self.operation_succeeded.emit(f"Applied stash@{{{index}}}")
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def stash_drop(self, index: int = 0) -> None:
        """Drop stash asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            return self.git_service.stash_drop(index)

        def _done(res: str):
            self.operation_succeeded.emit(f"Dropped stash@{{{index}}}")
            self.refresh()

        self._execute_async(_action, on_success=_done)

    # -------------------------------------------------------------------------
    # Conflict Actions
    # -------------------------------------------------------------------------

    def resolve_conflict(self, file_path: str, strategy: str = "ours") -> None:
        """Resolve a conflicted file asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.resolve_conflict(file_path, strategy)

        def _done(_):
            self.operation_succeeded.emit(f"Resolved conflict in {file_path} using {strategy}")
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    # -------------------------------------------------------------------------
    # History Actions (Revert, Reset) & Tags
    # -------------------------------------------------------------------------

    def revert_commit(self, commit_hash: str) -> None:
        """Revert a commit asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            return self.git_service.revert_commit(commit_hash)

        def _done(_):
            self.operation_succeeded.emit(f"Reverted commit {commit_hash[:7]}")
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def reset(self, target: str = "HEAD~1", mode: str = "mixed") -> None:
        """Reset repository asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            return self.git_service.reset(target, mode)

        def _done(_):
            self.operation_succeeded.emit(f"Reset ({mode}) to {target}")
            self.refresh()

        self._execute_async(_action, on_success=_done, pause_watcher=True)

    def create_tag(self, name: str, commit_hash: Optional[str] = None, message: str = "") -> None:
        """Create a new tag asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.create_tag(name, commit_hash, message)

        def _done(_):
            self.operation_succeeded.emit(f"Created tag '{name}'")
            self.refresh()

        self._execute_async(_action, on_success=_done)

    def delete_tag(self, name: str) -> None:
        """Delete tag asynchronously."""
        if not self.git_service:
            return

        def _action():
            assert self.git_service is not None
            self.git_service.delete_tag(name)

        def _done(_):
            self.operation_succeeded.emit(f"Deleted tag '{name}'")
            self.refresh()

        self._execute_async(_action, on_success=_done)

    # -------------------------------------------------------------------------
    # Async Runner Helper
    # -------------------------------------------------------------------------

    def _execute_async(
        self,
        task_fn: Callable[[], Any],
        on_success: Optional[Callable[[Any], None]] = None,
        pause_watcher: bool = False,
    ) -> GitTaskRunnable:
        """Execute a task in QThreadPool with automatic loading state management."""
        if pause_watcher:
            self.watcher.pause()

        self.is_loading = True
        self.loading_changed.emit(True)

        def _wrapped_success(res):
            self.is_loading = False
            self.loading_changed.emit(False)
            if pause_watcher:
                self.watcher.resume()
            if on_success:
                on_success(res)

        def _wrapped_error(err_str: str):
            self.is_loading = False
            self.loading_changed.emit(False)
            if pause_watcher:
                self.watcher.resume()
            self.error_occurred.emit(err_str)

        return run_async(
            task_fn,
            on_success=_wrapped_success,
            on_error=_wrapped_error,
            thread_pool=self.thread_pool,
        )
