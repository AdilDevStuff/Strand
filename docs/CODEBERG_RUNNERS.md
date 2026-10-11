# Setting Up Codeberg Runners & Automated Releases for Strand

This guide explains how automated builds and releases work for Strand on [Codeberg](https://codeberg.org), and how to configure Codeberg runners (Forgejo Actions and Woodpecker CI).

---

## 1. Overview of Automated Pipelines

Strand includes two CI/CD configurations for Codeberg:

1. **Codeberg Actions / Forgejo Actions (Primary)**:
   - `.forgejo/workflows/ci.yaml`: Runs tests and build validation on `main` and Pull Requests.
   - `.forgejo/workflows/release.yaml`: Automatically builds standalone Linux binaries (`.tar.gz`), Python wheels (`.whl`), and `SHA256SUMS.txt`, publishing them directly to **Codeberg Releases** when a version tag (`v*`) is pushed.

2. **Codeberg Woodpecker CI (Alternative)**:
   - `.woodpecker/release.yml`: Configured for repositories using Codeberg's hosted Woodpecker CI service (`ci.codeberg.org`).

---

## 2. Setting Up Codeberg Actions (Forgejo Actions)

Codeberg runs on Forgejo, which uses Forgejo Actions (compatible with GitHub Actions syntax) powered by `forgejo-runner`.

### Step 1: Enable Actions in Your Repository
1. Go to your repository on Codeberg.
2. Navigate to **Settings** > **Units**.
3. Under **Repository Units**, check **Actions**.
4. Click **Update Settings**.

### Step 2: Register a Runner (Self-Hosted Runner)
Codeberg provides limited shared runners for public projects; for guaranteed build availability and desktop library support, you can register a runner on your server or machine:

1. In your repository on Codeberg, go to **Settings** > **Actions** > **Runners**.
2. Click **Create new Runner** and copy the **Registration Token**.
3. Run `forgejo-runner` using Docker:

```bash
docker run -d \
  --name forgejo-runner \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e FORGEJO_INSTANCE="https://codeberg.org" \
  -e FORGEJO_RUNNER_TOKEN="<YOUR_REGISTRATION_TOKEN>" \
  -e FORGEJO_RUNNER_NAME="strand-runner" \
  -e FORGEJO_RUNNER_LABELS="docker:docker://catthehacker/ubuntu:act-latest,ubuntu-latest:docker://catthehacker/ubuntu:act-latest" \
  code.forgejo.org/forgejo/runner:latest
```

Or using `docker-compose.yml`:
```yaml
version: "3.8"
services:
  runner:
    image: code.forgejo.org/forgejo/runner:latest
    restart: always
    environment:
      FORGEJO_INSTANCE: "https://codeberg.org"
      FORGEJO_RUNNER_TOKEN: "<YOUR_REGISTRATION_TOKEN>"
      FORGEJO_RUNNER_NAME: "strand-builder"
      FORGEJO_RUNNER_LABELS: "docker:docker://catthehacker/ubuntu:act-latest,ubuntu-latest:docker://catthehacker/ubuntu:act-latest"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

### Step 3: Triggering an Automatic Release
To create a release, push a git version tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The `.forgejo/workflows/release.yaml` workflow will automatically:
1. Check out the tagged commit.
2. Install system packages (`libgit2-dev`, `libgl1-mesa-glx`, `build-essential`).
3. Run `python build.py --clean --package` to generate:
   - Standalone Linux application bundle (`dist/strand-0.1.0-linux-x86_64.tar.gz`)
   - Python Wheel distribution (`dist/strand-0.1.0-py3-none-any.whl`)
   - Release checksums (`dist/SHA256SUMS.txt`)
4. Create a new Release in Codeberg with the attached binaries, release title, and generated release notes using the built-in `${{ secrets.GITHUB_TOKEN }}`.

---

## 3. Alternative: Setting Up Woodpecker CI (ci.codeberg.org)

If you use Codeberg's dedicated Woodpecker CI instance:

1. Log in to [ci.codeberg.org](https://ci.codeberg.org) with your Codeberg account.
2. Enable your repository in the dashboard.
3. In repository settings on Woodpecker, add a secret named `codeberg_token`:
   - Generate a Personal Access Token on Codeberg (**Settings** > **Applications** > **Generate Token**) with `repo` scope.
4. When you push a tag (`v*`), Woodpecker runs `.woodpecker/release.yml` and attaches the release binaries using `woodpeckerci/plugin-release`.

---

## 4. Local Build Testing

You can run the build script locally at any time:

```bash
# Build standalone bundle only
python build.py

# Build both standalone binary and Python wheel / sdist
python build.py --clean --package

# Inspect generated files
ls -lh dist/
```
