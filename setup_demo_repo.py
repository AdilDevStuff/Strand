"""Utility to generate a rich sample repository for testing and visual demonstration."""

import os
import shutil
import time
import pygit2


def create_demo_repository(target_dir: str):
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir, ignore_errors=True)
    os.makedirs(target_dir, exist_ok=True)

    repo = pygit2.init_repository(target_dir)
    repo.config["core.autocrlf"] = "false"
    sig = pygit2.Signature("Alice Engineer", "alice@example.com")

    # Commit 1 (main)
    file_readme = os.path.join(target_dir, "README.md")
    with open(file_readme, "w", encoding="utf-8") as f:
        f.write("# Git Client Demo\n\nHigh-performance GitFiend client.\n")
    repo.index.add("README.md")
    repo.index.write()
    c1_oid = repo.create_commit("HEAD", sig, sig, "Initial commit: project structure", repo.index.write_tree(), [])
    c1 = repo[c1_oid]

    # Commit 2 (main)
    file_main = os.path.join(target_dir, "main.py")
    with open(file_main, "w", encoding="utf-8") as f:
        f.write("def start():\n    print('Hello World')\n\nif __name__ == '__main__':\n    start()\n")
    repo.index.add("main.py")
    repo.index.write()
    c2_oid = repo.create_commit("HEAD", sig, sig, "feat: core application entrypoint", repo.index.write_tree(), [c1.id])
    c2 = repo[c2_oid]

    # Branch: feature/theme
    branch_feat = repo.create_branch("feature/dark-theme", c2)
    
    # Commit on feature branch
    file_theme = os.path.join(target_dir, "theme.py")
    with open(file_theme, "w", encoding="utf-8") as f:
        f.write("BG_PRIMARY = '#18181b'\nACCENT = '#3b82f6'\n")
    repo.index.add("theme.py")
    repo.index.write()
    sig_bob = pygit2.Signature("Bob Designer", "bob@example.com")
    c3_feat_oid = repo.create_commit(branch_feat.name, sig_bob, sig_bob, "feat: add dark theme palette tokens", repo.index.write_tree(), [c2.id])

    # Commit on main
    with open(file_readme, "a", encoding="utf-8") as f:
        f.write("\n## Features\n- Virtual graph rendering\n- Bezier curve tracks\n")
    repo.index.add("README.md")
    repo.index.write()
    c4_main_oid = repo.create_commit("HEAD", sig, sig, "docs: add features list to README", repo.index.write_tree(), [c2.id])
    c4 = repo[c4_main_oid]

    # Merge commit
    with open(file_theme, "w", encoding="utf-8") as f:
        f.write("BG_PRIMARY = '#18181b'\nACCENT = '#3b82f6'\nTEXT_PRIMARY = '#fafafa'\n")
    repo.index.add("theme.py")
    repo.index.write()
    c_merge_oid = repo.create_commit("HEAD", sig, sig, "Merge branch 'feature/dark-theme' into main", repo.index.write_tree(), [c4.id, c3_feat_oid])

    # Unstaged modifications in working directory
    with open(file_main, "a", encoding="utf-8") as f:
        f.write("\ndef configure_logging():\n    pass\n")

    # Staged modification
    file_config = os.path.join(target_dir, "config.json")
    with open(file_config, "w", encoding="utf-8") as f:
        f.write('{\n  "version": "1.0.0",\n  "debug": true\n}\n')
    repo.index.add("config.json")
    repo.index.write()

    # Untracked file
    file_untracked = os.path.join(target_dir, "scratch_notes.txt")
    with open(file_untracked, "w", encoding="utf-8") as f:
        f.write("Quick developer notes for testing diffs.\n")

    print(f"Created demo repository at: {target_dir}")


if __name__ == "__main__":
    demo_path = os.path.abspath("demo_repo")
    create_demo_repository(demo_path)
