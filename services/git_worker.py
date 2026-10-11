"""Asynchronous worker abstractions bridging Git execution with Qt's event loop."""

from __future__ import annotations

import subprocess
import traceback
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal


class WorkerSignals(QObject):
    """
    Signals emitted during asynchronous background task execution.
    Must inherit from QObject since QRunnable does not provide Qt signals.
    """
    started = Signal()
    result = Signal(object)
    error = Signal(str)
    finished = Signal()
    progress = Signal(str)


class GitTaskRunnable(QRunnable):
    """
    QRunnable worker executing arbitrary callable functions in the global QThreadPool.
    Communicates safely with the UI thread strictly via Qt signals.
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        """Execute task inside the worker thread."""
        self.signals.started.emit()
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {str(exc)}"
            self.signals.error.emit(err_msg)
        finally:
            self.signals.finished.emit()


class GitWorkerThread(QThread):
    """
    Dedicated QThread for long-running streaming operations (e.g. clone, push, fetch, rebase)
    that emit line-by-line progress and support cooperative cancellation.
    """
    line_received = Signal(str)
    result = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        cmd: List[str],
        cwd: str,
        env: Optional[Dict[str, str]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self._process: Optional[subprocess.Popen] = None
        self._is_cancelled: bool = False

    def cancel(self) -> None:
        """Terminate the running subprocess and mark thread cancelled."""
        self._is_cancelled = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass

    def run(self) -> None:
        """Run the command line process and stream stdout/stderr line by line."""
        if self._is_cancelled:
            return

        try:
            self._process = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                env=self.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            assert self._process.stdout is not None
            for line in iter(self._process.stdout.readline, ""):
                if self._is_cancelled:
                    break
                stripped = line.rstrip()
                if stripped:
                    self.line_received.emit(stripped)

            self._process.wait()
            ret_code = self._process.returncode

            if self._is_cancelled:
                self.error.emit("Operation cancelled by user.")
            elif ret_code == 0:
                self.result.emit(True)
            else:
                self.error.emit(f"Process exited with error code {ret_code}")

        except Exception as exc:
            self.error.emit(f"Failed to execute command: {str(exc)}")


_ACTIVE_RUNNABLES: set[GitTaskRunnable] = set()


def run_async(
    fn: Callable[..., Any],
    *args: Any,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
    on_finished: Optional[Callable[[], None]] = None,
    thread_pool: Optional[QThreadPool] = None,
    **kwargs: Any,
) -> GitTaskRunnable:
    """
    Convenience helper to dispatch a function asynchronously on QThreadPool.
    Automatically binds callback slots to WorkerSignals and maintains a strong
    reference until completion to prevent premature garbage collection in Qt.
    """
    runnable = GitTaskRunnable(fn, *args, **kwargs)
    _ACTIVE_RUNNABLES.add(runnable)

    if on_success:
        runnable.signals.result.connect(on_success)
    if on_error:
        runnable.signals.error.connect(on_error)

    def _cleanup():
        _ACTIVE_RUNNABLES.discard(runnable)
        if on_finished:
            on_finished()

    runnable.signals.finished.connect(_cleanup)

    pool = thread_pool or QThreadPool.globalInstance()
    pool.start(runnable)
    return runnable
