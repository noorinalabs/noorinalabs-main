"""Tests for ontology_gen.aggregate — the cross-repo structural aggregator (main#856).

Covers repo-namespacing, cross-repo id-collision avoidance, graceful degradation when a
repo index is absent, determinism, edge preservation, and the CLI entry point. Fixtures
build small per-repo ``code-graph.json`` files in a temp tree mimicking the parent/child
repo layout (``<root>/ontology/structural/`` for main, ``<root>/<child>/ontology/
structural/`` for children).
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

# Package lives at .claude/lib/ontology_gen/; this test is at .claude/lib/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ontology_gen.aggregate as aggregate_module  # noqa: E402
from ontology_gen.aggregate import (  # noqa: E402
    DEFAULT_REPOS,
    INDEX_RELPATH,
    aggregate,
    main,
    regenerate_indices,
    write_aggregate,
)
from ontology_gen.model import CodeGraph, Edge, Node, serialize_graph  # noqa: E402


def _write_index(repo_root: Path, graph: CodeGraph) -> Path:
    """Write ``graph`` as a per-repo code-graph.json under ``repo_root`` and return it."""
    out = repo_root / INDEX_RELPATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(serialize_graph(graph.to_dict()), encoding="utf-8")
    return out


def _graph_with(path: str, lang: str = "python") -> CodeGraph:
    """A minimal graph: one module + one contained func with a contains edge."""
    graph = CodeGraph()
    graph.add_node(Node(path, "module", path, 1, lang))
    graph.add_node(Node(f"{path}::f", "func", path, 2, lang))
    graph.add_edge(Edge(path, f"{path}::f", "contains"))
    return graph


class TestNamespacing(unittest.TestCase):
    def test_ids_and_paths_are_repo_prefixed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("app.py"))
            graph_dict, statuses = aggregate(root, {"main": "."})

            ids = {n["id"] for n in graph_dict["nodes"]}
            paths = {n["path"] for n in graph_dict["nodes"]}
            self.assertEqual(ids, {"main/app.py", "main/app.py::f"})
            self.assertEqual(paths, {"main/app.py"})
            # Edge endpoints namespaced too, edge preserved.
            self.assertEqual(
                {(e["src"], e["dst"], e["type"]) for e in graph_dict["edges"]},
                {("main/app.py", "main/app.py::f", "contains")},
            )
            self.assertEqual([s.name for s in statuses], ["main"])
            self.assertTrue(statuses[0].present)

    def test_no_collision_across_repos_same_relpath(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("app.py"))
            _write_index(root / "noorinalabs-isnad-graph", _graph_with("app.py"))
            graph_dict, _ = aggregate(root, {"main": ".", "isnad-graph": "noorinalabs-isnad-graph"})
            ids = {n["id"] for n in graph_dict["nodes"]}
            # Identical relpath in two repos -> two distinct namespaced nodes.
            self.assertIn("main/app.py", ids)
            self.assertIn("isnad-graph/app.py", ids)
            self.assertEqual(len(graph_dict["nodes"]), 4)
            self.assertEqual(len(graph_dict["edges"]), 2)


class TestGracefulDegradation(unittest.TestCase):
    def test_absent_repo_is_skipped_not_fatal(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("app.py"))
            # isnad-graph has no index on disk.
            graph_dict, statuses = aggregate(
                root, {"main": ".", "isnad-graph": "noorinalabs-isnad-graph"}
            )
            by_name = {s.name: s for s in statuses}
            self.assertTrue(by_name["main"].present)
            self.assertFalse(by_name["isnad-graph"].present)
            # Present repo's nodes still aggregated.
            self.assertEqual(
                {n["id"] for n in graph_dict["nodes"]}, {"main/app.py", "main/app.py::f"}
            )

    def test_all_absent_yields_empty_graph(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph_dict, statuses = aggregate(root, {"main": ".", "isnad-graph": "x"})
            self.assertEqual(graph_dict, {"nodes": [], "edges": []})
            self.assertTrue(all(not s.present for s in statuses))

    def test_malformed_index_degrades(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / INDEX_RELPATH
            bad.parent.mkdir(parents=True, exist_ok=True)
            bad.write_text("{ not json", encoding="utf-8")
            graph_dict, statuses = aggregate(root, {"main": "."})
            self.assertEqual(graph_dict, {"nodes": [], "edges": []})
            self.assertFalse(statuses[0].present)


class TestDeterminism(unittest.TestCase):
    def test_aggregate_is_deterministic_and_canonical(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("b.py"))
            _write_index(root / "noorinalabs-user-service", _graph_with("a.py"))
            repos = {"main": ".", "user-service": "noorinalabs-user-service"}
            d1, _ = aggregate(root, repos)
            d2, _ = aggregate(root, repos)
            self.assertEqual(serialize_graph(d1), serialize_graph(d2))
            # Canonical sort by path: user-service/a.py sorts before main/b.py.
            paths = [n["path"] for n in d1["nodes"]]
            self.assertEqual(paths, sorted(paths))


class TestCli(unittest.TestCase):
    def test_main_writes_central_artifact(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("app.py"))
            out = root / "ontology" / "structural" / "cross-repo-graph.json"
            # --no-regenerate: roll up the pre-written fixture index rather than
            # rebuilding from source (the fixture tree has no real .py files).
            rc = main([str(root), "--out", str(out), "--repo", "main=.", "--no-regenerate"])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            parsed = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual({n["id"] for n in parsed["nodes"]}, {"main/app.py", "main/app.py::f"})

    def test_write_aggregate_returns_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_index(root, _graph_with("app.py"))
            out = root / "cross.json"
            nodes, edges, statuses = write_aggregate(root, out, {"main": "."})
            self.assertEqual(nodes, 2)
            self.assertEqual(edges, 1)
            self.assertEqual(len(statuses), 1)

    def test_bad_repo_override_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                main([tmp, "--repo", "noequalsign"])


class TestDefaultRepos(unittest.TestCase):
    def test_default_map_covers_main_and_seven_children(self) -> None:
        self.assertEqual(DEFAULT_REPOS["main"], ".")
        # main + 7 child repos (CLAUDE.md § Repository Map).
        self.assertEqual(len(DEFAULT_REPOS), 8)
        for child in ("isnad-graph", "user-service", "deploy", "design-system"):
            self.assertTrue(DEFAULT_REPOS[child].startswith("noorinalabs-"))


class TestRegeneration(unittest.TestCase):
    """main#939: the aggregator rebuilds each in-scope repo's index from source before
    roll-up, so it does not depend on a committed index existing on disk."""

    def test_regenerate_builds_index_from_source(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # A real source file, but NO pre-existing code-graph.json on disk.
            (root / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            index = root / INDEX_RELPATH
            self.assertFalse(index.exists())

            statuses = regenerate_indices(root, {"main": "."})

            self.assertTrue(index.exists(), "regeneration must create the per-repo index")
            self.assertEqual([s.name for s in statuses], ["main"])
            self.assertTrue(statuses[0].regenerated)
            self.assertGreaterEqual(statuses[0].files, 1)
            parsed = json.loads(index.read_text(encoding="utf-8"))
            paths = {n["path"] for n in parsed["nodes"]}
            self.assertIn("mod.py", paths)

    def test_regenerate_skips_absent_repo(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            statuses = regenerate_indices(root, {"main": ".", "isnad-graph": "not-cloned"})
            by_name = {s.name: s for s in statuses}
            self.assertTrue(by_name["main"].regenerated)
            self.assertFalse(by_name["isnad-graph"].regenerated)

    def test_main_default_regenerates_before_rollup(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Stale/empty pre-written index that regeneration must supersede.
            _write_index(root, CodeGraph())
            (root / "real.py").write_text("def g():\n    return 2\n", encoding="utf-8")
            out = root / "ontology" / "structural" / "cross-repo-graph.json"
            rc = main([str(root), "--out", str(out), "--repo", "main=."])
            self.assertEqual(rc, 0)
            parsed = json.loads(out.read_text(encoding="utf-8"))
            paths = {n["path"] for n in parsed["nodes"]}
            self.assertIn("main/real.py", paths)

    def test_raising_repo_generator_is_skipped_not_fatal(self) -> None:
        """A PRESENT repo whose generator RAISES is skipped + recorded, not fatal — the
        other repos still regenerate and the roll-up continues (main#939 review)."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.py").write_text("a = 1\n", encoding="utf-8")
            child = root / "noorinalabs-isnad-graph"
            child.mkdir()
            (child / "app.py").write_text("b = 2\n", encoding="utf-8")

            real_generate = aggregate_module.generate

            def flaky(repo_root: Path, out_dir: Path, name: str) -> dict[str, int]:
                if name == "isnad-graph":
                    raise RuntimeError("boom in child generator")
                return real_generate(repo_root, out_dir, name)

            with mock.patch.object(aggregate_module, "generate", side_effect=flaky):
                statuses = regenerate_indices(
                    root, {"main": ".", "isnad-graph": "noorinalabs-isnad-graph"}
                )

            by_name = {s.name: s for s in statuses}
            # The healthy repo still regenerated.
            self.assertTrue(by_name["main"].regenerated)
            # The raising repo is skipped, error recorded, no exception propagated.
            self.assertFalse(by_name["isnad-graph"].regenerated)
            self.assertIsNotNone(by_name["isnad-graph"].error)
            self.assertIn("boom in child generator", by_name["isnad-graph"].error or "")
            # A raising repo (error set) is distinct from an absent repo (error None).
            self.assertIsNone(by_name["main"].error)

    def test_main_returns_zero_when_a_repo_generator_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.py").write_text("c = 3\n", encoding="utf-8")
            out = root / "ontology" / "structural" / "cross-repo-graph.json"

            def always_raises(repo_root: Path, out_dir: Path, name: str) -> dict[str, int]:
                raise OSError("disk gone")

            with mock.patch.object(aggregate_module, "generate", side_effect=always_raises):
                rc = main([str(root), "--out", str(out), "--repo", "main=."])
            # Roll-up still completes (rc 0) and writes the central artifact, even though
            # the only repo's generator crashed — it just rolls up an empty/absent index.
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
