#!/usr/bin/env python3
"""
Comprehensive build and packaging script for Strand Git Client.

Usage:
    python scripts/build.py [--clean] [--no-standalone] [--package] [--output-dir DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"


def get_version() -> str:
    """Extract version from main.py or pyproject.toml."""
    main_file = ROOT_DIR / "main.py"
    if main_file.exists():
        for line in main_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("__version__"):
                return line.split("=")[-1].strip().strip('"\'')
    return "0.1.0"


def compute_sha256(file_path: Path) -> str:
    """Compute the SHA256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def clean_build_artifacts() -> None:
    """Remove previous build and dist directories."""
    print("🧹 Cleaning previous build artifacts...")
    for d in [BUILD_DIR, DIST_DIR]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            print(f"   Removed {d}")


def build_standalone(version: str, output_dir: Path) -> list[Path]:
    """Build standalone executable bundle using PyInstaller."""
    print(f"\n📦 Building standalone executable for Strand v{version}...")
    output_dir.mkdir(parents=True, exist_ok=True)

    spec_file = ROOT_DIR / "strand.spec"
    if not spec_file.exists():
        raise FileNotFoundError(f"Missing spec file: {spec_file}")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(output_dir),
        "--workpath",
        str(BUILD_DIR),
        str(spec_file),
    ]

    print(f"   Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if result.returncode != 0:
        print("❌ PyInstaller build failed!")
        sys.exit(result.returncode)

    bundle_dir = output_dir / "Strand"
    if not bundle_dir.exists():
        raise RuntimeError(f"Expected bundle directory not found: {bundle_dir}")

    sys_name = platform.system().lower()
    arch_name = platform.machine().lower()
    if arch_name in ("amd64", "x86_64"):
        arch_name = "x86_64"
    elif arch_name in ("arm64", "aarch64"):
        arch_name = "arm64"

    archive_base = f"strand-{version}-{sys_name}-{arch_name}"
    artifacts: list[Path] = []

    if sys_name == "windows":
        archive_path = output_dir / f"{archive_base}.zip"
        print(f"📦 Packaging Windows archive: {archive_path.name}...")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(bundle_dir):
                for f in files:
                    full_p = Path(root) / f
                    arc_p = Path(archive_base) / full_p.relative_to(bundle_dir)
                    zf.write(full_p, str(arc_p))
        artifacts.append(archive_path)
    else:
        archive_path = output_dir / f"{archive_base}.tar.gz"
        print(f"📦 Packaging Linux/macOS archive: {archive_path.name}...")
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(bundle_dir, arcname=archive_base)
        artifacts.append(archive_path)

    print(f"✅ Standalone archive created: {archive_path}")
    return artifacts


def build_python_packages(output_dir: Path) -> list[Path]:
    """Build Python wheel and source distribution (sdist) using pypa/build."""
    print("\n📦 Building Python package distributions (sdist and wheel)...")
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-c",
        (
            "import sys; "
            "sys.path = [p for p in sys.path if p not in ('', '.')]; "
            "from build import ProjectBuilder; "
            f"b = ProjectBuilder(r'{ROOT_DIR}'); "
            f"b.build('sdist', r'{output_dir}'); "
            f"b.build('wheel', r'{output_dir}')"
        ),
    ]
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if result.returncode != 0:
        print("❌ Python package build failed!")
        sys.exit(result.returncode)

    built_files = [
        p for p in output_dir.glob("strand*")
        if p.suffix in (".whl", ".gz")
    ]
    return built_files


def generate_checksums(output_dir: Path) -> Path:
    """Generate SHA256 checksums file for all release archives."""
    sums_file = output_dir / "SHA256SUMS.txt"
    lines: list[str] = []

    for file_path in sorted(output_dir.iterdir()):
        if file_path.is_file() and file_path.name != "SHA256SUMS.txt" and not file_path.name.startswith("."):
            if file_path.suffix in (".zip", ".gz", ".whl", ".AppImage"):
                sha = compute_sha256(file_path)
                lines.append(f"{sha}  {file_path.name}")
                print(f"   SHA256 ({file_path.name}) = {sha}")

    if lines:
        sums_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"✅ Checksums written to: {sums_file}")
    return sums_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and package Strand Git Client.")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts before building")
    parser.add_argument("--no-standalone", action="store_true", help="Skip building standalone PyInstaller binary")
    parser.add_argument("--package", action="store_true", help="Build Python sdist and wheel")
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR, help="Destination directory for built files")
    args = parser.parse_args()

    version = get_version()
    print("=" * 60)
    print(f"  Strand Git Client Build System (v{version})")
    print(f"  Platform: {platform.system()} ({platform.machine()})")
    print(f"  Python:   {sys.version.split()[0]}")
    print("=" * 60)

    if args.clean:
        clean_build_artifacts()

    output_dir = args.output_dir.resolve()
    all_artifacts: list[Path] = []

    if not args.no_standalone:
        standalone_artifacts = build_standalone(version, output_dir)
        all_artifacts.extend(standalone_artifacts)

    if args.package:
        pkg_artifacts = build_python_packages(output_dir)
        all_artifacts.extend(pkg_artifacts)

    if all_artifacts:
        generate_checksums(output_dir)

    print("\n🎉 Build completed successfully!")
    print(f"Artifacts located in: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
