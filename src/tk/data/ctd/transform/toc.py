"""Traverse collection ``toc.json`` trees into a flat manifest.

Each collection has ``files/toc.json`` — a recursive tree whose nodes carry
``name``, ``type``, ``path``, ``children``; leaves are tagged with ``drug``
and ``accession``.

EMA's toc is sharded: non-leaf folders carry a ``$ref`` pointing to a nested
``toc.json`` (a repo-relative path) instead of inline ``children``; these are
followed transparently. ``accession``/``drug`` are inherited from the nearest
tagged node, and the collection folder name is an accession fallback.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class TocRow:
    accession: str
    drug: str
    type: str
    name: str
    path: str
    depth: int
    is_leaf: bool


def load_toc(toc_path: Path):
    """Load a toc.json file, raising FileNotFoundError if missing."""
    if not toc_path.is_file():
        raise FileNotFoundError(f"no toc.json at {toc_path}")
    return json.loads(toc_path.read_text())


def _default_bases(collection_dir: Path) -> list[Path]:
    # $ref paths are repo-relative (documents/...); resolve against the data
    # root (parent of documents/), then fall back to documents/ and the
    # collection dir itself.
    return [
        collection_dir.parent.parent,
        collection_dir.parent,
        collection_dir,
    ]


def _load_cached(path: Path, cache: dict):
    if path not in cache:
        cache[path] = json.loads(path.read_text())
    return cache[path]


def _resolve_ref(ref: str, bases: list[Path], cache: dict):
    p = Path(ref)
    if p.is_absolute() and p.is_file():
        return _load_cached(p, cache)
    for base in bases:
        cand = base / p
        if cand.is_file():
            return _load_cached(cand, cache)
    return None


def _children(node, bases: list[Path], cache: dict) -> list:
    """Inline children, or the children of a $ref'd nested toc if sharded."""
    ch = node.get("children")
    if not ch and node.get("$ref"):
        sub = _resolve_ref(node["$ref"], bases, cache)
        if isinstance(sub, dict):
            ch = sub.get("children") or []
        elif isinstance(sub, list):
            ch = sub
        else:
            ch = []
    return ch or []


def _walk(node, *, accession, drug, depth, parent_path, rows: list[TocRow], bases, cache) -> None:
    if not isinstance(node, dict):
        return
    acc = node.get("accession") or accession or ""
    drug_v = node.get("drug") or drug or ""
    name = node.get("name", "")
    # EMA shard leaves carry no `path`; reconstruct from the parent folder path.
    path = node.get("path") or (f"{parent_path}/{name}" if parent_path and name else "")
    children = _children(node, bases, cache)
    rows.append(TocRow(
        accession=acc, drug=drug_v, type=node.get("type", ""),
        name=name, path=path,
        depth=depth, is_leaf=not children,
    ))
    for c in children:
        _walk(c, accession=acc, drug=drug_v, depth=depth + 1, parent_path=path,
              rows=rows, bases=bases, cache=cache)


def flatten(collection_dir: Path, *, leaves_only: bool = True, root: Path | None = None) -> list[TocRow]:
    """Flatten a collection's toc.json (following $ref shards) into rows."""
    bases = _default_bases(collection_dir) if root is None else [root, *_default_bases(collection_dir)]
    cache: dict = {}
    tree = load_toc(collection_dir / "files" / "toc.json")
    rows: list[TocRow] = []
    _walk(tree, accession="", drug="", depth=0, parent_path="", rows=rows,
          bases=bases, cache=cache)
    fallback = collection_dir.name
    for r in rows:
        if not r.accession:
            r.accession = fallback
    if leaves_only:
        rows = [r for r in rows if r.is_leaf]
    return rows


def iter_tree(collection_dir: Path, *, root: Path | None = None) -> Iterator[str]:
    """Yield indented lines for a pretty tree view of toc.json (with $ref shards)."""
    bases = _default_bases(collection_dir) if root is None else [root, *_default_bases(collection_dir)]
    cache: dict = {}
    tree = load_toc(collection_dir / "files" / "toc.json")
    yield from _iter_tree(tree, bars="", connector="", bases=bases, cache=cache)


def _iter_tree(node, *, bars: str, connector: str, bases, cache) -> Iterator[str]:
    if not isinstance(node, dict):
        return
    name = node.get("name", "")
    ntype = node.get("type", "")
    drug = node.get("drug", "")
    tag = f"  [{drug}]" if drug else ""
    label = f"{name} ({ntype}){tag}" if ntype else f"{name}{tag}"
    yield f"{bars}{connector}{label}"
    children = _children(node, bases, cache)
    for i, c in enumerate(children):
        last = i == len(children) - 1
        if connector.startswith("├"):
            child_bars = bars + "│   "
        elif connector.startswith("└"):
            child_bars = bars + "    "
        else:
            child_bars = bars  # root's children get no extra bars
        child_conn = "└── " if last else "├── "
        yield from _iter_tree(c, bars=child_bars, connector=child_conn,
                             bases=bases, cache=cache)
