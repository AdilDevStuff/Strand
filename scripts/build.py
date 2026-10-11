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


# Ensure UTF-8 output streams across all platforms (prevents Windows cp1252 charmap errors)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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

    app_bundle = output_dir / "Strand.app"
    if sys_name == "darwin" and app_bundle.exists():
        archive_path = output_dir / f"{archive_base}.tar.gz"
        print(f"📦 Packaging macOS App bundle: {archive_path.name}...")
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(app_bundle, arcname="Strand.app")
        artifacts.append(archive_path)
    elif sys_name == "windows":
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
        print(f"📦 Packaging Linux/Unix archive: {archive_path.name}...")
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(bundle_dir, arcname=archive_base)
        artifacts.append(archive_path)

    print(f"✅ Standalone archive created: {archive_path}")

    # Build Linux system distribution packages (.deb, .rpm, .AppImage)
    if sys_name == "linux":
        deb_pkg = build_deb_package(bundle_dir, version, output_dir)
        if deb_pkg:
            artifacts.append(deb_pkg)

        rpm_pkg = build_rpm_package(bundle_dir, version, output_dir)
        if rpm_pkg:
            artifacts.append(rpm_pkg)

        appimage_pkg = build_appimage(bundle_dir, version, output_dir)
        if appimage_pkg:
            artifacts.append(appimage_pkg)

    return artifacts


def build_deb_package(bundle_dir: Path, version: str, output_dir: Path) -> Optional[Path]:
    """Package Strand bundle as a Debian (.deb) package."""
    print("\n📦 Packaging Debian (.deb) package...")
    deb_dir = BUILD_DIR / "pkg_deb"
    if deb_dir.exists():
        shutil.rmtree(deb_dir, ignore_errors=True)

    opt_dir = deb_dir / "opt" / "strand"
    opt_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle_dir, opt_dir, dirs_exist_ok=True)

    bin_dir = deb_dir / "usr" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    symlink_path = bin_dir / "strand"
    try:
        os.symlink("/opt/strand/strand", symlink_path)
    except Exception:
        symlink_path.write_text("#!/bin/sh\nexec /opt/strand/strand \"$@\"\n", encoding="utf-8")
        symlink_path.chmod(0o755)

    apps_dir = deb_dir / "usr" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    desktop_src = ROOT_DIR / "resources" / "strand.desktop"
    if desktop_src.exists():
        shutil.copy(desktop_src, apps_dir / "strand.desktop")

    icons_dir = deb_dir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    icons_dir.mkdir(parents=True, exist_ok=True)
    icon_src = ROOT_DIR / "resources" / "icons" / "strand.png"
    if icon_src.exists():
        shutil.copy(icon_src, icons_dir / "strand.png")

    debian_dir = deb_dir / "DEBIAN"
    debian_dir.mkdir(parents=True, exist_ok=True)
    control_content = f"""Package: strand
Version: {version}
Section: devel
Priority: optional
Architecture: amd64
Maintainer: Strand Core Team <team@strand.local>
Depends: libgl1, libegl1, libxkbcommon-x11-0
Description: Production-grade desktop Git client built with Python, Qt6, and libgit2.
 High-performance visual Git client featuring an elevated commit box,
 visual history graph, hunk-level diff staging, and branch management.
"""
    (debian_dir / "control").write_text(control_content, encoding="utf-8")

    deb_filename = f"strand_{version}_amd64.deb"
    deb_path = output_dir / deb_filename

    if shutil.which("dpkg-deb"):
        res = subprocess.run(["dpkg-deb", "--build", str(deb_dir), str(deb_path)], capture_output=True)
        if res.returncode == 0 and deb_path.exists():
            print(f"✅ Debian package created (via dpkg-deb): {deb_path}")
            return deb_path

    # Pure Python fallback for building .deb ar archive
    try:
        import io
        deb_binary = b"2.0\n"

        control_buf = io.BytesIO()
        with tarfile.open(fileobj=control_buf, mode="w:gz") as tf:
            for item in sorted(debian_dir.iterdir()):
                tf.add(item, arcname=f"./{item.name}")
        control_data = control_buf.getvalue()

        data_buf = io.BytesIO()
        with tarfile.open(fileobj=data_buf, mode="w:gz") as tf:
            for item in ["opt", "usr"]:
                src = deb_dir / item
                if src.exists():
                    tf.add(src, arcname=f"./{item}")
        data_tar = data_buf.getvalue()

        with open(deb_path, "wb") as f:
            f.write(b"!<arch>\n")
            for fname, content in [("debian-binary", deb_binary), ("control.tar.gz", control_data), ("data.tar.gz", data_tar)]:
                header = f"{fname:<16}{0:<12}{0:<6}{0:<6}{100644:<8o}{len(content):<10}`\n".encode("ascii")
                f.write(header)
                f.write(content)
                if len(content) % 2 != 0:
                    f.write(b"\n")
        print(f"✅ Debian package created (pure python): {deb_path}")
        return deb_path
    except Exception as exc:
        print(f"⚠️ Could not build Debian package: {exc}")
        return None


