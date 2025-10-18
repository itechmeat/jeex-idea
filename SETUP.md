# Project Setup Guide

This document explains the project structure and setup steps for the JEEX Idea repository.

## Project Overview

This repository contains AI agent configurations and command workflows for JEEX IDEA project development. It provides:

- **Agent Definitions** - Specialized agents for architecture, development, testing, and planning
- **Development Commands** - Workflow commands for story-based development with automated orchestration
- **IDE Integration** - Symlink structure for Cursor, Claude, and other AI IDEs

## Directory Structure

```text
.ai/
├── agents/                    # AI agent definitions
│   ├── tech-architect.md      # Solution/Backend Architect
│   ├── tech-backend.md        # FastAPI/Python backend (tech-python)
│   ├── tech-devops.md         # Docker/Infrastructure
│   ├── tech-frontend.md       # React/TypeScript frontend
│   ├── tech-pm.md             # Project Manager (EARS-based planning)
│   ├── tech-postgres.md       # PostgreSQL database
│   ├── tech-qa.md             # QA Engineer (Playwright/pytest)
│   ├── tech-redis.md          # Redis caching/pub-sub
│   └── tech-vector-db.md      # Qdrant vector search
│
├── commands/                  # Development workflow commands
│   ├── develop.prompt.md      # Standard development workflow
│   ├── develop.toml           # Development command config
│   ├── develop-cov.prompt.md  # Chain-of-Verification development
│   ├── develop-cov.toml       # CoV command config
│   ├── plan.prompt.md         # Story planning workflow
│   ├── plan.toml              # Planning command config
│   ├── test.prompt.md         # Testing workflow
│   ├── test.toml              # Testing command config
│   ├── commit-suggest.prompt.md # Branch/commit message suggestions
│   ├── commit-suggest.toml    # Commit suggest config
│   ├── coderabbit.prompt.md   # Code review workflow
│   ├── coderabbit.toml        # Code review config
│   ├── pre-commit.prompt.md   # Pre-commit checks
│   ├── pre-commit.toml        # Pre-commit config
│   └── utilities/             # Utility commands
│
└── settings.local.json        # Local AI IDE settings

docs/                          # Project documentation
├── about.md                   # Project vision and requirements
├── architecture.md            # System architecture
├── specs.md                   # Technical specifications
├── feature.md                 # Feature descriptions
└── prompt.md                  # Prompt templates

stories/                       # Story-based planning (created by /plan)
├── plan.md                    # Planned stories
├── backlog.md                 # Completed stories
└── <story-slug>/              # Detailed story folders
    ├── design.md              # Architecture & diagrams
    ├── requirements.md        # EARS-compliant requirements
    └── tasks.md               # Task checklist
```

## Symbolic Links Setup

The project uses symbolic links for cross-IDE compatibility and organizational consistency.

### Automated Setup with Makefile (Recommended)

Use the provided Makefile for automated setup:

```bash
# View all available commands
make help

# Setup all symlinks and directory structure
make setup

# Verify setup is correct
make verify-setup
```

**Alternative:** If you're on **Linux/macOS** or **Windows with Developer Mode**, symlinks should work automatically after cloning.

### Manual Setup

If symlinks weren't preserved (e.g., Windows without Developer Mode), create them manually:

#### 1. File Symlinks

```bash
# Create CLAUDE.md symlink pointing to AGENTS.md
ln -s AGENTS.md CLAUDE.md
```

#### 2. Directory Symlinks

```bash
# .claude -> .ai (Claude IDE integration)
ln -s .ai .claude

# .qwen -> .ai (Qwen IDE integration)
ln -s .ai .qwen

# .github/prompts -> .ai/commands (GitHub Copilot integration)
cd .github && ln -s ../.ai/commands prompts && cd ..
```

#### 3. Cursor IDE Rules

```bash
# Create .cursor/rules with symlinks to agents (as .mdc files)
mkdir -p .cursor/rules
cd .cursor/rules

# Link all agent files with .mdc extension
for file in ../../.ai/agents/*.md; do
  basename="${file##*/}"
  ln -s "$file" "${basename%.md}.mdc"
done

cd ../..
```

### Verification

