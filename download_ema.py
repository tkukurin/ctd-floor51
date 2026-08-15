#!/usr/bin/env python3
"""
Download EMA EPAR documents as text (markdown) from the EMA JSON API.

EMA provides a JSON feed of all EPAR documents at:
  https://www.ema.europa.eu/en/documents/report/documents-output-epar_documents_json-report_en.json

This script:
1. Fetches the JSON feed (structured metadata for all EPAR docs)
2. Filters for assessment reports (the scientifically relevant ones)
3. Downloads each PDF -> extracts text with pdftotext -> saves as .md
4. Skips already-downloaded files (resumable)

Output: ~/proj/data/ctdcommons/ema-texts/<medicine-name>/<document-title>.md

https://www.ema.europa.eu/en/about-us/about-website/download-website-data-json-data-format


https://gemini.google.com/app/305e8cc0df2594d1

If you want to access European Medicines Agency (EMA) regulatory data, European Public Assessment Reports (EPARs), and scientific discussions without downloading and parsing thousands of individual PDF files, the EMA actually provides official structured data exports.

Here is where you can download the data in non-PDF formats:

**1. Structured JSON Data Files (Best for Developers/Databases)**
The EMA exports its entire website's data in machine-readable JSON format, specifically designed for automated systems to fetch document data and metadata without scraping. These files are updated twice a day (at 06:00 and 18:00 CET).

* **Where to find it:** [Download website data in JSON data format](https://www.ema.europa.eu/en/about-us/about-website/download-website-data-json-data-format)
* **What it includes:** You can download bulk JSON files for "All documents in English," "Centrally authorised medicines and translations," and "Other documents." This covers EPARs, scientific guidelines, product information, and regulatory procedures. It provides the metadata, summaries, and structured properties for the documents you are seeing linked as PDFs.

**2. Medicines Data Tables (Best for Excel/CSV Users)**
If you are looking for tabular data rather than JSON, the EMA provides downloadable datasets (Excel tables) that are automatically updated overnight.

* **Where to find it:** [Download medicine data](https://www.ema.europa.eu/en/medicines/download-medicine-data)
* **What it includes:** Detailed datasets on centrally authorised human and veterinary medicines (the medicines that receive EPARs), withdrawn applications, refused authorisations, post-authorisation procedures (variations), and medicine supply shortages.

**3. EMA ePI API (For Product Information)**
For exact labeling and summary of product characteristics (SmPC), the EMA provides a public Application Programming Interface (API) for electronic Product Information (ePI) built on the FHIR standard.

* **Where to find it:** [EMA API Developer Portal](https://epi.developer.ema.europa.eu/api-details)
* **What it includes:** It allows you to query endpoints to get raw, structured text for product characteristics, labeling, and package leaflets without needing an API key.

**4. Third-Party Developer Tools**
If you want to query the data rather than downloading the bulk dumps directly from the EMA, open-source projects like **BioMCP** or tools on **Apify** maintain auto-updating pipelines of the EMA human-medicines JSON feeds. These tools convert the EMA's daily JSON batches into easily queryable databases for regulatory intelligence.
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote
from urllib.request import urlopen, Request

BASE = "https://www.ema.europa.eu"
FEED_URL = f"{BASE}/en/documents/report/documents-output-epar_documents_json-report_en.json"
OUT_DIR = Path(__file__).parent / "ema-texts"


def fetch_json(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def download_pdf_bytes(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=60) as resp:
        return resp.read()


def pdf_to_markdown(pdf_bytes):
    """Convert PDF bytes to text using pdftotext."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        tmp_pdf = f.name
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", tmp_pdf, "-"],
            capture_output=True, timeout=30
        )
        return result.stdout.decode("utf-8", errors="ignore")
    finally:
        os.unlink(tmp_pdf)


def slugify(s):
    """Simple filename-safe slug."""
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in s).strip()[:120]


