# AGENT.md

## Purpose

This document defines the operational rules for AI coding agents contributing to this repository.

The agent must behave like a senior software engineer working in a production environment.

Goals:

- Maintain clean architecture
- Preserve system stability
- Prevent regressions
- Ensure full documentation
- Maintain test coverage
- Avoid security risks
- Keep repository understandable for future developers

---

# 1. Core Principles

## 1.1 Never break working functionality

Before modifying existing logic:

- understand full execution flow
- inspect dependencies
- identify downstream consumers
- preserve backward compatibility unless explicitly instructed otherwise

If unsure:

- ask for clarification
- do not make destructive assumptions

## 1.2 Always prefer maintainability over shortcuts

Avoid:

- quick hacks
- hidden side effects
- duplicated logic
- oversized files
- tightly coupled components

Prefer:

- abstraction
- composition
- interfaces
- reusable components
- testability

## 1.3 Production-ready code only

Every code contribution must be:

- typed
- documented
- testable
- modular
- observable
- deterministic where possible

---

# 2. Security Rules

## Never expose secrets

The agent must NEVER:

- print API keys
- print tokens
- print credentials
- hardcode secrets
- expose `.env` contents
- log sensitive credentials

Use:

- environment variables
- secret managers
- configuration abstraction

---

# 3. Required Project Structure

```bash
project/
├── ingestion/
├── retrieval/
├── api/
├── orchestration/
├── core/
├── state/
├── tests/
├── scripts/
├── docs/
└── README.md
```

---

# 4. Testing Requirements

After EVERY change run:

```bash
pytest
```

Required:

- unit tests
- integration tests
- e2e tests
- regression tests for bug fixes

---

# 5. Code Quality

```bash
ruff check .
ruff format .
mypy .
```

Mandatory for all commits.

---

# 6. Documentation

README.md must function as a full wiki:

- architecture
- setup
- workflows
- deployment
- troubleshooting
- scaling

Use nested sections and ASCII diagrams.

Example:

```text
User → API → Retrieval → Reranker → LLM
```

---

# 7. Design Patterns

Use where appropriate:

- Strategy
- Factory
- Adapter
- Repository
- Dependency Injection

---

# 8. State Management

State must be explicit.

Examples:

- checkpoints
- workflow state
- cache
- session state

Never hide state in globals.

---

# 9. Pre-commit Hooks

Every repo must include pre-commit hooks for:

- pytest
- ruff
- mypy

---

# 10. RAG / Agent Systems

Validate:

- parsing quality
- chunking quality
- retrieval metrics
- hallucination rate
- latency
- fallback behavior

Metrics:

- recall@k
- precision@k
- p95 latency
- token cost

---

# 11. Failure Handling

Define:

- retries
- timeouts
- fallbacks
- recovery strategy

---

# 12. Forbidden Behavior

Never:

- bypass tests
- ignore linting
- expose secrets
- rewrite architecture impulsively
- leave undocumented complexity

---

# 13. Definition of Done

Work is complete only when:

- tests pass
- docs updated
- architecture remains clean
- feature works
- maintainability improves