```bash
# Check file symlinks
ls -la | grep CLAUDE
# Expected: lrwxr-xr-x CLAUDE.md -> AGENTS.md

# Check directory symlinks
ls -lad .ai .claude .qwen
# Expected:
# drwxr-xr-x .ai
# lrwxr-xr-x .claude -> .ai
# lrwxr-xr-x .qwen -> .ai

# Check .github/prompts
ls -la .github/ | grep prompts
# Expected: lrwxr-xr-x prompts -> ../.ai/commands

# Check .cursor/rules
ls -la .cursor/rules/
# Expected: Multiple .mdc files like:
# tech-architect.mdc -> ../../.ai/agents/tech-architect.md
# tech-backend.mdc -> ../../.ai/agents/tech-backend.md
# tech-pm.mdc -> ../../.ai/agents/tech-pm.md
```

## Agent Descriptions

### Development Agents

| Agent                  | File                | Purpose                                                               |
| ---------------------- | ------------------- | --------------------------------------------------------------------- |
| **Solution Architect** | `tech-architect.md` | System architecture design, C4 diagrams, ADRs, tech stack decisions   |
| **Backend Developer**  | `tech-backend.md`   | FastAPI, Pydantic, SQLAlchemy, async I/O, OAuth2, SSE streaming       |
| **Frontend Developer** | `tech-frontend.md`  | React 19+, TypeScript, TanStack DB, CSS Modules, accessibility        |
| **PostgreSQL Expert**  | `tech-postgres.md`  | Database design, Alembic migrations, project isolation, performance   |
| **Redis Expert**       | `tech-redis.md`     | Caching, pub/sub for SSE, rate limiting, queue management             |
| **Vector DB Expert**   | `tech-vector-db.md` | Qdrant setup, embedding pipelines, semantic search, payload filtering |
| **DevOps Engineer**    | `tech-devops.md`    | Docker, orchestration, environment setup, deployment                  |
| **QA Engineer**        | `tech-qa.md`        | Playwright E2E, pytest integration, project isolation testing         |
| **Code Reviewer**      | `tech-reviewer.md`  | Story completion verification, architecture compliance, code review   |
| **Project Manager**    | `tech-pm.md`        | EARS-based story planning, requirements, task tracking                |

### Key Agent Principles

- **Schema-Driven Development** - Single source of truth (Pydantic → OpenAPI → TypeScript)
- **Project Isolation** - All operations scoped to `project_id` (no tenant concept)
- **EARS Requirements** - Structured requirements using Easy Approach to Requirements Syntax
- **No Fallbacks** - Zero tolerance for mock data, defaults, or stubs in production
- **Type Safety** - Strict TypeScript/Python typing, no `any` types

## Command Workflows

### Primary Commands

| Command           | Purpose                                | Example                                                |
| ----------------- | -------------------------------------- | ------------------------------------------------------ |
| `/develop`        | Standard development workflow          | `/develop "Implement OAuth2" story:auth task:1.1`      |
| `/develop-cov`    | Development with Chain-of-Verification | `/develop-cov "Build real-time system" story:realtime` |
| `/plan`           | Story planning and management          | `/plan "Create implementation plan from docs/"`        |
| `/test`           | Comprehensive testing                  | `/test` (runs all tests)                               |
| `/commit-suggest` | Suggest branch name and commit message | `/commit-suggest "Added OAuth2 authentication"`        |
| `/reviewer`       | Code review for story completion       | `/reviewer "focus on security"`                        |

### Support Commands

| Command       | Purpose                                |
| ------------- | -------------------------------------- |
| `/coderabbit` | Code review and quality analysis       |
| `/reviewer`   | Story completion and compliance review |
| `/pre-commit` | Pre-commit validation checks           |

**Note:** `/commit-suggest` command follows [Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) specification for semantic commit messages and automated changelog generation.

### Command Usage Patterns

```bash
# Planning Phase
/plan "Analyze docs/ and create story plan"
/plan "Create detailed story for user-auth"

# Development Phase
/develop "Implement user-auth" story:user-auth task:1.1,1.2
# OR with architectural analysis:
/develop-cov "Implement complex feature" story:feature

# Testing Phase
/test

# Git Workflow Phase
/commit-suggest                                 # Analyze git status automatically
/commit-suggest "Added OAuth2 authentication"   # With context
/commit-suggest "story:user-auth task:2.1"      # With story reference

# Code Review Phase
/reviewer
/reviewer "focus on security and isolation"

# Progress Tracking
/plan "Mark tasks 1.1-1.3 complete in user-auth"
/plan "Move user-auth story to backlog"
```

