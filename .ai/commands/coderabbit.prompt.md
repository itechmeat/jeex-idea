---
allowed-tools: Bash(coderabbit:*), Task
description: Run CodeRabbit analysis and automatically fix all found issues with smart agent selection
argument-hint: [scope] [additional-instructions] (frontend/backend/all) (optional custom prompt)
---

# CodeRabbit Code Review and Auto-Fix

Run CodeRabbit CLI analysis in prompt-only mode optimized for AI agents, then systematically fix all identified issues using appropriate specialized agents.

## Agent Selection Logic

**Step 1: Argument Analysis and Agent Selection**

- Argument `frontend` or path contains `frontend/` → activate the `tech-frontend` agent
- Argument `backend` or path contains `backend/` → activate the `tech-backend` agent
- Argument `all` or no argument provided → analyze the entire project and auto-select agents based on results

## Process

1. **Analysis Phase**: Execute CodeRabbit CLI with `--prompt-only` flag to get AI-optimized output
2. **Agent Activation**: Based on scope argument, activate appropriate specialized agent using Task tool
3. **Fix Phase**: Let the specialized agent implement all suggested fixes
4. **Verification**: Ensure all changes maintain code quality and follow project conventions

## Scope Examples

- `/coderabbit.prompt frontend` - analyze frontend directory with tech-frontend agent
- `/coderabbit.prompt backend` - analyze backend directory with tech-backend agent
- `/coderabbit.prompt frontend/components/ui` - analyze specific frontend module with tech-frontend agent
- `/coderabbit.prompt backend/app` - analyze specific backend module with tech-backend agent
- `/coderabbit.prompt all` - analyze entire project with appropriate agents
- `/coderabbit.prompt` - same as 'all' - analyze entire project

## Instructions

**Step 1: CodeRabbit Analysis**
Run CodeRabbit analysis on ${ARGUMENTS:-.} (current directory if no arguments provided):

!timeout 1200 coderabbit --prompt-only ${ARGUMENTS:+--cwd $ARGUMENTS}

**IMPORTANT: Analysis Duration**
CodeRabbit analysis can take up to 10 minutes to complete, especially for large changesets or projects with many files. **Wait patiently** - do NOT interrupt the process.

**CRITICAL: Error Handling**
If CodeRabbit returns any error (rate limits, authentication, network issues, etc.):

1. **Immediately stop execution** - do NOT proceed with agent activation
2. **Notify the user** about the specific error encountered
3. **Provide guidance** on how to resolve the issue (e.g., wait for rate limit reset, check authentication)
4. **Exit gracefully** without launching any agents

Common error scenarios:

- **Rate limit exceeded**: "CodeRabbit API rate limit exceeded. Please wait and try again later."
- **Authentication failed**: "CodeRabbit authentication failed. Please check your API credentials."
- **Network/connectivity issues**: "CodeRabbit API is unreachable. Please check your internet connection."
- **Invalid arguments**: "Invalid CodeRabbit arguments provided. Please check the command syntax."

**Step 2: Agent Selection and Activation**
**ONLY proceed if CodeRabbit analysis completed successfully without errors.**

**CRITICAL: NO FALLBACKS, MOCKS, OR STUBS RULE**

Before activating any agent, inject these ABSOLUTE requirements into the agent prompt:

**PROHIBITED IN PRODUCTION CODE:**

- ❌ **NO fallback logic** except for legitimate architectural patterns (Vault→Env, JWT→Headers for dev/test)
- ❌ **NO default project creation or fallback** - project_id must be explicit and required
- ❌ **NO mock/stub implementations** - only real, functional code
- ❌ **NO placeholder values** - all values must be real and functional
- ❌ **NO string conversion fallbacks** - raise TypeError for unsupported types
- ❌ **NO generic error messages** - preserve original errors with full context

**ALLOWED:**

