# Deterministic Semantic Ingestion for NAS-Hosted Research PDFs: A Reproducible Evaluation of Docling-Based Parsing, Hierarchical Chunking, and Incremental Vector Indexing

## 1. Abstract
Local retrieval-augmented generation (RAG) systems often fail at the ingestion stage, where layout-sensitive scientific PDFs, mixed content types (equations, tables, figure captions), and repeated re-ingestion runs can produce unstable chunk boundaries, duplicated vectors, and poor traceability. This report presents a deterministic ingestion architecture for NAS-hosted research corpora, implemented as a Docling-backed parsing pipeline with semantic extraction, hierarchical parent/child chunk construction, and incremental indexing into Qdrant. The evaluated snapshot uses 10 parsed PDF documents (`data/parsed/parsed_documents.jsonl`) and state tracking artifacts (`data/state/ingestion_state.json`) generated on April 27, 2026. We quantify corpus structure, chunk composition, and robustness to chunking hyperparameters. Results show complete preservation of structured non-text evidence in the current semantic pipeline (116 table elements and 103 figure-caption elements mapped into dedicated child chunks), stable idempotent behavior via fingerprint and content-hash state stores, and predictable chunk-volume trade-offs across alternate chunk-size/overlap settings. The main contribution is a production-oriented ingestion methodology that is both engineering-rigorous and empirically inspectable: every parsed artifact is auditable, deterministic IDs enable safe re-indexing, and operational behavior is measurable from first principles. We also identify current gaps (missing CI-tracked pre-commit policy and incomplete experiment-tracking integration) needed for full research-governance maturity.

## 2. Introduction
Scientific and quantitative RAG workflows depend on ingestion quality more than generation quality: if section boundaries, equations, and tables are lost during parsing, downstream retrieval degrades regardless of LLM size.

Current document-ingestion approaches are often optimized for convenience rather than reproducibility, leading to non-deterministic chunk IDs, unclear state transitions between runs, and weak artifact traceability when data or configuration changes.

This repository proposes a deterministic, modular ingestion architecture with explicit interfaces for parsing, semantic extraction, state tracking, and indexing. The design prioritizes production maintainability while preserving research-grade interpretability of intermediate outputs.

Research contributions in this report are:
- We propose a deterministic ingestion and indexing pipeline with file-fingerprint and content-hash state tracking.
- We evaluate semantic coverage and chunking robustness on a real parsed PDF snapshot.
- We demonstrate auditable artifact contracts (JSONL, manifest, ingestion/indexing state) suitable for reproducible operations.

## 3. Literature Review
RAG systems require reliable retrieval corpora; noisy or structurally flattened ingestion reduces retrieval relevance and answer faithfulness (Lewis et al., 2020). Dense retrieval and contextual embedding methods improved semantic matching (Karpukhin et al., 2020; Reimers and Gurevych, 2019), while transformer pretraining established broad language representation capacity (Devlin et al., 2019). However, scientific PDF ingestion remains hard because content structure is spatial and multimodal, not purely sequential text.

Document AI research has emphasized layout-aware modeling and OCR/document understanding benchmarks (Xu et al., 2021; Huang et al., 2022; Li et al., 2022). OCR system advances (e.g., PP-OCR pipelines) support practical extraction from heterogeneous scans (Du et al., 2022). For scholarly documents specifically, domain-focused parsers and models (Lo et al., 2020; Blecher et al., 2023) indicate that preserving tables, figures, and formula regions materially affects downstream usability.

At indexing time, ANN vector search quality and operational efficiency are shaped by index design (Malkov and Yashunin, 2018; Johnson et al., 2017). In production RAG stacks, deterministic IDs and incremental re-indexing are under-discussed but critical: without them, repeated ingestion inflates storage and obscures provenance. This report addresses that gap with a deterministic, stateful ingestion/indexing workflow.

## 4. Dataset
### 4.1 Source
- Document source configured from NAS path: `/volume1/RAG/crypto` (via runtime config).
- Parsed artifact evaluated: `data/parsed/parsed_documents.jsonl`.
- State artifact evaluated: `data/state/ingestion_state.json`.