## Story-Based Planning

The project uses **EARS-compliant story-based planning** (not epic-based):

```text
stories/
├── plan.md              # Planned stories (future work)
├── backlog.md           # Completed stories (history)
└── <story-slug>/        # Detailed story (kebab-case)
    ├── design.md        # Architecture, diagrams (13 sections)
    ├── requirements.md  # EARS requirements (strict patterns)
    └── tasks.md         # Task checklist (max 2-level depth)
```

**EARS Patterns Required:**

- Ubiquitous: `The <system> shall <response>`
- State-driven: `While <condition>, the <system> shall <response>`
- Event-driven: `When <trigger>, the <system> shall <response>`
- Optional: `Where <feature>, the <system> shall <response>`
- Unwanted: `If <trigger>, then the <system> shall <response>`

## Development Standards

### Required Practices

1. **Project Isolation** - All queries filter by `project_id` (NEVER optional)
2. **Schema-Driven** - Pydantic/SQLAlchemy as single source of truth
3. **EARS Requirements** - All requirements.md follow EARS patterns
4. **Task Format** - Use `[x]` for completed tasks (not emoji)
5. **English Only** - All filenames, folder names, code in English
6. **No Temporal References** - No dates in plan content

### Prohibited Practices

- ❌ Fallback to default project (ALWAYS explicit)
- ❌ Mock/stub implementations in production
- ❌ Manual schema duplication (use code generation)
- ❌ Epic hierarchy (flat story structure only)
- ❌ CSS selectors in E2E tests (use data-testid)

## Environment Notes

### Platform Compatibility

- **Linux/macOS**: Symlinks work automatically
- **Windows**: Requires Developer Mode or Administrator privileges
- **Git**: Symlinks are committed and preserved across clones

### IDE Integration

- **Cursor**: Uses `.cursor/rules/*.mdc` (agent definitions)
- **Claude**: Uses `.claude/` (symlink to `.ai/`)
- **Qwen**: Uses `.qwen/` (symlink to `.ai/`)
- **GitHub Copilot**: Uses `.github/prompts/` (symlink to `.ai/commands/`)

## Getting Started

1. **Clone repository**

   ```bash
   git clone <repository-url>
   cd jeex-agents
   ```

2. **Run setup** (creates all symlinks and directories)

   ```bash
   make setup
   make verify-setup
   ```

3. **Review documentation**

   ```bash
   cat docs/about.md        # Project overview
   cat docs/architecture.md # Architecture decisions
   cat docs/specs.md        # Technical specs
   ```

4. **Start planning**

   ```bash
   # Use /plan command to create initial story plan
   /plan "Create implementation plan based on docs/"
   ```

5. **Begin development**

   ```bash
   # Use /develop command to implement stories
   /develop "Implement first story" story:<slug>
   ```

6. **Git workflow with Conventional Commits**

   ```bash
   # Get smart suggestions for branch name and commit message
   /commit-suggest

   # Use suggested branch name (example output)
   git checkout -b feat/auth-add-oauth2-authentication

   # Use suggested commit message (example output)
   git commit -m "feat(auth): add OAuth2 authentication with Twitter provider"
   ```

## Makefile Commands

The project includes a Makefile with useful commands:

| Command             | Description                                  |
| ------------------- | -------------------------------------------- |
| `make help`         | Display all available commands               |
| `make setup`        | Setup all symlinks and directory structure   |
| `make verify-setup` | Verify all symlinks are correctly configured |
| `make clean-setup`  | Remove all symlinks (use with caution)       |
| `make dev`          | Start development environment (TODO)         |
| `make test`         | Run all tests (TODO)                         |
| `make lint`         | Run linters (TODO)                           |
| `make format`       | Format code (TODO)                           |

**Note:** Commands marked with (TODO) are placeholders for future implementation.

## Additional Resources

- **Makefile** - Automation commands for setup and development
- **AGENTS.md** - Comprehensive agent descriptions and workflows
- **docs/architecture.md** - System architecture and design decisions
- **docs/specs.md** - Technical specifications and requirements
- **EARS Standard** - <https://alistairmavin.com/ears/>

## Support

For questions or issues with setup, refer to:

- Agent definitions in `.ai/agents/`
- Command workflows in `.ai/commands/`
- Project documentation in `docs/`
