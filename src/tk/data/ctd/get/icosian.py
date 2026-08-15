"""Download CTD Commons datasets from archive.icosian.net.

Resumable: files already on disk are skipped. Each collection's
``index-full.json`` is saved next to its files.
"""
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
    """Walk the tree via ``children`` keys, collecting leaf entries that carry a url."""
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
    """HEAD-request a sample of files to estimate total download size."""
    sample = random.sample(files, min(sample_n, len(files)))
    sizes: list[int] = []
    for entry in sample:
        try:
            req = Request(entry["url"], method="HEAD", headers={"User-Agent": UA})
            with urlopen(req) as resp:
                cl = resp.headers.get("Content-Length")
                if cl:
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
        return f"{nbytes/1024:.1f} KB"
    if nbytes < 1024**3:
        return f"{nbytes/1024**2:.1f} MB"
    return f"{nbytes/1024**3:.2f} GB"


def download_file(url, path: Path) -> int:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req) as resp:
        data = resp.read()
    path.write_bytes(data)
    return len(data)


def download(root: Path, *, delay: float = 0.5, estimate: bool = True, quiet: bool = False) -> dict:
    """Download all collections from archive.icosian.net into ``<root>/documents/``.

    Returns a stats dict: ``{downloaded, skipped, failed, bytes, failed_paths}``.
    """
    def log(*a, **k):
        if not quiet:
            print(*a, **k)

    log("Fetching top-level index...")
    accessions = fetch_json(f"{BASE_URL}/index.json").get("accessions", [])
    log(f"Found {len(accessions)} collections\n")

    all_collections: list[tuple] = []
    total_files = 0
    for acc in accessions:
        acc_id = acc["id"]
        try:
            full_index = fetch_json(f"{BASE_URL}/documents/{acc_id}/index-full.json")
        except Exception as e:
            log(f"  ERROR fetching index for {acc_id}: {e}")
            continue
        files = extract_files(full_index)
        all_collections.append((acc, full_index, files))
        total_files += len(files)
        log(f"  {acc['name']}: {len(files)} files")

    log(f"\nTotal files across all collections: {total_files}")
    if estimate:
        flat = [f for _, _, files in all_collections for f in files]
        est = estimate_size(flat, sample_n=30)
        if est:
            log(f"Estimated total download size: ~{fmt_size(est)} (sampled 30 files)")
    log("")

    downloaded_bytes = 0
    downloaded_count = 0
    skipped_count = 0
    failed_paths: list[str] = []

    for acc, full_index, files in all_collections:
        acc_id = acc["id"]
        log("=" * 60)
        log(f"Collection: {acc['name']} ({acc_id}) — {len(files)} files")
        log("=" * 60)

        index_dir = root / "documents" / acc_id
        index_dir.mkdir(parents=True, exist_ok=True)
        (index_dir / "index-full.json").write_text(json.dumps(full_index, indent=2))

        for i, entry in enumerate(files, 1):
            url = entry["url"]
            rel_path = entry.get("path") or url.replace(BASE_URL + "/", "")
            out_path = root / rel_path
            if out_path.exists():
                skipped_count += 1
                continue
            out_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                size = download_file(url, out_path)
                downloaded_bytes += size
                downloaded_count += 1
                log(f"  [{i}/{len(files)}] {out_path.name} ({fmt_size(size)})  "
                    f"[total: {fmt_size(downloaded_bytes)}]")
            except Exception as e:
                failed_paths.append(str(out_path))
                log(f"  [{i}/{len(files)}] FAILED {out_path.name}: {e}")
            if delay and i % 10 == 0:
                time.sleep(delay)

    log(f"\nDone! Downloaded {downloaded_count} files ({fmt_size(downloaded_bytes)}), "
        f"skipped {skipped_count} existing, failed {len(failed_paths)}.")
    return {
        "downloaded": downloaded_count,
        "skipped": skipped_count,
        "failed": len(failed_paths),
        "bytes": downloaded_bytes,
        "failed_paths": failed_paths,
    }
