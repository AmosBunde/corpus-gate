# Corpus selection

The corpus is a pinned set of 21 SEC EDGAR filings from three issuers across three industries. Selection happened before any ingestion code was written, because the eval set (milestone M1) is authored against these documents and the eval set comes first.

## Why SEC EDGAR

- **Real.** These are the actual disclosure documents of public companies, produced under regulatory deadline pressure by different legal and finance teams with different tooling. Nothing about them was prepared for machine consumption beyond what the SEC mandates.
- **Messy.** The primary documents are inline-XBRL HTML: deeply nested tables, tagged financial facts interleaved with narrative, page-break artifacts, and structure that differs by issuer, by form type, and by filing agent. The same logical section (risk factors, MD&A) is laid out differently in every document. File sizes in this corpus run from 32 KB (an 8-K) to 5.7 MB (a proxy statement), which forces the M2 chunker to be genuinely structure aware rather than length based.
- **Unencumbered.** EDGAR filings are public records; the SEC states that submitted filings are not subject to copyright protection. They can be committed, quoted, and republished in findings without clearance.

## Issuers

| Issuer | Ticker | CIK | Industry | Why included |
| --- | --- | --- | --- | --- |
| Apple Inc. | AAPL | 320193 | Technology hardware | Large, conventionally structured filings; the clean end of messy |
| The Coca-Cola Company | KO | 21344 | Consumer staples | Segment-heavy reporting, long proxy; different filing agent conventions |
| Ford Motor Company | F | 37996 | Automotive and credit | Two-business structure (automotive plus Ford Credit) makes cross-reference questions genuinely hard |

Three industries mean lookup questions cannot be answered from priors about one sector, and cross-reference questions can span issuers (for example, comparing stated risk factors) as well as documents of one issuer.

## Form types and date range

Per issuer: one 10-K (fiscal 2025), two 10-Qs (2026), three 8-Ks (2026), one DEF 14A proxy statement (2026). 21 documents total, spanning October 2025 to July 2026.

- **10-K**: the annual report; long narrative plus audited financials; source for lookup and synthesis questions.
- **10-Q**: quarterly updates; smaller, repetitive structure; good for time-anchored lookups and for out-of-corpus refusal contrast (quarters not in the corpus).
- **8-K**: event disclosures; short, heterogeneous, often exhibit-driven; the small end of the parsing problem and the demo slice.
- **DEF 14A**: proxy statements; the messiest HTML in the set (compensation tables, graphics-heavy layouts); a stress test for normalization.

## Acquisition

Every document is pinned by accession number in `corpus/manifest.json`. `make fetch-corpus` downloads exactly those documents into `corpus/raw/` (gitignored), skipping files already present, one request at a time with a 0.5 second pause, far under the SEC fair-access ceiling. The SEC asks for a descriptive User-Agent with contact information: set `SEC_USER_AGENT` accordingly; the default identifies this repository.

Re-running the command is idempotent: a second run downloads nothing. Verified on 2026-08-03: 21 downloaded, then 0 downloaded and 21 present, 31 MB total.

## Demo slice

`corpus/demo/` commits the smallest 8-K per issuer (128 KB total) so a clean machine can exercise the full pipeline from `docker compose up` without hitting EDGAR. The demo slice is a strict subset of the manifest; it exists for demonstration, and eval runs use the full corpus.

## Known limitations

- Exhibits are not fetched at M1; the manifest pins primary documents only. If M1 question authoring needs a specific exhibit (for example, a press release attached to an 8-K), the manifest grows by that exhibit in the same PR as the question that cites it.
- The corpus is English only and United States only; nothing in the eval set should assume otherwise.
- Filed HTML occasionally references external image assets that are not fetched; parsing must tolerate broken image references.