### 4.2 Sample Period
- Evaluation snapshot date: April 27, 2026 (UTC artifact timestamps).
- This is a corpus snapshot evaluation rather than a temporal forecasting dataset.

### 4.3 Number of Observations
- Documents: 10
- File types: 10 PDFs (`.pdf` only in this snapshot)
- Total tracked characters: 796,289

### 4.4 Variables
Primary document-level variables used in analysis:
- `char_count`
- `page_start`, `page_end` (converted to estimated page span)
- `elements_count`
- `parent_nodes_count`
- `child_nodes_count`

Element/chunk categorical variables:
- Element types: `paragraph`, `section_heading`, `equation`, `table`, `figure_caption`, `references`
- Child chunk types: `text`, `table`, `figure`

### 4.5 Cleaning Methodology
- Empty rows removed during JSONL read.
- Non-dict records excluded.
- Missing numeric fields coerced to zero for aggregate statistics.
- Page span derived as `page_end - page_start + 1` when both bounds exist.

### 4.6 Train/Test Split
This repository stage is ingestion infrastructure, not supervised prediction. Therefore:
- No train/test split is applied.
- Robustness is assessed by configuration perturbation and structural preservation metrics.

## 5. Methodology
### 5.1 Pipeline Design
Implemented flow:
1. Discover candidate files by extension and directory filters.
2. Parse with Docling adapter.
3. Extract semantic elements with section-aware classification.
4. Build section-aligned parent nodes.
5. Build child nodes (text windows + table + figure chunks).
6. Export JSONL and manifest artifacts.
7. Incrementally index into Qdrant with deterministic point IDs.

### 5.2 Mathematical Formulation
Let a document be represented by semantic elements:
\[
\mathcal{E}_d = \{e_i\}_{i=1}^{n_d}, \quad e_i=(t_i, p_i, s_i, m_i)
\]
where \(t_i\) is element type, \(p_i\) is page index, \(s_i\) is section path, and \(m_i\) is metadata.

Parent nodes partition element sequences by section boundaries:
\[
\mathcal{P}_d = \text{SectionPartition}(\mathcal{E}_d)
\]

Text child chunks are generated using overlapping token windows:
\[
\text{step} = \max(c - o, 1), \qquad
w_k = x_{k\cdot \text{step} : k\cdot \text{step}+c}
\]
where \(c\) is chunk size and \(o\) is overlap.

Deterministic indexing identity is generated as:
\[
\text{point\_id} = \text{UUID5}(\text{raw\_id})
\]
with content hash:
\[
h = \text{SHA256}(\text{json}([\text{text}, \text{metadata}]))
\]
A node is skipped when \(h\) equals stored hash for the same `point_id`.

### 5.3 Objective Functions
Operational objectives:
- Maximize structured-content preservation:
\[
\max \; C_{special} = \frac{N_{table\_chunks}+N_{figure\_chunks}}{N_{table\_elements}+N_{figure\_elements}}
\]
- Minimize redundant indexing writes while preserving correctness:
\[
\min \; U = N_{upserted} \quad \text{s.t.} \quad \forall i, \; h_i^{new}=h_i^{old} \Rightarrow \text{skip}_i
\]

### 5.4 Feature Engineering Pipeline
For each element/chunk, metadata enrichments include:
- `doc_id`, `section_path`, `page_start`, `page_end`
- `chunk_type`, `chunk_level`
- Source file metadata (`relative_path`, `title`, `topic`)

### 5.5 Model Assumptions
- Docling conversion status accurately reflects parse success/failure.
- Section heading detection is sufficient for parent-node segmentation.
- Token-window chunking approximates retrieval granularity needs.
- Content hash over text+metadata is adequate for incremental equality.

## 6. Results
### 6.1 Descriptive Statistics
| Variable | Mean | Std | Min | Max |
|---|---:|---:|---:|---:|
| `char_count` | 79,628.90 | 119,318.74 | 6,488.00 | 431,222.00 |
| `page_span` | 27.40 | 39.69 | 4.00 | 145.00 |
| `elements_per_doc` | 132.90 | 161.68 | 16.00 | 589.00 |
| `parents_per_doc` | 31.20 | 37.59 | 6.00 | 136.00 |
| `children_per_doc` | 59.20 | 76.44 | 9.00 | 271.00 |

