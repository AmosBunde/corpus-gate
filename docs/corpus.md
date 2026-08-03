# Corpus selection

The pinned corpus is public commercial contracts: a 16-contract subset of CUAD supplemented with 4 exhibit 10 material contracts fetched directly from SEC EDGAR, 20 documents total. The owner pinned this corpus on 2026-08-04; substituting another corpus requires owner approval. An earlier corpus of general EDGAR filings was selected before the pin existed; its manifest entries are retained temporarily (marked `legacy: true`) until the eval set re-authoring lands in issues #39 and #40, after which they are removed.

## Why commercial contracts

- **Real.** Every document is an actual agreement between real parties, filed as a material contract exhibit or collected by CUAD from such filings. Nothing was prepared for machine consumption.
- **Messy.** The CUAD texts carry OCR-era artifacts, inconsistent numbering, ALL-CAPS headings, and wildly varying drafting styles across 16 agreement types. The direct EDGAR exhibits are modern inline-XBRL-adjacent HTML with nested tables and page furniture. Together they force the M2 parsers to handle plain text and HTML, and the chunker to find structure that differs per document.
- **Unencumbered.** CUAD v1 is released under CC BY 4.0 by The Atticus Project; EDGAR exhibits are public records not subject to copyright protection. Both can be committed, quoted, and republished in findings.

## CUAD subset

CUAD (Contract Understanding Atticus Dataset) v1 contains 510 expert-annotated commercial contracts. The subset pins one contract per agreement type, chosen at 18K to 90K characters so every document is fully readable during question authoring:

| doc id | Agreement type |
| --- | --- |
| CUAD-DISTRIBUTOR | Distributor agreement |
| CUAD-SUPPLY | Supply agreement |
| CUAD-LICENSE | Content license agreement |
| CUAD-HOSTING | License and hosting agreement |
| CUAD-ENDORSEMENT | Endorsement agreement |
| CUAD-JOINTVENTURE | Joint venture agreement |
| CUAD-FRANCHISE | Franchise agreement |
| CUAD-AGENCY | Agency agreement |
| CUAD-OUTSOURCING | Outsourcing agreement |
| CUAD-MAINTENANCE | Support and maintenance agreement |
| CUAD-SPONSORSHIP | Sponsorship agreement |
| CUAD-MANUFACTURING | Manufacturing, design, and marketing agreement |
| CUAD-SERVICES | Services agreement |
| CUAD-ALLIANCE | Strategic alliance agreement |
| CUAD-COBRANDING | Co-branding agreement |
| CUAD-PROMOTION | Promotion and distribution agreement |

### Licensing and attribution

CUAD v1 is licensed CC BY 4.0. Attribution: **CUAD v1, The Atticus Project** (Hendrycks, Burns, Chen, and Ball, "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review", NeurIPS Datasets and Benchmarks, 2021), https://www.atticusprojectai.org/cuad. This repository redistributes extracted contract texts from the dataset with this attribution, as the license permits and requires. The extracted texts are unmodified.

## Direct EDGAR exhibit 10 supplement

Four material contracts fetched directly from recent filings, pinned by accession number. These are modern HTML exhibits, distinct in format and vintage from the CUAD texts:

| doc id | Filed with | Date |
| --- | --- | --- |
| AAPL-EX-10-1-2026-02-24 | Apple Inc. Form 8-K | 2026-02-24 |
| AAPL-EX-10-2-2026-02-24-B | Apple Inc. Form 8-K | 2026-02-24 |
| KO-EX-10-1-2026-06-25 | The Coca-Cola Company Form 8-K | 2026-06-25 |
| KO-EX-10-1-2026-07-29 | The Coca-Cola Company Form 10-Q | 2026-07-29 |

## Acquisition

`make fetch-corpus` materializes everything reproducibly and idempotently:

- The CUAD data archive downloads once into `corpus/cache/` and is verified against its pinned sha256 (`f8161d18…`) on every run; per-contract texts are extracted from the archive member by exact title into `corpus/raw/CUAD/`.
- EDGAR documents download by accession with the SEC fair-access User-Agent (`SEC_USER_AGENT`) and rate limiting, as before.

Verified on 2026-08-04: 20 contracts materialized (784 KB of CUAD text plus 4 HTML exhibits), and an immediate re-run downloaded nothing.

## Known limitations

- The CUAD texts are the dataset's extracted plain text, not the original filed images; occasional OCR artifacts are part of the corpus by design.
- The demo slice under `corpus/demo/` still holds legacy filing documents; it is replaced with contract documents in issue #40 together with the legacy manifest removal.
- The corpus is English only; nothing in the eval set should assume otherwise.