def fmt_size(n):
    if n < 1024**2:
        return f"{n/1024:.0f} KB"
    elif n < 1024**3:
        return f"{n/1024**2:.1f} MB"
    return f"{n/1024**3:.2f} GB"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Fetch the feed
    feed_cache = OUT_DIR / "_feed_cache.json"
    if feed_cache.exists() and (time.time() - feed_cache.stat().st_mtime < 86400):
        print(f"Using cached feed ({fmt_size(feed_cache.stat().st_size)})")
        with open(feed_cache) as f:
            docs = json.load(f)
    else:
        print(f"Fetching EMA EPAR documents feed...")
        print(f"  URL: {FEED_URL}")
        docs = fetch_json(FEED_URL)
        feed_cache.write_text(json.dumps(docs))
        print(f"  Downloaded: {fmt_size(feed_cache.stat().st_size)}")

    # Normalize: could be list or dict with a data key
    if isinstance(docs, dict):
        for v in docs.values():
            if isinstance(v, list):
                docs = v
                break

    print(f"  Total documents in feed: {len(docs)}")
    print(f"  Sample keys: {list(docs[0].keys()) if docs else 'empty'}")
    print()

    # Step 2: Show what we have and filter
    # Print category breakdown
    from collections import Counter
    categories = Counter()
    for doc in docs:
        cat = doc.get("category") or doc.get("type") or doc.get("document_type") or "unknown"
        if isinstance(cat, list):
            cat = cat[0] if cat else "unknown"
        categories[cat] += 1

    print("Document categories:")
    for cat, count in categories.most_common(20):
        print(f"  {count:5d}  {cat}")
    print()

    # Step 3: Filter for assessment reports (adjust filter after seeing categories)
    # For now, take everything that has a PDF URL
    targets = []
    for doc in docs:
        url = doc.get("url") or doc.get("file_url") or doc.get("document_url") or ""
        if not url:
            # Try nested
            for k, v in doc.items():
                if isinstance(v, str) and v.endswith(".pdf"):
                    url = v
                    break
        if not url or not url.endswith(".pdf"):
            continue
        if not url.startswith("http"):
            url = BASE + url
        targets.append((doc, url))

    print(f"Documents with PDF URLs: {len(targets)}")

    if not targets:
        print("\nNo PDF URLs found. Saving raw feed for inspection.")
        print(f"Check: {feed_cache}")
        print(f"First doc sample:\n{json.dumps(docs[0], indent=2)[:1000]}")
        return

    # Estimate size
    print(f"\nTo download all {len(targets)} PDFs and convert to text...")
    print("Sampling 5 files for size estimate...")
    import random
    sample = random.sample(targets, min(5, len(targets)))
    sample_sizes = []
    for doc, url in sample:
        try:
            data = download_pdf_bytes(url)
            sample_sizes.append(len(data))
        except Exception:
            pass
    if sample_sizes:
        avg = sum(sample_sizes) / len(sample_sizes)
        est_pdf = avg * len(targets)
        print(f"  Avg PDF size: {fmt_size(int(avg))}")
        print(f"  Estimated total PDF download: ~{fmt_size(int(est_pdf))}")
        print(f"  Text output will be ~10-20x smaller")
    print()

    # Step 4: Download and convert
    input(f"Press Enter to start downloading {len(targets)} documents (Ctrl+C to abort)...")

    done = 0
    failed = 0
    skipped = 0
    total_text_bytes = 0

    for i, (doc, url) in enumerate(targets, 1):
        medicine = slugify(doc.get("medicine_name") or doc.get("name") or "unknown")
        title = slugify(doc.get("title") or doc.get("document_type") or Path(url).stem)
        out_path = OUT_DIR / medicine / f"{title}.md"

        if out_path.exists():
            skipped += 1
            continue

        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            pdf_bytes = download_pdf_bytes(url)
            text = pdf_to_markdown(pdf_bytes)
            if text.strip():
                out_path.write_text(text)
                total_text_bytes += len(text.encode())
                done += 1
                print(f"  [{i}/{len(targets)}] {medicine}/{title}.md ({fmt_size(len(text.encode()))})")
            else:
                failed += 1
                print(f"  [{i}/{len(targets)}] EMPTY (no extractable text): {url.split('/')[-1]}")
        except Exception as e:
            failed += 1
            print(f"  [{i}/{len(targets)}] FAILED: {e}")

        if i % 10 == 0:
            time.sleep(0.5)

    print(f"\nDone! Converted: {done}, Skipped: {skipped}, Failed: {failed}")
    print(f"Total text output: {fmt_size(total_text_bytes)}")


if __name__ == "__main__":
    main()
