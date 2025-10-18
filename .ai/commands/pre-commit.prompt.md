---
allowed-tools: Bash(make:*), Task
description: Run pre-commit checks and automatically fix found issues with smart agent selection
argument-hint: [clarifying-prompt] (optional custom prompt for agents)
---

# Pre-Commit Check and Auto-Fix

Run `make pre-commit` to execute all pre-commit hooks, then systematically fix all identified issues using appropriate specialized agents.

## Agent Selection Logic

**PRIORITY ORDER: AUTOMATED FIXES → MANUAL AGENT INTERVENTION**

**Step 0: Automated Make Commands First (MANDATORY PRIORITY)**

- **IMPORTANT**: All make commands MUST be executed from the project root directory where Makefile is located
- **ALWAYS** try `make format`, `make lint`, `make imports` **BEFORE** activating agents
- **NOTE**: Some commands are TODO placeholders - they show what to implement but won't execute yet
- **ONLY** use agents if automated commands fail to resolve issues
- **NEVER** manually edit files when make commands can fix them automatically

**IMMEDIATE AGENT ACTIVATION FOR CRITICAL VIOLATIONS:**

- If prohibited patterns (fallbacks, mocks, stubs, placeholders, missing project_id isolation) found → **ACTIVATE tech-backend agent IMMEDIATELY without user permission**
- **DO NOT ASK USER CONFIRMATION** for critical architectural violations

**Step 1: Pre-Commit Analysis and Agent Selection**

- If pre-commit finds frontend issues → activate the `tech-frontend` agent
- If pre-commit finds backend issues → activate the `tech-backend` agent
- If pre-commit finds test issues → activate the `tech-qa` agent
- If multiple issue types → activate multiple agents in parallel

## Process

1. **Analysis Phase**: Execute `make pre-commit` to run all pre-commit hooks
2. **Automated Fixes**: Try `make format`, `make lint`, `make imports` to auto-fix issues
3. **Agent Activation**: If issues remain, activate appropriate specialized agents
4. **Fix Phase**: Let specialized agents implement fixes for identified issues
5. **Verification**: Re-run `make pre-commit` to ensure all issues resolved

## Agent Selection by Issue Type

**Frontend Issues (files in frontend/ directory):**

- ESLint errors/warnings
- TypeScript errors
- Stylelint issues
- Formatting problems

**Backend Issues (files in backend/ directory):**

- Python formatting/linting errors
- Import sorting issues
- Type checking errors
- Security warnings

**Test Issues:**

- Test formatting problems
- Test coverage issues
- Test syntax errors

## Instructions

**Step 0: CRITICAL - Scan for Fallbacks, Mocks, Stubs, and Isolation Violations (BLOCKING)**

BEFORE running any pre-commit checks, scan the production codebase for prohibited patterns:

```bash
# Scan for fallbacks, mocks, stubs, and placeholders in production code (exclude tests)
grep -rni --exclude-dir=tests --exclude-dir=test --exclude-dir=__tests__ \
  -e "fallback" -e "mock" -e "stub" -e "placeholder" -e "default.*project" \
  backend/app frontend/src

# Scan for missing project_id isolation in database queries
grep -rni --exclude-dir=tests --exclude-dir=test \
  -e "select.*from.*where" \
  backend/app | grep -v "project_id"

# Scan for missing language filter in Qdrant searches
grep -rni --exclude-dir=tests --exclude-dir=test \
  -e "qdrant.*search" -e "Filter.*must" \
  backend/app | grep -v "language"

# Exit code 0 means patterns found (FAIL), exit code 1 means no patterns found (PASS)
```

**CRITICAL RULES (from specs.md & architecture.md):**

- **NO fallbacks** except for legitimate architectural patterns:

  - ✅ Vault → Environment variables (secrets management)
  - ✅ JWT → Headers (development/testing)
  - ❌ Default project creation
  - ❌ String conversion fallbacks
  - ❌ Mock/stub data in production code

- **STRICT project_id isolation** in ALL database queries and vector searches

  - PostgreSQL: ALWAYS filter by `project_id` in WHERE clauses
  - Qdrant: ALWAYS use server-side Filter with `project_id` AND `language`
  - Redis: ALWAYS use `proj:{project_id}:` key prefix
  - ❌ Client-side filters (can be bypassed)

- **Language isolation**: Project language determined via LLM (NOT scripts/libraries)

  - Stored in project metadata, applied to all documents/interactions
  - Vector search MUST filter by both `project_id` AND `language`

