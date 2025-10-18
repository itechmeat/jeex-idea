---
allowed-tools: Bash(make:*), Bash(docker-compose:*), Bash(pnpm:*), Task
description: Run comprehensive testing - E2E tests and backend tests with automatic issue fixing
argument-hint: [clarifying-prompt] (optional custom prompt for agents)
---

# Comprehensive Testing Command

Run complete testing suite including E2E tests (Playwright) and backend tests (pytest), then automatically fix any identified issues using appropriate specialized agents.

## Agent Selection Logic

**IMMEDIATE TEST SKIPPING FOR UNIMPLEMENTED FEATURES:**

- If tests fail for features with TODO/FIXME/NotImplementedError in source code → **SKIP TESTS IMMEDIATELY with TODO references**
- **DO NOT implement missing features** during test fixing - only skip tests with clear documentation
- **CHECK source code first** before attempting any fixes

**Step 1: Test Analysis and Agent Selection**

- If E2E tests fail → activate appropriate agents based on failure type
- If backend tests fail → activate appropriate agents based on failure type
- If both fail → activate multiple agents in parallel

## Process

1. **E2E Testing Phase**: Execute Playwright tests in `tests/e2e/` directory
2. **Backend Testing Phase**: Execute pytest tests in `backend/tests/` directory
3. **Agent Activation**: Based on test results, activate appropriate specialized agents
4. **Fix Phase**: Let specialized agents implement fixes for identified issues
5. **Verification**: Ensure all changes maintain code quality and functionality

## Agent Selection by Issue Type

**E2E Test Failures:**

- Frontend component issues → activate `tech-frontend` agent
- API endpoint issues → activate `tech-python` agent
- Integration/flow issues → activate `tech-qa` agent

**Backend Test Failures:**

- API/business logic errors → activate `tech-python` agent
- Database/model issues → activate `tech-python` agent
- Authentication/security issues → activate `tech-python` agent
- Project isolation issues → activate `tech-python` agent
- Performance issues → activate `tech-qa` agent

**Test Infrastructure Issues:**

- Flaky tests → activate `tech-qa` agent
- Coverage gaps → activate `tech-qa` agent
- Test data/setup issues → activate `tech-qa` agent

## Instructions

**Step 1: Run Comprehensive Test Suite**
Execute all tests using the integrated Makefile command with proper test isolation:

```bash
make test
```

This will automatically:

1. Run E2E tests (Playwright) - 100% pass rate
2. Run backend batch tests (excluding isolated tests) - runs together without pollution
3. Run isolated tests one by one - ensures problematic tests pass individually

**Alternative Commands:**

- `make test-e2e` - Run only E2E tests
- `make test-batch` - Run only batch backend tests (non-isolated)
- `make test-isolated` - Run only isolated tests (one by one)
- `make test-all` - Run ALL tests in batch mode (may have failures due to test pollution)

**Step 2.5: Handle Unimplemented Feature Tests (CRITICAL)**

**IMMEDIATE SKIPPING FOR UNIMPLEMENTED FEATURES:**

If tests fail for features that are **explicitly marked as not implemented** with TODO comments in the code:

1. **IDENTIFY TODO-RELATED FAILURES:** Check if failed tests correspond to features with `TODO`, `FIXME`, or `NotImplementedError` in the source code
2. **SKIP TESTS IMMEDIATELY:** Add `@pytest.mark.skip(reason="Feature not implemented - TODO in source code")` to the test
3. **DOCUMENT SKIPPING:** Add clear TODO comment in the test file explaining why it's skipped
4. **NO CODE FIXES REQUIRED:** Do NOT attempt to implement the feature - only skip the test

**Automatic TODO Detection Pattern:**

```bash
# For each failed test, check source code:
grep -r "TODO\|FIXME\|NotImplementedError" backend/app --include="*.py" | grep -i "$(test_feature_name)"

# If TODO found, skip the test immediately:
pytest.mark.skip(reason="Feature not implemented - TODO exists in source code")
```

**Examples of TODO-Related Test Skipping:**

- Test fails for `/projects/{id}/step1` → Check if `projects.py` has `TODO: Implement actual agent orchestration` → Skip test
- Test fails for agent integration → Check if agent files have `NotImplementedError` → Skip test
- Test fails for export functionality → Check if `export_project_documents` has `TODO` → Skip test

