"""Desktop application entry point and CLI runner for GitFiend Client."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from typing import List, Optional

# Auto-delegate to local virtual environment if run with global Python
_venv_python = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".venv",
    "Scripts" if os.name == "nt" else "bin",
    "python.exe" if os.name == "nt" else "python",
)
if os.path.isfile(_venv_python) and os.path.abspath(sys.executable).lower() != os.path.abspath(_venv_python).lower():
    try:
        import pygit2
    except ImportError:
        import subprocess
        sys.exit(subprocess.call([_venv_python, os.path.abspath(__file__)] + sys.argv[1:]))

try:
    import pygit2
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QApplication
except ImportError as _err:
    print(f"Error: Missing required dependency: {_err.name}")
    if os.name == "nt":
        print("Please activate the project virtual environment before running:")
        print("    .\\.venv\\Scripts\\Activate.ps1")
        print("Or run directly using:")
        print("    .\\.venv\\Scripts\\python.exe main.py")
    else:
        print("Please activate the project virtual environment before running:")
        print("    source .venv/bin/activate")
        print("Or run directly using:")
        print("    .venv/bin/python main.py")
    sys.exit(1)

from core.git_service import find_git_executable
from services.app_state import AppState
from ui.main_window import MainWindow
from ui.theme import Theme

__version__ = "0.1.0"
__app_name__ = "Strand"


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="strand",
        description="Production-grade, high-performance desktop Git client.",
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=None,
        help="Path to local Git repository to open on startup.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="Show application and environment version details, then exit.",
    )
    parser.add_argument(
        "--software-rendering",
        action="store_true",
        help="Force software rendering (useful for VMs or systems without GPU acceleration).",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging verbosity level (default: INFO).",
    )
    return parser


def print_version_info() -> None:
    """Print version information for the client, Qt runtime, and Git backends."""
    git_bin = find_git_executable() or "Not found"
    print(f"{__app_name__} v{__version__}")
    print(f"Python: {sys.version.split()[0]}")
    import PySide6
    print(f"PySide6 (Qt): {PySide6.__version__}")
    print(f"pygit2 (libgit2): {pygit2.__version__} (libgit2 {pygit2.LIBGIT2_VERSION})")
    print(f"Git CLI Binary: {git_bin}")


def resolve_repository_path(requested_path: Optional[str]) -> Optional[str]:
    """
    Resolve and validate the repository path to open.
    Searches upwards from requested path or current working directory.
    """
    start_path = requested_path or os.getcwd()
    start_path = os.path.abspath(os.path.expanduser(start_path))

    # Check if start_path itself has .git or is a bare repo
    candidate = start_path
    while candidate and os.path.dirname(candidate) != candidate:
        if os.path.isdir(os.path.join(candidate, ".git")) or os.path.isfile(os.path.join(candidate, ".git")):
            return candidate
        candidate = os.path.dirname(candidate)

    if requested_path and os.path.isdir(start_path):
        return start_path

    return None


def main(argv: Optional[List[str]] = None) -> int:
    """Application main entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.version:
        print_version_info()
        return 0

    # Configure logging
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("Strand")
    logger.info("Starting %s v%s...", __app_name__, __version__)

    if args.software_rendering:
        os.environ["QT_QUICK_BACKEND"] = "software"
        os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"

    # High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication.instance()
    owns_app = False
    if app is None:
        app = QApplication(sys.argv if argv is None else [sys.argv[0]] + argv)
        owns_app = True

    app.setApplicationName(__app_name__)
    app.setOrganizationName("Strand")
    app.setApplicationVersion(__version__)
    app.setStyleSheet(Theme.main_stylesheet())

    state = AppState()
    window = MainWindow(app_state=state)
    window.show()

    # Allow Python to process SIGINT (Ctrl+C) periodically
    sigint_timer = QTimer(window)
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start(500)

    # Resolve target repository
    # Do not implicitly open the repository containing the working directory.
    # Launching without a path should leave the user on the home screen.
    target_repo = resolve_repository_path(args.repo_path) if args.repo_path else None
    if target_repo:
        logger.info("Opening repository at %s", target_repo)
        state.open_repository(target_repo)
    elif args.repo_path:
        logger.warning("Specified path '%s' is not a valid Git repository", args.repo_path)

    if owns_app:
        return app.exec()
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(main())
