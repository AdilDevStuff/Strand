"""Configure certificate discovery before pygit2 initializes libgit2."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _certificate_candidates() -> list[Path]:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "resources" / "ca-certificates.crt")
    candidates.extend(
        [
            Path("/etc/ssl/certs/ca-certificates.crt"),
            Path("/etc/pki/tls/certs/ca-bundle.crt"),
        ]
    )
    return candidates


for certificate_path in _certificate_candidates():
    if certificate_path.is_file():
        os.environ.setdefault("SSL_CERT_FILE", str(certificate_path))
        os.environ.setdefault("GIT_SSL_CAINFO", str(certificate_path))
        break
