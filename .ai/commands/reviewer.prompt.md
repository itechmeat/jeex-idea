---
allowed-tools: Bash(git:*), Bash(cat:*), Bash(grep:*), Bash(find:*), Task
description: Run comprehensive code review for story completion, architecture compliance, and technical standards
argument-hint: [custom-review-focus] (optional specific review focus)
---

# Story Code Review Command

Run comprehensive code review of current git changes to verify story completion, architecture compliance, technical standards adherence, and code quality.

## Review Scope

This command reviews code changes against:

1. **Story Requirements**: Check implementation against story tasks and acceptance criteria
2. **Architecture Compliance**: Verify alignment with `docs/architecture.md` decisions
3. **Tech Stack Compliance**: Validate against `docs/specs.md` specifications
4. **Project Isolation**: Enforce strict `project_id` scoping at all layers
5. **Security Standards**: Check authentication, authorization, data protection
6. **Code Quality**: Detect anti-patterns, fallbacks, mocks, hardcoded values
7. **Best Practices**: Validate async patterns, error handling, testing coverage

## Process

1. **Change Detection Phase**: Get list of changed files from git
2. **Story Identification Phase**: Determine which story is being implemented
3. **Context Loading Phase**: Load story requirements and architectural docs
4. **Agent Activation Phase**: Activate tech-reviewer agent with full context
5. **Review Phase**: Agent performs comprehensive multi-phase review
6. **Reporting Phase**: Generate structured review report with blocking/non-blocking issues
7. **Report File Creation**: Save review report to `reviews/REVIEW_REPORT.md`

## Instructions

**Step 1: Detect Git Changes**

Get the list of all changed files in the current branch:

```bash
echo "=== Git Status ==="
git status

echo ""
echo "=== Changed Files ==="
git diff --name-status origin/main...HEAD 2>/dev/null || git diff --name-status --cached

echo ""
echo "=== Staged Changes Summary ==="
git diff --cached --stat

echo ""
echo "=== Unstaged Changes Summary ==="
git diff --stat
```

**Step 2: Identify Current Story**

Determine which story is being implemented by checking:

```bash
# Check if we're in a story branch
CURRENT_BRANCH=$(git branch --show-current)
echo "Current Branch: $CURRENT_BRANCH"

# Look for story references in commit messages
echo ""
echo "=== Recent Commits ==="
git log --oneline -5

# Check stories directory for context
echo ""
echo "=== Available Stories ==="
ls -1 stories/ | grep -v "plan.md" | grep -v "backlog.md" | head -10
```

**Step 3: Load Story Context (if story identified)**

If a specific story folder is identified:

```bash
STORY_SLUG="<detected-story-slug>"

# Load story requirements
echo "=== Story Requirements ==="
cat stories/$STORY_SLUG/requirements.md

echo ""
echo "=== Story Tasks ==="
cat stories/$STORY_SLUG/tasks.md

echo ""
echo "=== Story Design ==="
cat stories/$STORY_SLUG/design.md
```

**Step 4: Activate Reviewer Agent**

Activate the `tech-reviewer` agent with full context:

```text
Use the Task tool with parameters:
- subagent_type: "tech-reviewer"
- description: "Review code changes for story completion and compliance"
- prompt: "Perform comprehensive code review of the current git changes.

CONTEXT:
- Current Branch: {{current_branch}}
- Changed Files: {{list_of_changed_files}}
- Story Being Implemented: {{story_name}} (if identified)
- Custom Focus: {{args}} (if provided by user)

REVIEW REQUIREMENTS:

1. **Story Completion Verification**
   - Load story requirements from: stories/{{story_slug}}/requirements.md
   - Load story tasks from: stories/{{story_slug}}/tasks.md
   - Verify each task's acceptance criteria is met
   - Check that all requirements are addressed
   - Confirm quality gates from tasks.md are satisfied

2. **Architecture Compliance Check**
   - Validate against docs/architecture.md decisions
   - Check component selection and integration patterns
   - Verify API contracts match specifications
   - Ensure proper layer separation
   - Confirm observability instrumentation present

3. **Tech Stack Compliance Validation**
   - Check against docs/specs.md component versions
   - Verify minimum version requirements met
   - Validate technology choices (no prohibited libraries)
   - Ensure language detection via LLM only (NO langdetect/langid/fastText)
   - Confirm OAuth2 implementation (Twitter only in MVP)

4. **Project Isolation Enforcement** (CRITICAL)
   - Verify ALL database queries filter by project_id
   - Check Qdrant searches include project_id + language filters
   - Validate Redis keys use project_id namespace
   - Ensure API endpoints validate project access
   - Confirm no cross-project data leakage

5. **Security & Best Practices Review**
   - Check for hardcoded credentials/secrets
   - Verify input validation (Pydantic models)
   - Review error handling patterns
   - Validate async patterns (no sync I/O in async context)
   - Check for fallback logic (PROHIBITED)

6. **Code Quality Assessment**
   - Review type hints and documentation
   - Check for TODOs/FIXMEs with tracking
   - Validate test coverage
   - Assess maintainability

DELIVERABLE:

**CRITICAL: Save review report to file reviews/REVIEW_REPORT.md**

The report MUST be written in:
- **English** by default
- **User's language** if specified in custom focus argument (e.g., "review in Russian", "отчет на русском")

Provide structured review report following the format in your agent description, including:
- Story completion status
- Architecture compliance assessment
- Tech stack validation results
- Project isolation verification
- Security review findings
- Code quality evaluation
- List of BLOCKING issues (must fix before merge)
- List of recommended improvements (non-blocking)
- Overall pass/fail status with next steps

After generating the complete review, save it to reviews/REVIEW_REPORT.md file. Create the reviews/ directory if it doesn't exist.
"
```

