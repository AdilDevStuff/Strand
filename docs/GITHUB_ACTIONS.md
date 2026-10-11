# GitHub Actions & Automated Releases for Strand

This guide explains how CI/CD and automated releases are configured for Strand on [GitHub](https://github.com/AdilDevStuff/Strand).

---

## 1. Overview of Automated Pipelines

Strand includes GitHub Actions workflows in `.github/workflows/`:

1. **Continuous Integration (`.github/workflows/ci.yml`)**:
   - Triggers on `push` to `main` and on all Pull Requests targeting `main`.
   - Sets up Python 3.12, installs system dependencies (`libgit2-dev`, `libgl1-mesa-glx`, `xvfb`), installs Python dependencies, runs the full test suite (`xvfb-run pytest`), and verifies package generation.

2. **Automated Releases (`.github/workflows/release.yml`)**:
   - Triggers when a git version tag is pushed (e.g. `v0.1.0`).
   - Automatically compiles standalone Linux binaries (`.tar.gz`), Python wheels (`.whl`), and calculates cryptographic `SHA256SUMS.txt`.
   - Publishes a **GitHub Release** with all assets and auto-generated release notes using `softprops/action-gh-release@v2`.

---

## 2. Triggering an Automated Release

To publish a new release:

```bash
# Tag the commit
git tag v0.1.0

# Push the tag to GitHub
git push origin v0.1.0
```

GitHub Actions will automatically run the release pipeline, compile the release binaries, and create the release page at:
`https://github.com/AdilDevStuff/Strand/releases`

---

## 3. Local Build Testing

You can run the build script locally at any time:

```bash
# Build standalone bundle only
python build.py

# Build both standalone binary and Python packages (sdist + wheel)
python build.py --clean --package

# Inspect generated files
ls -lh dist/
```
