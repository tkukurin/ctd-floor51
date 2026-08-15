"""Download EMA EPAR documents and convert PDFs to markdown text.

Fetches the EMA EPAR JSON feed, filters for PDFs, downloads each, and converts
to text via ``pdftotext -layout``. Resumable: existing ``.md`` files are
skipped.

Output: ``<root>/ema-texts/<medicine>/<title>.md``

EMA data sources:
  - JSON feed: https://www.ema.europa.eu/en/about-us/about-website/download-website-data-json-data-format
  - Medicines data tables: https://www.ema.europa.eu/en/medicines/download-medicine-data
  - ePI API (FHIR): https://epi.developer.ema.europa.eu/api-details
"""
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
# All EMA website documents in English (~69k records, ~85 doc types). Written to
# <root>/ema-texts/all_docs.json and read by `ctd ema-summary`.
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
    """Convert PDF bytes to text using ``pdftotext -layout``."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        tmp_pdf = f.name
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", tmp_pdf, "-"],
            capture_output=True, timeout=30,
        )
        return result.stdout.decode("utf-8", errors="ignore")
    finally:
        os.unlink(tmp_pdf)


def slugify(s: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in s).strip()[:120]


def fmt_size(n: int) -> str:
    if n < 1024**2:
        return f"{n/1024:.0f} KB"
    if n < 1024**3:
        return f"{n/1024**2:.1f} MB"
    return f"{n/1024**3:.2f} GB"


def parse_medicine_name(name: str) -> str:
    """Extract a medicine name from an EMA all-documents record ``name``.

    EPAR records look like ``<Medicine>[-H-C-<code>] : EPAR - <doctype>``; the medicine
    is the prefix before `` : EPAR`` with any trailing ``-H-C-<digits>`` variation code
    stripped. Non-EPAR names are returned as-is so they slugify to a stable folder.
    """
    if not name:
        return "unknown"
    pre = re.split(r"\s*:\s*EPAR\b", name, maxsplit=1, flags=re.I)[0]
    pre = re.sub(r"-H-C-\d.*$", "", pre).strip()
    return pre or name


def download(root: Path, *, assume_yes: bool = False, epar_only: bool = True, quiet: bool = False) -> dict:
    """Download EMA document PDFs and convert to markdown under ``<root>/ema-texts/``.

    Fetches the all-English EMA documents feed into ``<root>/ema-texts/all_docs.json``
    (24h cache), shared with ``ctd ema-summary``. By default only the EPAR corpus
    (records whose ``name`` contains "EPAR", ~19k PDFs) is downloaded; pass
    ``epar_only=False`` to download every EMA document PDF. Requires ``pdftotext``.
    """
    def log(*a, **k):
        if not quiet:
            print(*a, **k)

    out_dir = root / "ema-texts"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Feed (with 24h cache) — canonical EMA metadata, shared with `ctd ema-summary`.
    docs_path = out_dir / "all_docs.json"
    if docs_path.exists() and (time.time() - docs_path.stat().st_mtime < 86400):
        log(f"Using cached feed {docs_path.name} ({fmt_size(docs_path.stat().st_size)})")
        docs = json.loads(docs_path.read_text())
    else:
        log("Fetching EMA all-documents feed...")
        docs = fetch_json(FEED_URL)
        docs_path.write_text(json.dumps(docs))
        log(f"  Saved: {docs_path.name} ({fmt_size(docs_path.stat().st_size)})")

    if isinstance(docs, dict):
        for v in docs.values():
            if isinstance(v, list):
                docs = v
                break

    log(f"  Total documents in feed: {len(docs)}")
    if docs:
        log(f"  Sample keys: {list(docs[0].keys())}")
    log("")

    # 2. Category breakdown
    categories: Counter = Counter()
    for doc in docs:
        cat = doc.get("category") or doc.get("type") or doc.get("document_type") or "unknown"
        if isinstance(cat, list):
            cat = cat[0] if cat else "unknown"
        categories[cat] += 1
    log("Document categories:")
    for cat, count in categories.most_common(20):
        log(f"  {count:5d}  {cat}")
    log("")

    # 3. Filter for PDF URLs (optionally to the EPAR corpus only)
    targets: list[tuple] = []
    for doc in docs:
        name = doc.get("name") or ""
        if epar_only and "EPAR" not in name.upper():
            continue
        url = doc.get("url") or doc.get("file_url") or doc.get("document_url") or ""
        if not url:
            for v in doc.values():
                if isinstance(v, str) and v.endswith(".pdf"):
                    url = v
                    break
        if not url or not url.endswith(".pdf"):
            continue
        if not url.startswith("http"):
            url = BASE + url
        targets.append((doc, url))

    log(f"Documents with PDF URLs: {len(targets)}")
    if not targets:
        log(f"\nNo PDF URLs found. Feed saved: {docs_path}")
        return {"done": 0, "skipped": 0, "failed": 0, "bytes": 0}

    # 4. Size estimate (sample 5)
    log("\nSampling 5 files for size estimate...")
    sample_sizes: list[int] = []
    for doc, url in random.sample(targets, min(5, len(targets))):
        try:
            sample_sizes.append(len(download_pdf_bytes(url)))
        except Exception:
            pass
    if sample_sizes:
        avg = sum(sample_sizes) / len(sample_sizes)
        log(f"  Avg PDF size: {fmt_size(int(avg))}")
        log(f"  Estimated total PDF download: ~{fmt_size(int(avg * len(targets)))}")
    log("")

    if not assume_yes:
        log("Aborted (pass --yes / confirm to proceed).")
        return {"done": 0, "skipped": 0, "failed": 0, "bytes": 0, "aborted": True}

    # 5. Download + convert
    done = failed = skipped = 0
    total_text_bytes = 0
    for i, (doc, url) in enumerate(targets, 1):
        name = doc.get("name") or ""
        medicine = slugify(doc.get("medicine_name") or parse_medicine_name(name) or "unknown")
        title = slugify(doc.get("title") or doc.get("document_type") or Path(url).stem)
        out_path = out_dir / medicine / f"{title}.md"
        if out_path.exists():
            skipped += 1
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = pdf_to_markdown(download_pdf_bytes(url))
            if text.strip():
                out_path.write_text(text)
                total_text_bytes += len(text.encode())
                done += 1
                log(f"  [{i}/{len(targets)}] {medicine}/{title}.md ({fmt_size(len(text.encode()))})")
            else:
                failed += 1
                log(f"  [{i}/{len(targets)}] EMPTY: {url.split('/')[-1]}")
        except Exception as e:
            failed += 1
            log(f"  [{i}/{len(targets)}] FAILED: {e}")
        if i % 10 == 0:
            time.sleep(0.5)

    log(f"\nDone! Converted: {done}, Skipped: {skipped}, Failed: {failed}")
    log(f"Total text output: {fmt_size(total_text_bytes)}")
    return {"done": done, "skipped": skipped, "failed": failed, "bytes": total_text_bytes}
