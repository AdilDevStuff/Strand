"""Global test fixtures and environment configuration."""

from __future__ import annotations

import os
import subprocess
import pytest


@pytest.fixture(autouse=True, scope="session")
def setup_test_environment() -> None:
    """Ensure git author/committer identity and headless Qt are configured for all test runs."""
    os.environ.setdefault("GIT_AUTHOR_NAME", "Strand Tester")
    os.environ.setdefault("GIT_AUTHOR_EMAIL", "tester@example.com")
    os.environ.setdefault("GIT_COMMITTER_NAME", "Strand Tester")
    os.environ.setdefault("GIT_COMMITTER_EMAIL", "tester@example.com")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        subprocess.run(["git", "config", "--global", "user.name", "Strand Tester"], check=False)
        subprocess.run(["git", "config", "--global", "user.email", "tester@example.com"], check=False)
    except Exception:
        pass