- **Schema-driven architecture**:

  - Pydantic = single source of truth (validation + API contracts + OpenAPI docs)
  - SQLAlchemy models = single source of truth (Alembic autogenerate migrations)
  - NO manual schema duplication

- **Minimum versions** (from specs.md):

  - FastAPI 0.116.2+, PostgreSQL 18, Redis 6.4.0+, Qdrant 1.15.4+
  - CrewAI 0.186.1+, Pydantic AI 1.0.8+, Tenacity 9.0+, OpenTelemetry 1.27+

- **TODO/FIXME allowed** for unimplemented functionality (better explicit TODO than hidden fallback)
- **NO placeholder** values in production code
- **NO mock/stub** implementations outside test directories

**If prohibited patterns are found:**

1. **STOP** - Do not proceed with pre-commit checks
2. **ACTIVATE tech-backend agent IMMEDIATELY** - Do NOT ask for user permission
3. **Remove** all fallbacks, mocks, stubs, placeholders, and isolation violations from production code using the agent
4. **Verify** removal with another scan
5. **Then** proceed to Step 1

**MANDATORY AGENT ACTIVATION FOR PROHIBITED PATTERNS:**

When fallbacks, mocks, stubs, or isolation violations are found in production code, activate the `tech-backend` agent WITHOUT user confirmation:

```
Use the Task tool with parameters:
- subagent_type: "tech-backend"
- description: "Remove prohibited fallbacks/mocks/stubs and enforce isolation"
- prompt: "CRITICAL: Remove all prohibited fallbacks, mocks, stubs, placeholder values, and isolation violations from production code. Found patterns: [insert found patterns].

ARCHITECTURE REQUIREMENTS (from specs.md & architecture.md):
- Replace fallbacks with proper implementations or explicit TODO exceptions
- Enforce STRICT project_id isolation in ALL database queries (PostgreSQL, Qdrant, Redis)
- Enforce language isolation: Qdrant searches MUST filter by project_id AND language
- Use server-side filters only (NO client-side constructed filters)
- NO default project creation, NO mock data, NO placeholder values
- Use architectural patterns: Vault → environment variables, JWT → Headers (dev/test only)
- FastAPI 0.116.2+ with async I/O, Pydantic 2+ schemas as single source of truth
- CrewAI 0.186.1+ for multi-agent orchestration, Google ADK support

Verify removal with follow-up scan. Do not ask for permission - fix immediately."
```

**AUTOMATIC FIXING REQUIRED:**

- Default project creation → Remove or replace with explicit project requirement (UUID, never Optional)
- Mock responses → Replace with real implementations or explicit TODO
- Placeholder values → Use config/environment variables or TODO
- Missing project_id filters → Add to ALL database queries (PostgreSQL WHERE clauses, Qdrant Filter, Redis keys)
- Missing language filters → Add to Qdrant searches (project_id + language)
- Client-side filters → Replace with server-side Filter construction
- Fallback logic → Keep only legitimate architectural patterns (Vault→env, JWT→headers for dev/test)

