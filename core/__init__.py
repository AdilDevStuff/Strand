"""Core backend Git abstractions and graph modeling."""

from core.models import (
    CommitNode,
    DiffLine,
    DiffLineType,
    FileChange,
    FileStatus,
    GraphConnector,
    Hunk,
)
from core.graph_builder import GraphBuilder
from core.git_service import GitService, find_git_executable

__all__ = [
    "CommitNode",
    "DiffLine",
    "DiffLineType",
    "FileChange",
    "FileStatus",
    "GraphConnector",
    "Hunk",
    "GraphBuilder",
    "GitService",
    "find_git_executable",
]
