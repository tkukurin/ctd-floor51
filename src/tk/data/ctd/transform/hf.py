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


def write_dataset_card(out_dir: Path) -> Path:
    content = """---
license: odc-by
tags:
  - clinical-trials
  - regulatory
  - medicine
  - biology
---
# CTD Commons Dataset Manifest

Dataset manifest mapping files from the [CTD Commons](https://www.ctdcommons.org/) initiative. The initiative acquires, de-identifies, and publishes regulatory dossiers from bankrupt or defunct biotechs to prevent clinical trial data loss.

This manifest provides structured metadata and stable checksums for heterogeneous regulatory files (PDFs, XPTs, SAS scripts) hosted on [archive.icosian.net](https://archive.icosian.net/).

## Data Structure

- `id` (string): SHA-256 hash of accession ID and relative path.
- `accession` (string): CTD accession identifier (e.g., `RDCP-A26-0001`).
- `drug` (string): Associated drug name (e.g., `ALLN-177`).
- `name` (string): Original file name.
- `source_url` (string): HTTPS URL to the raw file on the Icosian archive.
- `source_path` (string): Relative file path in the original eCTD hierarchy.
- `extension` (string): File extension.
- `media_type` (string): MIME type or document category.
- `parents` (list): Directory ancestry.
- `size_bytes` (int): File size.
- `sha256` (string): SHA-256 content checksum.

## Source Data

CTD data is product- and submission-centred. It preserves the evidence trail around a drug, including eCTD structures, CMC, nonclinical material, protocols, Clinical Study Reports (CSRs), and CDISC datasets.

- **RDCP-A26-0001 / 0002 / 0003**: Full eCTD submission for ALLN-177 (reloxaliase, Allena Pharma). Contains ~3,639 files including per-study CSRs, protocols, TLFs, and CDISC datasets (`.xpt`, `.sas7bdat`).
- **RDCP-E26-EMA**: EMA European Public Assessment Reports (EPAR) corpus documents.

## Recommended Tooling

- **DuckDB**: Query the Parquet manifest and join across accession, drug, or study.
- **pyreadstat**: Read `.xpt` (XPORT) and `.sas7bdat` clinical tables into pandas.
- **lxml**: Parse `define.xml` into ItemDefs and CodeLists.
- **Pinnacle21 Community**: View `define.xml` and run SDTM/ADaM conformance checks.
- **markitdown** / **Apache Tika**: Extract text from heterogeneous documents.
- **docling** / **pdfplumber**: Extract PDF tables.

## Background

- **[CTD Commons](https://www.ctdcommons.org/)**: Open-access initiative publishing regulatory dossiers.
- **[The Forgotten Files Project](https://ifp.org/wp-content/uploads/The-Forgotten-Files-Project-Teslo.pdf)**: Policy proposal by Ruxandra Teslo outlining the framework for recovering abandoned trial data.
- **[archive.icosian.net](https://archive.icosian.net/)**: Archive hosting the initial CTD accession packages.
"""
    readme_path = out_dir / "README.md"
    readme_path.write_text(content)
    return readme_path


def push_to_hub(
    repo_id: str, parquet_path: Path, readme_path: Path, private: bool = False
) -> str:
    from huggingface_hub import HfApi

    api = HfApi()

    api.create_repo(
        repo_id=repo_id, repo_type="dataset", private=private, exist_ok=True
    )
    api.upload_file(
        path_or_fileobj=str(parquet_path),
        path_in_repo="data/manifest.parquet",
        repo_id=repo_id,
        repo_type="dataset",
    )
    api.upload_file(
        path_or_fileobj=str(readme_path),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
    )
    return f"https://huggingface.co/datasets/{repo_id}"