**Step 5: Review Execution**

The tech-reviewer agent will:

1. Read all changed files and analyze modifications
2. Load story requirements and check implementation completeness
3. Validate architecture and tech stack compliance
4. Perform deep project isolation audit
5. Review security patterns and best practices
6. Generate comprehensive structured report

## Expected Output Format

The reviewer agent will produce a structured report and save it to **`reviews/REVIEW_REPORT.md`**:

```markdown
# Code Review: [Story Name]

## ✅ Story Completion: [COMPLETE | INCOMPLETE | PARTIAL]

[Detailed requirements coverage]

## ✅ Architecture Compliance: [PASS | FAIL | WARNING]

[Architecture alignment details]

## ✅ Tech Stack Compliance: [PASS | FAIL | WARNING]

[Specs validation results]

## ✅ Project Isolation: [PASS | FAIL | CRITICAL]

[Isolation audit findings]

## ✅ Security Review: [PASS | FAIL | WARNING]

[Security assessment]

## ✅ Code Quality: [PASS | FAIL | WARNING]

[Quality evaluation]

## 📋 Required Changes (BLOCKING)

[List of critical issues with fix examples]

## ⚠️ Recommended Improvements (NON-BLOCKING)

[List of suggestions]

## 📊 Review Summary

[Overall status and next steps]
```

**Report Location:** `reviews/REVIEW_REPORT.md`  
**Report Language:** English by default, or user-specified language from argument

## Review Focus Options

You can customize the review focus with optional argument:

- `/dev:reviewer "focus on security"` - emphasize security audit
- `/dev:reviewer "check project isolation only"` - focus on isolation
- `/dev:reviewer "verify API contracts"` - focus on API compliance
- `/dev:reviewer "quick review"` - abbreviated review for minor changes
- `/dev:reviewer "review in Russian"` - full review with report in Russian
- `/dev:reviewer "отчет на русском"` - full review with report in Russian
- `/dev:reviewer` - full comprehensive review (default, English report)

## Critical Requirements

- **Always provide exact `subagent_type: "tech-reviewer"`** in Task tool
- **Pass complete git change context** to the agent
- **Include story slug** if identified from branch/commits
- **Provide custom focus** from user argument if specified
- **Wait for complete review** - do not interrupt the agent

## Agent Selection Logic

This command ALWAYS activates the `tech-reviewer` agent:

```text
Changed files detected → Load story context → Activate tech-reviewer → Generate report
```

No other agents are activated by this command. If fixes are needed, the review report will recommend which agents to use.

## Command Execution Flow

1. **Detect changes** - run git commands to list modified files
2. **Identify story** - determine which story is being implemented
3. **Load context** - read story requirements and architectural docs
4. **Activate reviewer** - launch tech-reviewer agent with full context
5. **Wait for review** - agent performs comprehensive analysis
6. **Present report** - display structured review findings
7. **Provide next steps** - guide user on required actions

## Usage Examples

- `/dev:reviewer` - comprehensive review, saves to reviews/REVIEW_REPORT.md (English)
- `/dev:reviewer "focus on security and isolation"` - security-focused review (English)
- `/dev:reviewer "quick check before commit"` - fast review (English)
- `/dev:reviewer "verify story XYZ is complete"` - story completion check (English)
- `/dev:reviewer "review in Russian"` - comprehensive review with Russian report
- `/dev:reviewer "отчет на русском языке"` - comprehensive review with Russian report

## Post-Review Actions

Based on review outcome:

- **BLOCKED status**: Fix critical issues before merge
- **WARNING status**: Consider recommended improvements
- **PASS status**: Ready to merge (subject to team approval)

**Next Commands After Review:**

- If issues found: Use `/dev:develop "fix review issues"` to implement fixes
- If tests needed: Use `/dev:test` to run comprehensive tests
- If ready: Proceed with git commit and push

## Important Notes

- This command is **read-only** - it only reviews, does not modify code
- The reviewer agent will **not fix issues** - it only identifies them
- Review report is **saved to reviews/REVIEW_REPORT.md**
- Report language: **English by default**, or specify in argument (e.g., "review in Russian")
- Use appropriate specialized agents to implement fixes after review
- Always run tests after addressing review issues
- Re-run review after fixes to verify resolution

**Remember:** The reviewer is your quality gatekeeper - take its findings seriously!
