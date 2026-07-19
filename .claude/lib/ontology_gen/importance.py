#!/usr/bin/env python3
"""PageRank importance layer over the structural repo-map (main#1002, Move #8).

The structural graph (`code-graph.json`) treats every file equally — an agent
orienting in a large repo gets no "what matters most here" signal, so its first
grep can be blind. This module adds the cheap additive win the token-efficiency
survey (#986) flagged: a **PageRank importance ranking** so `llms.txt` can lead
with the repo's genuine hub files (the depended-upon core), the way Aider's
tree-sitter + PageRank repo-map does.

Design
======
- **File-level graph.** The node/edge graph is collapsed to a weighted file →
  file dependency graph: an edge from a node in file A to a node in file B
  becomes a weighted A→B file edge (weight = number of such cross-file edges).
  Ranking whole files (not symbols) is what an agent orients on, and collapsing
  sidesteps the `contains` self-inflation a symbol-level rank would suffer.
- **Dependency edges only.** `contains` (file→its own symbols) is structural,
  not a dependency signal, so it is excluded. `imports`, `imports_from`,
  `calls`, `inherits`, `references` are the candidate dependency edges; self-loops
  (A→A) are dropped, since a file depending on itself says nothing about
  cross-file importance. NOTE that `calls`/`inherits` are resolved intra-file only
  today (see the `DEP_EDGE_TYPES` caveat below), so the *live* signal is the
  cross-file import/re-export graph; the other two are kept forward-compatibly.
- **Edge direction = importance flow.** In the graph an edge `src→dst` means
  "src depends on / references dst" (assemble.py), so standard PageRank
  accumulates score at the *depended-upon* node — exactly "what everything else
  needs." A file imported/called/subclassed from many places ranks high.
- **Pure Python, no new dependency.** Power iteration; ~15K nodes is trivial.
  Keeps the generator's stdlib-only footprint (no networkx).
- **Deterministic.** Sorted traversal + fixed damping/tolerance/iteration cap →
  the same graph always yields the same ranking (the generator's #855 invariant).
"""

from __future__ import annotations

from collections import defaultdict

from .model import GraphDict

# Edges that carry a "depends-on" signal. `contains` is deliberately excluded
# (a file containing its own symbols is not a dependency). This is the same
# vocabulary as model.EDGE_TYPES minus `contains`.
#
# Caveat (accuracy over aspiration): today only `imports`, `imports_from`, and
# `references` actually feed the ranking. `calls` and `inherits` are resolved by
# assemble.py *intra-file only* (same-file name matching), so both endpoints
# always share a path and `build_file_graph` drops them as self-loops — they
# contribute ZERO signal at present. They are kept here for forward-compatibility:
# if cross-file call/inherit resolution is ever added, they light up automatically
# with no change here. So the live signal is the cross-file *import/re-export*
# graph; do not read "calls/inherits" as currently influencing hub ranks.
DEP_EDGE_TYPES = frozenset({"imports", "imports_from", "calls", "inherits", "references"})

_DAMPING = 0.85  # standard PageRank teleport probability
_MAX_ITERS = 100  # power-iteration cap (converges well before this at 15K nodes)
_TOL = 1e-9  # L1 convergence threshold across one iteration


def build_file_graph(
    graph: GraphDict,
) -> tuple[list[str], dict[str, dict[str, int]]]:
    """Collapse the node/edge graph to a weighted file→file dependency graph.

    Returns ``(files, out_weights)`` where ``files`` is the sorted list of every
    distinct file path (a node's ``path``) and ``out_weights[a][b]`` is the count
    of dependency edges from a node in file ``a`` to a node in file ``b`` (a≠b).
    """
    id_to_path = {node["id"]: node["path"] for node in graph["nodes"]}
    files = sorted({node["path"] for node in graph["nodes"]})
    out_weights: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for edge in graph["edges"]:
        if edge["type"] not in DEP_EDGE_TYPES:
            continue
        src_path = id_to_path.get(edge["src"])
        dst_path = id_to_path.get(edge["dst"])
        if src_path is None or dst_path is None or src_path == dst_path:
            continue
        out_weights[src_path][dst_path] += 1
    return files, {src: dict(dsts) for src, dsts in out_weights.items()}


def pagerank(
    files: list[str],
    out_weights: dict[str, dict[str, int]],
    *,
    damping: float = _DAMPING,
    max_iters: int = _MAX_ITERS,
    tol: float = _TOL,
) -> dict[str, float]:
    """Weighted PageRank via power iteration. Deterministic; scores sum to ~1.

    Dangling files (no outgoing dependency edges) redistribute their score
    uniformly across all files, the standard handling that keeps the total mass
    conserved. Iteration is over ``files`` in the caller's (sorted) order so the
    floating-point sums are order-stable and the result is reproducible.
    """
    n = len(files)
    if n == 0:
        return {}

    out_total = {f: sum(out_weights.get(f, {}).values()) for f in files}
    # Invert to in-links: dst -> [(src, weight), ...], for the per-node update.
    in_links: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for src in files:
        for dst, weight in out_weights.get(src, {}).items():
            in_links[dst].append((src, weight))

    rank = {f: 1.0 / n for f in files}
    base = (1.0 - damping) / n
    for _ in range(max_iters):
        dangling_mass = sum(rank[f] for f in files if out_total[f] == 0)
        dangling_share = damping * dangling_mass / n
        new_rank: dict[str, float] = {}
        delta = 0.0
        for f in files:
            score = base + dangling_share
            for src, weight in in_links.get(f, []):
                score += damping * rank[src] * weight / out_total[src]
            new_rank[f] = score
            delta += abs(score - rank[f])
        rank = new_rank
        if delta < tol:
            break
    return rank


def rank_files(graph: GraphDict, limit: int = 20) -> list[tuple[str, float]]:
    """Top-``limit`` files by PageRank importance, most-important first.

    Ties break by path (ascending) so the ranking is fully deterministic. A file
    with no dependency edges at all still appears (with the teleport-floor score)
    but ranks below any depended-upon file.
    """
    files, out_weights = build_file_graph(graph)
    scores = pagerank(files, out_weights)
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return ordered[:limit]
