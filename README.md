# JEEX Idea

> **Transform raw ideas into professional documentation packages.**

JEEX Idea is a web application that turns your raw project concept into a complete set of professional Markdown documents (description, specifications, architecture, implementation plan) — ready for developers or AI agents to confidently start building.

**Domain:** idea.jeex.org  
**Status:** Early development

## Why JEEX Idea?

Ideas often drown in chat streams: lots of thoughts, little structure. JEEX Idea extracts the essence, asks the right questions, captures decisions, and automatically assembles a polished documentation package ready for work.

## Who Is It For?

- **Solo developers / indie founders** — quickly package ideas into clear plans without management overhead
- **Product managers** — structure requirements and technical vision for teams
- **Startup founders** — prepare technical documentation for investors and CTOs
- **Team leads / architects** — get aligned artifacts for team tracking
- **Agencies / studios** — standardize client idea onboarding
- **Students / hackathon participants** — formalize projects for demos in hours, not weeks

## Key Features

- **Multi-agent team architecture** — Product Manager coordinates specialized expert agents at each stage
- **LLM-powered language localization** — project language detected from first message, persists throughout
- **Interactive workflow** — agents ask structured questions with answer options; user responds in free text or numbered choices
- **Project isolation** — strict isolation at URL path and data level; agents work only within current project
- **Document versioning** — linear versioning; every significant edit creates new version
- **Open source & free** — no paywalls for core functionality
- **Flexible LLM policy** — supports cloud and self-hosted models (ChatGPT, Claude, Gemini, Grok, Mistral, Llama, Kimi, Qwen, etc.)

## How It Works (4 Steps)

### 1. Project Description

Product Manager guides user through idea exploration with expert team:

- **Business Analyst** — audience, goals, KPIs, monetization
- **Venture Expert** — scaling potential, investment appeal
- **TRIZ Expert** — innovative solutions, contradictions
- **Design Thinker** — user experience, empathy
- **Systems Analyst** — interconnections, dependencies

**Output:** _Project Description_ document

### 2. Specifications (planned)

Technical experts create _Engineering Specifications_: technical requirements, development standards, Definition of Done, code review processes, testing approaches, security rules.

### 3. Architecture (planned)

Architecture team proposes technical architecture, stack, patterns, and rationale. User can swap key decisions; documentation rebuilds consistently.

**Output:** _Architecture_ document

### 4. Planning (planned)

Planning team creates high-level _Implementation Plan_ with phases, tasks, acceptance criteria, risks, and dependencies.

**Final step:** Download archive with Markdown files organized in project language.

## Document Package

- **Project Description** — problem, goals, audience, scenarios, constraints, KPIs, risks, monetization
- **Engineering Specifications** (planned) — technical requirements, standards, DoD, code review, testing, security
- **Architecture** (planned) — approach, key decisions, components, integrations, trade-offs
- **Implementation Plan** (planned) — phases, tasks, acceptance criteria, risks/dependencies

## Development

### Quick Start

```bash
# Clone and setup
git clone <repository-url>
cd jeex-idea
make setup

# Setup Docker development environment
make dev-setup

# Verify Docker setup
make verify-docker

# Start development environment
make dev-up
```

### Development Environment

The project uses Docker Compose for a complete development stack:

- **PostgreSQL 18** - Primary database (port 5220)
- **Redis 6.4.0+** - Cache and queue (port 5240)
- **Qdrant 1.15.4+** - Vector database (port 5230)
- **FastAPI** - Backend API (port 5210)
- **Nginx** - Reverse proxy (port 80/443)
- **OpenTelemetry** - Observability (port 8888)

### Key Commands

- `make dev-up` - Start all development services
- `make dev-down` - Stop all services
- `make dev-logs` - View service logs
- `make dev-status` - Check service status
- `make db-shell` - Access PostgreSQL shell
- `make verify-docker` - Validate Docker setup

For detailed setup instructions, see [Docker Development Environment Setup](docs/instructions/DOCKER-SETUP.md).

## What's Next

- **MVP:** 4 steps with multi-agent teams, automatic language localization, basic templates, database versioning, archive download
- **Post-MVP:** Agent service isolation, expanded expert pool, partner integrations, web search for agents, industry templates, collaboration, Git export, A2A integrations, document quality analytics, agent learning from feedback

## License

[License information to be added]
