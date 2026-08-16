"""CLI for the CTD Commons / EMA regulatory document collection (simple_parsing)."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from simple_parsing import ArgumentParser, field, flag, subparsers

from .get import ema, icosian
from .transform import toc

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from datasets import Dataset

    from .transform.hf import build_manifest, push_to_hub, write_dataset_card
except ImportError:
    Dataset = None
    build_manifest = None
    push_to_hub = None
    write_dataset_card = None

try:
    from . import ui
except ImportError:
    ui = None


FIELDS = ["accession", "drug", "type", "name", "path", "depth", "is_leaf"]


def _die(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


@dataclass
class GetIcosian:
    """Download all collections from archive.icosian.net into <root>/documents/."""

    delay: float = 0.5
    estimate: bool = flag(default=True, negative_option="--no-estimate")

    def execute(self, root: Path) -> None:
        icosian.download(root, delay=self.delay, estimate=self.estimate)


@dataclass
class GetEma:
    """Download EMA document PDFs as markdown under <root>/ema-texts/."""

    yes: bool = flag(default=False)
    all_types: bool = flag(default=False, alias="all-types")

    def execute(self, root: Path) -> None:
        if not self.yes:
            try:
                if input("Download + convert EMA PDFs? [y/N] ").strip().lower() not in {
                    "y",
                    "yes",
                }:
                    _die("aborted")
            except EOFError:
                _die("aborted")
        ema.download(root, assume_yes=True, epar_only=not self.all_types)


@dataclass
class Get:
    """Download data sources."""

    command: GetIcosian | GetEma = subparsers({"icosian": GetIcosian, "ema": GetEma})

    def execute(self, root: Path) -> None:
        self.command.execute(root)


@dataclass
class Inventory:
    """File-type distribution per collection under documents/."""

    def execute(self, root: Path) -> None:
        if not (docs := root / "documents").is_dir():
            _die(f"no documents/ at {root}")

        for col in sorted(
            p for p in docs.iterdir() if p.is_dir() and not p.name.startswith(".")
        ):
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

    path: Path | None = field(default=None, positional=True)

    def execute(self, root: Path) -> None:
        path = self.path or (root / "ema-texts/all_docs.json")
        if not path.is_file():
            _die(f"not found: {path}")

        records = json.loads(path.read_text())["data"]
        types = Counter(r.get("type", "") for r in records)
        print(f"{len(records)} records in {path.name}")
        for t, n in types.most_common():
            print(f"  {t:<28} {n}")


def _toc_list_collections(cols: list[Path]) -> None:
    for c in cols:
        try:
            print(f"{c.name}\t{len(toc.flatten(c, leaves_only=True))}")
        except FileNotFoundError:
            print(f"{c.name}\tno toc.json")


def _toc_print_flat(target: Path, all_nodes: bool) -> None:
    rows = toc.flatten(target, leaves_only=not all_nodes)
    print("\t".join(FIELDS))
    for r in rows:
        print("\t".join(str(asdict(r)[k]) for k in FIELDS))
    print(f"# {len(rows)} rows", file=sys.stderr)


@dataclass
class Toc:
    """Traverse a single collection's files/toc.json; without COLLECTION, list collections."""

    collection: str | None = field(default=None, positional=True)
    as_tree: bool = flag(default=False, alias="tree")
    all_nodes: bool = flag(
        default=False, alias="all-nodes", negative_option="--leaves-only"
    )
    docs_dir: Path | None = field(default=None, alias="docs")

    def execute(self, root: Path) -> None:
        if not (docs := self.docs_dir or (root / "documents")).is_dir():
            _die(f"no documents/ at {docs}")

        cols = sorted(
            p for p in docs.iterdir() if p.is_dir() and not p.name.startswith(".")
        )

        if not self.collection:
            _toc_list_collections(cols)
            return

        if not (target := next((c for c in cols if c.name == self.collection), None)):
            _die(f"unknown collection: {self.collection}")

        if self.as_tree:
            for line in toc.iter_tree(target):
                print(line)
        else:
            _toc_print_flat(target, self.all_nodes)


def _write_manifest(out: Path, dicts: list[dict], fields: list[str]) -> None:
    ext = out.suffix.lower()
    if ext == ".parquet":
        if pd is None:
            _die("parquet needs pandas/pyarrow (uv sync)")
        try:
            pd.DataFrame(dicts).to_parquet(out, index=False)
        except Exception as e:
            _die(f"parquet write failed: {e}")
    elif ext == ".csv":
        with out.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(dicts)
    else:
        with out.open("w") as f:
            f.write("\t".join(fields) + "\n")
            for d in dicts:
                f.write("\t".join(str(d[k]) for k in fields) + "\n")