**MANDATORY SKIPPING RULES:**

- **DO NOT** implement missing features during test fixing
- **DO NOT** modify production code to make tests pass
- **ALWAYS** skip tests with clear TODO references
- **MUST** document why each test is skipped
- **VERIFY** skipping doesn't hide actually implemented bugs

**Step 2: Analyze Test Results**
Carefully review the test output to identify:

1. **Failed tests and their locations**
2. **Error types and root causes**
3. **Affected components and services**

**Step 3: Determine Agent Activation**

Analyze test output from `make test` command:

**Status Interpretation:**

- All tests pass → No agent activation needed, report success
- E2E tests fail → Activate appropriate agents based on failure type
- Backend batch tests fail → Activate appropriate agents based on failure type
- Isolated tests fail → Activate tech-qa agent (test infrastructure issue)
- Multiple test categories fail → Activate agents in parallel

**Pattern Matching for Agent Selection:**

Use regex patterns to identify failure types and select appropriate agents:

**E2E Test Failure Patterns (`__PW_STATUS:1`):**

```text
Frontend Component Issues → tech-frontend:
- Error: Component .* (failed to render|not found)
- TypeError.*\.tsx
- React.*Hook.*error
- State.*undefined
- props\..*is not a function

API Endpoint Issues → tech-python:
- Error:.*(/api/v1/|fetch.*failed)
- Status.*[45]\d{2}
- Network.*error.*localhost:\d+/api
- POST|GET|PUT|DELETE.*failed

Integration/Flow Issues → tech-qa:
- Timeout.*waiting for
- expect\(.*\)\.toBe.*failed
- Screenshot.*mismatch
- Navigation.*failed
```

**Backend Test Failure Patterns (`__PY_STATUS:1`):**

```text
API/Business Logic → tech-python:
- AssertionError.*test_.*api
- /api/v1/.*returned.*[45]\d{2}
- ValidationError
- Pydantic.*validation error

Database/Model Issues → tech-python:
- sqlalchemy\..*Error
- IntegrityError
- UNIQUE constraint failed
- ForeignKeyViolation

Authentication/Security → tech-python:
- (project_id|authentication|authorization).*error
- JWT.*invalid
- Unauthorized|Forbidden
- RBAC.*denied

Project Isolation → tech-python:
- test_.*project.*failed
- Cross-project.*leak
- isolation.*violated

Performance Issues → tech-qa:
- test_.*performance.*failed
- Timeout after \d+ seconds
- Memory.*exceeded
```

**Automated Agent Selection Algorithm:**

```python
# Pseudo-code for agent selection
def select_agents(pw_status, py_status, test_output):
    agents_to_activate = []

    # Parse E2E test failures
    if pw_status == 1:
        if re.search(r'(Component .* failed|React.*error|props\..*function)', test_output):
            agents_to_activate.append('tech-frontend')
        if re.search(r'(/api/v1/|Status.*[45]\d{2}|fetch.*failed)', test_output):
            agents_to_activate.append('tech-python')
        if re.search(r'(Timeout.*waiting|expect.*toBe.*failed)', test_output):
            agents_to_activate.append('tech-qa')

    # Parse backend test failures
    if py_status == 1:
        if re.search(r'(AssertionError|ValidationError|api.*[45]\d{2})', test_output):
            agents_to_activate.append('tech-python')
        if re.search(r'(project_id|authentication|authorization|JWT)', test_output):
            agents_to_activate.append('tech-python')
        if re.search(r'(performance.*failed|Timeout after|Memory.*exceeded)', test_output):
            agents_to_activate.append('tech-qa')

    # Infrastructure errors
    if pw_status > 1 or py_status > 1:
        agents_to_activate.append('tech-qa')

    return list(set(agents_to_activate))  # Remove duplicates
```

**Decision Matrix:**

