#!/usr/bin/env python3
"""Download all datasets from archive.icosian.net to ~/proj/data/ctdcommons"""

import json
import time
from pathlib import Path
from urllib.parse import unquote
from urllib.request import urlopen, Request

BASE_URL = "https://archive.icosian.net"
OUT_DIR = Path(__file__).parent


def fetch_json(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req) as resp:
        return json.loads(resp.read())


def extract_files(node):
    """Walk the tree via 'children' keys, collecting leaf (non-folder) entries."""
    files = []
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
    import random
    sample = random.sample(files, min(sample_n, len(files)))
    sizes = []
    for entry in sample:
        try:
            req = Request(entry["url"], method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req) as resp:
                cl = resp.headers.get("Content-Length")
                if cl:
                    sizes.append(int(cl))
        except Exception:
            pass
    if not sizes:
        return None
    avg = sum(sizes) / len(sizes)
    return avg * len(files)


def fmt_size(nbytes):
    if nbytes < 1024:
        return f"{nbytes} B"
    elif nbytes < 1024**2:
        return f"{nbytes/1024:.1f} KB"
    elif nbytes < 1024**3:
        return f"{nbytes/1024**2:.1f} MB"
    else:
        return f"{nbytes/1024**3:.2f} GB"


def download_file(url, path):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req) as resp:
        data = resp.read()
        path.write_bytes(data)
        return len(data)


def main():
    print("Fetching top-level index...")
    top_index = fetch_json(f"{BASE_URL}/index.json")

    accessions = top_index.get("accessions", [])
    print(f"Found {len(accessions)} collections\n")

    # First pass: gather all files and estimate total size
    all_collections = []
    total_files = 0
    for acc in accessions:
        acc_id = acc["id"]
        full_index_url = f"{BASE_URL}/documents/{acc_id}/index-full.json"
        try:
            full_index = fetch_json(full_index_url)
        except Exception as e:
            print(f"  ERROR fetching index for {acc_id}: {e}")
            continue
        files = extract_files(full_index)
        all_collections.append((acc, full_index, files))
        total_files += len(files)
        print(f"  {acc['name']}: {len(files)} files")

    print(f"\nTotal files across all collections: {total_files}")

    # Estimate download size from a sample across all collections
    all_files_flat = [f for _, _, files in all_collections for f in files]
    est = estimate_size(all_files_flat, sample_n=30)
    if est:
        print(f"Estimated total download size: ~{fmt_size(est)} (based on sampling 30 files)")
    print()

    # Second pass: download
    downloaded_bytes = 0
    downloaded_count = 0
    skipped_count = 0

    for acc, full_index, files in all_collections:
        acc_id = acc["id"]
        acc_name = acc["name"]
        print(f"{'='*60}")
        print(f"Collection: {acc_name} ({acc_id}) — {len(files)} files")
        print(f"{'='*60}")

        # Save the index itself
        index_dir = OUT_DIR / "documents" / acc_id
        index_dir.mkdir(parents=True, exist_ok=True)
        (index_dir / "index-full.json").write_text(json.dumps(full_index, indent=2))

        for i, entry in enumerate(files, 1):
            url = entry["url"]
            rel_path = unquote(entry.get("path", ""))
            if not rel_path:
                rel_path = unquote(url.replace(BASE_URL + "/", ""))

            out_path = OUT_DIR / rel_path
            if out_path.exists():
                skipped_count += 1
                continue

            out_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                size = download_file(url, out_path)
                downloaded_bytes += size
                downloaded_count += 1
                print(f"  [{i}/{len(files)}] {out_path.name} ({fmt_size(size)})  [total: {fmt_size(downloaded_bytes)}]")
            except Exception as e:
                print(f"  [{i}/{len(files)}] FAILED {out_path.name}: {e}")

            # Small delay to be polite
            if i % 10 == 0:
                time.sleep(0.5)

    print(f"\nDone! Downloaded {downloaded_count} files ({fmt_size(downloaded_bytes)}), skipped {skipped_count} existing.")

if __name__ == "__main__":
    main()
