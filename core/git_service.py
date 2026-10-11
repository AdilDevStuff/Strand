"""High-performance Git service wrapping pygit2 with CLI fallback integration."""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import threading
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import pygit2

from core.models import (
    CommitNode,
    DiffLine,
    DiffLineType,
    FileChange,
    FileStatus,
    Hunk,
)


def find_git_executable() -> str:
    """
    Locates the best available Git executable across standard installation paths.
    Prioritizes full binary git over batch/cmd wrappers on Windows.
    """
    # 1. Check known GitHub Desktop git distributions on Windows
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        gh_root = os.path.join(local_app_data, "GitHubDesktop")
        if os.path.isdir(gh_root):
            for entry in sorted(os.listdir(gh_root), reverse=True):
                if entry.startswith("app-"):
                    candidate = os.path.join(
                        gh_root, entry, "resources", "app", "git", "cmd", "git.exe"
                    )
                    if os.path.isfile(candidate):
                        return candidate

    # 2. Check standard Program Files
    prog_files = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    for pf in prog_files:
        candidate = os.path.join(pf, "Git", "cmd", "git.exe")
        if os.path.isfile(candidate):
            return candidate

    # 3. System PATH lookup
    system_git = shutil.which("git.exe") or shutil.which("git")
    if system_git:
        return system_git

    return "git"


