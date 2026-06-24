"""Owned structural ontology generator (noorinalabs-main#855, #820 C×T2 Task-3a).

Generates the per-repo *structural* layer of the C×T2 ontology — ``code-graph.json`` +
``llms.txt`` under ``ontology/structural/`` — from source (Python ``ast`` / TypeScript /
Cypher), replacing hand-resolution of that layer with regeneration. The hand-curated
*semantic* overlay (``domain.yaml``, ``services.yaml``, ``conventions.md``,
``ontology/repos/*.yaml``) stays as-is.

CLI: ``python3 -m ontology_gen <repo-root> --out ontology/structural/``
"""

from __future__ import annotations

from .generate import build_graph, discover, generate
from .model import CodeGraph, Edge, FileInfo, Node

__all__ = [
    "CodeGraph",
    "Edge",
    "FileInfo",
    "Node",
    "build_graph",
    "discover",
    "generate",
]
