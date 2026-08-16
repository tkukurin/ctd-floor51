"""Hugging Face dataset builder for CTD Commons."""

import hashlib
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _iter_nodes(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if node.get("type") != "folder" and "url" in node:
        yield node
    for child in node.get("children", []):
        yield from _iter_nodes(child)


def _process_accession(c_dir: Path, docs_dir: Path) -> Iterator[dict[str, Any]]:
    if not (index_file := c_dir / "index-full.json").is_file():
        return

    tree = json.loads(index_file.read_text(encoding="utf-8"))

    for node in _iter_nodes(tree):
        if not (rel_path := node.get("path")):
            continue

        if not (local_path := docs_dir.parent / rel_path).is_file():
            continue

        parts = list(Path(rel_path).parent.parts)
        parents = (
            parts[3:]
            if len(parts) >= 3 and parts[0] == "documents" and parts[2] == "files"
            else parts
        )

        yield {
            "id": hashlib.sha256(
                f"{c_dir.name}:{rel_path}".encode("utf-8")
            ).hexdigest(),
            "accession": c_dir.name,
            "drug": node.get("drug", ""),
            "name": node.get("name", ""),
            "source_url": node.get("url", ""),
            "source_path": rel_path,
            "extension": Path(rel_path).suffix.lower(),
            "media_type": node.get("type", ""),
            "parents": parents,
            "size_bytes": local_path.stat().st_size,
            "sha256": _sha256_file(local_path),
        }


def build_manifest(docs_dir: Path, skip_ema: bool = True) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for c_dir in sorted(
        p for p in docs_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
    ):
        if skip_ema and c_dir.name == "RDCP-E26-EMA":
            continue
        records.extend(_process_accession(c_dir, docs_dir))

    return records