class GitService:
    """
    Thread-safe Git engine interface wrapping pygit2 for zero-latency in-memory
    inspection and manipulation, paired with CLI fallback for advanced operations.
    """

    def __init__(self, repo_path: str) -> None:
        self.repo_path = os.path.abspath(repo_path)
        self.git_bin = find_git_executable()
        self._lock = threading.RLock()
        # Initialize or discover repository
        discovered = pygit2.discover_repository(self.repo_path)
        if not discovered:
            raise ValueError(f"No git repository found at {self.repo_path}")
        self.repo = pygit2.Repository(discovered)

    def refresh(self) -> None:
        """Reload repository in-memory state and index from disk."""
        with self._lock:
            self.repo.index.read()

    @property
    def is_empty(self) -> bool:
        """True if the repository has no commits yet."""
        return self.repo.head_is_unborn

    def get_current_branch(self) -> str:
        """Return the active branch name or short commit hash if detached."""
        if self.repo.head_is_unborn:
            return "master"
        if self.repo.head_is_detached:
            return str(self.repo.head.target)[:7]
        return self.repo.head.shorthand

    def get_status(self) -> List[FileChange]:
        """
        Inspect working tree and index status.
        Emits separate FileChange records for staged and unstaged states of the same file.
        """
        self.refresh()
        status_dict = self.repo.status()
        changes: List[FileChange] = []

        # Bitmask constants
        idx_flags = (
            pygit2.GIT_STATUS_INDEX_NEW
            | pygit2.GIT_STATUS_INDEX_MODIFIED
            | pygit2.GIT_STATUS_INDEX_DELETED
            | pygit2.GIT_STATUS_INDEX_RENAMED
            | pygit2.GIT_STATUS_INDEX_TYPECHANGE
        )
        wt_flags = (
            pygit2.GIT_STATUS_WT_NEW
            | pygit2.GIT_STATUS_WT_MODIFIED
            | pygit2.GIT_STATUS_WT_DELETED
            | pygit2.GIT_STATUS_WT_RENAMED
            | pygit2.GIT_STATUS_WT_TYPECHANGE
        )

        for path, flags in status_dict.items():
            if flags & pygit2.GIT_STATUS_IGNORED:
                continue

            # 1. Staged section
            if flags & idx_flags:
                staged_status = FileStatus.MODIFIED
                if flags & pygit2.GIT_STATUS_INDEX_NEW:
                    staged_status = FileStatus.ADDED
                elif flags & pygit2.GIT_STATUS_INDEX_DELETED:
                    staged_status = FileStatus.DELETED
                elif flags & pygit2.GIT_STATUS_INDEX_RENAMED:
                    staged_status = FileStatus.RENAMED
                elif flags & pygit2.GIT_STATUS_INDEX_TYPECHANGE:
                    staged_status = FileStatus.TYPECHANGE

                changes.append(
                    FileChange(
                        file_path=path,
                        status=staged_status,
                        is_staged=True,
                    )
                )

            # 2. Unstaged section
            if flags & wt_flags:
                wt_status = FileStatus.MODIFIED
                if flags & pygit2.GIT_STATUS_WT_NEW:
                    wt_status = FileStatus.UNTRACKED
                elif flags & pygit2.GIT_STATUS_WT_DELETED:
                    wt_status = FileStatus.DELETED
                elif flags & pygit2.GIT_STATUS_WT_RENAMED:
                    wt_status = FileStatus.RENAMED
                elif flags & pygit2.GIT_STATUS_WT_TYPECHANGE:
                    wt_status = FileStatus.TYPECHANGE

                changes.append(
                    FileChange(
                        file_path=path,
                        status=wt_status,
                        is_staged=False,
                    )
                )

            # 3. Conflicted state
            if flags & pygit2.GIT_STATUS_CONFLICTED:
                changes.append(
                    FileChange(
                        file_path=path,
                        status=FileStatus.CONFLICTED,
                        is_staged=False,
                    )
                )

        return changes

    def get_diff(self, file_path: str, staged: bool) -> List[Hunk]:
        """
        Produce a list of structured Hunks for a given file.
        staged=True diffs Index against HEAD.
        staged=False diffs Working Tree against Index.
        """
        self.refresh()
        norm_path = file_path.replace("\\", "/")

        if staged:
            # Diff index against HEAD
            if self.repo.head_is_unborn:
                empty_tree_oid = self.repo.TreeBuilder().write()
                diff = self.repo.diff(self.repo[empty_tree_oid], None, cached=True)
            else:
                head_commit = self.repo.head.peel(pygit2.Commit)
                diff = self.repo.diff(head_commit.tree, None, cached=True)
        else:
            # Diff workdir against index, including untracked files
            diff = self.repo.diff(flags=pygit2.GIT_DIFF_INCLUDE_UNTRACKED)

        hunks_out: List[Hunk] = []
        target_patch: Optional[pygit2.Patch] = None

        for patch in diff:
            p_old = patch.delta.old_file.path.replace("\\", "/")
            p_new = patch.delta.new_file.path.replace("\\", "/")
            if p_old == norm_path or p_new == norm_path:
                target_patch = patch
                break

        if target_patch is not None and len(target_patch.hunks) > 0:
            for h_idx, raw_hunk in enumerate(target_patch.hunks):
                hdr = raw_hunk.header.strip()
                lines: List[DiffLine] = []
                for raw_line in raw_hunk.lines:
                    origin = raw_line.origin
                    content = raw_line.content
                    if content.endswith("\r\n"):
                        content = content[:-2]
                    elif content.endswith("\n"):
                        content = content[:-1]

                    if origin == "+":
                        l_type = DiffLineType.ADDITION
                    elif origin == "-":
                        l_type = DiffLineType.DELETION
                    elif origin == "@":
                        l_type = DiffLineType.HEADER
                    else:
                        l_type = DiffLineType.CONTEXT

                    lines.append(
                        DiffLine(
                            line_type=l_type,
                            content=content,
                            old_lineno=raw_line.old_lineno if raw_line.old_lineno > 0 else None,
                            new_lineno=raw_line.new_lineno if raw_line.new_lineno > 0 else None,
                        )
                    )

                hunks_out.append(
                    Hunk(
                        file_path=norm_path,
                        header=hdr,
                        old_start=raw_hunk.old_start,
                        old_lines=raw_hunk.old_lines,
                        new_start=raw_hunk.new_start,
                        new_lines=raw_hunk.new_lines,
                        lines=lines,
                        is_staged=staged,
                        hunk_index=h_idx,
                    )
                )
        else:
            # Synthetic hunk for untracked files
            full_path = os.path.join(self.repo_path, norm_path)
            if not staged and os.path.isfile(full_path) and (norm_path not in self.repo.index):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        file_lines = f.read().splitlines()
                    
                    diff_lines = [
                        DiffLine(
                            line_type=DiffLineType.ADDITION,
                            content=line,
                            old_lineno=None,
                            new_lineno=idx + 1,
                        )
                        for idx, line in enumerate(file_lines)
                    ]
                    hunks_out.append(
                        Hunk(
                            file_path=norm_path,
                            header=f"@@ -0,0 +1,{len(file_lines)} @@",
                            old_start=0,
                            old_lines=0,
                            new_start=1,
                            new_lines=len(file_lines),
                            lines=diff_lines,
                            is_staged=False,
                            hunk_index=0,
                        )
                    )
                except Exception:
                    pass

        return hunks_out

    def stage_file(self, path: str) -> None:
        """Stage an entire modified, newly created, or deleted file."""
        self.refresh()
        norm_path = path.replace("\\", "/")
        full_path = os.path.join(self.repo_path, norm_path)

        if os.path.exists(full_path):
            self.repo.index.add(norm_path)
        else:
            # File was deleted in working tree
            if norm_path in self.repo.index:
                self.repo.index.remove(norm_path)
        self.repo.index.write()

    def unstage_file(self, path: str) -> None:
        """Unstage a file from the index back to the HEAD state."""
        self.refresh()
        norm_path = path.replace("\\", "/")

        if self.repo.head_is_unborn:
            # Initial commit: unstage means removing from index
            if norm_path in self.repo.index:
                self.repo.index.remove(norm_path)
            self.repo.index.write()
            return

        head_commit = self.repo.head.peel(pygit2.Commit)
        try:
            entry = head_commit.tree[norm_path]
            idx_entry = pygit2.IndexEntry(norm_path, entry.id, entry.filemode)
            self.repo.index.add(idx_entry)
        except KeyError:
            # File did not exist in HEAD commit (was newly added and staged)
            if norm_path in self.repo.index:
                self.repo.index.remove(norm_path)
        self.repo.index.write()

    def stage_all(self) -> None:
        """Stage all modified, untracked, and deleted files to the index."""
        self.refresh()
        self.repo.index.add_all()
        self.repo.index.write()

    def unstage_all(self) -> None:
        """Unstage all files from the index back to HEAD."""
        self.refresh()
        if self.repo.head_is_unborn:
            self.repo.index.clear()
            self.repo.index.write()
            return
        head_commit = self.repo.head.peel(pygit2.Commit)
        self.repo.index.read_tree(head_commit.tree)
        self.repo.index.write()

    def stage_hunk(self, hunk: Hunk) -> None:
        """
        Stage a single hunk to the index without affecting other unstaged changes.
        Uses git apply --cached with normalized LF bytes.
        """
        self.refresh()
        self.repo.index.write()
        patch_text = hunk.to_patch(reverse=False)
        # Normalize to LF
        patch_bytes = patch_text.replace("\r\n", "\n").encode("utf-8")

        result = subprocess.run(
            [self.git_bin, "apply", "--cached", "--unidiff-zero", "--whitespace=nowarn", "-"],
            input=patch_bytes,
            cwd=self.repo_path,
            capture_output=True,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed to stage hunk: {err}")
        self.refresh()

    def unstage_hunk(self, hunk: Hunk) -> None:
        """
        Unstage a single hunk from the index back to unstaged.
        Uses git apply --cached --reverse.
        """
        self.refresh()
        self.repo.index.write()
        patch_text = hunk.to_patch(reverse=False)
        patch_bytes = patch_text.replace("\r\n", "\n").encode("utf-8")

        result = subprocess.run(
            [self.git_bin, "apply", "--cached", "--reverse", "--whitespace=nowarn", "-"],
            input=patch_bytes,
            cwd=self.repo_path,
            capture_output=True,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed to unstage hunk: {err}")
        self.refresh()

    def discard_hunk(self, hunk: Hunk) -> None:
        """
        Discard changes for a single hunk in the working tree.
        Uses git apply --reverse against working tree.
        """
        self.refresh()
        patch_text = hunk.to_patch(reverse=False)
        patch_bytes = patch_text.replace("\r\n", "\n").encode("utf-8")

        result = subprocess.run(
            [self.git_bin, "apply", "--reverse", "--whitespace=nowarn", "-"],
            input=patch_bytes,
            cwd=self.repo_path,
            capture_output=True,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed to discard hunk: {err}")
        self.refresh()

    def commit(self, message: str, amend: bool = False) -> str:
        """
        Commit staged changes. Returns the hex commit hash.
        """
        if not message.strip():
            raise ValueError("Commit message cannot be empty")

        self.refresh()
        tree_oid = self.repo.index.write_tree()

        # Resolve author and committer signatures
        try:
            author = self.repo.default_signature
        except KeyError:
            # Fallback signature if git config is unset
            name = os.environ.get("GIT_AUTHOR_NAME") or os.environ.get("USERNAME") or "Git User"
            email = os.environ.get("GIT_AUTHOR_EMAIL") or "git@local"
            author = pygit2.Signature(name, email)
        committer = author

        if amend:
            if self.repo.head_is_unborn:
                raise ValueError("Cannot amend commit in an unborn repository")
            head_commit = self.repo.head.peel(pygit2.Commit)
            commit_oid = self.repo.create_commit(
                None,
                author,
                committer,
                message.strip() + "\n",
                tree_oid,
                list(head_commit.parent_ids),
            )
            if self.repo.head_is_detached:
                self.repo.set_head(commit_oid)
            else:
                self.repo.references[self.repo.head.name].set_target(commit_oid)
        else:
            parents: List[pygit2.Oid] = []
            if not self.repo.head_is_unborn:
                parents = [self.repo.head.target]

            commit_oid = self.repo.create_commit(
                "HEAD",
                author,
                committer,
                message.strip() + "\n",
                tree_oid,
                parents,
            )

        self.repo.index.write()
        return str(commit_oid)

    def get_branches(self) -> Dict[str, List[str]]:
        """Return lists of local and remote branch names."""
        self.refresh()
        local_branches = list(self.repo.branches.local)
        remote_branches = list(self.repo.branches.remote)
        return {"local": local_branches, "remote": remote_branches}

    def checkout(self, branch_name: str) -> None:
        """Switch to a specified branch or commit."""
        self.refresh()
        clean_name = branch_name.strip()
        
        # Check if local branch
        if clean_name in self.repo.branches.local:
            ref_name = f"refs/heads/{clean_name}"
            self.repo.checkout(ref_name)
            return

        # Check full ref
        if clean_name.startswith("refs/"):
            self.repo.checkout(clean_name)
            return

        # Check remote branch or commit hash
        try:
            obj = self.repo.revparse_single(clean_name)
            commit = obj.peel(pygit2.Commit)
            self.repo.checkout_tree(commit)
            self.repo.set_head(commit.id)
        except Exception as e:
            raise ValueError(f"Could not checkout '{clean_name}': {e}")

    def get_commit_history(self, max_count: int = 500) -> List[CommitNode]:
        """
        Walk all commit DAG branches and construct CommitNodes with branch/tag badges.
        """
        self.refresh()
        if self.repo.head_is_unborn:
            return []

        # Map commit hashes to branch and tag references
        refs_map: Dict[str, List[str]] = defaultdict(list)
        for ref_name in self.repo.references:
            try:
                ref = self.repo.references[ref_name]
                target_oid = ref.target
                if isinstance(target_oid, pygit2.Oid):
                    refs_map[str(target_oid)].append(ref.shorthand)
            except Exception:
                pass

        walker = self.repo.walk(self.repo.head.target, pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_TIME)
        for ref_name in self.repo.references:
            try:
                ref = self.repo.references[ref_name]
                if isinstance(ref.target, pygit2.Oid):
                    walker.push(ref.target)
            except Exception:
                pass

        commits: List[CommitNode] = []
        for c in walker:
            commit_hash = str(c.id)
            c_time = c.commit_time
            dt_str = datetime.datetime.fromtimestamp(c_time).strftime("%Y-%m-%d %H:%M")
            msg = c.message or ""
            summary = msg.splitlines()[0] if msg else ""

            commits.append(
                CommitNode(
                    hash=commit_hash,
                    short_hash=commit_hash[:7],
                    author=c.author.name if c.author else "Unknown",
                    email=c.author.email if c.author else "",
                    timestamp=c_time,
                    datetime_str=dt_str,
                    parent_hashes=[str(p) for p in c.parent_ids],
                    message=msg,
                    summary=summary,
                    refs=refs_map.get(commit_hash, []),
                )
            )
            if len(commits) >= max_count:
                break

        return commits

    def get_remote_sync_status(self) -> Tuple[int, int]:
        """
        Return (ahead_count, behind_count) relative to upstream tracking branch.
        """
        if self.repo.head_is_unborn or self.repo.head_is_detached:
            return (0, 0)

        try:
            branch = self.repo.branches.local[self.repo.head.shorthand]
            upstream = branch.upstream
            if upstream is None:
                return (0, 0)
            ahead, behind = self.repo.ahead_behind(branch.target, upstream.target)
            return (ahead, behind)
        except Exception:
            return (0, 0)

    def create_branch(self, branch_name: str) -> None:
        """Create a new branch pointing at current HEAD."""
        self.refresh()
        if self.repo.head_is_unborn:
            raise ValueError("Cannot create branch in an empty repository with no commits.")
        commit = self.repo.head.peel(pygit2.Commit)
        self.repo.create_branch(branch_name, commit)

    def get_commit_details(self, commit_hash: str) -> Tuple[Optional[CommitNode], List[FileChange], Dict[str, List[Hunk]]]:
        """
        Inspect commit metadata, list of modified files, and structured hunks for each file.
        """
        self.refresh()
        try:
            obj = self.repo.revparse_single(commit_hash)
            c = obj.peel(pygit2.Commit)
        except Exception:
            return (None, [], {})

        c_time = c.commit_time
        dt_str = datetime.datetime.fromtimestamp(c_time).strftime("%Y-%m-%d %H:%M")
        msg = c.message or ""
        summary = msg.splitlines()[0] if msg else ""

        node = CommitNode(
            hash=str(c.id),
            short_hash=str(c.id)[:7],
            author=c.author.name if c.author else "Unknown",
            email=c.author.email if c.author else "",
            timestamp=c_time,
            datetime_str=dt_str,
            parent_hashes=[str(p) for p in c.parent_ids],
            message=msg,
            summary=summary,
        )

        if c.parents:
            parent_tree = c.parents[0].tree
        else:
            empty_oid = self.repo.TreeBuilder().write()
            parent_tree = self.repo[empty_oid]

        diff = self.repo.diff(parent_tree, c.tree)
        file_changes: List[FileChange] = []
        hunks_by_file: Dict[str, List[Hunk]] = {}

        delta_status_map = {
            pygit2.GIT_DELTA_ADDED: FileStatus.ADDED,
            pygit2.GIT_DELTA_DELETED: FileStatus.DELETED,
            pygit2.GIT_DELTA_MODIFIED: FileStatus.MODIFIED,
            pygit2.GIT_DELTA_RENAMED: FileStatus.RENAMED,
            pygit2.GIT_DELTA_TYPECHANGE: FileStatus.TYPECHANGE,
        }

        for patch in diff:
            p_old = patch.delta.old_file.path.replace("\\", "/")
            p_new = patch.delta.new_file.path.replace("\\", "/")
            f_path = p_new if patch.delta.status != pygit2.GIT_DELTA_DELETED else p_old
            f_status = delta_status_map.get(patch.delta.status, FileStatus.MODIFIED)

            additions = sum(1 for h in patch.hunks for l in h.lines if l.origin == "+")
            deletions = sum(1 for h in patch.hunks for l in h.lines if l.origin == "-")

            file_changes.append(
                FileChange(
                    file_path=f_path,
                    status=f_status,
                    is_staged=True,
                    old_path=p_old if patch.delta.status == pygit2.GIT_DELTA_RENAMED else None,
                    additions=additions,
                    deletions=deletions,
                )
            )

            hunks: List[Hunk] = []
            for h_idx, raw_hunk in enumerate(patch.hunks):
                hdr = raw_hunk.header.strip()
                lines: List[DiffLine] = []
                for raw_line in raw_hunk.lines:
                    content = raw_line.content
                    if content.endswith("\r\n"):
                        content = content[:-2]
                    elif content.endswith("\n"):
                        content = content[:-1]

                    origin = raw_line.origin
                    if origin == "+":
                        l_type = DiffLineType.ADDITION
                    elif origin == "-":
                        l_type = DiffLineType.DELETION
                    elif origin == "@":
                        l_type = DiffLineType.HEADER
                    else:
                        l_type = DiffLineType.CONTEXT

                    lines.append(
                        DiffLine(
                            line_type=l_type,
                            content=content,
                            old_lineno=raw_line.old_lineno if raw_line.old_lineno > 0 else None,
                            new_lineno=raw_line.new_lineno if raw_line.new_lineno > 0 else None,
                        )
                    )

                hunks.append(
                    Hunk(
                        file_path=f_path,
                        header=hdr,
                        old_start=raw_hunk.old_start,
                        old_lines=raw_hunk.old_lines,
                        new_start=raw_hunk.new_start,
                        new_lines=raw_hunk.new_lines,
                        lines=lines,
                        is_staged=True,
                        hunk_index=h_idx,
                    )
                )

            hunks_by_file[f_path] = hunks

        return (node, file_changes, hunks_by_file)

    def push(self, remote: str = "origin") -> str:
        """Push commits to remote upstream via CLI fallback."""
        res = subprocess.run(
            [self.git_bin, "push", remote],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        return res.stdout.strip()

    def pull(self, remote: str = "origin") -> str:
        """Pull commits from remote upstream via CLI fallback."""
        res = subprocess.run(
            [self.git_bin, "pull", remote],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        return res.stdout.strip()

    def fetch(self, remote: str = "origin") -> str:
        """Fetch references from remote upstream via CLI fallback."""
        res = subprocess.run(
            [self.git_bin, "fetch", remote],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        return res.stdout.strip()

    # -------------------------------------------------------------------------
    # Stash Management
    # -------------------------------------------------------------------------

    def get_stashes(self) -> List[Dict[str, Any]]:
        """Return list of stashes with index, hash, message, and relative date."""
        self.refresh()
        res = subprocess.run(
            [self.git_bin, "stash", "list", "--pretty=format:%gd|%h|%gs|%cr"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return []

        stashes: List[Dict[str, Any]] = []
        for line in res.stdout.strip().splitlines():
            parts = line.split("|")
            if len(parts) >= 4:
                ref, h, msg, cr = parts[0], parts[1], parts[2], parts[3]
                idx = 0
                if "{" in ref and "}" in ref:
                    try:
                        idx = int(ref.split("{")[1].split("}")[0])
                    except ValueError:
                        pass
                stashes.append({
                    "ref": ref,
                    "index": idx,
                    "hash": h,
                    "message": msg,
                    "date": cr,
                })
        return stashes

    def stash_save(self, message: str = "", include_untracked: bool = False, keep_index: bool = False) -> str:
        """Stash working tree changes."""
        self.refresh()
        cmd = [self.git_bin, "stash", "push"]
        if include_untracked:
            cmd.append("-u")
        if keep_index:
            cmd.append("--keep-index")
        if message.strip():
            cmd.extend(["-m", message.strip()])

        res = subprocess.run(cmd, cwd=self.repo_path, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        self.refresh()
        return res.stdout.strip()

    def stash_pop(self, index: int = 0) -> str:
        """Pop a stash by index and apply to working tree."""
        self.refresh()
        res = subprocess.run(
            [self.git_bin, "stash", "pop", f"stash@{{{index}}}"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        self.refresh()
        return res.stdout.strip()

    def stash_apply(self, index: int = 0) -> str:
        """Apply a stash by index without removing it from the stash stack."""
        self.refresh()
        res = subprocess.run(
            [self.git_bin, "stash", "apply", f"stash@{{{index}}}"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        self.refresh()
        return res.stdout.strip()

    def stash_drop(self, index: int = 0) -> str:
        """Drop a stash by index from the stash stack."""
        self.refresh()
        res = subprocess.run(
            [self.git_bin, "stash", "drop", f"stash@{{{index}}}"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        self.refresh()
        return res.stdout.strip()

    # -------------------------------------------------------------------------
    # Conflict Resolution
    # -------------------------------------------------------------------------

    def get_conflicted_files(self) -> List[str]:
        """Return list of file paths that currently have merge/rebase conflicts."""
        self.refresh()
        status_dict = self.repo.status()
        conflicted: List[str] = []
        for path, flags in status_dict.items():
            if flags & pygit2.GIT_STATUS_CONFLICTED:
                conflicted.append(path.replace("\\", "/"))
        return conflicted

    def resolve_conflict(self, file_path: str, strategy: str = "ours") -> None:
        """
        Resolve a merge conflict for a file using 'ours', 'theirs', or 'mark_resolved'.
        """
        self.refresh()
        norm_path = file_path.replace("\\", "/")
        full_path = os.path.join(self.repo_path, norm_path)

        if strategy in ("ours", "theirs"):
            handled = False
            if os.path.isfile(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                except Exception:
                    lines = []

                if any(l.startswith("<<<<<<<") for l in lines):
                    resolved_lines = []
                    in_conflict = False
                    in_theirs = False
                    for line in lines:
                        if line.startswith("<<<<<<<"):
                            in_conflict = True
                            in_theirs = False
                        elif line.startswith("=======") and in_conflict:
                            in_theirs = True
                        elif line.startswith(">>>>>>>") and in_conflict:
                            in_conflict = False
                            in_theirs = False
                        else:
                            if not in_conflict:
                                resolved_lines.append(line)
                            elif strategy == "ours" and not in_theirs:
                                resolved_lines.append(line)
                            elif strategy == "theirs" and in_theirs:
                                resolved_lines.append(line)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.writelines(resolved_lines)
                    handled = True

            if not handled:
                subprocess.run(
                    [self.git_bin, "checkout", f"--{strategy}", "--", norm_path],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                )

            self.stage_file(norm_path)
        elif strategy == "mark_resolved":
            self.stage_file(norm_path)
        else:
            raise ValueError(f"Unknown conflict resolution strategy: {strategy}")

    def parse_conflict_blocks(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Parse Git conflict markers (<<<<<<<, =======, >>>>>>>) from a conflicted file.
        Returns a list of structured conflict blocks.
        """
        full_path = os.path.join(self.repo_path, file_path.replace("\\", "/"))
        if not os.path.isfile(full_path):
            return []

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            return []

        blocks: List[Dict[str, Any]] = []
        in_conflict = False
        in_theirs = False
        current_ours: List[str] = []
        current_theirs: List[str] = []
        start_line = 0

        for idx, line in enumerate(lines):
            if line.startswith("<<<<<<<"):
                in_conflict = True
                in_theirs = False
                current_ours = []
                current_theirs = []
                start_line = idx + 1
            elif line.startswith("=======") and in_conflict:
                in_theirs = True
            elif line.startswith(">>>>>>>") and in_conflict:
                in_conflict = False
                in_theirs = False
                blocks.append({
                    "start_line": start_line,
                    "end_line": idx + 1,
                    "ours": "".join(current_ours),
                    "theirs": "".join(current_theirs),
                })
            else:
                if in_conflict:
                    if in_theirs:
                        current_theirs.append(line)
                    else:
                        current_ours.append(line)

        return blocks

    # -------------------------------------------------------------------------
    # History Operations & Tags
    # -------------------------------------------------------------------------

    def revert_commit(self, commit_hash: str) -> str:
        """Revert a commit by creating an inverse commit."""
        self.refresh()
        res = subprocess.run(
            [self.git_bin, "revert", "--no-edit", commit_hash],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        self.refresh()
        return res.stdout.strip()

    def reset(self, target: str = "HEAD~1", mode: str = "mixed") -> str:
        """Reset HEAD to target with specified mode ('soft', 'mixed', 'hard')."""
        self.refresh()
        if mode not in ("soft", "mixed", "hard"):
            raise ValueError(f"Invalid reset mode: {mode}")
        res = subprocess.run(
            [self.git_bin, "reset", f"--{mode}", target],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        self.refresh()
        return res.stdout.strip()

    def get_tags(self) -> List[Dict[str, str]]:
        """Return list of local tags with name and target commit hash."""
        self.refresh()
        tags: List[Dict[str, str]] = []
        for ref_name in self.repo.references:
            if ref_name.startswith("refs/tags/"):
                ref = self.repo.references[ref_name]
                tag_name = ref.shorthand
                try:
                    target_obj = ref.peel(pygit2.Commit)
                    target_oid = str(target_obj.id)
                except Exception:
                    target_oid = str(ref.target) if isinstance(ref.target, pygit2.Oid) else ""
                tags.append({
                    "name": tag_name,
                    "hash": target_oid[:7],
                    "full_hash": target_oid,
                })
        return sorted(tags, key=lambda t: t["name"])

    def create_tag(self, name: str, commit_hash: Optional[str] = None, message: str = "") -> None:
        """Create a tag pointing at a commit or current HEAD."""
        self.refresh()
        cmd = [self.git_bin, "tag"]
        if message.strip():
            cmd.extend(["-a", name.strip(), "-m", message.strip()])
        else:
            cmd.append(name.strip())
        if commit_hash:
            cmd.append(commit_hash.strip())

        res = subprocess.run(cmd, cwd=self.repo_path, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        self.refresh()

    def delete_tag(self, name: str) -> None:
        """Delete a local tag."""
        self.refresh()
        res = subprocess.run([self.git_bin, "tag", "-d", name.strip()], cwd=self.repo_path, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or res.stdout.strip())
        self.refresh()

