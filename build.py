#!/usr/bin/env python3
"""Strand build entrypoint."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    script = Path(__file__).resolve().parent / "scripts" / "build.py"
    sys.exit(subprocess.run([sys.executable, str(script)] + sys.argv[1:]).returncode)
