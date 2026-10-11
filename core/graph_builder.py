"""Topological sorting and branch lane layout engine for Git commit DAG graphs."""

from __future__ import annotations

from typing import Dict, List, Optional, Set
from collections import defaultdict, deque

from core.models import CommitNode, GraphConnector

# Palette of 8 harmonious low-contrast / modern colors (indices 0..7)
COLOR_PALETTE_SIZE = 8


class GraphBuilder:
    """
    Computes topological ordering, branch lane column allocations,
    and routing connectors (bezier merge and branch paths) for commit DAGs.
    """

    def __init__(self, palette_size: int = COLOR_PALETTE_SIZE) -> None:
        self.palette_size = palette_size

    def sort_topological(self, commits: List[CommitNode]) -> List[CommitNode]:
        """
        Sort commits topologically: children before parents,
        breaking ties by commit timestamp descending.
        """
        if not commits:
            return []

        commit_map: Dict[str, CommitNode] = {c.hash: c for c in commits}
        in_degree: Dict[str, int] = defaultdict(int)
        children_map: Dict[str, List[str]] = defaultdict(list)

        all_hashes = set(commit_map.keys())

        # Children depend on parents, but in visual order we want children first (row 0).
        # A parent cannot be shown until its children are visited in topological order.
        for node in commits:
            for p_hash in node.parent_hashes:
                if p_hash in all_hashes:
                    in_degree[p_hash] += 1
                    children_map[node.hash].append(p_hash)

        # Roots in reverse DAG: commits with no children in this set (in_degree in reverse sense)
        # i.e., heads/tips of branches
        tips = [c for c in commits if c.hash in all_hashes and sum(1 for ch in commits if c.hash in ch.parent_hashes) == 0]
        if not tips:
            # Fallback if cyclic or all have parents within set
            tips = [commits[0]]

        # Use priority queue / sorted deque by timestamp descending
        tips.sort(key=lambda c: c.timestamp, reverse=True)
        ready_queue: List[CommitNode] = list(tips)
        
        # Child count waiting on parents
        waiting_children = in_degree.copy()
        visited: Set[str] = set()
        result: List[CommitNode] = []

        while ready_queue:
            # Pick commit with latest timestamp among ready ones
            ready_queue.sort(key=lambda c: c.timestamp, reverse=True)
            current = ready_queue.pop(0)
            
            if current.hash in visited:
                continue
            visited.add(current.hash)
            result.append(current)

            for p_hash in current.parent_hashes:
                if p_hash in all_hashes:
                    waiting_children[p_hash] -= 1
                    if waiting_children[p_hash] <= 0 and p_hash not in visited:
                        ready_queue.append(commit_map[p_hash])

        # If any commits remain unvisited (disconnected components), add them sorted by time
        remaining = [c for c in commits if c.hash not in visited]
        if remaining:
            remaining.sort(key=lambda c: c.timestamp, reverse=True)
            result.extend(remaining)

        return result

    def build(self, commits: List[CommitNode]) -> List[CommitNode]:
        """
        Calculates branch lanes, column indices, colors, and routing connectors
        for the given list of commits.
        """
        if not commits:
            return []

        # Ensure topological order
        sorted_commits = self.sort_topological(commits)
        
        # active_tracks: active_tracks[col] = commit_hash expected in this column
        # None indicates a free lane that can be recycled
        active_tracks: List[Optional[str]] = []
        commit_by_hash: Dict[str, CommitNode] = {c.hash: c for c in sorted_commits}

        # Step 1: Assign rows and columns
        for row, node in enumerate(sorted_commits):
            node.row = row
            
            # Find if this commit is already expected on an active track
            assigned_col: Optional[int] = None
            if node.hash in active_tracks:
                assigned_col = active_tracks.index(node.hash)
            else:
                # Find the lowest free column index
                try:
                    assigned_col = active_tracks.index(None)
                except ValueError:
                    assigned_col = len(active_tracks)
                    active_tracks.append(None)

            node.column = assigned_col
            node.color_index = assigned_col % self.palette_size
            active_tracks[assigned_col] = None  # Consumed this commit

            # Assign tracks for parent commits
            parents = node.parent_hashes
            if not parents:
                # Root commit: lane closes
                pass
            elif len(parents) == 1:
                p0 = parents[0]
                if p0 in active_tracks:
                    # Parent is already tracked on another column
                    pass
                else:
                    # Continue current column for the first parent
                    active_tracks[assigned_col] = p0
            else:
                # Merge commit: first parent continues in current column if possible
                p0 = parents[0]
                if p0 not in active_tracks:
                    active_tracks[assigned_col] = p0
                
                # Additional merge parents get existing or new columns
                for p_other in parents[1:]:
                    if p_other not in active_tracks:
                        # Find a free lane
                        try:
                            free_col = active_tracks.index(None)
                            active_tracks[free_col] = p_other
                        except ValueError:
                            active_tracks.append(p_other)

            # Trim trailing None tracks
            while active_tracks and active_tracks[-1] is None:
                active_tracks.pop()

        # Step 2: Build connectors between each commit and its parents
        for node in sorted_commits:
            node.connectors = []
            for idx, p_hash in enumerate(node.parent_hashes):
                parent_node = commit_by_hash.get(p_hash)
                is_merge_parent = (idx > 0)
                
                if parent_node is not None:
                    connector = GraphConnector(
                        from_column=node.column,
                        to_column=parent_node.column,
                        from_row=node.row,
                        to_row=parent_node.row,
                        color_index=parent_node.color_index if is_merge_parent else node.color_index,
                        is_merge=is_merge_parent,
                    )
                else:
                    # Parent is outside the loaded range; draw connector extending downward
                    connector = GraphConnector(
                        from_column=node.column,
                        to_column=node.column,
                        from_row=node.row,
                        to_row=node.row + 1,
                        color_index=node.color_index,
                        is_merge=is_merge_parent,
                    )
                node.connectors.append(connector)

        return sorted_commits
