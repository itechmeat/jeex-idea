#!/bin/bash

# Test runner script for automated testing after code changes
# Detects file types and runs appropriate test commands

set -e

# File path from environment variable
FILE_PATH="${CLAUDE_TOOL_FILE_PATH:-}"

# Function to run tests based on file type
run_tests() {
    local file_path="$1"

    # JavaScript/TypeScript files
    if [[ "$file_path" == *.js || "$file_path" == *.ts || "$file_path" == *.jsx || "$file_path" == *.tsx ]]; then
        if [[ -f package.json ]]; then
            echo "📝 Running JavaScript/TypeScript tests..."
            if command -v npm >/dev/null 2>&1; then
                npm test 2>/dev/null || echo "ℹ️ npm test not configured"
            elif command -v yarn >/dev/null 2>&1; then
                yarn test 2>/dev/null || echo "ℹ️ yarn test not configured"
            elif command -v pnpm >/dev/null 2>&1; then
                pnpm test 2>/dev/null || echo "ℹ️ pnpm test not configured"
            fi
        fi
    fi

    # Python files
    if [[ "$file_path" == *.py ]]; then
        if [[ -f pytest.ini || -f setup.cfg || -f pyproject.toml || -f requirements.txt ]]; then
            echo "🐍 Running Python tests..."
            if command -v pytest >/dev/null 2>&1; then
                if ! pytest "$file_path"; then
                    echo "⚠️  pytest failed for $file_path"
                fi
            elif command -v python >/dev/null 2>&1; then
                if ! python -m pytest "$file_path"; then
                    echo "⚠️  pytest module execution failed for $file_path"
                fi
            fi
        fi
    fi

    # Ruby files
    if [[ "$file_path" == *.rb ]]; then
        if [[ -f Gemfile ]]; then
            echo "💎 Running Ruby tests..."
            if command -v bundle >/dev/null 2>&1; then
                bundle exec rspec "$file_path" 2>/dev/null || echo "ℹ️ rspec failed or not configured"
            fi
        fi
    fi

    # Go files
    if [[ "$file_path" == *.go ]]; then
        if [[ -f go.mod ]]; then
            echo "🐹 Running Go tests..."
            if command -v go >/dev/null 2>&1; then
                go test "${file_path%/*}" 2>/dev/null || echo "ℹ️ go test failed"
            fi
        fi
    fi

    # Rust files
    if [[ "$file_path" == *.rs ]]; then
        if [[ -f Cargo.toml ]]; then
            echo "🦀 Running Rust tests..."
            if command -v cargo >/dev/null 2>&1; then
                cargo test 2>/dev/null || echo "ℹ️ cargo test failed"
            fi
        fi
    fi
}

# Main execution
if [[ -n "$FILE_PATH" && -f "$FILE_PATH" ]]; then
    echo "🔍 Auto-running tests for: $FILE_PATH"
    run_tests "$FILE_PATH"
    echo "✅ Test runner completed"
else
    echo "ℹ️ No valid file path provided for test runner"
fi