"""Core data models and abstractions for the Git engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class FileStatus(Enum):
    """Enumeration of possible Git file states."""
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    UNTRACKED = "untracked"
    RENAMED = "renamed"
    TYPECHANGE = "typechange"
    CONFLICTED = "conflicted"

    @property
    def short_char(self) -> str:
        """Single-letter status identifier for UI display."""
        mapping = {
            FileStatus.MODIFIED: "M",
            FileStatus.ADDED: "A",
            FileStatus.DELETED: "D",
            FileStatus.UNTRACKED: "U",
            FileStatus.RENAMED: "R",
            FileStatus.TYPECHANGE: "T",
            FileStatus.CONFLICTED: "C",
        }
        return mapping.get(self, "?")


class DiffLineType(Enum):
    """Type of line in a unified diff hunk."""
    CONTEXT = " "
    ADDITION = "+"
    DELETION = "-"
    HEADER = "@"


@dataclass(slots=True)
class DiffLine:
    """Represents a single line within a diff hunk."""
    line_type: DiffLineType
    content: str
    old_lineno: Optional[int] = None
    new_lineno: Optional[int] = None

    @property
    def prefix(self) -> str:
        return self.line_type.value


@dataclass(slots=True)
class Hunk:
    """Represents a structured diff hunk with metadata and actionable patch generator."""
    file_path: str
    header: str
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: List[DiffLine] = field(default_factory=list)
    is_staged: bool = False
    hunk_index: int = 0

    @property
    def additions_count(self) -> int:
        return sum(1 for line in self.lines if line.line_type == DiffLineType.ADDITION)

    @property
    def deletions_count(self) -> int:
        return sum(1 for line in self.lines if line.line_type == DiffLineType.DELETION)

    def to_patch(self, reverse: bool = False) -> str:
        """
        Generate a valid unified diff patch string for this single hunk.
        Can be applied directly with `git apply`.
        If reverse is True, generates a patch that inverts the hunk (for unstaging/discarding).
        """
        old_file = f"a/{self.file_path}"
        new_file = f"b/{self.file_path}"
        
        patch_header = [
            f"--- {old_file}",
            f"+++ {new_file}",
        ]

        if not reverse:
            hunk_hdr = f"@@ -{self.old_start},{self.old_lines} +{self.new_start},{self.new_lines} @@"
            lines_out = []
            for line in self.lines:
                lines_out.append(f"{line.prefix}{line.content}")
        else:
            # Reversing: additions become deletions, deletions become additions
            hunk_hdr = f"@@ -{self.new_start},{self.new_lines} +{self.old_start},{self.old_lines} @@"
            lines_out = []
            for line in self.lines:
                if line.line_type == DiffLineType.ADDITION:
                    lines_out.append(f"-{line.content}")
                elif line.line_type == DiffLineType.DELETION:
                    lines_out.append(f"+{line.content}")
                elif line.line_type == DiffLineType.CONTEXT:
                    lines_out.append(f" {line.content}")

        return "\n".join(patch_header + [hunk_hdr] + lines_out) + "\n"


@dataclass(slots=True)
class FileChange:
    """Represents a file with working-tree or index modifications."""
    file_path: str
    status: FileStatus
    is_staged: bool
    old_path: Optional[str] = None
    additions: int = 0
    deletions: int = 0

    @property
    def display_name(self) -> str:
        if self.old_path and self.status == FileStatus.RENAMED:
            return f"{self.old_path} -> {self.file_path}"
        return self.file_path


@dataclass(slots=True)
class GraphConnector:
    """Bezier curve routing coordinates between commit nodes in the DAG graph."""
    from_column: int
    to_column: int
    from_row: int
    to_row: int
    color_index: int
    is_merge: bool = False


@dataclass(slots=True)
class CommitNode:
    """Represents a commit in the topological graph."""
    hash: str
    short_hash: str
    author: str
    email: str
    timestamp: int
    datetime_str: str = ""
    parent_hashes: List[str] = field(default_factory=list)
    message: str = ""
    summary: str = ""
    refs: List[str] = field(default_factory=list)
    column: int = 0
    row: int = 0
    color_index: int = 0
    connectors: List[GraphConnector] = field(default_factory=list)

    @property
    def is_merge(self) -> bool:
        return len(self.parent_hashes) > 1
