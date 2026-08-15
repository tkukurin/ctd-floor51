# tk-data-ctd

CLI for investigating the **CTD Commons / EMA** regulatory document collection.

```bash
uv sync                       # core: click, duckdb, pandas
uv sync --extra analysis      # + pyreadstat, lxml, pdfplumber
uv sync --extra docs          # + markitdown

uv run ctd inventory        # file-type counts per collection
uv run ctd ema-summary      # doc-type counts from the EMA JSON
uv run ctd manifest         # (stub) flatten toc.json -> manifest table
```


## What's in CTD commons (Aug 2026)

~3.4 GB / 5,295 files , plus a 33 MB EMA metadata dump.

| Collection | Files | Contents |
|---|---|---|
| `RDCP-A26-0001/0002/0003` | ~3,639 | One drug (ALLN-177 / reloxaliase, Allena Pharma) full eCTD submission: `1) Administrative`, `2) Summaries`, `3) Quality`, `4) Nonclinical`, `5) Clinical`. Per-study CSRs, protocols, TLFs, CDISC datasets. |
| `RDCP-E26-EMA` | 1,149 | EMA EPAR corpus, shelved by `EMEA-H-C-NNN/<doc-id>/` and also by ATC class under `By-ATC/`. |
| `ema_documents_all_en_only_en.json` | — | 69,325 structured EMA records (`id, name, type, status, dates, reference_number, document_url`). ~30 doc types. |

**Grouping is already mostly done** — each collection has `index-full.json` + `files/toc.json`,
recursive trees where every node carries `drug`, `accession`, `type`, `path`. Walk once → flat
5,295-row manifest.

### File-type mix (0001 sample)
`sas7bdat` 382, `pdf` 372, `txt` 297 (mostly SAS program dumps, not tables), `xpt` 227 (CDISC
XPORT), `sas` 155, `docx` 123, `rtf` 106, `xlsx` 66. Each study also has `define.xml` (CDISC
ODM v1.3 / def v2.0) — the variable dictionary.

## Suggested tooling

- **DuckDB** — query Parquet+JSON; join layer across accession/drug/study/ATC/EPAR.
- **pyreadstat** — read `.xpt` (XPORT) + `.sas7bdat` into pandas. *(optional: `uv sync --extra analysis`)*
- **lxml** — parse `define.xml` → ItemDefs / CodeLists.
- **Pinnacle21 Community** (free GUI) — `define.xml` viewer + SDTM/ADaM conformance.
- **markitdown** / **Apache Tika** — heterogeneous doc → text/markdown.
- **docling** — PDF tables (use pdfplumber if ML models are slow)
- **file / trid / exiftool** — true format ID + cheap metadata (author/date).
- **fdupes / jdupes** — content-hash dedup (`By-Date`, `By-ATC`, `Additional-Items-Backup` are re-shelvings of the same files).
- `pandas`, `jq`.