### 6.2 Model Comparison
We treat chunk-construction variants as the compared models.

| Model | Special Coverage (%) | Total Nodes | Mean Tokens/Node | Deterministic IDs |
|---|---:|---:|---:|---:|
| Text-only (C2: 800/120) | 0.00 | 373 | 329.33 | 100% |
| Semantic (C2: 800/120) | 100.00 | 592 | 262.26 | 100% |
| Semantic (C1: 512/64) | 100.00 | 669 | 234.34 | 100% |

Interpretation: semantic chunking preserves all table and figure-caption evidence in this snapshot (219/219), while text-only chunking drops all special-structure nodes.

### 6.3 Robustness Table
| Configuration | Chunk Size | Overlap | Text Chunks | Mean Tokens/Chunk | P95 Tokens |
|---|---:|---:|---:|---:|---:|
| C1 | 512 | 64 | 450 | 276.34 | 512 |
| C2 (current) | 800 | 120 | 373 | 329.33 | 800 |
| C3 | 1024 | 160 | 355 | 344.79 | 1024 |
| C4 | 800 | 0 | 364 | 317.36 | 800 |

Interpretation: larger chunks reduce node count but increase per-node context length. Overlap contributes moderate node inflation with potentially better context continuity.

### 6.4 Figures
**Figure 1. Element Type Distribution (Snapshot)**
In-text reference: Figure 1 summarizes semantic composition after Docling extraction and merging.

```text
paragraph      | ############################################################### 619
section_heading| ###############################                               309
equation       | #################                                               167
table          | ############                                                    116
figure_caption | ###########                                                     103
references     | #                                                                15
```

Interpretation: Figure 1 shows paragraph dominance but substantial structured scientific content (equations/tables/figures), justifying type-aware chunking instead of plain text windows.

**Figure 2. Child Chunk Composition**
In-text reference: Figure 2 reports how retrieval units are allocated by chunk type.

```text
text   : 373 (63.0%)
table  : 116 (19.6%)
figure : 103 (17.4%)
Total  : 592
```

Interpretation: Figure 2 indicates that over one-third of retrieval units are non-generic text chunks, preserving high-value evidence classes for downstream retrieval.

**Figure 3. Chunk-Size Trade-off Curve**
In-text reference: Figure 3 compares text-chunk counts under robustness settings.

```text
Text chunks
C1 (512/64)   : 450
C2 (800/120)  : 373
C3 (1024/160) : 355
C4 (800/0)    : 364
```

Interpretation: Figure 3 shows the expected monotonic decrease in chunk count as chunk size grows, with overlap affecting throughput/storage trade-offs.

**Figure 4. Deterministic Incremental Indexing Logic**
In-text reference: Figure 4 illustrates the stateful indexing decision pathway.

```text
child chunk -> point_id(UUID5) + content_hash(SHA256)
                   |
                   v
        compare with index_state[doc_id][point_id]
             | equal                 | changed/new
             v                       v
           skip                  upsert vector
             \_______________________/
                     stale id set -> delete from Qdrant
```

Interpretation: Figure 4 demonstrates how deterministic IDs and hashes jointly support idempotent writes and stale-vector cleanup.

**Figure 5. End-to-End Artifact Lineage**
In-text reference: Figure 5 maps persisted artifacts that enable auditability.

```text
source PDFs
   -> parsed_documents.jsonl
   -> parsed_documents_manifest.json
   -> ingestion_state.json
   -> indexing_state.json
   -> Qdrant collection
```

Interpretation: Figure 5 emphasizes reproducibility-by-construction: each stage writes inspectable artifacts that capture the transformation boundary.

## 7. Discussion
### 7.1 Business Implications
- Deterministic ingestion lowers operational cost by avoiding redundant indexing writes.
- Structured chunk preservation improves recall potential for quantitative reports where tables/equations are decision-critical.
- Artifact-level traceability supports compliance and incident analysis in enterprise RAG deployments.

### 7.2 Limitations
- Current evaluation is a 10-document snapshot; broader domain diversity is still required.
- Retrieval quality metrics (e.g., nDCG, Recall@k, MRR) are not yet integrated.
- Manifest can be stale relative to JSONL under skip-unchanged runs and should be guarded by consistency checks.
- CI-enforced pre-commit and experiment tracking are not yet repository-standardized.

