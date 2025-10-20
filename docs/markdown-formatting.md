# Markdown Formatting Configuration

This document explains the markdown formatting setup in the JEEX Idea project.

## Overview

The project uses **markdownlint-cli2** for consistent markdown formatting and linting across all documentation files.

## Installation

The markdownlint-cli2 tool is installed globally:

```bash
npm install -g markdownlint-cli2@0.18.1
```

## Configuration Files

### `.markdownlint.jsonc`

Main configuration file that defines linting rules and exceptions:

- Allows long lines (MD013: false) for URLs and code examples
- Allows inline HTML (MD033: false) for enhanced documentation
- Uses ATX style headers (# style)
- Configures list indentation and spacing
- Requires language specification in fenced code blocks

### `.markdownlint-cli2.jsonc`

CLI-specific configuration that defines:

- Config file path (`.markdownlint.jsonc`)
- Ignore patterns for build artifacts, dependencies, and cache directories
- File glob patterns for markdown files to process

## Makefile Commands

### `make markdown-lint`

Run markdown linting checks on all markdown files in the project.

```bash
make markdown-lint
```

### `make markdown-fix`

Automatically fix markdown formatting issues where possible.

```bash
make markdown-fix
```

### Integration with Other Commands

Markdown linting is integrated into the main linting workflow:

- `make lint` - Includes markdown linting alongside backend and SQL checks
- `make lint-fix` - Includes markdown fixes alongside other code fixes

## File Coverage

The following markdown files are processed:

- `*.md` (root level)
- `docs/**/*.md`
- `frontend/**/*.md`
- `stories/**/*.md`
- `.github/**/*.md`
- `scripts/**/*.md`

## Ignored Directories

The following directories are ignored to avoid processing generated files and dependencies:

- `node_modules/**`
- `backend/**`
- `frontend/node_modules/**`
- Build artifacts (`.git/**`, `build/**`, `dist/**`, etc.)
- Cache directories (`.coverage/**`, `__pycache__/**`, etc.)
- Configuration files (`.env*`, `*.log`, etc.)

## Pre-commit Integration

The pre-commit hook (`.github/hooks/pre-commit`) automatically runs markdown linting before allowing commits. If markdown issues are found:

1. The commit will be blocked
2. Error messages will be displayed
3. Instructions for fixing will be provided (`make markdown-fix`)

## Common Issues and Fixes

### Missing Language Specification

**Error**: `MD040/fenced-code-language Fenced code blocks should have a language specified`

**Fix**: Add language to code blocks:

````markdown
<!-- Before -->

```
code here
```

<!-- After -->

```python
code here
```
````

### Emphasis Used as Heading

**Error**: `MD036/no-emphasis-as-heading Emphasis used instead of a heading`

**Fix**: Use proper heading syntax:

```markdown
<!-- Before -->

**This is a heading**

<!-- After -->

### This is a heading
```

### Trailing Newline

**Error**: `MD047/single-trailing-newline Files should end with a single newline character`

**Fix**: Add a single newline at the end of the file.

## Best Practices

1. **Run `make markdown-fix`** before committing to auto-fix issues
2. **Check `make markdown-lint`** to see remaining issues that need manual fixes
3. **Use proper code block syntax** with language specification
4. **Follow consistent heading hierarchy** (use # style headers)
5. **Add blank lines around lists and headings** for better readability

## Integration with Development Workflow

The markdown formatting is seamlessly integrated into the development workflow:

1. **Development**: Write documentation following markdown best practices
2. **Pre-commit**: Automatic linting catches issues before commits
3. **CI/CD**: Linting can be integrated into CI pipelines
4. **Code Reviews**: Consistent formatting makes reviews easier

This ensures high-quality, consistent documentation across the entire project.
