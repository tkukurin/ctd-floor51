# ctd-floor51

For context see [complex systems podcast with Ruxandra Teslo](https://www.complexsystemspodcast.com/episodes/ruxandra-teslo/).

> We as a society essentially burn the lab notes every time we go through a $1 billion process to get a drug into play. And so this Common Technical Documents thing that you're proposing is a proposal to not burn the lab notes anymore.

Here we fetch currently active list of the files.

```bash
uv sync
uv sync --extra analysis
uv sync --extra docs

uv run ctd get icosian
uv run ctd get ema --yes
uv run ctd get ema --yes --all-types   # every EMA document PDF, not just EPAR
uv run ctd inventory
uv run ctd ema-summary
uv run ctd toc [COLLECTION]
uv run ctd manifest
```

`get ema` writes/refreshes `ema-texts/all_docs.json` (all-English EMA documents feed,
~70k records); `ema-summary` reads that same file.

## What's in CTD commons (Aug 2026)

~3.4 GB / 5,295 files , plus a 33 MB EMA metadata dump.

| Collection | Files | Contents |
|---|---|---|
| `RDCP-A26-0001/0002/0003` | ~3,639 | One drug (ALLN-177 / reloxaliase, Allena Pharma) full eCTD submission: `1) Administrative`, `2) Summaries`, `3) Quality`, `4) Nonclinical`, `5) Clinical`. Per-study CSRs, protocols, TLFs, CDISC datasets. |
| `RDCP-E26-EMA` | 1,149 | EMA EPAR corpus, shelved by `EMEA-H-C-NNN/<doc-id>/` and also by ATC class under `By-ATC/`. |
| `all_docs.json` | — | ~70k structured EMA records (`id, name, type, status, dates, reference_number, document_url`), ~85 doc types; refreshed by `ctd get ema`. |

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