**Step 1: Run Pre-Commit Checks**
Execute all pre-commit hooks (ensure you're in project root directory):

```bash
!timeout 600 bash -c 'make pre-commit; echo "__PRECOMMIT_STATUS:$?"'
```

**Step 2: Automated Fix Attempts with Make Commands (PRIORITY)**

**ALWAYS TRY AUTOMATED FIXES FIRST before manual file-by-file editing:**

**CRITICAL: All make commands MUST be executed from the project root directory where Makefile is located**

**NOTE: Some commands below are placeholders (marked TODO in Makefile). These commands will show what needs to be implemented but won't fail. If a command is not fully implemented, proceed to manual agent intervention.**

1. **Frontend/Backend Formatting Issues → Run `make format` command:**

   ```bash
   make format  # TODO in Makefile - shows commands to implement
   ```

2. **Linting Issues → Run `make lint` command:**

   ```bash
   make lint  # TODO in Makefile - shows commands to implement
   ```

3. **Import Sorting Issues → Run `make imports` command:**

   ```bash
   make imports  # TODO in Makefile - shows commands to implement
   ```

**Step 3: Verify Automated Fixes**
Re-run pre-commit checks to see if automated commands resolved the issues (ensure you're in project root):

```bash
make pre-commit
```

**Step 4: Manual Agent Intervention (If Automated Fixes Failed)**

Only if automated make commands did NOT resolve all issues, then proceed to manual file-by-file agent intervention:

**Analyze remaining pre-commit output to identify:**

1. **Issue types and locations**
2. **Severity levels (errors vs warnings)**
3. **Files affected and their locations** (frontend/, backend/, tests/)

**Step 5: Agent Selection and Activation**
Based on the remaining pre-commit results (after automated fix attempts), activate appropriate agents:

**If frontend issues found:**

```
Use the Task tool with parameters:
- subagent_type: "tech-frontend"
- description: "Fix pre-commit frontend issues"
- prompt: "SECURITY-FIRST: Run detect-secrets/trufflehog scan and license compliance checks BEFORE any fixes. Generate structured reports (ESLint --format=json, TypeScript --pretty false, Playwright --reporter=html) for data-driven analysis instead of log scraping. Redact all secrets in outputs with [REDACTED]. Fix the following pre-commit issues in the frontend code: [insert pre-commit frontend errors]. Resolve ESLint, TypeScript, and formatting issues. Follow React 19+, TypeScript strict mode, and accessibility standards. Apply all fixes using the exact tools and configurations specified in the project."
```

**If backend issues found:**

```
Use the Task tool with parameters:
- subagent_type: "tech-backend"
- description: "Fix pre-commit backend issues"
- prompt: "SECURITY-FIRST: Run detect-secrets/trufflehog scan and license compliance checks BEFORE any fixes. Generate structured reports (pytest --junit-xml, mypy --xml-report, ruff --format=json, bandit --format=json, safety --json) for data-driven analysis instead of log scraping. Redact all secrets in outputs with [REDACTED].

CRITICAL ARCHITECTURE REQUIREMENTS (from specs.md & architecture.md):
- STRICT project_id isolation in ALL database queries (PostgreSQL, Qdrant, Redis)
- Language isolation: Qdrant searches MUST filter by project_id AND language (server-side only)
- NO fallbacks, mocks, stubs, placeholders in production code
- Schema-driven: Pydantic as single source of truth (validation + API contracts + docs)
- SQLAlchemy models as single source of truth (Alembic autogenerate migrations)
- FastAPI 0.116.2+ with async I/O, OAuth2 (Twitter only in MVP), SSE streaming
- CrewAI 0.186.1+ for multi-agent orchestration, Google ADK support
- PostgreSQL 18+, Redis 6.4.0+, Qdrant 1.15.4+, OpenTelemetry 1.27+
- Project_id ALWAYS required (UUID, never Optional), no default project creation
- TODO/FIXME allowed for unimplemented functionality

Fix the following pre-commit issues: [insert pre-commit backend errors]. Resolve Python formatting, linting, import sorting, and type checking issues. Use ruff, black, isort, and mypy as configured. Verify project+language isolation maintained."
```

**If test issues found:**

```
Use the Task tool with parameters:
- subagent_type: "tech-qa"
- description: "Fix pre-commit test issues"
- prompt: "SECURITY-FIRST: Run detect-secrets/trufflehog scan and license compliance checks BEFORE any fixes. Generate structured reports (pytest --junit-xml --html=reports/pytest-report.html, Playwright --reporter=html,junit, coverage xml --fail-under=90) for data-driven analysis instead of log scraping. Redact all secrets in outputs with [REDACTED]. Fix the following pre-commit issues in test files: [insert pre-commit test errors]. Resolve test formatting, coverage, and syntax issues. Follow testing best practices and maintain test quality standards."
```

**For multiple issue types:**
Launch agents in parallel for each issue type identified.

## Security-First Pre-Commit Gates

**MANDATORY: Run these checks BEFORE any formatting/linting:**

1. **Secret Scanning** (BLOCKING):

   ```bash
   # Run detect-secrets baseline scan
   detect-secrets scan --baseline .secrets.baseline
   # Or run trufflehog for comprehensive scanning
   trufflehog filesystem . --exclude-paths trufflehog-exclude.txt
   # EXIT CODE: Non-zero blocks commit
   ```

2. **License Compliance** (BLOCKING):

   ```bash
   # Verify license headers exist in all source files
   licensecheck --check .licensecheck.yml
   # EXIT CODE: Non-zero blocks commit on missing headers
   ```

3. **Redaction Verification** (BLOCKING):
   - All agent outputs MUST redact secrets with `[REDACTED]` markers
   - Pre-commit hook fails if redaction markers are missing from logs
   - Agents must scan their own outputs before submission
   - Automated checks verify redaction patterns in all generated artifacts

## Failure Artifacts Requirements

**MANDATORY: Agents must generate structured reports for data-driven remediation**

### Frontend Agent Artifacts:

```bash
# ESLint JSON report for structured error analysis
eslint . --format=json --output-file=reports/eslint-report.json

# TypeScript compiler output for type error analysis
tsc --noEmit --pretty false > reports/typescript-errors.txt

# Playwright HTML report for E2E test failures
npx playwright test --reporter=html,junit --output-dir=reports/
```

### Backend Agent Artifacts:

```bash
# pytest JUnit XML + HTML reports for test failures
pytest --junit-xml=reports/pytest-junit.xml --html=reports/pytest-report.html

# mypy XML report for type checking issues
mypy . --xml-report reports/mypy-report/

# ruff JSON report for linting issues
ruff check . --format=json --output-file=reports/ruff-report.json
```

### QA Agent Artifacts:

```bash
# Ensure report directories exist
mkdir -p reports/{unit,e2e,coverage}

# Comprehensive test reporting
pytest --junit-xml=reports/unit-tests.xml --html=reports/unit-tests.html --cov-report=xml:reports/coverage.xml
npx playwright test --reporter=html,junit --output-dir=reports/e2e/
```

**Step 6: Specialized Agent Execution**

The activated agent must:

1. **SECURITY-FIRST CHECKS** - run secret scanning (detect-secrets/trufflehog) and license compliance BEFORE any other checks
2. **Redact sensitive data** - ensure all logs and outputs have secrets properly redacted with [REDACTED] markers
3. **Generate failure artifacts** - produce JUnit XML/HTML reports (pytest --junit-xml, Playwright --reporter=html) for data-driven analysis
4. **Attach structured reports** - use artifacts instead of log scraping for reliable automatic remediation
5. **Read each issue carefully** - understand the error, location, and suggested fix from structured data
6. **Implement exact fixes** - apply the corrections using the appropriate tools
7. **Maintain consistency** - follow existing patterns and project conventions
8. **Preserve functionality** - ensure fixes don't break existing functionality
9. **Follow project standards** - comply with CLAUDE.md requirements
10. **Verify fixes** - run relevant checks after applying fixes and generate post-fix reports
11. **Artifact scrubbing** - remove sensitive data from all generated reports before publishing
12. **Project-safe publishing** - ensure all published artifacts are project-isolated and secure

## Key Principles for Agents

- **MANDATORY SECRET SCANNING** - run detect-secrets or trufflehog before any code changes, fail on findings
- **LICENSE COMPLIANCE** - verify all files have proper license headers, fail on missing headers
- **REDACTION ENFORCEMENT** - all copied logs/outputs MUST have secrets redacted with [REDACTED] markers
- **DATA-DRIVEN REMEDIATION** - generate and attach JUnit/HTML reports instead of log scraping for reliable fixes
- **STRUCTURED ARTIFACTS** - use pytest --junit-xml, Playwright --reporter=html, ESLint --format=json for analysis
- **Use project tools** - apply fixes using configured tools (ruff, black, ESLint, etc.)
- **Follow DRY principles** - extract reusable code where appropriate
- **Maintain project isolation architecture** - ensure all changes respect project isolation
- **Follow security best practices** - implement proper validation and sanitization
- **Preserve test coverage** - maintain or improve test coverage after fixes

## Critical Requirements

- **Always provide the exact `subagent_type`** in the Task tool
- **Confirm agent activation** - the agent must introduce itself when it starts
- **Pass specific error details** - include exact error messages and file locations
- **Retry with corrected parameters** if agent activation fails

## Expected Output from Specialized Agents

- **Issue Analysis**: Summary of pre-commit issues found and their categorization
- **Fix Status**: Status of each issue (fixed/skipped/needs-review)
- **Changes Summary**: Detailed list of files modified and changes applied
- **Verification Results**: Output from re-running relevant checks
- **Quality Confirmation**: Assurance that fixes don't introduce new issues

## Command Execution Flow

1. **Run pre-commit checks** using `make pre-commit` (ensure you're in project root directory)
2. **Analyze output** to identify issue types and affected areas
3. **Activate matching agents** based on issue categorization
4. **Pass specific error details** to each agent
5. **Collect agent reports** detailing applied changes
6. **Verify fixes** - ensure no new issues introduced

## IMPORTANT LOCATION REQUIREMENT

**All make commands MUST be executed from the project root directory where Makefile is located**

- Use `cd ..` if you're in a subdirectory like `frontend/` or `backend/`
- Verify you're in the correct directory by running `ls Makefile`
- Make commands will fail with "No rule to make target" if not executed from the project root

## Usage Examples

- `/dev:pre-commit` - run pre-commit and fix all found issues
- `/dev:pre-commit "focus on ESLint errors"` - run pre-commit with specific focus
- `/dev:pre-commit "prioritize security warnings"` - run pre-commit with security emphasis

**Important:** Always verify that agents actually activated - each agent must introduce itself at the start of its response!
