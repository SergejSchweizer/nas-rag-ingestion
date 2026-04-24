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
  - [Testing](#testing)
  - [Troubleshooting](#troubleshooting)
  - [Security Notes](#security-notes)
- [Project Governance](#project-governance)
  - [Roadmap](#roadmap)
  - [Contributing](#contributing)
  - [License](#license)

## Overview

## Architecture
- Data ingestion: local/NAS documents and other configured sources
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
.github/workflows/      CI workflows
config/                 Local and example configuration
data/                   Optional local data mounts
docs/                   Extra design and operational docs
requirements/           Dependency definitions (base/dev)
scripts/                Helper scripts for ingestion/index ops
src/                    Pipeline source code
tests/                  Test suite
README.md               Project documentation
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
   - `cp config/config.example.yaml config/config.yaml`
2. Fill secrets and endpoints in `config/config.yaml`.
3. Create and activate virtual environment:
   - `python3 -m venv .venv && source .venv/bin/activate`
4. Install dependencies:
   - Runtime: `pip install -r requirements.txt`
   - Dev/test: `pip install -r requirements/dev.txt`
5. Run parsing step for your NAS corpus:
   - `python3 scripts/parse_corpus.py --source-dir /volume1/RAG/crypto`
6. Continue with indexing/retrieval services (next implementation steps).

## Dependency Management
- `requirements/base.txt`: runtime dependencies
- `requirements/dev.txt`: runtime + test/lint tooling
- `requirements.txt`: convenience entrypoint to runtime dependencies
- Dependencies are pinned with exact versions (`==`) for reproducibility.

Rule for this repository:
- Target is GPU-free hardware only; keep dependencies and defaults CPU-compatible.
- Every new/changed functionality must update dependency files if package needs changed.
- Every new/changed functionality must also update tests.

## Ingestion Design

## Step 1: Parsing
Current parser implementation:
- Module: `src/ingestion/parsing.py`
- CLI: `scripts/parse_corpus.py`
- Default source: `/volume1/RAG/crypto`
- Supported file types: `.pdf`, `.md`, `.txt`

Output:
- JSONL file at `data/parsed/parsed_documents.jsonl` (one parsed document per line)
- Metadata suitable for hierarchical chunking, including:
  - `doc_id`
  - `source_path`
  - `relative_path`
  - `topic`
  - `title`
  - `char_count`

## Design Patterns
Patterns currently used in ingestion/parsing:

1. Strategy Pattern
- Where: `FileTextExtractor`, `TextFileExtractor`, `PdfFileExtractor` in `src/ingestion/parsing.py`
- Why: each file type has distinct parsing logic; Strategy keeps each parser isolated and replaceable.

2. Factory Pattern
- Where: `ExtractorFactory` in `src/ingestion/parsing.py`
- Why: centralizes extension-to-extractor mapping so new formats can be added without changing `CorpusParser`.

3. Dependency Injection
- Where: `CorpusParser(..., extractor_factory=...)` in `src/ingestion/parsing.py`
- Why: allows swapping parser behavior in tests and production (for custom loaders) without editing parser internals.
- Validation: `test_parser_supports_custom_extractor_via_dependency_injection` in `tests/test_parsing.py`

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
- `config/config.yaml` (local, ignored by Git)

Tracked, non-sensitive template:
- `config/config.example.yaml`

Suggested config sections:
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
- Ensure the backend uses `config/config.yaml` for model and Qdrant settings.
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

## Testing
- Unit tests for parsing/chunking/retrieval logic
- Integration test against a local Qdrant instance
- End-to-end smoke test with OpenWebUI

## Troubleshooting
- Qdrant connection errors: verify URL, API key, and network.
- Empty retrieval results: verify ingestion ran and collection has points.
- Embedding mismatch: verify model dimensions match collection vector size.
- OpenWebUI integration issues: verify endpoint URL and request format.

## Security Notes
- Never place tokens, API keys, or passwords in README, source code, or committed files.
- Keep secrets only in `config/config.yaml`.
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

## License
Add your chosen license (for example, MIT).