def build_rpm_package(bundle_dir: Path, version: str, output_dir: Path) -> Optional[Path]:
    """Package Strand bundle as an RPM package if fpm is available."""
    rpm_filename = f"strand-{version}-1.x86_64.rpm"
    rpm_path = output_dir / rpm_filename

    if shutil.which("fpm"):
        print("\n📦 Packaging RPM package using fpm...")
        pkg_dir = BUILD_DIR / "pkg_deb"
        if not pkg_dir.exists():
            return None
        cmd = [
            "fpm",
            "-s", "dir",
            "-t", "rpm",
            "-n", "strand",
            "-v", version,
            "--iteration", "1",
            "--architecture", "x86_64",
            "--description", "Production-grade desktop Git client built with Python, Qt6, and libgit2.",
            "-p", str(rpm_path),
            "-C", str(pkg_dir),
            "opt", "usr",
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0 and rpm_path.exists():
            print(f"✅ RPM package created: {rpm_path}")
            return rpm_path
        else:
            print(f"⚠️ fpm RPM packaging returned code {res.returncode}")
            if res.stderr:
                print(res.stderr.decode("utf-8", errors="replace"))
            if res.stdout:
                print(res.stdout.decode("utf-8", errors="replace"))
    return None


def build_appimage(bundle_dir: Path, version: str, output_dir: Path) -> Optional[Path]:
    """Package Strand bundle as an AppImage if appimagetool is available."""
    appimagetool = shutil.which("appimagetool")
    if not appimagetool:
        return None

    print("\n📦 Packaging AppImage using appimagetool...")
    app_dir = BUILD_DIR / "AppDir"
    if app_dir.exists():
        shutil.rmtree(app_dir, ignore_errors=True)

    opt_dir = app_dir / "opt" / "strand"
    opt_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle_dir, opt_dir, dirs_exist_ok=True)

    apprun = app_dir / "AppRun"
    apprun.write_text(
        "#!/bin/sh\n"
        "SELF=$(readlink -f \"$0\")\n"
        "HERE=${SELF%/*}\n"
        "if [ -f \"${HERE}/opt/strand/resources/ca-certificates.crt\" ]; then\n"
        "  export SSL_CERT_FILE=\"${HERE}/opt/strand/resources/ca-certificates.crt\"\n"
        "  export GIT_SSL_CAINFO=\"${HERE}/opt/strand/resources/ca-certificates.crt\"\n"
        "fi\n"
        "export PATH=\"${HERE}/opt/strand:${PATH}\"\n"
        "export LD_LIBRARY_PATH=\"${HERE}/opt/strand:${LD_LIBRARY_PATH}\"\n"
        "exec \"${HERE}/opt/strand/strand\" \"$@\"\n",
        encoding="utf-8",
    )
    apprun.chmod(0o755)

    desktop_src = ROOT_DIR / "resources" / "strand.desktop"
    if desktop_src.exists():
        shutil.copy(desktop_src, app_dir / "strand.desktop")

    icon_src = ROOT_DIR / "resources" / "icons" / "strand.png"
    if icon_src.exists():
        shutil.copy(icon_src, app_dir / "strand.png")
        shutil.copy(icon_src, app_dir / ".DirIcon")

    appimage_path = output_dir / f"Strand-{version}-x86_64.AppImage"
    cmd = [appimagetool, "--no-appstream", str(app_dir), str(appimage_path)]
    env = dict(os.environ, ARCH="x86_64")
    res = subprocess.run(cmd, env=env, capture_output=True)
    if res.returncode == 0 and appimage_path.exists():
        print(f"✅ AppImage created: {appimage_path}")
        return appimage_path
    else:
        print(f"⚠️ appimagetool returned code {res.returncode}")
        if res.stderr:
            print(res.stderr.decode("utf-8", errors="replace"))
        if res.stdout:
            print(res.stdout.decode("utf-8", errors="replace"))
        return None


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
            if file_path.suffix in (".zip", ".gz", ".whl", ".AppImage", ".deb", ".rpm"):
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
