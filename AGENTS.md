# agent.md

# Engineering Operating Principles for AI Coding Agents

This document defines mandatory engineering standards for all code generation, refactoring, architecture decisions, documentation updates, and testing activities performed by AI coding agents.

The goal is to ensure that generated systems remain:

- scalable
- maintainable
- modular
- testable
- observable
- production-ready
- transferable to future engineers

This applies to:

- RAG systems
- multi-agent systems
- ML pipelines
- document ingestion systems
- APIs
- backend services
- research prototypes transitioning into production systems

---

# 1. Security Rules

## Never expose secrets

Never:

- print secrets
- log secrets
- commit secrets
- hardcode secrets

Secrets include:

- API keys
- database credentials
- JWT secrets
- OAuth credentials
- cloud credentials
- private certificates
- internal infrastructure endpoints
- `.env` values

Use:

- `.env`
- environment variables
- secret managers
- vault systems

---

## Git hygiene

Ensure:

- `.gitignore` exists
- sensitive files are excluded
- temporary artifacts are excluded
- local environment files are excluded

Examples:

```bash
.env
.venv/
__pycache__/
*.pem
*.key
.ipynb_checkpoints/
```

---

## Secret scanning

All repositories must include secret detection:

- detect-secrets
- gitleaks
- equivalent tooling

---

# 2. Project Architecture

All projects must be modular.

Never build monolithic applications.

Required architecture:

```bash
project-root/
│
├── api/                  # API interfaces
├── ingestion/            # parsing, ETL, chunking
├── retrieval/            # search, embeddings, reranking
├── orchestration/        # workflows, agents, graph execution
├── domain/               # business logic
├── infrastructure/       # databases, providers, adapters
├── state/                # workflow state definitions
├── configs/              # configs
├── scripts/              # utility scripts
├── docs/                 # architecture docs
├── tests/                # test suites
├── README.md
└── pyproject.toml
```

---

# 3. Module Design Rules

Every module must have:

- clear responsibility
- explicit ownership
- minimal coupling
- strong cohesion

Example:

```bash
retrieval/
├── interfaces.py
├── services.py
├── providers/
├── models.py
├── exceptions.py
├── config.py
└── tests/
```

---

# 4. Clear Interfaces

Every major component must expose explicit interfaces.

Use:

- abstract base classes
- protocols
- service interfaces
- repositories

Example:

```python
from abc import ABC, abstractmethod

class EmbeddingProvider(ABC):

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        pass
```

This allows swapping:

- OpenAI embeddings
- HuggingFace embeddings
- TEI embeddings
- local models
- future providers

without changing business logic.

---

# 5. Required Python Design Patterns

Use proper design patterns when applicable.

---

## Strategy Pattern

For interchangeable algorithms:

- chunking
- embeddings
- reranking
- retrieval

---

## Factory Pattern

For dynamic object creation:

- model loaders
- parser creation
- provider selection

---

## Adapter Pattern

For external systems:

- OpenAI
- Qdrant
- Elasticsearch
- APIs

---

## Repository Pattern

For storage abstraction:

- documents
- metadata
- vector storage

---

## Builder Pattern

For complex pipelines:

- ingestion pipelines
- RAG workflows

---

## Observer Pattern

For:

- event tracking
- monitoring
- metrics
- logging

---

## Dependency Injection

Required for:

- testing
- modularity
- maintainability

Avoid tightly coupled services.

---

# 6. State Management

Complex workflows must explicitly define state.

Examples:

- LangGraph workflows
- agent workflows
- ingestion pipelines
- long-running jobs

Required structure:

```bash
state/
├── models.py
├── persistence.py
├── transitions.py
```

Example:

```python
class RetrievalState(TypedDict):
    query: str
    retrieved_docs: list
    reranked_docs: list
    final_response: str
```

State transitions must be:

- deterministic
- documented
- testable
- observable

---

# 7. Code Quality Standards

All code must include:

- type hints
- docstrings
- proper exception handling
- structured logging

Code must be:

- modular
- readable
- reusable
- maintainable

---

## Required tooling

### Ruff

```bash
ruff check .
ruff format .
```

---

## MyPy

```bash
mypy .
```

---

## Pytest

```bash
pytest
```

---

# 8. Testing Requirements

Every feature must be tested.

Required test categories:

- unit tests
- integration tests
- regression tests
- edge case tests

---

## Critical workflows that always require tests

- ingestion pipelines
- retrieval pipelines
- reranking
- API endpoints
- workflow orchestration
- state transitions

---

## Test organization

```bash
tests/
├── unit/
├── integration/
├── regression/
└── fixtures/
```

---

# 9. Pre-Commit Hooks

Every repository must include pre-commit hooks.

Required checks:

- pytest
- ruff
- mypy
- secret scanning

Example:

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest
        language: system
        pass_filenames: false

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: rff
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
```

---

# 10. README Requirements

README must be treated as a long-term wiki.

It must remain sufficiently structured and precise to onboard future engineers.

README must explain:

- business problem
- architecture
- design decisions
- module boundaries
- interfaces
- state flows
- deployment
- testing
- troubleshooting
- roadmap

---

# 11. Required README Structure

```md
# Project Name

## 1. Business Problem
### 1.1 Context
### 1.2 Requirements

## 2. Architecture
### 2.1 System Overview
### 2.2 Module Responsibilities
### 2.3 Interfaces
### 2.4 State Management

## 3. Ingestion Flow

## 4. Retrieval Flow

## 5. API Layer

## 6. Deployment

## 7. Testing Strategy

## 8. Monitoring

## 9. Troubleshooting

## 10. Future Improvements
```

---

# 12. Architecture Documentation

Complex relationships must be documented using ASCII diagrams.

---

## Example system diagram

```text
                User
                 |
                 v
          API Gateway
                 |
                 v
       Orchestration Layer
         /             \
        v               v
 Retrieval Layer   Ingestion Layer
        |               |
        v               v
 Vector DB         Object Storage
        |
        v
      LLM
```

---

## Example state diagram

```text
RAW_DOCUMENT
    |
PARSED
    |
CHUNKED
    |
EMBEDDED
    |
INDEXED
```

---

# 13. Observability

Systems should support:

- structured logging
- metrics
- tracing
- monitoring
- alerting

Recommended tools:

- Prometheus
- Grafana
- OpenTelemetry
- Sentry

---

# 14. Configuration Management

Never hardcode config values.

Use:

- config classes
- YAML
- TOML
- environment variables

Example:

```python
class Settings(BaseSettings):
    api_key: str
    db_url: str
```

---

# 15. CI/CD Requirements

Projects should support CI pipelines.

Minimum checks:

- tests
- linting
- static typing
- security scanning

Example pipeline:

```text
commit
  ↓
pre-commit
  ↓
CI tests
  ↓
build
  ↓
deploy
```

---

# 16. Documentation Discipline

Whenever functionality changes:

- update README
- update diagrams
- update tests
- update interfaces
- update configs

Documentation must evolve with code.

---

# 17. Forbidden Practices

Never:

- create giant scripts
- mix business logic with infrastructure code
- skip tests
- skip linting
- skip typing
- leave outdated docs
- hardcode secrets
- deploy untested code

---

# 18. Definition of Done

A task is complete only when:

- implementation works
- tests pass
- ruff passes
- mypy passes
- documentation updated
- README updated
- architecture updated
- interfaces documented
- state documented
- pre-commit passes
- no secrets exposed

If any of these are missing:

the task is NOT complete.