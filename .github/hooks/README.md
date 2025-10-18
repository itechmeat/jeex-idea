# Git Hooks Technical Details

This directory contains git hooks stored in the repository.

## Setup

```bash
git config core.hooksPath .github/hooks
```

## Available Hooks

### pre-commit

Runs comprehensive checks before commits. See root README.md for full details.

## Adding New Hooks

1. Create the hook file in this directory
2. Make it executable: `chmod +x .github/hooks/hook-name`
3. Test the hook before committing

## Troubleshooting

- **Hook not running**: Check that `git config core.hooksPath` returns `.github/hooks`
- **Permission denied**: Run `chmod +x .github/hooks/pre-commit`
- **Command not found**: Ensure you have `pnpm` installed