| Test Category  | Error Pattern                 | Agent(s) to Activate        |
| -------------- | ----------------------------- | --------------------------- |
| E2E Tests      | Component/React errors        | `tech-frontend`             |
| E2E Tests      | API endpoint errors           | `tech-python`               |
| E2E Tests      | Timeout/assertion errors      | `tech-qa`                   |
| Backend Batch  | API/validation errors         | `tech-python`               |
| Backend Batch  | Authentication/project errors | `tech-python`               |
| Backend Batch  | Database/model errors         | `tech-python`               |
| Isolated Tests | Test infrastructure issues    | `tech-qa`                   |
| Multiple       | Multiple patterns             | Multiple agents in parallel |

**Test Isolation Strategy:**

The `make test` command implements a three-stage strategy:

1. **E2E Tests (Playwright)** - Run first, 100% pass rate expected
2. **Backend Batch Tests** - Run tests marked with `-m "not isolated"` together
3. **Isolated Tests** - Run tests marked with `@pytest.mark.isolated` one by one

This ensures that tests requiring isolation don't pollute shared state in batch mode.

**Step 4: Agent Selection and Activation**
Based on test results, activate appropriate agents:

**For frontend/E2E issues:**

```text
Use the Task tool with parameters:
- subagent_type: "tech-frontend"
- description: "Fix E2E test failures"
- prompt: "Fix the following E2E test failures: [insert E2E test errors]. Resolve UI component issues, form validation problems, navigation errors, or state management issues. Follow React 19+, TypeScript strict mode, and accessibility standards. Ensure all fixes maintain project isolation architecture and security requirements."
```

**For backend test failures:**

```text
Use the Task tool with parameters:
- subagent_type: "tech-python"
- description: "Fix backend test failures"
- prompt: "Fix the following backend test failures: [insert backend test errors]. Resolve API endpoint issues, business logic errors, database problems, authentication failures, or project isolation violations. Follow FastAPI best practices, async patterns, security requirements, and project isolation architecture principles."
```

**For test infrastructure issues:**

```text
Use the Task tool with parameters:
- subagent_type: "tech-qa"
- description: "Fix test infrastructure issues"
- prompt: "Fix the following test infrastructure issues: [insert test errors]. Resolve flaky test problems, coverage gaps, test data issues, or configuration problems. Follow testing best practices and maintain test quality standards using Playwright, pytest, and appropriate mocking strategies."
```

**For multiple issue types:**
Launch agents in parallel for each issue type identified.

**Step 5: Specialized Agent Execution**

The activated agent must:

1. **Analyze each failure** - understand the root cause and error context
2. **Implement targeted fixes** - address the specific test failures
3. **Maintain test coverage** - ensure fixes don't break existing tests
4. **Follow project standards** - comply with CLAUDE.md requirements
5. **Verify fixes** - re-run affected tests to confirm resolution

## Key Principles for Agents

- **Fix root causes** - don't just suppress symptoms
- **Maintain test coverage** - ensure comprehensive testing after fixes
- **Follow project isolation architecture** - ensure all changes respect project isolation
- **Use appropriate tools** - leverage configured testing frameworks and utilities
- **Document fixes** - provide clear explanations of changes made

## Critical Requirements

- **Always provide the exact `subagent_type`** in the Task tool
- **Confirm agent activation** - the agent must introduce itself when it starts
- **Pass specific test failure details** - include exact error messages and stack traces
- **Retry with corrected parameters** if agent activation fails

## Expected Output from Specialized Agents

- **Failure Analysis**: Summary of test failures and their root causes
- **Fix Status**: Status of each failure (fixed/skipped/needs-review)
- **Changes Summary**: Detailed list of files modified and fixes applied
- **Test Results**: Output from re-running affected tests
- **Quality Confirmation**: Assurance that fixes don't introduce new issues

## Command Execution Flow

1. **Run E2E tests** using Playwright
2. **Run backend tests** using pytest
3. **Analyze failures** to identify issue types and affected areas
4. **Activate matching agents** based on failure categorization
5. **Pass specific failure details** to each agent
6. **Collect agent reports** detailing applied changes
7. **Verify fixes** - re-run tests to confirm resolution

## Usage Examples

- `/dev:test` - run comprehensive testing and fix all found issues
- `/dev:test "focus on authentication tests"` - run tests with specific focus
- `/dev:test "prioritize project isolation tests"` - run tests with security emphasis

**Important:** Always verify that agents actually activated - each agent must introduce itself at the start of its response!
