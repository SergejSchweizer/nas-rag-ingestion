# NAS RAG Ingestion

LlamaIndex-based RAG ingestion and retrieval pipeline using Qdrant as vector database and OpenWebUI as chat interface.

## Table of Contents
- [Overview](#overview)
  - [Architecture](#architecture)
  - [Features](#features)
  - [Tech Stack](#tech-stack)
  - [Repository Structure](#repository-structure)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [Quick Start](#quick-start)
  - [Editable Install](#editable-install)
  - [Dependency Management](#dependency-management)
  - [Configuration](#configuration)
- [Ingestion Design](#ingestion-design)
  - [Step 1: Parsing](#step-1-parsing)
  - [Implementation Guide](#implementation-guide)
  - [Semantic Schema](#semantic-schema)
  - [Hierarchy Build](#hierarchy-build)
  - [Table And Figure Handling](#table-and-figure-handling)
  - [Metadata Contract](#metadata-contract)
  - [Design Patterns](#design-patterns)
  - [Hierarchical Chunking Strategy](#hierarchical-chunking-strategy)
  - [Pipeline Flow](#pipeline-flow)
- [Integration](#integration)
  - [OpenWebUI Integration](#openwebui-integration)
  - [Qdrant Collection Design](#qdrant-collection-design)
- [Operations](#operations)
  - [Runbook](#runbook)
  - [Logging](#logging)
  - [Testing](#testing)
  - [Troubleshooting](#troubleshooting)
  - [Security Notes](#security-notes)
- [Project Governance](#project-governance)
  - [Roadmap](#roadmap)
  - [Contributing](#contributing)
  - [Author](#author)
  - [License](#license)

## Overview

## Architecture
- Data ingestion: local NAS documents and other configured sources
- Processing: parse, normalize, chunk documents
- Embeddings: generate vectors using configured embedding model
- Storage: upsert vectors + metadata into Qdrant
- Retrieval and answer: LlamaIndex retriever/query engine
- UI: OpenWebUI calls the query endpoint for chat

## Features
- Config-driven ingestion and indexing
- Metadata-aware retrieval
- Repeatable ingestion jobs
- OpenWebUI-ready integration path
- Secret-safe setup (secrets only in local config, not in README/Git)

## Tech Stack
- Python 3.11+
- LlamaIndex
- Qdrant
- OpenWebUI

## Repository Structure
```text
CI workflows
configuration
local data mounts
documentation
dependency definitions
helper scripts
pipeline source code
tests
project documentation
```

## Setup

## Prerequisites
- Docker and Docker Compose
- Python 3.11+
- Running Qdrant instance
- Running OpenWebUI instance
- Model provider credentials (if required)
- CPU-only environment (no GPU required)

## Quick Start
1. Create local config from template:
   - Copy the example config to your local runtime config file.
2. Fill secrets and endpoints in your local runtime config file.
3. Create and activate virtual environment.
4. Install dependencies:
   - Runtime dependencies install command from your dependency files.
   - Dev/test dependencies install command from your dependency files.
5. Install project in editable mode:
   - `pip install -e .`
6. Run parsing step for your NAS corpus:
   - Default (all runtime locations from config): `python3 <parse-script> --config <runtime-config-file>`
   - Limited sample run: `python3 <parse-script> --config <runtime-config-file> --max-files 50`
   - Override one output location temporarily with a CLI override flag if needed.
7. Continue with indexing/retrieval services (next implementation steps).

## Editable Install
- Project now includes `pyproject.toml`, so `pip install -e .` works.
- Use editable mode during development so imports stay stable while code changes.

## Dependency Management
- Base dependency file: runtime dependencies
- Dev dependency file with test and lint tooling
- Root dependency entrypoint file
- Dependencies are pinned with exact versions (`==`) for reproducibility.

Rule for this repository:
- Target is GPU-free hardware only; keep dependencies and defaults CPU-compatible.
- Every new/changed functionality must update dependency files if package needs changed.
- Every new/changed functionality must also update tests.
- Every class and function must have a docstring; keep docstrings and README sections updated with each change.
- Runtime locations are configured under `paths` in local config; avoid hardcoding them in code.

## Ingestion Design

## Step 1: Parsing
Current parser implementation:
- Parsing package with dedicated modules:
  - Parser orchestration
  - Extractor strategies and factory
  - Parsed data model
  - Parsing defaults
- CLI parser entrypoint script
- Runtime config file
- Supported file types: `.pdf`, `.md`, `.txt`
- Optional run limiter: `--max-files N` to ingest only first N discovered files per run
- Idempotent ingestion state location is configured in `paths.state_file`
- Unchanged files are skipped by default (disable with `--no-skip-unchanged`)

Output:
- JSONL output (one parsed document per line)
- Human-readable tracking manifest output
- Ingestion state output (fingerprints to avoid re-ingesting unchanged files)
- Structured semantic elements
- Parent retrieval nodes aligned to section boundaries
- Child retrieval nodes for fine-grained retrieval

## Implementation Guide
This section is the complete implementation guide for parsing.

### Purpose
The parsing implementation is designed to:
1. transform raw files into semantic elements,
2. build hierarchy-aware parent and child retrieval nodes,
3. attach rich metadata for filtering and reranking,
4. serialize outputs for downstream indexing and audit.

### Scope
Current implementation covers:
1. file discovery and extension filtering,
2. extractor-based content loading,
3. semantic element extraction,
4. section-aligned parent node construction,
5. retrieval-granularity child node construction,
6. table and figure specialized chunk handling,
7. metadata enrichment,
8. idempotent state tracking,
9. failure-aware logging.

### Core Data Model
`ParsedDocument` includes:
1. legacy compatibility fields:
   - `doc_id`
   - `text`
   - `metadata`
2. structured fields:
   - `elements` (`SemanticElement[]`)
   - `parent_nodes` (`ParentNode[]`)
   - `child_nodes` (`ChildNode[]`)

`SemanticElement` fields:
- `element_id`
- `element_type`
- `text`
- `page`
- `order`
- `section_path`
- `metadata`

Supported `element_type` values:
- `title`
- `section_heading`
- `paragraph`
- `table`
- `figure_caption`
- `equation`
- `references`

`ParentNode` fields:
- `parent_id`
- `doc_id`
- `section_path`
- `page_start`
- `page_end`
- `text`
- `metadata`

`ChildNode` fields:
- `child_id`
- `parent_id`
- `doc_id`
- `chunk_level`
- `chunk_type`
- `section_path`
- `page_start`
- `page_end`
- `text`
- `metadata`

Supported `chunk_type` values:
- `text`
- `table`
- `figure`

### End-to-End Flow
1. discover files.
2. optionally skip unchanged files (state fingerprint match).
3. extract raw text by file extension.
4. split text into page units.
5. classify line-level semantic elements.
6. merge adjacent compatible elements.
7. infer paper metadata (`paper_title`, `authors`, `year`).
8. build parent nodes from section boundaries.
9. build child nodes:
   - text windows from parent text,
   - dedicated table chunks,
   - dedicated figure chunks with nearby context.
10. serialize outputs to JSONL and manifest.
11. update state.
12. log run stats and unparsed-file details.

### Semantic Extraction Details
Heading detection uses:
1. markdown headings (`#`, `##`, ...),
2. numbered headings (`1`, `1.2`, `2.3.4`),
3. known keywords (`Abstract`, `Introduction`, `References`).

Figure detection:
- lines starting with `Figure` or `Fig.` and a numeric marker.

Table detection:
- pipe-delimited rows,
- tab-delimited rows,
- multi-column spacing heuristics.

Equation detection:
- lines containing `=`,
- plus math-like operators or symbols.

References mode:
- after references section begins, subsequent lines are tagged as `references`.

### Parent Node Construction
Parent nodes are structure-aligned, not fixed-token:
1. accumulate elements until a new `section_heading` appears,
2. flush current parent on heading transition,
3. start a new parent for the new section path.

This preserves semantic boundaries and improves section-grounded retrieval.

### Child Node Construction
Text child nodes:
1. generated from parent text via token windows,
2. chunk size from `chunking.chunk_size`,
3. overlap from `chunking.chunk_overlap`.

Table child nodes:
1. emitted separately from text chunks,
2. preserve row/column arrays in metadata (`table_rows`).

Figure child nodes:
1. emitted separately from text chunks,
2. include figure caption plus nearby explanatory paragraph context.

### Metadata Contract
Document-level metadata:
- `doc_id`
- `paper_title`
- `authors`
- `year`
- `source_path`
- `relative_path`
- `topic`
- `char_count`
- `page_start`
- `page_end`
- `elements_count`
- `parent_nodes_count`
- `child_nodes_count`

Parent metadata includes:
- `chunk_level = "parent"`
- section and page context
- paper-level metadata

Child metadata includes:
- `chunk_level = "child"`
- `chunk_type` in `{text, table, figure}`
- `parent_id`, `child_id`
- section and page context
- paper-level metadata
- specialized fields (`table_rows`, `figure_context`) when available

### Serialization Format
JSONL row includes:
1. legacy fields (`doc_id`, `text`, `metadata`)
2. `elements`
3. `parent_nodes`
4. `child_nodes`

Manifest includes:
1. document-level summary stats,
2. semantic and hierarchy counts,
3. element type distribution,
4. preview text.

### Idempotent State Tracking
With state enabled:
1. fingerprint each source file,
2. skip unchanged files,
3. reprocess changed files,
4. remove missing files on full runs.

State entries store:
- fingerprint
- doc_id
- char_count
- last ingestion timestamp

### Logging And Parse Failures
Failure markers:
- `UNPARSED_FILE` for per-file parse failures,
- `UNPARSED_FILE_SUMMARY` for end-of-run recap.

Run stats track:
- discovered count
- parsed count
- skipped unchanged count
- removed missing count
- parse error count
- unparsed file details

### Configuration Inputs
Parser runtime depends on:
1. `paths` (source, outputs, state, logs),
2. `parsing` (minimum size, preview, skip policy, logging),
3. `chunking` (child chunk size, overlap).

### Current Heuristic Limits
Known limitations:
1. author extraction can over-capture noisy PDF lines.
2. year extraction is heuristic from early content.
3. section detection may degrade on OCR-heavy documents.
4. table detection can over-classify multi-column plain text.

### Extension Points
Recommended next upgrades:
1. dedicated author/year metadata extraction,
2. stronger PDF layout-aware backend,
3. explicit section graph and citation parsing,
4. learned table/figure detectors,
5. chunk quality evaluator with retrieval benchmark loop.

### Developer Checklist
When changing parsing logic:
1. update model and function docstrings,
2. update this README implementation section,
3. add or adjust tests,
4. validate JSONL and manifest outputs,
5. run parser smoke test on representative files.

## Semantic Schema
Each parsed document now includes:
1. `elements`: ordered semantic units with:
   - `element_type` in `{title, section_heading, paragraph, table, figure_caption, equation, references}`
   - `page`
   - `order`
   - `section_path`
   - `source_doc_id` linkage through document context
2. `parent_nodes`: section/subsection aligned nodes.
3. `child_nodes`: retrieval-granularity nodes linked to parent nodes.

This allows downstream retrieval to preserve structure while still supporting granular search.

## Hierarchy Build
Parent node construction:
1. Section headings define boundaries.
2. Parent nodes are built from section/subsection blocks.
3. Boundaries are aligned with heading transitions, not fixed token length.

Child node construction:
1. Text child chunks are generated from parent node text using overlapping token windows.
2. Chunk size and overlap use `chunking.chunk_size` and `chunking.chunk_overlap`.
3. Each child stores:
   - `parent_id`
   - `child_id`
   - `section_path`
   - `page_start` / `page_end`
   - `chunk_level=child`

## Table And Figure Handling
Table handling:
1. Table-like lines are detected and parsed into row/column arrays.
2. Table chunks are emitted separately with `chunk_type=table`.
3. Table metadata preserves `table_rows`.

Figure handling:
1. Figure captions are detected from `Figure`/`Fig.` patterns.
2. Figure chunks are emitted separately with `chunk_type=figure`.
3. Figure chunk text includes caption + nearby explanatory paragraph context when available.

## Metadata Contract
Document-level metadata includes:
- `doc_id`
- `paper_title`
- `authors` (heuristic extraction when available)
- `year` (heuristic extraction when available)
- `section` context via nodes
- `page_start` / `page_end`
- `chunk_level` at parent and child levels

These fields are designed for:
1. strict metadata filtering,
2. reranking with section/page awareness,
3. citation-ready answer generation.

## Design Patterns
Patterns currently used in ingestion/parsing:

1. Strategy Pattern
- Where: `FileTextExtractor`, `TextFileExtractor`, `PdfFileExtractor` in the extractor module
- Why: each file type has distinct parsing logic; Strategy keeps each parser isolated and replaceable.

2. Factory Pattern
- Where: `ExtractorFactory` in the extractor module
- Why: centralizes extension-to-extractor mapping so new formats can be added without changing `CorpusParser`.

3. Dependency Injection
- Where: `CorpusParser(..., extractor_factory=...)` in the parser module
- Why: allows swapping parser behavior in tests and production (for custom loaders) without editing parser internals.
- Validation: parser DI test in the ingestion test suite

## Hierarchical Chunking Strategy
Recommended for your corpus (papers + books + MScFE notes):
1. Document-level parse (already implemented).
2. Parent chunks: 1200 to 1800 tokens with 10% overlap.
3. Child chunks: 250 to 450 tokens with 10% overlap.
4. Persist parent-child linkage in metadata (`parent_id`, `chunk_level`).
5. Retrieve children first, then include parent context for answer synthesis.

Model suggestions for local-first setup:
- Embeddings: `bge-m3`
- LLMs: `llama`, `gemma`, `phi` (switch by workload/latency)
- Reranker: `llama-reranker`
- Vector DB: local Qdrant
- UI: OpenWebUI

## Configuration
All sensitive values must be stored only in:
- local runtime config file (ignored by Git)

Tracked, non-sensitive template:
- configuration example template

Suggested config sections:
- `paths`
- `parsing`
- `qdrant`
- `llm`
- `embeddings`
- `reranker`
- `ingestion`
- `chunking`
- `retrieval`
- `openwebui`

## Pipeline Flow
1. Load documents from configured sources.
2. Parse and clean text.
3. Split into chunks using configured strategy.
4. Generate embeddings.
5. Upsert vectors and payload metadata to Qdrant.
6. Retrieve top-k relevant chunks for each query.
7. Synthesize final answer with LLM.

## Integration

## OpenWebUI Integration
- Configure OpenWebUI to call your backend endpoint.
- Ensure the backend uses runtime config for model and Qdrant settings.
- Validate with a smoke-test prompt and inspect retrieved sources.

## Qdrant Collection Design
Recommended payload fields:
- `doc_id`
- `source`
- `path`
- `chunk_id`
- `tags`
- `created_at`
- `updated_at`

Vector settings should match your embedding model dimensions and distance metric.

## Operations

## Runbook
Common operations:
- Full ingest
- Incremental ingest
- Reindex one source
- Collection health check
- Query smoke test

## Logging
- Logs are written to the directory configured in `paths.log_dir`.
- Weekly rotation is enabled (new file each week).
- Historical logs are preserved (no deletion policy in app).
- Unparsed files are logged with dedicated markers:
  - `UNPARSED_FILE` for per-file failures during parsing
  - `UNPARSED_FILE_SUMMARY` for end-of-run failed file recap
- CLI options:
  - `--log-dir` to change log directory
  - `--log-level` to set verbosity

## Testing
- Unit tests for parsing/chunking/retrieval logic
- Integration test against a local Qdrant instance
- End-to-end smoke test with OpenWebUI

## Troubleshooting
- Qdrant connection errors: verify URL, API key, and network.
- Empty retrieval results: verify ingestion ran and collection has points.
- Embedding mismatch: verify model dimensions match collection vector size.
- OpenWebUI integration issues: verify endpoint URL and request format.
- Noisy PDF parse messages (for example `Object ... 0 ...`): parser now uses tolerant PDF mode and continues on broken pages/files; check `parse_errors` in run stats.

## Security Notes
- Never place tokens, API keys, or passwords in README, source code, or committed files.
- Keep secrets only in your local runtime config file.
- Rotate credentials if they were ever committed by mistake.

## Project Governance

## Roadmap
- Hybrid retrieval (sparse + dense)
- Reranking stage
- Multi-tenant access control
- Evaluation pipeline for answer quality

## Contributing
1. Create a feature branch.
2. Add/adjust tests.
3. Run checks locally.
4. Open a pull request.

## Author
Sergej Schweizer

## License
Add your chosen license (for example, MIT).