- ✅ **TODO/FIXME comments** - better explicit TODO than hidden fallback/mock
- ✅ **Unimplemented functions** - throw NotImplementedError with clear message

**REQUIRED IN ALL CODE:**

- ✅ **Real implementations only** - no temporary or partial solutions with fallbacks
- ✅ **Explicit error handling** - fail fast with clear error messages
- ✅ **Type safety** - strict type checking, no 'any' types
- ✅ **Project isolation** - project_id required, no defaults

**If the argument equals "frontend" or includes "frontend/":**

```
Use the Task tool with parameters:
- subagent_type: "tech-frontend"
- description: "Fix CodeRabbit frontend issues"
- prompt: "INTELLIGENT TRIAGE REQUIRED: Balance MVP pragmatism with code quality. Use the severity matrix to decide which issues to fix vs skip.

🚨 CRITICAL (FIX IMMEDIATELY): Security vulnerabilities, data leaks, fallbacks/mocks/stubs, critical bugs
⚠️ HIGH (SHOULD FIX): Performance issues, reliability problems, architecture violations (unless MVP constraint)
📋 MEDIUM (JUDGMENT CALL): Code quality, type safety, best practices (fix if quick win, defer if complex)
ℹ️ LOW (SKIP): Style issues, formatting, naming preferences (formatters handle these)
🤔 CONTEXT-DEPENDENT: Use engineering judgment - skip outdated suggestions, over-engineering, false positives

CRITICAL: NO FALLBACKS, MOCKS, OR STUBS IN PRODUCTION CODE. Project_id must be explicit and required. TODO/FIXME allowed for unimplemented functionality.

Analyze CodeRabbit output: [insert the CodeRabbit analysis output]

For each issue:
1. Categorize severity (CRITICAL/HIGH/MEDIUM/LOW/CONTEXT-DEPENDENT)
2. Make fix/skip/defer decision based on matrix
3. Document deferred HIGH/MEDIUM issues with TODO comments
4. Apply fixes following React 19+, TypeScript strict, accessibility standards

Provide STRUCTURED TRIAGE REPORT with fix status for each issue."
```

**If the argument equals "backend" or includes "backend/":**

```
Use the Task tool with parameters:
- subagent_type: "tech-backend"
- description: "Fix CodeRabbit backend issues"
- prompt: "INTELLIGENT TRIAGE REQUIRED: Balance MVP pragmatism with code quality. Use the severity matrix to decide which issues to fix vs skip.

🚨 CRITICAL (FIX IMMEDIATELY): Security vulnerabilities, data leaks, fallbacks/mocks/stubs, critical bugs, missing project_id isolation, cross-project data access
⚠️ HIGH (SHOULD FIX): Performance issues, reliability problems, architecture violations (unless MVP constraint), missing language isolation
📋 MEDIUM (JUDGMENT CALL): Code quality, type safety, best practices (fix if quick win, defer if complex)
ℹ️ LOW (SKIP): Style issues, formatting, naming preferences (formatters handle these)
🤔 CONTEXT-DEPENDENT: Use engineering judgment - skip outdated suggestions, over-engineering, false positives

CRITICAL ARCHITECTURE REQUIREMENTS (from specs.md & architecture.md):
- NO FALLBACKS, MOCKS, OR STUBS in production code
- NO default project fallbacks - project_id ALWAYS required (UUID, never Optional)
- STRICT project_id isolation in ALL database queries (project-scoped data access)
- Language isolation: project language determined via LLM, applied to all documents/interactions
- FastAPI 0.116.2+ with async I/O, PostgreSQL 18+, Redis 6.4.0+, Qdrant 1.15.4+
- Schema-driven: Pydantic as single source of truth (validation + API contracts + docs)
- SQLAlchemy models as source of truth (Alembic autogenerate migrations)
- OAuth2 (Twitter only in MVP), SSE streaming, OpenTelemetry tracing
- CrewAI 0.186.1+ for multi-agent orchestration, Google ADK support for future agent scaling
- TODO/FIXME allowed for unimplemented functionality

Analyze CodeRabbit output: [insert the CodeRabbit analysis output]

For each issue:
1. Categorize severity (CRITICAL/HIGH/MEDIUM/LOW/CONTEXT-DEPENDENT)
2. Make fix/skip/defer decision based on matrix
3. Document deferred HIGH/MEDIUM issues with TODO comments
4. Apply fixes following architectural principles, security requirements, project+language isolation
5. Verify minimum component versions (FastAPI 0.116.2+, PostgreSQL 18, etc.)

Provide STRUCTURED TRIAGE REPORT with fix status for each issue."
```

