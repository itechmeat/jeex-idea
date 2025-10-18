---
allowed-tools: Task
description: Story planning and progress tracking - create stories, manage tasks, track completion
argument-hint: <instruction> (required: what to plan, create, or update)
---

# Story Planning Command

Manage story-based planning using EARS-compliant requirements and actionable task breakdowns through the tech-pm agent.

## Command Purpose

This command invokes the `tech-pm` agent to:

1. **Create initial story plans** - Generate `stories/plan.md` with prioritized story list
2. **Create detailed stories** - Build complete story folders with design, requirements, and tasks
3. **Track progress** - Update task completion status and story lifecycle
4. **Manage backlog** - Move completed stories to historical record

## Usage Patterns

```bash
# Create initial plan from project requirements
/plan "Create implementation plan based on docs/architecture.md and docs/specs.md"

# Create detailed story for specific feature
/plan "Create detailed story for user authentication with OAuth2"

# Update progress after development work
/plan "Mark tasks 1.1, 1.2 as complete in story user-authentication"

# Move completed story to backlog
/plan "Move user-authentication story to backlog with completion summary"

# Review and update existing story
/plan "Update requirements for document-versioning story based on new constraints"
```

## Agent Activation

**Invoke tech-pm agent with user's instruction:**

```yaml
Task:
  - subagent_type: "tech-pm"
  - description: "Story planning and management"
  - prompt: "[User's instruction verbatim]

      Context:
      - Project documentation: docs/architecture.md, docs/specs.md, docs/about.md
      - Story structure: stories/plan.md, stories/backlog.md, stories/<slug>/
      - Requirements standard: EARS (https://alistairmavin.com/ears/)

      Determine the appropriate action based on the instruction and execute accordingly."
```

## Agent Modes (Automatically Selected)

The tech-pm agent will determine which mode to use based on the instruction:

### Planning Mode

**When to use:** User requests initial story planning or story list creation

**Agent creates:**

- `stories/plan.md` with story list ordered by dependencies
- Brief descriptions with scope, dependencies, complexity
- Flat structure (no priority grouping, ordered by dependencies only)

**Triggers:**

- "create plan", "generate story list", "plan implementation"
- "list stories for", "break down project into stories"

### Story Creation Mode

**When to use:** User requests detailed story documentation

**Agent creates:**

- `stories/<slug>/design.md` - Architecture, diagrams, components
- `stories/<slug>/requirements.md` - EARS-compliant requirements
- `stories/<slug>/tasks.md` - Actionable task checklist

**Triggers:**

- "create detailed story", "detail story", "document story"
- "write requirements for", "design story"

### Progress Tracking Mode

**When to use:** User reports completed work or requests progress update

**Agent updates:**

- `stories/<slug>/tasks.md` - Mark completed tasks with `[x]`
- Verify acceptance criteria met
- Assess story completion status
- Update plan.md or move to backlog.md

**Triggers:**

- "mark task complete", "update progress", "tasks done"
- "completed tasks", "finished work"

### History Tracking Mode

**When to use:** User requests moving story to backlog

**Agent performs:**

- Remove story from plan.md
- Add to backlog.md with completion date
- Document key outcomes
- Link to story folder

**Triggers:**

- "move to backlog", "story complete", "archive story"
- "mark story done", "finalize story"

## Quality Requirements

**Tech-pm agent MUST ensure:**

- [ ] All requirements follow EARS patterns strictly
- [ ] Story folders use kebab-case naming
- [ ] Task hierarchy maximum 2 levels (phases → tasks)
- [ ] All tasks link to REQ-IDs for traceability
- [ ] Task checkboxes use `[x]` format (not emoji)
- [ ] Acceptance criteria are verifiable
- [ ] No epic hierarchy (flat story structure only)
- [ ] English filenames and folder names
- [ ] No footers, signatures, or temporal references

## Story Structure Reference

```text
stories/
├── plan.md                    # PLANNED stories
├── backlog.md                 # COMPLETED stories
└── <story-slug>/              # Detailed story
    ├── design.md              # 13 required sections
    ├── requirements.md        # EARS-compliant only
    └── tasks.md               # Task checklist with phases
```

## Common Use Cases

### Use Case 1: Starting New Project

```bash
/plan "Analyze docs/ and create initial implementation plan with prioritized stories"
```

**Expected:** tech-pm creates `stories/plan.md` with story list

### Use Case 2: Preparing for Development

```bash
/plan "Create detailed story for API authentication system from plan.md"
```

**Expected:** tech-pm creates `stories/api-authentication/` with 3 files

### Use Case 3: After Development Sprint

```bash
/plan "Update progress: tasks 1.1, 1.2, 2.1 complete in api-authentication story. Tests passing. Move to backlog if complete."
```

**Expected:** tech-pm updates tasks.md, moves story if done

### Use Case 4: Story Refinement

```bash
/plan "Add performance requirements to document-search story requirements.md"
```

**Expected:** tech-pm updates requirements.md with new EARS requirements

## Integration with Development Workflow

**Typical flow:**

1. **Planning:** `/plan "Create implementation plan"` → generates plan.md
2. **Detailing:** `/plan "Detail story user-auth"` → creates story folder
3. **Development:** `/develop "Implement user-auth" story:user-auth` → builds feature
4. **Tracking:** `/plan "Mark tasks 1.1-1.3 complete in user-auth"` → updates progress
5. **Completion:** Story auto-moved to backlog.md when all tasks done

## Agent Responsibilities Summary

**Tech-pm agent handles** (see tech-pm.md for details):

- EARS requirements writing
- Story decomposition and planning
- Task breakdown with acceptance criteria
- Progress tracking and status assessment
- Story lifecycle management (plan → backlog)
- Traceability maintenance (REQ-IDs → tasks)
- Architecture compliance validation

**NOT handled by this command:**

- Actual code implementation (use `/develop`)
- Testing execution (use `/test`)
- Architecture design (handled in stories/\*/design.md)

## Output Format

**Agent should provide:**

```markdown
## Planning Action: [What was done]

### Files Created/Updated

- stories/plan.md (if planning mode)
- stories/<slug>/design.md (if story creation)
- stories/<slug>/requirements.md (if story creation)
- stories/<slug>/tasks.md (if story creation or tracking)
- stories/backlog.md (if completion mode)

### Summary

[Brief description of what was created, updated, or tracked]

### Next Steps

[Recommended actions, e.g., "Run /develop to implement story X"]
```

## Error Handling

**If instruction is unclear:**

- Agent should ask clarifying questions:
  - Which story are you referring to?
  - Do you want to create plan.md or detail a specific story?
  - Which tasks are completed?

**If files don't exist:**

- For progress tracking: inform user to create story first
- For story creation: verify story exists in plan.md
- For planning: create plan.md from scratch

**If EARS violations detected:**

- Fix requirements to comply with EARS patterns
- Add proper keywords (While, When, Where, If-Then)
- Ensure correct clause order

## Critical Rules

1. **EARS compliance is mandatory** - no exceptions for requirements.md
2. **Flat story structure** - no epic hierarchy in plan.md
3. **Checkbox format** - use `[x]` not emoji for task completion
4. **English only** - all filenames and folder names
5. **Traceability** - REQ-IDs must link to tasks
6. **No temporal references** - no dates in plan content
7. **Verifiable tasks** - each task must have clear acceptance criteria

Remember: This command delegates ALL story management to tech-pm agent. Focus on WHAT to do, agent knows HOW to do it following EARS and project standards.
