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
- Every new/changed functionality must update code docstrings and README sections impacted by the change.
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
- Metadata suitable for hierarchical chunking, including:
  - `doc_id`
  - `source_path`
  - `relative_path`
  - `topic`
  - `title`
  - `char_count`
  - `text_preview` (manifest only, for easy inspection)

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
