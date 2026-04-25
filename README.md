# NAS RAG Ingestion

CPU-first ingestion pipeline for local RAG workloads.  
Current implementation focus: **document parsing, semantic structuring, incremental indexing, and export artifacts** for downstream retrieval.

## Contents
- [Project Status](#project-status)
  - [Implemented](#implemented)
  - [In Progress / Planned](#in-progress--planned)
- [Architecture](#architecture)
  - [Current (implemented)](#current-implemented)
  - [Target (planned)](#target-planned)
  - [System Relationship Map](#system-relationship-map)
- [Repository Layout](#repository-layout)
- [Quick Start](#quick-start)
  - [1. Create environment](#1-create-environment)
  - [2. Create local runtime config](#2-create-local-runtime-config)
  - [3. Run parser](#3-run-parser)
  - [4. Run sample-limited parse](#4-run-sample-limited-parse)
  - [5. Index parsed chunks into Qdrant with LlamaIndex](#5-index-parsed-chunks-into-qdrant-with-llamaindex)
- [Configuration Reference](#configuration-reference)
  - [`paths`](#paths)
  - [`parsing`](#parsing)
  - [`chunking`](#chunking)
  - [`qdrant`](#qdrant)
  - [`embeddings`](#embeddings)
  - [Model Endpoint Variables](#model-endpoint-variables)
- [Parsing Pipeline](#parsing-pipeline)
  - [Parsing Module Relationship Graph](#parsing-module-relationship-graph)
  - [Semantic schema](#semantic-schema)
  - [Child chunk types](#child-chunk-types)
  - [Table and image handling](#table-and-image-handling)
  - [Extending extracted fields](#extending-extracted-fields)
  - [Idempotency and Incremental Ingestion Flow](#idempotency-and-incremental-ingestion-flow)
  - [Output Contract Relationship (High Level)](#output-contract-relationship-high-level)
  - [Metadata shape](#metadata-shape)
- [Tested Hierarchy](#tested-hierarchy)
- [Output Artifacts](#output-artifacts)
  - [Parsed JSONL](#parsed-jsonl)
  - [Tracking manifest](#tracking-manifest)
  - [Ingestion state](#ingestion-state)
  - [Indexing state](#indexing-state)
- [CLI Reference](#cli-reference)
  - [Random Parser PDF Audit Batch](#random-parser-pdf-audit-batch)
- [Development](#development)
  - [Quality gates](#quality-gates)
  - [Recommended Wiki-Style Reading Order](#recommended-wiki-style-reading-order)
  - [Current test coverage areas](#current-test-coverage-areas)
- [Operations Runbook](#operations-runbook)
  - [Standard parse run](#standard-parse-run)
  - [Reprocess all files](#reprocess-all-files)
  - [Validate incremental behavior](#validate-incremental-behavior)
  - [Validate incremental indexing behavior](#validate-incremental-indexing-behavior)
- [Troubleshooting](#troubleshooting)
  - [`ModuleNotFoundError: No module named 'src'`](#modulenotfounderror-no-module-named-src)
  - [Missing parser dependencies](#missing-parser-dependencies)
  - [No output generated](#no-output-generated)
  - [Many parse failures](#many-parse-failures)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Project Status
### Implemented
- Config-driven parsing workflow.
- Docling-backed parsing for `.pdf`, `.md`, `.txt`.
- Semantic element extraction (`title`, `section_heading`, `paragraph`, `table`, `figure_caption`, `equation`, `references`).
- Parent/child retrieval node generation.
- JSONL export and readable tracking manifest export.
- Idempotent state tracking to skip unchanged files.
- LlamaIndex indexing stage for child chunks -> embeddings -> Qdrant.
- Incremental indexing state (`index_state_file`) for skip-unchanged upserts.
- Stale vector deletion for removed/changed chunks.
- Live availability tests for embeddings, LLM endpoint, and Qdrant health.

### In Progress / Planned
- Retrieval/query service integration.
- OpenWebUI query endpoint wiring.

## Architecture
### Current (implemented)
1. Discover files from configured source directory.
2. Parse with Docling and map to semantic schema.
3. Build parent nodes from section boundaries.
4. Build child nodes for retrieval granularity.
5. Export JSONL + manifest.
6. Index child chunks with LlamaIndex into Qdrant.
7. Update ingestion + indexing state.

### Target (planned)
1. Serve retrieval/query endpoint for OpenWebUI.
2. Add retrieval quality evaluation and reranking validation.
3. Add end-to-end ingest-to-retrieval integration tests.

### System Relationship Map
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

## Repository Layout
```text
config/                      Runtime templates and local config
scripts/                     CLI scripts
  parse_corpus.py            Parse source documents into hierarchical chunks
  index_corpus.py            Index child chunks into Qdrant via LlamaIndex
src/ingestion/parsing/       Parsing pipeline and schema
  parser.py                  Parse orchestration + semantic/chunk/metadata assembly
  docling_adapter.py         Docling conversion + low-level Docling item extraction
  semantic_extractor.py      Semantic element extraction + section-aware classification
src/ingestion/indexing/
  indexer.py                 LlamaIndex node build + Qdrant upsert flow
src/ingestion/runtime_config.py
src/logging_utils.py         Shared logging setup
data/                        Local artifacts (ignored by default)
tests/                       Unit tests
requirements/                Base and dev dependency sets
```

## Quick Start
### 1. Create environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements/dev.txt
pip install -e .
```

### 2. Create local runtime config
```bash
cp config/config.example.yaml config/config.yaml
```

Update `config/config.yaml` paths and secrets for your environment.

### 3. Run parser
```bash
python3 scripts/parse_corpus.py --config config/config.yaml
```

### 4. Run sample-limited parse
```bash
python3 scripts/parse_corpus.py --config config/config.yaml --max-files 50
```

### 5. Index parsed chunks into Qdrant with LlamaIndex
```bash
python3 scripts/index_corpus.py --config config/config.yaml
```

Docling model cache behavior:
- Models can download on first use (on-the-fly) and are cached under `DOCLING_ARTIFACTS_PATH`.
- In this repo, the parser defaults `DOCLING_ARTIFACTS_PATH` to `./docling` when not already set.

## Configuration Reference
Main keys in `config/config.yaml`:

### `paths`
- `source_dir`: root directory to scan.
- `output_jsonl`: parsed records output.
- `output_manifest`: human-readable summary output.
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
- `distance`: vector distance metric (`Cosine`, `Dot`, `Euclid`, `Manhattan`).

### `embeddings`
- `provider`: embedding backend (`ollama` or `tei`).
- `model`: embedding model identifier.
- `endpoint`: provider endpoint URL built from `ip` + `port`.

### Model Endpoint Variables
Use only config values for model names and addresses:

```yaml
llm:
  model: "<LLM_MODEL>"
  endpoint: "http://<LLM_IP>:<LLM_PORT>"
embeddings:
  model: "<EMBEDDING_MODEL>"
  endpoint: "http://<EMBEDDING_IP>:<EMBEDDING_PORT>"
```

Other sections (`llm`, `reranker`, `retrieval`, `openwebui`) are configuration placeholders for retrieval/query stages.

## Parsing Pipeline
### Parsing Module Relationship Graph
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

### Semantic schema
Each parsed document includes:
- `elements`: ordered semantic units.
- `parent_nodes`: section-aligned blocks.
- `child_nodes`: retrieval-level chunks.

### Child chunk types
- `text`: overlapping windows from parent text.
- `table`: table-focused chunks with row metadata.
- `figure`: caption + nearby context.

### Table and image handling
- Tables are mapped to semantic elements of type `table`.
- Table rows are extracted into element metadata (`rows`) and propagated into table child chunks (`table_rows`).
- Images are treated as figure-caption content (semantic type `figure_caption`), not as raw pixel embeddings.
- Figure child chunks include caption text plus nearby paragraph context (`figure_context`) when available.

### Extending extracted fields
- Update semantic extraction rules in `src/ingestion/parsing/semantic_extractor.py`:
  - `extract(...)` to add new element types/metadata.
  - `_classify_text_block(...)` and `_looks_like_*` helpers for heuristic routing.
- Update Docling-specific conversion/item handling in `src/ingestion/parsing/docling_adapter.py`:
  - `convert(...)` for source-format conversion behavior.
  - `extract_item_text(...)`, `item_page(...)`, and `table_rows(...)` for low-level Docling mapping.
- Add document-level fields in `_build_metadata(...)`.
- Add chunk-level fields in `_build_parent_nodes(...)` and `_build_child_nodes(...)`.
- JSONL export already serializes full document/element/parent/child payloads; update `export_tracking_manifest(...)` if you also want new fields in the manifest.

### Idempotency and Incremental Ingestion Flow
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
end loop
    |
    v
remove_missing(seen_relative_paths) [only when max_files is not set]
    |
    v
save state
```

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

### Metadata shape
Document metadata includes:
- source and relative paths.
- topic, title, inferred paper metadata.
- page and char-count stats.
- element/parent/child counts.

## Tested Hierarchy
The ingestion hierarchy validated by tests is:

1. `ParsedDocument` (document root)
2. `elements` (ordered semantic sequence)
3. `parent_nodes` (section-aligned hierarchy level)
4. `child_nodes` (retrieval chunks linked to parent nodes)

Incremental indexing hierarchy validated by tests is:

1. `doc_id`
2. deterministic `point_id` (UUID)
3. `content_hash` snapshot in `index_state_file`
4. stale-point deletion when a previously indexed point no longer exists in current doc snapshot

Related tests:
- `tests/test_parsing.py`
- `tests/test_indexing_state.py`
- `tests/test_model_availability.py`

## Output Artifacts
### Parsed JSONL
- Path: `paths.output_jsonl`
- One parsed document per line.
- Contains full text, semantic elements, parent nodes, and child nodes.

### Tracking manifest
- Path: `paths.output_manifest`
- Aggregated run metadata and per-document summaries.
- Useful for manual QA and pipeline observability.

### Ingestion state
- Path: `paths.state_file`
- Stores per-file fingerprints and last ingestion metadata.
- Enables deterministic skip-unchanged behavior.

### Indexing state
- Path: `paths.index_state_file`
- Stores per-doc point_id -> content_hash snapshots.
- Enables incremental indexing skip and stale-point deletion.

## CLI Reference
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

### Random Parser PDF Audit Batch
Use this to recreate `N` random original PDFs with parser labels.
Generated files use sequential numeric names in selection order: `1.pdf`, `2.pdf`, ..., `N.pdf`.

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

## Development
### Quality gates
```bash
.venv/bin/pytest -q
```

### Recommended Wiki-Style Reading Order
1. Read `Architecture` to understand current vs target scope.
2. Read `Parsing Pipeline` and its relationship graphs.
3. Read `Configuration Reference` to understand runtime controls.
4. Read `Output Artifacts` before integrating downstream systems.
5. Use `Operations Runbook` + `Troubleshooting` for day-2 operations.

### Current test coverage areas
- parsing behavior and semantic extraction.
- skip-unchanged state flow.
- incremental indexing state behavior.
- config resolution and override precedence.
- logging configuration.
- live endpoint availability checks for embeddings, llm, and qdrant.

## Operations Runbook
### Standard parse run
1. Validate config paths exist and are writable.
2. Run parser.
3. Check summary line in console output.
4. Inspect manifest for document counts and previews.

### Reprocess all files
Run with `--no-skip-unchanged`.

### Validate incremental behavior
1. Run parser once.
2. Run parser again with unchanged corpus.
3. Confirm `skipped_unchanged` increases.

### Validate incremental indexing behavior
1. Run `scripts/index_corpus.py` once.
2. Run it again against unchanged JSONL.
3. Confirm `Skipped nodes` increases and `Indexed` remains low/zero.

## Troubleshooting
### `ModuleNotFoundError: No module named 'src'`
Use repository root as working directory and run via:
```bash
python3 scripts/parse_corpus.py --config config/config.yaml
```
Optionally install editable package with `pip install -e .`.

### Missing parser dependencies
Install requirements:
```bash
pip install -r requirements.txt
```

### No output generated
Check:
- `paths.source_dir` points to real files.
- file extensions are supported (`.pdf`, `.md`, `.txt`).
- `min_characters` is not too high.

### Many parse failures
Review logs in `paths.log_dir` and inspect `UNPARSED_FILE` lines.

## Roadmap
- Add retrieval/query service for OpenWebUI.
- Add end-to-end ingest-to-retrieval integration tests.
- Add retrieval quality and reranking evaluation benchmarks.

## Contributing
- Keep changes CPU-compatible.
- Add or update tests with behavior changes.
- Update this README when functionality changes.

## License
MIT
