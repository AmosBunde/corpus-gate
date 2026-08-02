# Architecture diagrams

Five interactive HTML diagrams, rendered with Archify from the JSON specifications in this directory. Each HTML file opens directly in a browser, works without network access (one optional web font loads when online; all rendering logic and data are inline), and supports theme switching, pan and zoom, search, focus, and guided views. Every diagram passed showcase validation with zero composition errors and zero warnings.

| Diagram | Type | Source | Shows |
| --- | --- | --- | --- |
| [system.html](system.html) | architecture | `system.architecture.json` | Component map with the self-hosted deployment boundary and the eval gate boundary |
| [query.html](query.html) | sequence | `query.sequence.json` | One question through the agent loop, ending in an answer with chunk ID citations |
| [eval-gate.html](eval-gate.html) | workflow | `eval-gate.workflow.json` | How a candidate variant is scored, audited, and gated against the champion |
| [ingestion.html](ingestion.html) | dataflow | `ingestion.dataflow.json` | Filings to provenance-carrying chunks, vectors, and independently scored retrieval |
| [adapter.html](adapter.html) | lifecycle | `adapter.lifecycle.json` | A LoRA adapter version from curated pairs through decontamination and the gate |

The Mermaid sources in the repository README section 2 and the styled overview in `docs/architecture.html` remain the canonical quick references. Any PR that changes a component boundary or a tool updates the affected diagram here in the same PR, by editing the JSON specification and re-rendering with Archify at showcase quality.
