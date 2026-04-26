# NAS RAG Ingestion

NAS RAG Ingestion is a CPU-first document ingestion pipeline for local RAG workloads.

The implemented scope today is parsing, semantic structuring, stateful incremental ingestion, and stateful incremental indexing into Qdrant. Retrieval and API-serving layers are tracked as planned work.

## Table of Contents
- [Project Status](#project-status)
  - [Implemented](#implemented)
  - [In Progress / Planned](#in-progress--planned)
- [System Architecture](#system-architecture)
  - [Current Flow (Implemented)](#current-flow-implemented)
  - [Target Flow (Planned)](#target-flow-planned)
  - [End-to-End Relationship Map](#end-to-end-relationship-map)
  - [Ingestion and Indexing Lifecycle](#ingestion-and-indexing-lifecycle)
- [Repository Layout](#repository-layout)
- [Runtime and Dependency Model](#runtime-and-dependency-model)
  - [Python Version](#python-version)
  - [Requirements Structure](#requirements-structure)
- [Quick Start](#quick-start)
  - [1. Create Environment](#1-create-environment)
  - [2. Create Local Runtime Config](#2-create-local-runtime-config)
  - [3. Run Parser](#3-run-parser)
  - [4. Run Sample-Limited Parse](#4-run-sample-limited-parse)
  - [5. Index Parsed Chunks into Qdrant](#5-index-parsed-chunks-into-qdrant)
- [Configuration Reference](#configuration-reference)
  - [`paths`](#paths)
  - [`parsing`](#parsing)
  - [`chunking`](#chunking)
  - [`qdrant`](#qdrant)
  - [`embeddings`](#embeddings)
  - [Model Endpoint Variables](#model-endpoint-variables)
- [Parsing and Indexing Pipeline](#parsing-and-indexing-pipeline)
  - [Module Relationship Graph](#module-relationship-graph)
  - [Semantic Schema](#semantic-schema)
  - [Child Chunk Types](#child-chunk-types)
  - [Table and Image Handling](#table-and-image-handling)
  - [Extension Points for Future Providers](#extension-points-for-future-providers)
- [Data Contract and Output Artifacts](#data-contract-and-output-artifacts)
  - [Output Contract Relationship (High Level)](#output-contract-relationship-high-level)
  - [Metadata Shape](#metadata-shape)
  - [Parsed JSONL](#parsed-jsonl)
  - [Tracking Manifest](#tracking-manifest)
  - [Ingestion State](#ingestion-state)
  - [Indexing State](#indexing-state)
- [CLI Reference](#cli-reference)
  - [`parse_corpus.py`](#parse_corpuspy)
  - [`index_corpus.py`](#index_corpuspy)
  - [`annotate_random_parsed_pdfs.py`](#annotate_random_parsed_pdfspy)
- [Development Workflow](#development-workflow)
  - [Quality Gates](#quality-gates)
  - [Git Pre-Commit Hook](#git-pre-commit-hook)
  - [Wiki Reading Order](#wiki-reading-order)
- [Testing Strategy](#testing-strategy)
  - [Tested Hierarchy](#tested-hierarchy)
  - [Coverage Areas](#coverage-areas)
- [Operations Runbook](#operations-runbook)
  - [Standard Parse Run](#standard-parse-run)
  - [Reprocess All Files](#reprocess-all-files)
  - [Validate Incremental Parse Behavior](#validate-incremental-parse-behavior)
  - [Validate Incremental Indexing Behavior](#validate-incremental-indexing-behavior)
- [Troubleshooting](#troubleshooting)
  - [`ModuleNotFoundError: No module named 'src'`](#modulenotfounderror-no-module-named-src)
  - [Missing Parser Dependencies](#missing-parser-dependencies)
  - [No Output Generated](#no-output-generated)
  - [Many Parse Failures](#many-parse-failures)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Project Status
This section documents what is in production use versus what is intentionally left for future phases.

### Implemented
- Config-driven parsing workflow.
- Docling-backed parsing for `.pdf`, `.md`, `.txt`.
- Semantic element extraction (`title`, `section_heading`, `paragraph`, `table`, `figure_caption`, `equation`, `references`).
- Parent/child retrieval node generation.
- JSONL export and manifest export.
- Idempotent state tracking to skip unchanged files.
- LlamaIndex indexing stage for child chunks to embeddings to Qdrant.
- Incremental indexing state (`index_state_file`) with skip-unchanged behavior.
- Stale-vector deletion for removed or changed chunks.
- Live endpoint availability tests for embeddings, LLM endpoint, and Qdrant health.

### In Progress / Planned
- Retrieval and query service integration.
- OpenWebUI query endpoint wiring.
- Retrieval quality and reranking validation workflows.

## System Architecture
The architecture is split into an implemented ingestion/indexing path and a planned retrieval/query path.

### Current Flow (Implemented)
1. Discover files from configured source directory.
2. Parse with Docling and map content to semantic schema.
3. Build parent nodes from section boundaries.
4. Build child nodes for retrieval granularity.
5. Export JSONL and tracking manifest.
6. Index child chunks with LlamaIndex into Qdrant.
7. Persist ingestion and indexing state.

### Target Flow (Planned)
1. Serve a retrieval/query endpoint for OpenWebUI.
2. Add retrieval-quality evaluation and reranking validation.
3. Add end-to-end ingest-to-retrieval integration tests.

### End-to-End Relationship Map
```text
                                  (Planned Query Path)
                               +--------------------------+
                               |        OpenWebUI         |
                               +------------+-------------+
                                            |
                                            v
                               +--------------------------+
                               |   Retrieval API Service  |
                               +------------+-------------+
                                            |
                                            v
                               +--------------------------+
                               |          Qdrant          |
                               +------------+-------------+
                                            ^
                                            |
                        (Implemented Indexing)
                                            |
+-------------------+      +----------------+----------------+
| Source Documents  |----->|  NAS RAG Ingestion (Current)   |
| .pdf .md .txt     |      |  - discover/parse/chunk/export |
+-------------------+      |  - stateful skip-unchanged     |
                           +----------------+----------------+
                                            |
                                            v
                           +----------------+----------------+
                           | Artifacts                        |
                           | - parsed_documents.jsonl         |
                           | - parsed_documents_manifest.json |
                           | - ingestion_state.json           |
                           | - indexing_state.json            |
                           +----------------------------------+
```

### Ingestion and Indexing Lifecycle
```text
discover_files()
    |
    v
for each file ----------------------------------------------+
    |                                                       |
    v                                                       |
fingerprint(file)                                           |
    |                                                       |
    v                                                       |
should_ingest(relative_path, fingerprint)?                  |
    | yes                                                   | no
    v                                                       v
parse + build nodes + metadata                        skipped_unchanged++
    |
    v
record_ingested(relative_path, fingerprint, doc_id, char_count)
    |
    v
build index points (deterministic point_id + content_hash)
    |
    v
upsert changed points + delete stale points
    |
    v
save ingestion_state + indexing_state
```

## Repository Layout
The codebase is organized around ingestion-first concerns, with tests separated by behavior.

```text
config/                      Runtime templates and local config
scripts/                     CLI scripts
  parse_corpus.py            Parse source documents into hierarchical chunks
  index_corpus.py            Index child chunks into Qdrant via LlamaIndex
src/ingestion/parsing/       Parsing pipeline and schema
  parser.py                  Parse orchestration + semantic/chunk/metadata assembly
  docling_adapter.py         Docling conversion + low-level Docling item extraction
  semantic_extractor.py      Semantic extraction + section-aware classification
src/ingestion/indexing/
  indexer.py                 LlamaIndex node build + Qdrant upsert flow
src/ingestion/runtime_config.py
src/logging_utils.py         Shared logging setup
data/                        Local artifacts (ignored by default)
tests/                       Unit and integration tests
requirements/                Base and dev dependency sets
```

## Runtime and Dependency Model
This project is intentionally Python 3.11-based and dependency-driven through `requirements/` files.

### Python Version
- Required: Python `3.11`.
- Declared in `pyproject.toml` (`requires-python = ">=3.11"`).

### Requirements Structure
- `requirements/base.txt`: runtime + core quality dependencies used in this repository.
- `requirements/dev.txt`: extends base for additional development helpers.
- `requirements.txt`: convenience entrypoint forwarding to `requirements/base.txt`.

## Quick Start
Quick start covers local setup, parse execution, and indexing execution.

### 1. Create Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements/dev.txt
pip install -e .
```

### 2. Create Local Runtime Config
```bash
cp config/config.example.yaml config/config.yaml
```

Update `config/config.yaml` paths and endpoint/secrets for your environment.

### 3. Run Parser
```bash
python3 scripts/parse_corpus.py --config config/config.yaml
```

### 4. Run Sample-Limited Parse
```bash
python3 scripts/parse_corpus.py --config config/config.yaml --max-files 50
```

### 5. Index Parsed Chunks into Qdrant
```bash
python3 scripts/index_corpus.py --config config/config.yaml
```

Docling model cache behavior:
- Models can download on first use and are cached under `DOCLING_ARTIFACTS_PATH`.
- This repository defaults `DOCLING_ARTIFACTS_PATH` to `./docling` when not already set.

## Configuration Reference
Main keys in `config/config.yaml` are listed below.

### `paths`
- `source_dir`: root directory to scan.
- `output_jsonl`: parsed records output.
- `output_manifest`: human-readable run summary output.
- `state_file`: idempotency state store.
- `index_state_file`: incremental indexing state store.
- `log_dir`: weekly rotating log directory.

### `parsing`
- `min_characters`: minimum content length to keep a document.
- `preview_characters`: manifest preview length.
- `max_files`: optional global parse limit.
- `skip_unchanged`: skip files whose fingerprint has not changed.
- `log_level`: parser log level.

### `chunking`
- `chunk_size`: child node token-window size.
- `chunk_overlap`: child node overlap.

### `qdrant`
- `url`: Qdrant endpoint URL.
- `api_key`: optional API key.
- `collection`: target collection for vector upserts.
- `vector_size`: vector dimension used for collection creation.
- `distance`: vector metric (`Cosine`, `Dot`, `Euclid`, `Manhattan`).

### `embeddings`
- `provider`: embedding backend (`ollama` or `tei`).
- `model`: embedding model identifier.
- `endpoint`: provider endpoint URL built from `ip` and `port`.

### Model Endpoint Variables
Use configuration values for model names and addresses.

```yaml
llm:
  model: "<LLM_MODEL>"
  endpoint: "http://<LLM_IP>:<LLM_PORT>"
embeddings:
  model: "<EMBEDDING_MODEL>"
  endpoint: "http://<EMBEDDING_IP>:<EMBEDDING_PORT>"
```

Sections such as `llm`, `reranker`, `retrieval`, and `openwebui` currently act as placeholders for upcoming retrieval/query stages.

## Parsing and Indexing Pipeline
This section documents how scripts, adapters, parsers, and state stores interact.

### Module Relationship Graph
```text
scripts/parse_corpus.py
        |
        v
runtime_config.resolve_parse_runtime_config(...)
        |
        v
CorpusParser ---------------------------------------------------+
  |                                                             |
  | uses                                                        | uses
  v                                                             v
DoclingAdapter                                           IngestionStateStore
  |                                                             |
  | converts files                                              | fingerprints + save/load/remove-missing
  v                                                             v
Docling Document ---------------------------------------> state_file.json
        |
        v
SemanticExtractor (section path + type + merge)
        |
        v
Semantic Elements -> Parent Nodes -> Child Nodes -> JSONL + Manifest
```

### Semantic Schema
Each parsed document includes:
- `elements`: ordered semantic units.
- `parent_nodes`: section-aligned blocks.
- `child_nodes`: retrieval-level chunks.

### Child Chunk Types
- `text`: overlapping windows from parent text.
- `table`: table-focused chunks with row metadata.
- `figure`: caption plus nearby context.

### Table and Image Handling
- Tables are mapped to semantic elements of type `table`.
- Table rows are extracted into element metadata (`rows`) and propagated into table child chunks (`table_rows`).
- Images are handled as figure-caption content (`figure_caption`), not raw pixel embeddings.
- Figure child chunks include caption text plus nearby paragraph context (`figure_context`) when available.

### Extension Points for Future Providers
These extension points allow provider growth without changing current business behavior.

- Semantic extraction rules live in `src/ingestion/parsing/semantic_extractor.py`.
- Docling conversion and item mapping live in `src/ingestion/parsing/docling_adapter.py`.
- Document-level metadata assembly lives in parser metadata builders.
- Parent/child chunk field composition lives in parser node builders.
- Manifest export can be extended when new fields must be visible outside JSONL.

## Data Contract and Output Artifacts
The ingestion contract and artifact outputs are stable references for downstream systems.

### Output Contract Relationship (High Level)
```text
ParsedDocument
  |
  +-- doc_id
  +-- text
  +-- metadata
  |     +-- source_path / relative_path / file_ext
  |     +-- paper_title / authors / year / topic
  |     +-- elements_count / parent_nodes_count / child_nodes_count
  |
  +-- elements[*] (semantic sequence)
  |     +-- element_type: title | section_heading | paragraph | table | figure_caption | equation | references
  |
  +-- parent_nodes[*] (section-aligned)
  |
  +-- child_nodes[*] (retrieval chunks)
        +-- chunk_type: text | table | figure
```

### Metadata Shape
Document metadata includes:
- source and relative paths.
- topic, title, inferred paper metadata.
- page and char-count statistics.
- element, parent, and child counts.

### Parsed JSONL
- Path: `paths.output_jsonl`.
- One parsed document per line.
- Contains full text, semantic elements, parent nodes, and child nodes.

### Tracking Manifest
- Path: `paths.output_manifest`.
- Aggregated run metadata and per-document summaries.
- Useful for manual QA and pipeline observability.

### Ingestion State
- Path: `paths.state_file`.
- Stores per-file fingerprints and last ingestion metadata.
- Enables deterministic skip-unchanged behavior.

### Indexing State
- Path: `paths.index_state_file`.
- Stores per-document `point_id -> content_hash` snapshots.
- Enables incremental indexing skip and stale-point deletion.

## CLI Reference
All scripts are intended to run from repository root.

### `parse_corpus.py`
`python3 scripts/parse_corpus.py [options]`

Options:
- `--config`
- `--source-dir`
- `--output-jsonl`
- `--output-manifest`
- `--preview-characters`
- `--min-characters`
- `--max-files`
- `--state-file`
- `--no-skip-unchanged`
- `--log-dir`
- `--log-level`

### `index_corpus.py`
`python3 scripts/index_corpus.py [options]`

Options:
- `--config`
- `--input-jsonl`
- `--index-state-file`
- `--qdrant-url`
- `--qdrant-api-key`
- `--qdrant-collection`
- `--embedding-model`
- `--embedding-provider`
- `--embedding-endpoint`
- `--recreate-collection`
- `--batch-size`
- `--log-dir`
- `--log-level`

### `annotate_random_parsed_pdfs.py`
Use this script to recreate `N` random original PDFs with parser labels.

Generated files use sequential numeric names in selection order (`1.pdf`, `2.pdf`, ..., `N.pdf`).

`python3 scripts/annotate_random_parsed_pdfs.py [options]`

Options:
- `--parsed-jsonl`
- `--count`
- `--output-dir`
- `--seed`
- `--overwrite`

Example:
```bash
python3 scripts/annotate_random_parsed_pdfs.py \
  --parsed-jsonl data/parsed/parsed_documents.jsonl \
  --count 10 \
  --output-dir /volume1/Temp \
  --seed 42 \
  --overwrite
```

## Development Workflow
Development quality gates and local hooks are part of normal repository use.

### Quality Gates
```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src scripts tests
.venv/bin/pytest -q
```

Run live endpoint integration checks explicitly:
```bash
.venv/bin/pytest -q -m integration
```

### Git Pre-Commit Hook
Repository hook (`.git/hooks/pre-commit`) runs Ruff, MyPy, and tests before commit:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Running ruff before commit..."
.venv/bin/python -m ruff check .

echo "Running mypy before commit..."
.venv/bin/python -m mypy src scripts tests

echo "Running tests before commit..."
.venv/bin/pytest -q
```

### Wiki Reading Order
1. Read `System Architecture` to understand implemented and planned scope.
2. Read `Parsing and Indexing Pipeline` for data-flow details.
3. Read `Configuration Reference` for runtime controls.
4. Read `Data Contract and Output Artifacts` before downstream integration.
5. Use `Operations Runbook` and `Troubleshooting` for day-2 operations.

## Testing Strategy
Testing focuses on contract stability, incremental behavior, and operational safety.

### Tested Hierarchy
Ingestion hierarchy validated by tests:
1. `ParsedDocument` (document root).
2. `elements` (ordered semantic sequence).
3. `parent_nodes` (section-aligned hierarchy level).
4. `child_nodes` (retrieval chunks linked to parent nodes).

Incremental indexing hierarchy validated by tests:
1. `doc_id`.
2. Deterministic `point_id` (UUID).
3. `content_hash` snapshot in `index_state_file`.
4. Stale-point deletion when previously indexed points no longer exist.

### Coverage Areas
- Parsing behavior and semantic extraction.
- Skip-unchanged ingestion state flow.
- Incremental indexing state behavior.
- Runtime config resolution and override precedence.
- Logging configuration.
- Live endpoint availability checks for embeddings, LLM, and Qdrant (`integration` marker).

## Operations Runbook
Operational runbooks help validate deterministic behavior in local or CI-like runs.

### Standard Parse Run
1. Validate config paths exist and are writable.
2. Run parser.
3. Check summary line in console output.
4. Inspect manifest for document counts and previews.

### Reprocess All Files
Run parser with `--no-skip-unchanged`.

### Validate Incremental Parse Behavior
1. Run parser once.
2. Run parser again with unchanged corpus.
3. Confirm `skipped_unchanged` increases.

### Validate Incremental Indexing Behavior
1. Run `scripts/index_corpus.py` once.
2. Run it again against unchanged JSONL.
3. Confirm `Skipped nodes` increases and `Indexed` remains low or zero.

## Troubleshooting
This section covers common setup and runtime failure modes.

### `ModuleNotFoundError: No module named 'src'`
Use repository root as working directory and run:

```bash
python3 scripts/parse_corpus.py --config config/config.yaml
```

Optionally install editable package with `pip install -e .`.

### Missing Parser Dependencies
Install requirements:

```bash
pip install -r requirements.txt
```

### No Output Generated
Check:
- `paths.source_dir` points to real files.
- File extensions are supported (`.pdf`, `.md`, `.txt`).
- `min_characters` is not set too high.

### Many Parse Failures
Review logs in `paths.log_dir` and inspect `UNPARSED_FILE` lines.

## Roadmap
- Add retrieval/query service for OpenWebUI.
- Add end-to-end ingest-to-retrieval integration tests.
- Add retrieval-quality and reranking evaluation benchmarks.

## Contributing
- Keep changes CPU-compatible.
- Add or update tests with behavior changes.
- Keep Ruff and MyPy checks green.
- Update this README when functionality changes.

## License
MIT