**If the argument equals "all" or is omitted:**

```
1. Review the CodeRabbit output and identify the types of files with issues
2. If there are frontend issues, launch the tech-frontend agent
3. If there are backend issues, launch the tech-backend agent
4. When required, run both agents in parallel
```

**Step 3: Issue Triage and Decision Making**

Before applying any fixes, the agent must **INTELLIGENTLY TRIAGE** all CodeRabbit issues using the decision matrix below.

**PHILOSOPHY: Flexible triage with project benefit focus. LLM decides what helps the project most.**

### 🚨 CRITICAL SEVERITY - MUST FIX IMMEDIATELY (Security/Data Loss)

Apply these fixes **WITHOUT QUESTION**:

1. **Security Vulnerabilities:**

   - SQL injection, XSS, CSRF vulnerabilities
   - Hardcoded secrets (API keys, passwords, tokens)
   - Authentication/authorization bypass
   - Timing attacks in security-critical code
   - Missing input validation on user data

2. **Data Leaks:**

   - Missing `project_id` in project-scoped queries
   - Missing `language` filter in vector search (Qdrant requires project_id + language)
   - Cross-project data access
   - Cross-language data access (project language isolation violated)
   - Sensitive data in logs (passwords, PII, tokens)
   - Unvalidated project context
   - Client-side constructed filters (must be server-side only)

3. **Zero-Tolerance Violations:**

   - Fallback to default project (ALWAYS FIX)
   - Mock/stub implementations in production code
   - String conversion fallbacks that hide errors
   - Placeholder API keys or secrets

4. **Critical Bugs:**
   - Race conditions causing data corruption
   - Unhandled exceptions in critical paths
   - Resource leaks (unclosed DB connections, file handles)
   - Infinite loops without proper exit conditions

**ACTION: FIX IMMEDIATELY - These issues block production deployment.**

---

### ⚠️ HIGH SEVERITY - SHOULD FIX (Reliability/Performance)

**LLM DECISION REQUIRED** - Fix if it clearly benefits the project:

1. **Performance Issues:**

   - N+1 query problems
   - Missing database indexes on project_id
   - Memory leaks in long-running processes
   - Inefficient algorithms causing noticeable slowdown

2. **Reliability Issues:**

   - Missing error handling in critical flows
   - Improper transaction management
   - Missing rollback on errors
   - Edge cases not handled

3. **Architecture Violations:**
   - Breaking project isolation patterns
   - Bypassing repository pattern (direct DB access)
   - Violating DRY principles in critical code
   - Missing abstraction layers

**DECISION CRITERIA:**

- **FIX IF**: Clear benefit to code quality, maintainability, or performance
- **DEFER IF**: Minor issue, current approach works fine, or refactoring would be extensive
- **SKIP IF**: Suggestion is outdated or doesn't fit project context

---

### 📋 MEDIUM SEVERITY - JUDGMENT CALL (Code Quality)

**LLM USES ENGINEERING JUDGMENT** based on project context:

1. **Code Quality:**

   - Minor refactoring suggestions (extract method, rename)
   - Complex logic that could be simplified
   - Missing unit tests (if not blocking deployment)
   - Code duplication concerns

