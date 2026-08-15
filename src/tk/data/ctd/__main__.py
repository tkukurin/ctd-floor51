"""CLI for the CTD Commons / EMA regulatory document collection (simple_parsing)."""
from __future__ import annotations

import csv
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Union

from simple_parsing import ArgumentParser, field, flag, subparsers

from . import toc

FIELDS = ["accession", "drug", "type", "name", "path", "depth", "is_leaf"]


def _die(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def _confirm(prompt: str) -> bool:
    try:
        return input(prompt + " [y/N] ").strip().lower() in {"y", "yes"}
    except EOFError:
        return False


@dataclass
class GetIcosian:
    """Download all collections from archive.icosian.net into <root>/documents/."""
    delay: float = 0.5  # Polite delay every 10 files (s).
    estimate: bool = flag(default=True, negative_option="--no-estimate")  # HEAD-sample to estimate total size.

    def execute(self, root: Path) -> None:
        from .get import icosian
        icosian.download(root, delay=self.delay, estimate=self.estimate)


@dataclass
class GetEma:
    """Download EMA document PDFs as markdown under <root>/ema-texts/ (needs pdftotext).

    Refreshes <root>/ema-texts/all_docs.json (all-English EMA feed, shared with
    `ctd ema-summary`). Defaults to the EPAR corpus (~19k PDFs); --all-types downloads
    every EMA document PDF.
    """
    yes: bool = flag(default=False)  # Skip confirmation prompt.
    all_types: bool = flag(default=False, alias="all-types")  # Download all EMA document PDFs, not just EPAR.

    def execute(self, root: Path) -> None:
        from .get import ema
        if not self.yes and not _confirm("Download + convert EMA PDFs (can be large)?"):
            _die("aborted")
        ema.download(root, assume_yes=True, epar_only=not self.all_types)


@dataclass
class Get:
    """Download data sources."""
    command: Union[GetIcosian, GetEma] = subparsers({"icosian": GetIcosian, "ema": GetEma})

    def execute(self, root: Path) -> None:
        self.command.execute(root)


@dataclass
class Inventory:
    """File-type distribution per collection under documents/."""

    def execute(self, root: Path) -> None:
        docs = root / "documents"
        if not docs.is_dir():
            _die(f"no documents/ at {root}")
        for col in sorted(p for p in docs.iterdir() if p.is_dir() and not p.name.startswith(".")):
            counts: Counter[str] = Counter()
            for f in col.rglob("*"):
                if f.is_file() and f.name != ".DS_Store":
                    counts[f.suffix.lower().lstrip(".") or "(none)"] += 1
            print(f"\n### {col.name}  ({sum(counts.values())} files)")
            for ext, n in counts.most_common():
                print(f"  {ext:<12} {n}")


@dataclass
class EmaSummary:
    """Doc-type counts from the EMA metadata JSON (default: <root>/ema-texts/all_docs.json)."""
    path: Optional[Path] = field(default=None, positional=True)

    def execute(self, root: Path) -> None:
        import json
        path = self.path or (root / "ema-texts/all_docs.json")
        if not path.is_file():
            _die(f"not found: {path}")
        records = json.loads(path.read_text())["data"]
        types = Counter(r.get("type", "") for r in records)
        print(f"{len(records)} records in {path.name}")
        for t, n in types.most_common():
            print(f"  {t:<28} {n}")


@dataclass
class Toc:
    """Traverse a single collection's files/toc.json; without COLLECTION, list collections."""
    collection: Optional[str] = field(default=None, positional=True)  # Folder name under documents/.
    as_tree: bool = flag(default=False, alias="tree")  # Indented tree instead of flat rows.
    all_nodes: bool = flag(default=False, alias="all-nodes", negative_option="--leaves-only")  # Include folder rows (default: leaves).
    docs_dir: Optional[Path] = field(default=None, alias="docs")  # documents/ dir.

    def execute(self, root: Path) -> None:
        docs = self.docs_dir or (root / "documents")
        if not docs.is_dir():
            _die(f"no documents/ at {docs}")
        cols = sorted(p for p in docs.iterdir() if p.is_dir() and not p.name.startswith("."))
        if not self.collection:
            for c in cols:
                try:
                    n = len(toc.flatten(c, leaves_only=True))
                except FileNotFoundError:
                    n = "no toc.json"
                print(f"{c.name}\t{n}")
            return
        target = next((c for c in cols if c.name == self.collection), None)
        if not target:
            _die(f"unknown collection: {self.collection}")
        if self.as_tree:
            for line in toc.iter_tree(target):
                print(line)
            return
        rows = toc.flatten(target, leaves_only=not self.all_nodes)
        print("\t".join(FIELDS))
        for r in rows:
            d = asdict(r)
            print("\t".join(str(d[k]) for k in FIELDS))
        print(f"# {len(rows)} rows", file=sys.stderr)


@dataclass
class Manifest:
    """Flatten all (or one) collection's toc.json into a manifest table."""
    collection: Optional[str] = None  # Only this collection.
    out: Optional[Path] = None  # Output file (.tsv/.csv/.parquet).
    all_nodes: bool = flag(default=False, alias="all-nodes", negative_option="--leaves-only")  # Include folder rows (default: leaves).

    def execute(self, root: Path) -> None:
        docs = root / "documents"
        if not docs.is_dir():
            _die(f"no documents/ at {root}")
        cols = sorted(p for p in docs.iterdir() if p.is_dir() and not p.name.startswith("."))
        if self.collection:
            cols = [c for c in cols if c.name == self.collection]
        rows, missing = [], []
        for c in cols:
            try:
                rows.extend(toc.flatten(c, leaves_only=not self.all_nodes))
            except FileNotFoundError:
                missing.append(c.name)
        dicts = [asdict(r) for r in rows]
        if self.out:
            _write_manifest(self.out, dicts)
            print(f"wrote {len(rows)} rows -> {self.out}", file=sys.stderr)
        else:
            print("\t".join(FIELDS))
            for d in dicts:
                print("\t".join(str(d[k]) for k in FIELDS))
            print(f"# {len(rows)} rows", file=sys.stderr)
        if missing:
            print(f"# no toc.json: {', '.join(missing)}", file=sys.stderr)


def _write_manifest(out: Path, dicts: list[dict]) -> None:
    ext = out.suffix.lower()
    if ext == ".parquet":
        try:
            import pandas as pd
        except ImportError:
            _die("parquet needs pandas (uv sync) + pyarrow")
        try:
            pd.DataFrame(dicts).to_parquet(out, index=False)
        except Exception as e:
            _die(f"parquet write failed ({e}); install pyarrow")
    elif ext == ".csv":
        with out.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(dicts)
    else:  # tsv
        with out.open("w") as f:
            f.write("\t".join(FIELDS) + "\n")
            for d in dicts:
                f.write("\t".join(str(d[k]) for k in FIELDS) + "\n")


@dataclass
class Program:
    """Investigate the CTD Commons / EMA regulatory document collection."""
    command: Union[Get, Inventory, EmaSummary, Toc, Manifest] = subparsers(
        {"get": Get, "inventory": Inventory, "ema-summary": EmaSummary,
         "toc": Toc, "manifest": Manifest})
    root: Optional[Path] = None  # CTD commons data root (default: cwd).


def main() -> None:
    parser = ArgumentParser(prog="ctd")
    parser.add_arguments(Program, dest="prog")
    args = parser.parse_args()
    prog: Program = args.prog
    root = prog.root or Path.cwd()
    prog.command.execute(root)


if __name__ == "__main__":
    main()
