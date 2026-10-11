"""File system monitoring with automated debounce for Git repositories."""

from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal


class RepoWatcher(QObject):
    """
    Monitors .git internal states (HEAD, index, refs) and working tree modifications.
    Debounces rapid bursts of filesystem events (e.g., branch checkout or build scripts)
    before emitting repository_changed to trigger state re-synchronization.
    """
    repository_changed = Signal()
    head_changed = Signal()
    index_changed = Signal()

    DEFAULT_DEBOUNCE_MS = 200

    def __init__(
        self,
        repo_path: Optional[str] = None,
        debounce_ms: int = DEFAULT_DEBOUNCE_MS,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.debounce_ms = debounce_ms
        self.repo_path: Optional[str] = None
        self._is_paused: bool = False

        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._watcher.directoryChanged.connect(self._on_directory_changed)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._on_debounce_timeout)

        if repo_path:
            self.watch(repo_path)

    def watch(self, repo_path: str) -> None:
        """Start observing the specified repository path."""
        self.unwatch()
        self.repo_path = os.path.abspath(repo_path)

        git_dir = os.path.join(self.repo_path, ".git")
        if not os.path.exists(git_dir):
            return

        # Add working directory
        self._safe_add_path(self.repo_path)

        # Watch crucial .git control files and directories
        paths_to_watch = [
            os.path.join(git_dir, "HEAD"),
            os.path.join(git_dir, "index"),
            os.path.join(git_dir, "refs", "heads"),
            os.path.join(git_dir, "refs", "tags"),
            git_dir,
        ]

        for p in paths_to_watch:
            self._safe_add_path(p)

    def unwatch(self) -> None:
        """Remove all active file and directory watches."""
        files = self._watcher.files()
        if files:
            self._watcher.removePaths(files)
        dirs = self._watcher.directories()
        if dirs:
            self._watcher.removePaths(dirs)
        self._debounce_timer.stop()
        self.repo_path = None

    def pause(self) -> None:
        """Temporarily suspend change events (e.g. during internal stage/commit operations)."""
        self._is_paused = True
        self._debounce_timer.stop()

    def resume(self) -> None:
        """Resume change event monitoring and re-verify registered watch paths."""
        self._is_paused = False
        if self.repo_path:
            self._re_register_paths()

    def _safe_add_path(self, path: str) -> None:
        """Add path to watcher if it exists on the filesystem and is not already tracked."""
        if os.path.exists(path):
            norm = os.path.normpath(path)
            all_watched = set(self._watcher.files() + self._watcher.directories())
            if norm not in all_watched:
                self._watcher.addPath(norm)

    def _re_register_paths(self) -> None:
        """Re-adds files that might have been removed due to atomic replacement by Git."""
        if not self.repo_path:
            return

        git_dir = os.path.join(self.repo_path, ".git")
        key_files = [
            os.path.join(git_dir, "HEAD"),
            os.path.join(git_dir, "index"),
        ]
        current_files = set(self._watcher.files())
        for kf in key_files:
            if os.path.exists(kf) and os.path.normpath(kf) not in current_files:
                self._safe_add_path(kf)

    def _trigger_debounce(self) -> None:
        """Restart single-shot debounce timer."""
        if self._is_paused:
            return
        self._debounce_timer.start(self.debounce_ms)

    def _on_file_changed(self, path: str) -> None:
        """Handle individual file mutation."""
        if self._is_paused:
            return

        # Specific signal dispatch
        norm = path.replace("\\", "/")
        if norm.endswith("/HEAD"):
            self.head_changed.emit()
        elif norm.endswith("/index"):
            self.index_changed.emit()

        # Re-register path in case of atomic replacement (e.g. .git/index)
        self._safe_add_path(path)
        self._trigger_debounce()

    def _on_directory_changed(self, path: str) -> None:
        """Handle directory file listing mutation."""
        if self._is_paused:
            return
        self._re_register_paths()
        self._trigger_debounce()

    def _on_debounce_timeout(self) -> None:
        """Emitted when filesystem changes have stabilized."""
        if not self._is_paused:
            self._re_register_paths()
            self.repository_changed.emit()