2. **Type Safety:**

   - Missing type hints (Python) or type annotations (TypeScript)
   - Using `Any` type when specific type is known
   - Type assertions that could be type guards

3. **Best Practices:**
   - Not using async/await where beneficial
   - Inconsistent error handling patterns
   - Magic numbers that should be constants
   - Missing validation

**DECISION CRITERIA:**

- **FIX IF**: Quick win (<5 min) OR significantly improves code clarity
- **DEFER IF**: Current code works fine and change adds complexity
- **SKIP IF**: Suggestion is outdated or doesn't fit current architecture

---

### ℹ️ LOW SEVERITY - PREFERENCE-BASED (Style/Personal)

**LLM DECIDES based on project needs and current state:**

1. **Style Issues:**

   - **SKIP**: Formatting inconsistencies (formatters handle this)
   - **SKIP**: Import ordering (tools handle this)
   - **CONSIDER**: Comment formatting (if improves documentation)
   - **SKIP**: Line length (unless truly unreadable)

2. **Naming Conventions:**

   - **CONSIDER**: Variable naming (if truly confusing)
   - **SKIP**: Function naming preferences (follow existing patterns)
   - **SKIP**: Style preferences (camelCase vs snakeCase)

3. **Subjective Improvements:**
   - **SKIP**: "Could use more descriptive name" (if current name is clear)
   - **SKIP**: "Consider using ternary operator" (preference)
   - **SKIP**: "This could be a one-liner" (preference unless more readable)

**DECISION LOGIC:**

- **SKIP**: Most style/preference issues
- **CONSIDER**: Only if it significantly improves readability
- **FIX**: Rarely, only if current code is genuinely problematic

---

### 🤔 CONTEXT-DEPENDENT - PROJECT BENEFIT ANALYSIS

**LLM EVALUATES each suggestion individually:**

**1. Outdated Suggestions:**

- **SKIP**: CodeRabbit suggests older pattern but code uses modern approach
- **EXAMPLE**: Suggests class components when using React 19+ hooks
- **REASONING**: Tool may not know latest best practices

**2. MVP vs Ideal Code:**

- **DECIDE CASE-BY-CASE**: Balance code quality with development velocity
- **FIX IF**: Quick win with clear benefit
- **DEFER IF**: Extensive refactoring for minor improvement
- **SKIP IF**: Current approach works fine

**3. False Positives:**

- **SKIP**: CodeRabbit misunderstands context
- **SKIP**: Flags legitimate architectural pattern as anti-pattern
- **SKIP**: Suggests removing code that's actually needed
- **REASONING**: LLM understands codebase better than generic suggestions

**4. Over-Engineering:**

- **SKIP**: Suggestion adds complexity without clear benefit
- **SKIP**: "Extract this 3-line function" when only used once
- **SKIP**: "Add factory pattern" for simple object creation
- **REASONING**: Simpler is often better

**5. Formatters and Linters:**

- **SKIP**: Anything that formatters (Biome/Black/ESLint) handle automatically
- **SKIP**: Import sorting, basic formatting, style issues
- **FOCUS**: Substantive code improvements only

---

### 📝 DOCUMENTATION REQUIREMENTS

When **SKIPPING** or **DEFERRING** an issue, document the decision:

```python
# CodeRabbit Triage Decision: DEFERRED
# Issue: Extract method for complex logic (Medium Severity)
# Reasoning: MVP timeline priority - works correctly, can refactor post-launch
# TODO: Refactor processUserData() after MVP (split into smaller functions)
async def processUserData(data: dict) -> ProcessedData:
    # Current implementation...
```

**ALWAYS document when skipping:**

- ⚠️ HIGH SEVERITY issues (must have strong justification)
- 📋 MEDIUM SEVERITY issues (explain MVP trade-off)

**No documentation needed when skipping:**

- ℹ️ LOW SEVERITY (style/preference issues)

---

**Step 4: Specialized Agent Execution**

After triage, the activated agent must:

