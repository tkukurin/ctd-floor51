# ctd-floor51

[![Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Dataset-blue)](https://huggingface.co/datasets/tkukurin/ctd-commons-manifest)

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
uv run ctd export-hf
uv run ctd ui
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


## Related

### Initiatives & Background
- **[CTD Commons](https://www.ctdcommons.org/)** — Open-access initiative (backed by 1Day Sooner & Renaissance Philanthropy) acquiring, de-identifying, and publishing regulatory dossiers from bankrupt/defunct biotechs.
- **[The Forgotten Files Project](https://ifp.org/wp-content/uploads/The-Forgotten-Files-Project-Teslo.pdf)** — Ruxandra Teslo / IFP policy proposal outlining the legal and operational framework for recovering abandoned biotech trial data.
- **[archive.icosian.net](https://archive.icosian.net/)** — Public archive hosting the initial CTD accession packages (`RDCP-A26-0001` through `0003`).

### Regulatory Transparency Portals
- **[EMA European Public Assessment Reports (EPAR)](https://www.ema.europa.eu/en/medicines/download-medicine-data)** — EMA database of assessment reports, SmPCs, and regulatory actions.
- **[EMA Policy 0070 / Clinical Data Publication](https://www.ema.europa.eu/en/human-regulatory-overview/clinical-trials-human-medicines/clinical-data-publication)** — Proactive publication portal for Clinical Study Reports (CSRs) submitted for marketing authorisation in the EU.
- **[Health Canada PRCI](https://clinical-information.canada.ca/)** — Public Release of Clinical Information database with de-identified CSRs and clinical summaries.
- **[Drugs@FDA](https://www.accessdata.fda.gov/scripts/cder/daf/) & [openFDA](https://openfda.fda.gov/)** — FDA drug approval packages, action letters, medical review PDFs, and structured query APIs.

### Patient-Level marker data

**CTD is product&submission-centred**: preserves evidence trail around a drug —
eCTD structure, CMC and nonclinical material, protocols, CSRs, TLFs, CDISC
datasets, and regulatory documents.

Resources below are **patient- or cohort-centred**: expose observed phenotypes,
treatment courses, images, omics, EHR, or sensor data.

#### Public

| Resource | Scale & access | Data quality, caveats | ▵CTD |
|---|---|---|---|
| **[Osteosarc](https://osteosarc.com/data/)** (Sid Sijbrandij) | **1 identified patient; ~25 TB and growing.** WGS/WES, single-cell and spatial assays, pathology/clinical imaging, and treatment timeline; public S3/HTTPS, no account or key. | longitudinal and multimodal depth, with manifest and checksums. intentionally identifiable, N=1, heterogeneous across providers and reference builds; no dataset-wide reuse licence. | longitudinal results for one patient |
| **[Harvard Personal Genome Project](https://my.pgp-hms.org/public_genetic_data)** | Dynamic participant-contributed collection; [current statistics](https://my.pgp-hms.org/public_genetic_data/statistics) list 925 public 23andMe records and 361 Complete Genomics records. possible overlap. Public profiles/files need no login. | Unusually open participant-linked genomes, surveys, records, microbiomes, and occasional imaging. Completeness, provenance, and formats vary sharply by participant; identification is often possible or intentional. | Personal-data donation platform. |
| **[MyConnectome / OpenNeuro `ds000031`](https://openneuro.org/datasets/ds000031)** | **1 participant**, repeatedly sampled across many sessions; CC0 and downloadable without an account. | Versioned, BIDS-formatted deep neuroimaging and physiology. N=1, dataset README notes some imaging-header discrepancies. | Repeated phenotyping of one volunteer. |
| **[NCI Imaging Data Commons](https://portal.imaging.datacommons.cancer.gov/)** | Release 24: **85,682 cases, 176 collections, ~99 TB** of radiology, digital pathology, segmentations, and metadata. No registration, but licences and attribution vary by DICOM series. | Strong DICOM normalisation, provenance, DOI, and per-series metadata. quality and licences vary; some collections are non-commercial. | Large case-level cancer-imaging commons. |
| **[Open Humans Public Data](https://www.openhumans.org/public-data/)** | Dynamic platform; members can expose genomes, wearables, location, and self-tracking files, and can later disable sharing. | Excellent for participant-controlled personal science, but no uniform schema, cohort definition, completeness, or permanence. | Participant-controlled sharing infrastructure, not a durable regulatory archive. |

#### Registered, mixed, or controlled access

| Resource | Scale & access | Data quality, caveats | ▵CTD |
|---|---|---|---|
| **[TCGA / NCI Genomic Data Commons](https://www.cancer.gov/ccg/research/genome-sequencing/tcga)** | **>20,000 primary-cancer and matched-normal samples, 33 cancer types, >2.5 PB.** Most high-level genomic, clinical, and biospecimen data are open; raw sequencing, germline, and identifying data require [dbGaP authorisation](https://gdc.cancer.gov/access-data/data-access-processes-and-tools). | Landmark, well-curated cross-cancer molecular resource with linked metadata; specimen-centric and not deeply longitudinal. | Multi-cancer cohort. |
| **[MIMIC-IV](https://physionet.org/content/mimiciv/3.1/)** | v3.1: **>65,000 ICU and >200,000 ED patients.** Requires PhysioNet credentialing, CITI training, and a signed DUA. | Rich, linkable hospital/ED/ICU EHR with compatible notes and chest X-rays. Single-centre; real-world artefacts remain, and dates are patient-shifted. | Routine-care longitudinal EHR. |
| **[OpenAPS Data Commons](https://openaps.org/outcomes/data-commons/)** | Four published data files; access requires a project request and acceptance of community criteria. | real-world DIY closed-loop diabetes telemetry. Device, configuration, and participant-generated provenance require harmonisation. | Treatment/self-tracking data. |
| **[PRO-ACT ALS Database](https://ncri1.partners.org/ProACT/)** | **13,717 subjects, 44 Phase II/III trials, >18 million longitudinal data points.** Registration, a proposed analysis, and restrictive terms are required. | Pooled trial IPD with outcomes, labs, and histories; protocols and populations differ. Not a complete archive of each trial or sponsor submission. | Participant data aggregated across trials; closer to CTD clinical datasets, missing the surrounding dossier and regulatory provenance. |
| **[Parkinson's Progression Markers Initiative (PPMI)](https://www.ppmi-info.org/access-data-specimens/download-data)** | Thousands of participants; dynamic. Application, DUA, and publication-policy agreement required. | Broad longitudinal clinical, imaging, omics, genetic, sensor, and biomarker coverage. Data are released as collected and updated frequently, so extracts and occasional errors change. | Prospective disease-progression cohort. |
| **[Alzheimer's Disease Neuroimaging Initiative (ADNI)](https://adni.loni.usc.edu/data-samples/adni-data/)** | Dynamic multi-phase cohort; no single current total. Institutional application and DUA required through LONI IDA. | Comprehensive scheduled longitudinal clinical, cognitive, MRI/PET, biofluid, and omics data. Definitions and procedures evolved between phases, and some omics use separate controlled repositories. | Biomarker cohort. |
| **[Undiagnosed Diseases Network](https://undiagnosed.hms.harvard.edu/research/data-availability/)** | [dbGaP release v8](https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id=phs001232.v8.p3): **7,544 consented subjects.** Full genomic/phenotypic data are controlled; ClinVar and selected profiles expose partial public layers. | High-quality rare-disease phenotyping, genotyping, and family structures. Public records are incomplete summaries of the controlled participant data. | Diagnostic patient/family cohort. |
| **[St. Jude Cloud](https://docs.stjude.cloud/genomics-platform/about-our-data/data-sets-and-data-access-units)** | **21 datasets**; counts are samples rather than unique patients (for example, 3,031 PCGP and 4,838 SJLIFE samples). Most raw data require account, DAC review, and a DAA. | Curated paediatric cancer, survivor, sickle-cell, and ALS genomics in governed access units. Samples can overlap, and access is granted per unit. | Governed disease-genomics platform. |
| **[All of Us Researcher Workbench](https://www.researchallofus.org/data-tools/workbench/)** | Population-scale, [continuously updated](https://www.researchallofus.org/data-tools/data-snapshots/). Aggregate public snapshots are open; row-level EHR, survey, wearable, and genomic data stay in a governed cloud workspace after institutional agreements and training. | Large and standardised to OMOP, but privacy transformations and workbench/export rules constrain linkage and analysis; compute/storage may cost money. | Population observational cohort. |

### Clinical Trial Data Sharing
- **[Vivli](https://vivli.org/)** — Global repository for individual participant data (IPD) and CSRs; most study-level data require a research proposal, sponsor review, DUA, and use of a secure environment.
- **[YODA Project](https://yoda.yale.edu/)** — Independent request and review route for participating sponsors' trial data; access is proposal-based rather than public download.
- **[ClinicalStudyDataRequest (CSDR)](https://www.clinicalstudydatarequest.com/)** — Multi-sponsor catalogue for anonymised trial data; availability and approval rules vary by sponsor and study.

### Standards & Specifications
- **[ICH CTD / eCTD Guidelines](https://www.ich.org/page/ctd)** — International Council for Harmonisation structure for Modules 1–5 (Administrative, Summaries, Quality/CMC, Nonclinical, Clinical).
- **[CDISC Standards](https://www.cdisc.org/standards)** — Clinical Data Interchange Standards Consortium data models (SDTM, ADaM, ODM, `define.xml`).
- **[Pinnacle 21 Community](https://www.pinnacle21.com/pinnacle21-community)** — Open-source validator and browser for CDISC data and `define.xml` dictionaries.
