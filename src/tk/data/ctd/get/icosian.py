"""Download CTD Commons datasets from archive.icosian.net."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from urllib.request import Request, urlopen

BASE_URL = "https://archive.icosian.net"
UA = "Mozilla/5.0 (tk-data-ctd)"


def fetch_json(url: str):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req) as resp:
        return json.loads(resp.read())


def extract_files(node):
    files: list[dict] = []
    if isinstance(node, dict):
        if node.get("type") and node["type"] != "folder" and "url" in node:
            files.append(node)
        for child in node.get("children", []):
            files.extend(extract_files(child))
    elif isinstance(node, list):
        for item in node:
            files.extend(extract_files(item))
    return files


def estimate_size(files, sample_n=20):
    sample = random.sample(files, min(sample_n, len(files)))
    sizes: list[int] = []
    for entry in sample:
        try:
            req = Request(entry["url"], method="HEAD", headers={"User-Agent": UA})
            with urlopen(req) as resp:
                if cl := resp.headers.get("Content-Length"):
                    sizes.append(int(cl))
        except Exception:
            pass
    if not sizes:
        return None
    return (sum(sizes) / len(sizes)) * len(files)


def fmt_size(nbytes):
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024**2:
        return f"{nbytes / 1024:.1f} KB"
    if nbytes < 1024**3:
        return f"{nbytes / 1024**2:.1f} MB"
    return f"{nbytes / 1024**3:.2f} GB"


def download_file(url, path: Path) -> int:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req) as resp:
        data = resp.read()
    path.write_bytes(data)
    return len(data)


def _fetch_collections(quiet: bool) -> list[tuple[dict, dict, list[dict]]]:
    if not quiet:
        print("Fetching top-level index...")
    accessions = fetch_json(f"{BASE_URL}/index.json").get("accessions", [])
    if not quiet:
        print(f"Found {len(accessions)} collections\n")

    cols: list[tuple[dict, dict, list[dict]]] = []
    for acc in accessions:
        acc_id = acc["id"]
        try:
            full_index = fetch_json(f"{BASE_URL}/documents/{acc_id}/index-full.json")
        except Exception as e:
            if not quiet:
                print(f"  ERROR fetching index for {acc_id}: {e}")
            continue
        files = extract_files(full_index)
        cols.append((acc, full_index, files))
        if not quiet:
            print(f"  {acc['name']}: {len(files)} files")
    return cols


def _print_estimates(cols: list[tuple[dict, dict, list[dict]]], quiet: bool) -> None:
    if quiet:
        return
    total_files = sum(len(f) for _, _, f in cols)
    print(f"\nTotal files across all collections: {total_files}")
    flat = [f for _, _, files in cols for f in files]
    if est := estimate_size(flat, sample_n=30):
        print(f"Estimated total download size: ~{fmt_size(est)} (sampled 30 files)")
    print("")


def _process_file(entry: dict, root: Path) -> tuple[int, int, str]:
    url = entry["url"]
    rel_path = entry.get("path") or url.replace(BASE_URL + "/", "")
    out_path = root / rel_path

    if out_path.exists():
        return 1, 0, ""  # skipped

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        size = download_file(url, out_path)
        return 0, size, out_path.name
    except Exception as e:
        return -1, 0, str(e)


def _download_collection(
    acc: dict, index: dict, files: list[dict], root: Path, quiet: bool, delay: float
) -> tuple[int, int, int, list[str]]:
    acc_id = acc["id"]
    if not quiet:
        print("=" * 60)
        print(f"Collection: {acc['name']} ({acc_id}) — {len(files)} files")
        print("=" * 60)

    index_dir = root / "documents" / acc_id
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "index-full.json").write_text(json.dumps(index, indent=2))

    downloaded_bytes = downloaded_count = skipped_count = 0
    failed_paths: list[str] = []

    for i, entry in enumerate(files, 1):
        status, b, msg = _process_file(entry, root)
        if status == 1:
            skipped_count += 1
        elif status == 0:
            downloaded_bytes += b
            downloaded_count += 1
            if not quiet:
                print(
                    f"  [{i}/{len(files)}] {msg} ({fmt_size(b)})  [total: {fmt_size(downloaded_bytes)}]"
                )
        else:
            failed_paths.append(msg)
            if not quiet:
                print(f"  [{i}/{len(files)}] FAILED: {msg}")

        if delay and i % 10 == 0:
            time.sleep(delay)

    return downloaded_count, downloaded_bytes, skipped_count, failed_paths


def download(
    root: Path, *, delay: float = 0.5, estimate: bool = True, quiet: bool = False
) -> dict:
    cols = _fetch_collections(quiet)
    if estimate:
        _print_estimates(cols, quiet)

    total_d_bytes = total_d_count = total_skipped = 0
    all_failed: list[str] = []

    for acc, full_index, files in cols:
        dc, db, sc, fp = _download_collection(
            acc, full_index, files, root, quiet, delay
        )
        total_d_count += dc
        total_d_bytes += db
        total_skipped += sc
        all_failed.extend(fp)

    if not quiet:
        print(
            f"\nDone! Downloaded {total_d_count} files ({fmt_size(total_d_bytes)}), "
            f"skipped {total_skipped} existing, failed {len(all_failed)}."
        )

    return {
        "downloaded": total_d_count,
        "skipped": total_skipped,
        "failed": len(all_failed),
        "bytes": total_d_bytes,
        "failed_paths": all_failed,
    }