1. **Apply CRITICAL fixes immediately** - no discussion needed
2. **Evaluate HIGH/MEDIUM issues** - use decision matrix above
3. **Skip LOW severity issues** - focus on substance
4. **Document deferred issues** - with clear reasoning
5. **Maintain consistency** - follow existing patterns and conventions
6. **Preserve functionality** - ensure fixes don't break anything
7. **Follow project standards** - comply with CLAUDE.md principles
8. **Test critical changes** - validate security/data fixes

## Key Principles for Agents

- **No placeholders or hardcoded values** - implement real, functional code
- **Follow DRY principles** - extract reusable code where suggested
- **Maintain accessibility** - implement keyboard navigation and ARIA labels as recommended
- **Use proper error handling** - replace console.error with standardized error handlers
- **Preserve project isolation architecture** - ensure all changes respect project isolation
- **Follow security best practices** - implement proper validation and sanitization

## Critical Requirements

- **Always provide the exact `subagent_type`** in the Task tool
- **Confirm the agent activation** - the agent must introduce itself when it starts
- **Pass the full CodeRabbit output** into the agent prompt
- **Retry with corrected parameters** if agent activation fails

## Expected Output from Specialized Agents

The agent must provide a **STRUCTURED TRIAGE REPORT**:

### 1. **Issue Triage Summary**

Categorize all CodeRabbit issues by severity:

```
🚨 CRITICAL (MUST FIX): X issues
⚠️ HIGH (SHOULD FIX): X issues
📋 MEDIUM (CONSIDER): X issues
ℹ️ LOW (SKIP): X issues
🤔 CONTEXT-DEPENDENT: X issues
```

### 2. **Fix Status Report**

For each issue, document the decision:

```
Issue #1: [Description]
Severity: CRITICAL
Decision: ✅ FIXED
Location: file.py:123
Reasoning: SQL injection vulnerability - immediate fix required

Issue #2: [Description]
Severity: MEDIUM
Decision: ⏸️ DEFERRED
Location: file.py:456
Reasoning: Minor refactoring - MVP timeline priority, added TODO
Documentation: Added comment with post-MVP action item

Issue #3: [Description]
Severity: LOW
Decision: ⏭️ SKIPPED
Location: file.py:789
Reasoning: Code style - handled by formatters
```

### 3. **Changes Summary**

Detailed list of implemented fixes:

- Files modified
- Critical security fixes applied
- Performance improvements made
- Documentation added for deferred items

### 4. **Deferred Items Log**

List all deferred HIGH/MEDIUM severity issues with:

- Issue description
- Location
- Reasoning for deferral
- TODO comment added in code

### 5. **Quality Verification**

- ✅ All CRITICAL issues resolved
- ✅ Security vulnerabilities fixed
- ✅ Project isolation maintained
- ✅ Type checks passing
- ✅ Tests passing (if applicable)

### 6. **Recommendations**

- Priority issues for post-MVP
- Technical debt introduced (if any)
- Suggested follow-up tasks

## Command Execution Flow

1. **Run the CodeRabbit analysis** with the provided scope
2. **Determine the analysis type** based on the argument
3. **Activate the matching agent** through the Task tool with the exact subagent_type
4. **Pass the CodeRabbit output** to the agent for fixes
5. **Collect the agent report** detailing the applied changes
6. **Verify quality** - run linters/type-checks when necessary

## Usage Examples

- `/dev:coderabbit frontend` - full analysis and remediation of the frontend code by the tech-frontend agent
- `/dev:coderabbit backend` - full analysis and remediation of the backend code by the tech-backend agent
- `/dev:coderabbit frontend/src/components` - focused analysis of specific frontend components
- `/dev:coderabbit backend/app/services` - focused analysis of specific backend services
- `/dev:coderabbit` - full project analysis with automatic agent selection

**Important:** Always verify that the agent actually activated—the agent must introduce itself at the start of its response!
