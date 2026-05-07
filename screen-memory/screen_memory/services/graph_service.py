"""GraphService: higher-level operations over the URI Graph.

Wraps GraphRepo with subtree queries, path materialization, bulk ops, traversal.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from screen_memory.models.uri import NocturneUri
from screen_memory.storage.graph_repo import GraphRepo


class GraphService:
    def __init__(self, repo: GraphRepo) -> None:
        self._repo = repo

    # -- Simple delegates with path materialization ---------------------------

    def write(self, uri: str | NocturneUri, content: str) -> dict:
        """Write a memory and materialize ancestor paths."""
        if isinstance(uri, str):
            uri = NocturneUri.parse(uri)
        self._materialize_paths(uri)
        return self._repo.write_memory(uri, content)

    def read(self, uri: str | NocturneUri) -> Optional[dict]:
        if isinstance(uri, str):
            uri = NocturneUri.parse(uri)
        return self._repo.read_memory(uri)

    def list_nodes(self, domain: Optional[str] = None) -> list[dict]:
        return self._repo.list_nodes(domain)

    # -- Subtree queries ------------------------------------------------------

    def get_subtree(
        self, uri: NocturneUri, max_depth: Optional[int] = None
    ) -> Optional[dict]:
        """Return a nested dict representing the subtree rooted at *uri*."""
        node = self._repo.get_node(uri)
        if node is None:
            return None
        mem = self._repo.read_memory(uri)
        children = self.get_children(uri)
        result = {
            "uri": str(uri),
            "content": mem["content"] if mem else None,
            "children": [],
        }
        if max_depth is not None and max_depth <= 0:
            return result
        next_depth = (max_depth - 1) if max_depth is not None else None
        for child_row in children:
            child_uri = NocturneUri.parse(child_row["uri"])
            subtree = self.get_subtree(child_uri, max_depth=next_depth)
            if subtree is not None:
                result["children"].append(subtree)
        return result

    def get_children(self, uri: NocturneUri) -> list[dict]:
        """Return direct children of *uri* in the URI hierarchy."""
        all_nodes = self._repo.list_nodes(uri.domain)
        prefix = uri.path + "/" if uri.path else ""
        children = []
        for n in all_nodes:
            p = n["path"]
            if not prefix:
                # domain root: children are depth-1 paths
                if p and "/" not in p:
                    children.append(n)
            else:
                if p.startswith(prefix) and "/" not in p[len(prefix):]:
                    children.append(n)
        return children

    # -- Path materialization -------------------------------------------------

    def _materialize_paths(self, uri: NocturneUri) -> None:
        """Ensure all ancestor nodes and paths table entries exist."""
        if not uri.path:
            return
        parts = uri.path.split("/")
        for i in range(len(parts)):
            ancestor_path = "/".join(parts[:i])
            ancestor = NocturneUri.make(uri.domain, ancestor_path)
            self._repo.create_node(ancestor)
        # Now materialize paths for uri against each ancestor
        node = self._repo.get_node(uri)
        if node is None:
            self._repo.create_node(uri)
        for i in range(1, len(parts)):
            ancestor_path = "/".join(parts[:i])
            ancestor_uri_str = f"{uri.domain}://{ancestor_path}"
            depth = len(parts) - i
            self._repo._db.execute(
                "INSERT OR IGNORE INTO paths (ancestor_uri, descendant_uri, depth) "
                "VALUES (?, ?, ?)",
                (ancestor_uri_str, str(uri), depth),
            )

    def get_ancestors(self, uri: NocturneUri) -> list[dict]:
        rows = self._repo._db.execute(
            "SELECT ancestor_uri, descendant_uri, depth FROM paths WHERE descendant_uri=? "
            "ORDER BY depth ASC",
            (str(uri),),
        ).fetchall()
        keys = ["ancestor_uri", "descendant_uri", "depth"]
        return [dict(zip(keys, r)) for r in rows]

    def get_descendants(self, uri: NocturneUri) -> list[dict]:
        rows = self._repo._db.execute(
            "SELECT ancestor_uri, descendant_uri, depth FROM paths WHERE ancestor_uri=? "
            "ORDER BY depth ASC",
            (str(uri),),
        ).fetchall()
        keys = ["ancestor_uri", "descendant_uri", "depth"]
        return [dict(zip(keys, r)) for r in rows]

    # -- Bulk operations ------------------------------------------------------

    def bulk_create(self, uri_strs: list[str]) -> list[NocturneUri]:
        results = []
        for raw in uri_strs:
            uri = NocturneUri.parse(raw)
            self._materialize_paths(uri)
            self._repo.create_node(uri)
            results.append(uri)
        return results

    def bulk_write(self, items: list[tuple[str, str]]) -> list[dict]:
        results = []
        for raw_uri, content in items:
            results.append(self.write(raw_uri, content))
        return results

    # -- Traversal ------------------------------------------------------------

    def traverse(
        self,
        root: NocturneUri,
        strategy: str = "bfs",
        max_depth: Optional[int] = None,
    ) -> list[dict]:
        """Traverse the URI hierarchy tree starting from *root*."""
        result = []
        root_node = self._repo.get_node(root)
        if root_node is None:
            return result
        result.append(root_node)

        if strategy == "bfs":
            self._traverse_bfs(root, result, max_depth)
        else:
            self._traverse_dfs(root, result, max_depth, 0)
        return result

    def _traverse_bfs(
        self, root: NocturneUri, result: list[dict], max_depth: Optional[int]
    ) -> None:
        queue: deque[tuple[NocturneUri, int]] = deque([(root, 0)])
        while queue:
            current, depth = queue.popleft()
            if max_depth is not None and depth >= max_depth:
                continue
            children = self.get_children(current)
            for child in children:
                child_uri = NocturneUri.parse(child["uri"])
                node = self._repo.get_node(child_uri)
                if node:
                    result.append(node)
                    queue.append((child_uri, depth + 1))

    def _traverse_dfs(
        self, root: NocturneUri, result: list[dict], max_depth: Optional[int], depth: int
    ) -> None:
        if max_depth is not None and depth >= max_depth:
            return
        children = self.get_children(root)
        for child in children:
            child_uri = NocturneUri.parse(child["uri"])
            node = self._repo.get_node(child_uri)
            if node:
                result.append(node)
                self._traverse_dfs(child_uri, result, max_depth, depth + 1)