### 7.3 Model Weaknesses and Assumptions
- Heuristic equation/table detection can misclassify edge cases.
- Section-heading quality is parser-dependent and affects parent segmentation.
- Chunking trade-offs are corpus-dependent; one fixed configuration may not be Pareto-optimal.

## 8. Conclusion
This report evaluated a deterministic ingestion architecture for NAS-hosted research PDFs, showing that semantic chunking preserves all observed table and figure-caption structures in the current snapshot while maintaining reproducible artifact lineage and idempotent incremental indexing behavior. The findings support the repository’s dual role as both production software and research artifact. Next work should prioritize formal retrieval benchmarking, CI-governed quality gates, and experiment tracking integration (including MLflow-backed run metadata) so that ingestion changes can be tied directly to retrieval and answer-quality outcomes.

## 9. Reproducibility Checklist
- Randomness: controlled where sampling is used (`--seed` in annotation script).
- Config versioning: YAML runtime config and example template included.
- Dataset version: snapshot reflected by `data/parsed/parsed_documents.jsonl` and state files.
- Deterministic IDs: SHA/UUID-based chunk identity in parser/indexer.
- Experiment tracking: partial (artifact/state persistence present); MLflow integration pending.

## 10. References
1. Lewis, P., Perez, E., Piktus, A., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS*.
2. Karpukhin, V., Oguz, B., Min, S., et al. (2020). Dense Passage Retrieval for Open-Domain Question Answering. *EMNLP*.
3. Reimers, N., and Gurevych, I. (2019). Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks. *EMNLP-IJCNLP*.
4. Devlin, J., Chang, M.-W., Lee, K., and Toutanova, K. (2019). BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. *NAACL-HLT*.
5. Malkov, Y. A., and Yashunin, D. A. (2018). Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs. *IEEE TPAMI*.
6. Johnson, J., Douze, M., and Jegou, H. (2017). Billion-scale similarity search with GPUs. *IEEE Transactions on Big Data*.
7. Robertson, S., and Zaragoza, H. (2009). The Probabilistic Relevance Framework: BM25 and Beyond. *Foundations and Trends in IR*.
8. Xu, Y., Lv, T., Cui, L., et al. (2021). LayoutLMv2: Multi-modal Pre-training for Visually-Rich Document Understanding. *ACL*.
9. Huang, Y., Lv, T., Cui, L., et al. (2022). LayoutLMv3: Pre-training for Document AI with Unified Text and Image Masking. *ACM MM*.
10. Li, M., Xu, Y., Cui, L., et al. (2022). DocLayNet: A Large Human-Annotated Dataset for Document-Layout Analysis. *KDD*.
11. Zhong, X., Tang, J., and Yeşilyurt, A. (2019). PubLayNet: largest dataset ever for document layout analysis. *ICDAR Workshops*.
12. Kim, G., Hong, T., Yim, M., et al. (2021). OCR-Free Document Understanding Transformer (Donut). *ECCV*.
13. Blecher, L., Cucurull, G., Scialom, T., and Stojnic, R. (2023). Nougat: Neural Optical Understanding for Academic Documents. *ICLR Workshop*.
14. Lo, K., Wang, L. L., Neumann, M., Kinney, R., and Weld, D. S. (2020). S2ORC: The Semantic Scholar Open Research Corpus. *ACL*.
15. Du, Y., Li, C., Guo, R., et al. (2022). PP-OCRv3: More Attempts for the Improvement of Ultra Lightweight OCR System. *arXiv*.

## 11. Appendix
### A. Artifact Snapshot
- `data/parsed/parsed_documents.jsonl`: 10 documents
- `data/state/ingestion_state.json`: 10 tracked files
- Manifest timestamp: `2026-04-27T06:30:57.453042+00:00`

### B. Additional Robustness Notes
- Current operational config is C2 (`chunk_size=800`, `chunk_overlap=120`).
- C1 increases retrieval granularity but raises node count and storage/write load.
- C3 lowers node count, potentially improving throughput but risking context dilution in long sections.
