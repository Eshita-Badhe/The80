from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


class Topology:
    def __init__(self, payload: dict[str, Any]):
        self.stations = {item["code"]: item for item in payload.get("stations", [])}
        self.nodes = {item["id"]: item for item in payload.get("nodes", [])}
        self._adj: dict[str, set[str]] = defaultdict(set)
        self._parents: dict[str, set[str]] = defaultdict(set)
        self._children: dict[str, set[str]] = defaultdict(set)
        for edge in payload.get("edges", []):
            if not edge.get("causal", False):
                continue
            source, target = edge["source"], edge["target"]
            self._adj[source].add(target)
            self._adj[target].add(source)
            self._parents[target].add(source)
            self._children[source].add(target)

    @classmethod
    def from_json(cls, path: str | Path) -> "Topology":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def station_code(self, value: str) -> str | None:
        value = value.strip()
        if value in self.stations:
            return value
        lowered = value.casefold()
        return next((code for code, item in self.stations.items() if item["name"].casefold() == lowered), None)

    def has_node(self, equipment_id: str) -> bool:
        return equipment_id in self.nodes

    def distance(self, left: str, right: str, max_hops: int = 3) -> int | None:
        if left == right:
            return 0
        queue = deque([(left, 0)])
        seen = {left}
        while queue:
            node, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for neighbor in sorted(self._adj.get(node, ())):
                if neighbor == right:
                    return depth + 1
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, depth + 1))
        return None

    def ancestors(self, equipment_id: str) -> set[str]:
        result: set[str] = set()
        queue = deque([equipment_id])
        while queue:
            node = queue.popleft()
            for parent in self._parents.get(node, ()):
                if parent not in result:
                    result.add(parent)
                    queue.append(parent)
        return result

    def descendants(self, equipment_id: str) -> set[str]:
        result: set[str] = set()
        queue = deque([equipment_id])
        while queue:
            node = queue.popleft()
            for child in self._children.get(node, ()):
                if child not in result:
                    result.add(child)
                    queue.append(child)
        return result

    def causal_neighbors(self, equipment_id: str) -> set[str]:
        return set(self._adj.get(equipment_id, ()))

