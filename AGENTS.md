# JEEX Plan Agent Guidelines

## Mission

- Transform raw user ideas into production-ready Markdown documentation packages.
- Uphold strict project isolation and security boundaries across all workflows.
- Coordinate with backend services, data stores, and infrastructure using the patterns described below.

## System Architecture Snapshot

- **API Backend**: FastAPI service (port 5210) orchestrating agent workflows
- **PostgreSQL**: Relational store (port 5220)
- **Qdrant**: Vector database (port 5230) for semantic retrieval of project-scoped content
- **Redis**: Cache and queue broker (port 5240) for coordination and rate control
- **Vault**: Secrets manager (port 5250) for all credentials; local `.env` files only hold Vault access
- **NGINX & OpenTelemetry**: Reverse proxy with TLS termination and observability pipeline

## Data Isolation Rules

- Every operation must include `project_id` from request context.
- Repository classes and vector payloads already enforce project scoping—never bypass them.
- Cache keys, logs, and telemetry data must carry project identifiers to avoid cross-project data leakage.
- Maintain soft-delete and timestamp conventions supplied by `TimestampMixin` and `SoftDeleteMixin`.

## Development Workflow

This project heavily utilizes a `Makefile` to simplify and standardize common development tasks. It is strongly recommended to use `make` targets for all routine operations like running the development environment, managing databases, and accessing service shells, instead of using raw `docker-compose` commands.

If you find yourself repeatedly typing a complex command, consider adding it as a new target to the `Makefile` to maintain consistency and ease of use.

The frontend is developed and run on the host machine, outside of the Docker environment. New database migrations should be generated from within the API container.

## Testing Expectations

The project maintains separate test suites for the backend (Pytest), frontend (pnpm), and E2E (Playwright). Refer to the QA agent's documentation for detailed testing strategies and commands.

## Secret Handling & Observability

- Store all secrets in Vault; never hardcode credentials or persist them in source control
- Use the root-level `.env` for local development overrides; do not create `backend/.env` files
- When debugging cross-agent flows, enable OpenTelemetry exporters within the local stack
- Regenerate embeddings and fixtures under `tests/fixtures/` whenever schema payloads evolve

## Language & Documentation Rules (Strict)

- **English-Only Policy**: All project files (code, configurations, scripts, etc.), with the exception of Markdown (`.md`) files, MUST be written exclusively in English. This includes all variable names, function names, comments, and any text content.
- **Markdown Exception**: Non-English content is permitted in `.md` files. However, mixing multiple languages within a single Markdown file is strongly discouraged.
- **Chat Communication**: AI assistants must respond in the same language used by the user.
- **Code Snippets in Markdown**: All code snippets, regardless of the file in which they appear, MUST be written in English. This rule is absolute and applies to all code within `.md` files.

## Development Conduct Restrictions

### Git Operations

- Never execute git commands; source control operations remain manual

### Production Code: NO FALLBACKS, MOCKS, OR STUBS (ZERO TOLERANCE)

**This is the most critical rule.** Better to have explicit TODO than hidden fallback.

#### Core Principles

- **No Silent Fallbacks**: Avoid logic that hides errors, such as default values for missing data or generic type conversions.
- **Real Implementations Only**: Production code must contain real logic, not mock or stub implementations that just log actions.
- **No Hardcoded Placeholders**: All configurations, like API keys or URLs, must come from environment variables or a secrets manager.
- **Preserve Error Context**: Catch exceptions to log them with full details, but re-raise them to preserve the original stack trace. Avoid generic error messages.
- **Explicit Requirements**: Functions must explicitly require all parameters. Fail fast if inputs are missing or invalid.
- **Use `NotImplementedError`**: For features that are not yet complete, explicitly raise `NotImplementedError` and add a `TODO` or `FIXME` comment.

#### 🚫 ENFORCEMENT Rules

1. **project_id**: Always REQUIRED (UUID, never Optional, never None)
2. **No mocks/stubs**: Outside test directories (`tests/`, `__tests__/`)
3. **No placeholders**: Use environment variables and config
4. **TODO/FIXME**: Allowed for genuinely unimplemented features
5. **All implementations**: Production-ready OR explicitly marked TODO
6. **All errors**: Preserve full context and stack traces

#### 🔍 EXCEPTIONS (Legitimate Architectural Patterns)

These fallbacks are **ALLOWED** as proper multi-tier architecture

- ✅ **Vault → Environment variables** (secrets management hierarchy)
- ✅ **JWT → Headers** (dev/test authentication fallback)
- ✅ **Primary → Replica** (database/service failover)

### Adherence to specs.md (CRITICAL)

**Strict compliance with `docs/specs.md` is mandatory.** This document is the single source of truth for all technical requirements, including API contracts, database schemas, and architectural patterns. Any deviation is a critical failure.

### Other Restrictions

- Keep prompts generic and reusable—no embedded domain-specific exemplars
- Adhere to DRY and SOLID principles when extending or refactoring agents and services

## Dependency & Version Policy

- Respect minimum versions documented in `docs/specs.md` (e.g., FastAPI ≥0.119.1, CrewAI ≥0.186.1)
- Resolve conflicts by upgrading related packages; never downgrade below mandated baselines

## Environment Notes

- Backend work executes inside Docker containers; use `docker-compose exec` for shell access
- Frontend development runs locally via pnpm, independent of Docker
- Set `ENVIRONMENT=development` to unlock dev tooling and hot reload inside containers