@dataclass
class Manifest:
    """Flatten all (or one) collection's toc.json into a manifest table."""

    collection: str | None = None
    out: Path | None = None
    all_nodes: bool = flag(
        default=False, alias="all-nodes", negative_option="--leaves-only"
    )

    def execute(self, root: Path) -> None:
        if not (docs := root / "documents").is_dir():
            _die(f"no documents/ at {root}")

        cols = sorted(
            p for p in docs.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
        if self.collection:
            cols = [c for c in cols if c.name == self.collection]

        rows, missing = [], []
        for c in cols:
            try:
                rows.extend(toc.flatten(c, leaves_only=not self.all_nodes))
            except FileNotFoundError:
                missing.append(c.name)

        dicts = [asdict(r) for r in rows]

        if not self.out:
            print("\t".join(FIELDS))
            for d in dicts:
                print("\t".join(str(d[k]) for k in FIELDS))
            print(f"# {len(rows)} rows", file=sys.stderr)
        else:
            _write_manifest(self.out, dicts, FIELDS)
            print(f"wrote {len(rows)} rows -> {self.out}", file=sys.stderr)

        if missing:
            print(f"# no toc.json: {', '.join(missing)}", file=sys.stderr)


@dataclass
class ExportHf:
    """Export the CTD Commons metadata to a Hugging Face Parquet dataset."""

    out: Path = field(
        default=Path("exports/huggingface/manifest.parquet"), positional=True
    )
    include_ema: bool = flag(default=False, alias="include-ema")
    push_to: str | None = field(default=None, alias="push")

    def execute(self, root: Path) -> None:
        if Dataset is None or build_manifest is None or write_dataset_card is None:
            _die("The 'huggingface' extra is required (uv sync --extra huggingface)")

        if not (docs_dir := root / "documents").is_dir():
            _die(f"No documents/ dir found at {root}")

        print(f"Building Hugging Face dataset from {docs_dir.name}...")
        records = build_manifest(docs_dir, skip_ema=not self.include_ema)

        if not records:
            _die("No files found to process.")

        ds = Dataset.from_list(records)
        out_path = root / self.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ds.to_parquet(str(out_path))
        print(f"Exported {len(ds)} records to {out_path}")

        readme_path = write_dataset_card(out_path.parent)
        print(f"Exported dataset card to {readme_path}")

        if self.push_to:
            print(f"Pushing to Hugging Face Hub: {self.push_to}...")
            try:
                url = push_to_hub(self.push_to, out_path, readme_path, private=True)
                print(f"Success! Dataset available at: {url}")
            except Exception as e:
                _die(
                    f"Failed to push to Hub: {e}\n(Make sure you run `huggingface-cli login` first)"
                )


@dataclass
class Ui:
    """Launch a local minimal web UI to view the Hugging Face manifest."""

    path: Path = field(
        default=Path("exports/huggingface/manifest.parquet"), positional=True
    )
    port: int = flag(default=7860)
    share: bool = flag(default=False)

    def execute(self, root: Path) -> None:
        if ui is None:
            _die("The 'ui' extra is required (uv sync --extra ui)")

        parquet_path = root / self.path
        if not parquet_path.exists():
            _die(
                f"Parquet file not found at {parquet_path}. Run `ctd export-hf` first."
            )

        print(f"Starting UI for {parquet_path} on port {self.port}...")
        ui.launch(parquet_path, root, share=self.share, server_port=self.port)


@dataclass
class Program:
    """Investigate the CTD Commons / EMA regulatory document collection."""

    command: Get | Inventory | EmaSummary | Toc | Manifest | ExportHf | Ui = subparsers(
        {
            "get": Get,
            "inventory": Inventory,
            "ema-summary": EmaSummary,
            "toc": Toc,
            "manifest": Manifest,
            "export-hf": ExportHf,
            "ui": Ui,
        }
    )
    root: Path | None = None


def main() -> None:
    parser = ArgumentParser(prog="ctd")
    parser.add_arguments(Program, dest="prog")
    args = parser.parse_args()

    root = args.prog.root or Path.cwd()
    args.prog.command.execute(root)


if __name__ == "__main__":
    main()
