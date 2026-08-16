"""Download EMA EPAR documents and convert PDFs to markdown text."""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://www.ema.europa.eu"
FEED_URL = f"{BASE}/en/documents/report/documents-output-json-report_en.json"
UA = "Mozilla/5.0 (tk-data-ctd)"


def fetch_json(url: str):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def download_pdf_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=60) as resp:
        return resp.read()


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        tmp_pdf = f.name
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", tmp_pdf, "-"],
            capture_output=True,
            timeout=30,
        )
        return result.stdout.decode("utf-8", errors="ignore")
    finally:
        os.unlink(tmp_pdf)


def slugify(s: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in s).strip()[:120]


def fmt_size(n: int) -> str:
    if n < 1024**2:
        return f"{n / 1024:.0f} KB"
    if n < 1024**3:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024**3:.2f} GB"


def parse_medicine_name(name: str) -> str:
    if not name:
        return "unknown"
    pre = re.split(r"\s*:\s*EPAR\b", name, maxsplit=1, flags=re.I)[0]
    pre = re.sub(r"-H-C-\d.*$", "", pre).strip()
    return pre or name


def _get_url(doc: dict) -> str:
    if url := (doc.get("url") or doc.get("file_url") or doc.get("document_url")):
        return url
    for v in doc.values():
        if isinstance(v, str) and v.endswith(".pdf"):
            return v
    return ""


def _extract_docs(docs: list | dict) -> list[dict]:
    if isinstance(docs, dict):
        for v in docs.values():
            if isinstance(v, list):
                return v
    return docs if isinstance(docs, list) else []


def _load_feed(out_dir: Path) -> tuple[Path, list[dict]]:
    docs_path = out_dir / "all_docs.json"
    if docs_path.exists() and (time.time() - docs_path.stat().st_mtime < 86400):
        return docs_path, _extract_docs(json.loads(docs_path.read_text()))

    docs = fetch_json(FEED_URL)
    docs_path.write_text(json.dumps(docs))
    return docs_path, _extract_docs(docs)


def _find_targets(docs: list[dict], epar_only: bool) -> list[tuple[dict, str]]:
    targets: list[tuple[dict, str]] = []
    for doc in docs:
        if epar_only and "EPAR" not in str(doc.get("name", "")).upper():
            continue
        if not (url := _get_url(doc)) or not url.endswith(".pdf"):
            continue
        targets.append((doc, url if url.startswith("http") else BASE + url))
    return targets


def _estimate_size(targets: list[tuple[dict, str]]) -> list[int]:
    sample_sizes = []
    for _doc, url in random.sample(targets, min(5, len(targets))):
        try:
            sample_sizes.append(len(download_pdf_bytes(url)))
        except Exception:
            pass
    return sample_sizes


def _process_one(doc: dict, url: str, out_dir: Path) -> tuple[int, int]:
    name = doc.get("name") or ""
    med = doc.get("medicine_name") or parse_medicine_name(name)
    title = doc.get("title") or doc.get("document_type") or Path(url).stem

    if (out_path := out_dir / slugify(med) / f"{slugify(title)}.md").exists():
        return 1, 0  # skipped, bytes

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if (text := pdf_to_markdown(download_pdf_bytes(url))).strip():
            out_path.write_text(text)
            return 0, len(text.encode())
    except Exception:
        pass

    return 0, 0


def _print_categories(docs: list[dict]) -> None:
    categories: Counter = Counter()
    for doc in docs:
        cat = (
            doc.get("category")
            or doc.get("type")
            or doc.get("document_type")
            or "unknown"
        )
        categories[cat[0] if isinstance(cat, list) and cat else cat] += 1
    print("Document categories:")
    for cat, count in categories.most_common(20):
        print(f"  {count:5d}  {cat}")
    print("")


def download(
    root: Path, *, assume_yes: bool = False, epar_only: bool = True, quiet: bool = False
) -> dict:
    out_dir = root / "ema-texts"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not quiet:
        print("Fetching EMA all-documents feed...")
    docs_path, docs = _load_feed(out_dir)

    if not quiet:
        print(f"  Total documents in feed: {len(docs)}")
        _print_categories(docs)

    if not (targets := _find_targets(docs, epar_only)):
        if not quiet:
            print(f"\nNo PDF URLs found. Feed saved: {docs_path}")
        return {"done": 0, "skipped": 0, "failed": 0, "bytes": 0}

    if not quiet:
        print(f"Documents with PDF URLs: {len(targets)}")
        print("\nSampling 5 files for size estimate...")

    if sample_sizes := _estimate_size(targets):
        if not quiet:
            avg = sum(sample_sizes) / len(sample_sizes)
            print(f"  Avg PDF size: {fmt_size(int(avg))}")
            print(
                f"  Estimated total PDF download: ~{fmt_size(int(avg * len(targets)))}"
            )

    if not assume_yes:
        if not quiet:
            print("\nAborted (pass --yes / confirm to proceed).")
        return {"done": 0, "skipped": 0, "failed": 0, "bytes": 0, "aborted": True}

    return _download_loop(targets, out_dir, quiet)


def _download_loop(targets: list[tuple[dict, str]], out_dir: Path, quiet: bool) -> dict:
    done = failed = skipped = total_bytes = 0
    for i, (doc, url) in enumerate(targets, 1):
        s, b = _process_one(doc, url, out_dir)
        skipped += s
        if b > 0:
            done += 1
            total_bytes += b
        elif s == 0:
            failed += 1
        if not quiet:
            print(f"  [{i}/{len(targets)}] Processed {Path(url).stem}")
        if i % 10 == 0:
            time.sleep(0.5)

    if not quiet:
        print(f"\nDone! Converted: {done}, Skipped: {skipped}, Failed: {failed}")
        print(f"Total text output: {fmt_size(total_bytes)}")

    return {"done": done, "skipped": skipped, "failed": failed, "bytes": total_bytes}
