# NAS RAG Ingestion

CPU-first ingestion pipeline for local RAG workloads.  
Current implementation focus: **document parsing, semantic structuring, and export artifacts** for downstream indexing and retrieval.

## Contents
- [Project Status](#project-status)
- [Architecture](#architecture)
- [Repository Layout](#repository-layout)
- [Quick Start](#quick-start)
- [Configuration Reference](#configuration-reference)
- [Parsing Pipeline](#parsing-pipeline)
- [Output Artifacts](#output-artifacts)
- [CLI Reference](#cli-reference)
- [Development](#development)
- [Operations Runbook](#operations-runbook)
- [Troubleshooting](#troubleshooting)
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

### In Progress / Planned
- Vector indexing (Qdrant write path).
- Retrieval/query service integration.
- OpenWebUI query endpoint wiring.

## Architecture
### Current (implemented)
1. Discover files from configured source directory.
2. Parse with Docling and map to semantic schema.
3. Build parent nodes from section boundaries.
4. Build child nodes for retrieval granularity.
5. Export JSONL + manifest.
6. Update ingestion state.

### Target (planned)
1. Generate embeddings for child nodes.
2. Upsert vectors + metadata to Qdrant.
3. Serve retrieval/query endpoint for OpenWebUI.

## Repository Layout
```text
config/                      Runtime templates and local config
scripts/                     CLI scripts
src/ingestion/parsing/       Parsing pipeline and schema
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

Other sections (`qdrant`, `llm`, `embeddings`, `reranker`, `retrieval`, `openwebui`) are configuration placeholders for upcoming indexing/retrieval stages.

## Parsing Pipeline
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
- Update semantic extraction rules in `src/ingestion/parsing/parser.py`:
  - `_extract_semantic_elements(...)` to add new element types/metadata.
  - `_classify_text_block(...)` and `_looks_like_*` helpers for heuristic routing.
- Add document-level fields in `_build_metadata(...)`.
- Add chunk-level fields in `_build_parent_nodes(...)` and `_build_child_nodes(...)`.
- JSONL export already serializes full document/element/parent/child payloads; update `export_tracking_manifest(...)` if you also want new fields in the manifest.

### Metadata shape
Document metadata includes:
- source and relative paths.
- topic, title, inferred paper metadata.
- page and char-count stats.
- element/parent/child counts.

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

## Development
### Quality gates
```bash
.venv/bin/pytest -q
```

### Current test coverage areas
- parsing behavior and semantic extraction.
- skip-unchanged state flow.
- config resolution and override precedence.
- logging configuration.

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
- Add embedding + Qdrant indexing stage.
- Add retrieval/query service for OpenWebUI.
- Add integration tests for end-to-end ingest-to-retrieval flow.

## Contributing
- Keep changes CPU-compatible.
- Add or update tests with behavior changes.
- Update this README when functionality changes.

## License
MIT
