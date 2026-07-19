"""Tests for ontology_gen.importance — the PageRank hub-file layer (main#1002).

Covers the file-graph collapse (dependency edges only, contains excluded,
self-loops dropped, weighted by count), the pure-Python weighted PageRank
(empty, star, exact 2-node fixed point, dangling-node mass conservation,
determinism), and rank_files (ordering, deterministic ties, limit).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ontology_gen.importance import (  # noqa: E402
    build_file_graph,
    pagerank,
    rank_files,
)
from ontology_gen.model import EdgeDict, GraphDict, NodeDict  # noqa: E402


def _node(node_id: str, path: str, kind: str = "func") -> NodeDict:
    return {"id": node_id, "kind": kind, "path": path, "line": 1, "lang": "python"}


def _edge(src: str, dst: str, etype: str) -> EdgeDict:
    return {"src": src, "dst": dst, "type": etype}


def _graph(nodes: list[NodeDict], edges: list[EdgeDict]) -> GraphDict:
    return {"nodes": nodes, "edges": edges}


class BuildFileGraphTests(unittest.TestCase):
    def test_collapses_symbol_edges_to_files_and_weights_by_count(self) -> None:
        # Two symbols in a.py both call into b.py -> weight 2 on a->b.
        graph: GraphDict = {
            "nodes": [
                _node("a:f", "a.py"),
                _node("a:g", "a.py"),
                _node("b:h", "b.py"),
            ],
            "edges": [
                _edge("a:f", "b:h", "calls"),
                _edge("a:g", "b:h", "calls"),
            ],
        }
        files, out_weights = build_file_graph(graph)
        self.assertEqual(files, ["a.py", "b.py"])
        self.assertEqual(out_weights, {"a.py": {"b.py": 2}})

    def test_contains_edges_excluded(self) -> None:
        # A file 'containing' its own symbol must NOT create a dependency edge.
        graph: GraphDict = {
            "nodes": [_node("a", "a.py", "file"), _node("a:f", "a.py")],
            "edges": [_edge("a", "a:f", "contains")],
        }
        _, out_weights = build_file_graph(graph)
        self.assertEqual(out_weights, {})

    def test_self_loop_dropped(self) -> None:
        # Intra-file call (both endpoints in a.py) is not a cross-file dependency.
        graph: GraphDict = {
            "nodes": [_node("a:f", "a.py"), _node("a:g", "a.py")],
            "edges": [_edge("a:f", "a:g", "calls")],
        }
        _, out_weights = build_file_graph(graph)
        self.assertEqual(out_weights, {})

    def test_all_dependency_edge_types_counted(self) -> None:
        graph: GraphDict = {
            "nodes": [_node("a", "a.py", "file"), _node("b", "b.py", "file")],
            "edges": [
                _edge("a", "b", "imports"),
                _edge("a", "b", "imports_from"),
                _edge("a", "b", "calls"),
                _edge("a", "b", "inherits"),
                _edge("a", "b", "references"),
            ],
        }
        _, out_weights = build_file_graph(graph)
        self.assertEqual(out_weights["a.py"]["b.py"], 5)


class PageRankTests(unittest.TestCase):
    def test_empty_graph(self) -> None:
        self.assertEqual(pagerank([], {}), {})

    def test_scores_sum_to_one(self) -> None:
        files = ["a.py", "b.py", "c.py"]
        out_weights = {"a.py": {"b.py": 1}, "b.py": {"c.py": 1}}
        scores = pagerank(files, out_weights)
        self.assertAlmostEqual(sum(scores.values()), 1.0, places=6)

    def test_star_center_ranks_highest(self) -> None:
        # a,b,c,d all depend on e -> e is the hub, must rank highest.
        files = ["a.py", "b.py", "c.py", "d.py", "e.py"]
        out_weights = {
            "a.py": {"e.py": 1},
            "b.py": {"e.py": 1},
            "c.py": {"e.py": 1},
            "d.py": {"e.py": 1},
        }
        scores = pagerank(files, out_weights)
        top = max(scores, key=lambda f: scores[f])
        self.assertEqual(top, "e.py")

    def test_two_node_exact_fixed_point(self) -> None:
        # A -> B, damping 0.85. Hand-solved fixed point (B is dangling):
        #   PR[A] = 0.075 + 0.425*PR[B];  PR[B] = 0.075 + 0.425*PR[B] + 0.85*PR[A]
        #   => PR[A] ~= 0.350877, PR[B] ~= 0.649123.
        files = ["a.py", "b.py"]
        out_weights = {"a.py": {"b.py": 1}}
        scores = pagerank(files, out_weights)
        self.assertAlmostEqual(scores["a.py"], 0.350877, places=4)
        self.assertAlmostEqual(scores["b.py"], 0.649123, places=4)
        self.assertGreater(scores["b.py"], scores["a.py"])

    def test_dangling_node_conserves_mass(self) -> None:
        # Every node dangling (no edges) -> uniform, still sums to 1.
        files = ["a.py", "b.py", "c.py"]
        scores = pagerank(files, {})
        self.assertAlmostEqual(sum(scores.values()), 1.0, places=6)
        for f in files:
            self.assertAlmostEqual(scores[f], 1.0 / 3, places=6)

    def test_deterministic(self) -> None:
        files = ["a.py", "b.py", "c.py"]
        out_weights = {"a.py": {"b.py": 2}, "c.py": {"b.py": 1}}
        self.assertEqual(pagerank(files, out_weights), pagerank(files, out_weights))

    def test_weight_increases_importance(self) -> None:
        # b is depended on 3x, c once -> b outranks c.
        files = ["a.py", "b.py", "c.py"]
        out_weights = {"a.py": {"b.py": 3, "c.py": 1}}
        scores = pagerank(files, out_weights)
        self.assertGreater(scores["b.py"], scores["c.py"])


class RankFilesTests(unittest.TestCase):
    def test_hub_ranks_first_and_contains_ignored(self) -> None:
        graph: GraphDict = {
            "nodes": [
                _node("a", "a.py", "file"),
                _node("b", "b.py", "file"),
                _node("hub", "hub.py", "file"),
                _node("hub:f", "hub.py"),
            ],
            "edges": [
                _edge("hub", "hub:f", "contains"),  # ignored
                _edge("a", "hub", "imports"),
                _edge("b", "hub", "imports"),
            ],
        }
        ranked = rank_files(graph)
        self.assertEqual(ranked[0][0], "hub.py")

    def test_limit_respected(self) -> None:
        nodes = [_node(f"n{i}", f"f{i}.py", "file") for i in range(10)]
        edges = [_edge("n0", f"n{i}", "imports") for i in range(1, 10)]
        ranked = rank_files(_graph(nodes, edges), limit=3)
        self.assertEqual(len(ranked), 3)

    def test_ties_break_by_path(self) -> None:
        # Two symmetric hubs with identical in-degree -> equal score, path order.
        graph: GraphDict = {
            "nodes": [
                _node("src", "src.py", "file"),
                _node("z", "z.py", "file"),
                _node("a", "a.py", "file"),
            ],
            "edges": [_edge("src", "z", "imports"), _edge("src", "a", "imports")],
        }
        ranked = rank_files(graph)
        by_path = {p: s for p, s in ranked}
        self.assertAlmostEqual(by_path["a.py"], by_path["z.py"], places=9)
        # a.py before z.py on the tie.
        order = [p for p, _ in ranked]
        self.assertLess(order.index("a.py"), order.index("z.py"))


if __name__ == "__main__":
    unittest.main()
