.PHONY: help setup verify-setup clean-setup
.DEFAULT_GOAL := help

# Colors for output
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
RESET  := \033[0m

##@ General

help: ## Display this help message
	@echo "$(GREEN)JEEX Idea - Makefile Commands$(RESET)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2 } /^##@/ { printf "\n$(GREEN)%s$(RESET)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)
	@echo ""

##@ Setup

setup: ## Setup project symlinks and directory structure
	@echo "$(GREEN)Setting up JEEX Idea repository...$(RESET)"
	@echo ""
	
	@echo "$(YELLOW)1. Creating file symlinks...$(RESET)"
	@if [ ! -e CLAUDE.md ]; then \
		ln -s AGENTS.md CLAUDE.md && echo "  ✓ Created CLAUDE.md -> AGENTS.md"; \
	else \
		echo "  ℹ CLAUDE.md already exists"; \
	fi
	
	@echo ""
	@echo "$(YELLOW)2. Creating directory symlinks...$(RESET)"
	@if [ ! -e .claude ]; then \
		ln -s .ai .claude && echo "  ✓ Created .claude -> .ai"; \
	else \
		echo "  ℹ .claude already exists"; \
	fi
	
	@if [ ! -e .qwen ]; then \
		ln -s .ai .qwen && echo "  ✓ Created .qwen -> .ai"; \
	else \
		echo "  ℹ .qwen already exists"; \
	fi
	
	@if [ ! -e .github/prompts ]; then \
		mkdir -p .github && cd .github && ln -s ../.ai/commands prompts && cd .. && echo "  ✓ Created .github/prompts -> .ai/commands"; \
	else \
		echo "  ℹ .github/prompts already exists"; \
	fi
	
	@echo ""
	@echo "$(YELLOW)3. Creating Cursor IDE rules symlinks...$(RESET)"
	@mkdir -p .cursor/rules
	@for file in .ai/agents/*.md; do \
		basename=$$(basename $$file .md); \
		target=.cursor/rules/$$basename.mdc; \
		if [ ! -e $$target ]; then \
			ln -s ../../.ai/agents/$$basename.md $$target && echo "  ✓ Created $$basename.mdc -> .ai/agents/$$basename.md"; \
		fi; \
	done
	
	@echo ""
	@echo "$(YELLOW)4. Creating reviews directory...$(RESET)"
	@if [ ! -d reviews ]; then \
		mkdir -p reviews && echo "  ✓ Created reviews/ directory"; \
	else \
		echo "  ℹ reviews/ directory already exists"; \
	fi
	
	@echo ""
	@echo "$(GREEN)✓ Setup complete!$(RESET)"
	@echo ""
	@echo "Run '$(YELLOW)make verify-setup$(RESET)' to verify all symlinks are correct."
	@echo ""

verify-setup: ## Verify all symlinks are correctly set up
	@echo "$(GREEN)Verifying JEEX Idea setup...$(RESET)"
	@echo ""
	
	@echo "$(YELLOW)File symlinks:$(RESET)"
	@if [ -L CLAUDE.md ] && [ "$$(readlink CLAUDE.md)" = "AGENTS.md" ]; then \
		echo "  $(GREEN)✓$(RESET) CLAUDE.md -> AGENTS.md"; \
	else \
		echo "  $(RED)✗$(RESET) CLAUDE.md symlink missing or incorrect"; \
	fi
	
	@echo ""
	@echo "$(YELLOW)Directory symlinks:$(RESET)"
	@if [ -L .claude ] && [ "$$(readlink .claude)" = ".ai" ]; then \
		echo "  $(GREEN)✓$(RESET) .claude -> .ai"; \
	else \
		echo "  $(RED)✗$(RESET) .claude symlink missing or incorrect"; \
	fi
	
	@if [ -L .qwen ] && [ "$$(readlink .qwen)" = ".ai" ]; then \
		echo "  $(GREEN)✓$(RESET) .qwen -> .ai"; \
	else \
		echo "  $(RED)✗$(RESET) .qwen symlink missing or incorrect"; \
	fi
	
	@if [ -L .github/prompts ] && [ "$$(readlink .github/prompts)" = "../.ai/commands" ]; then \
		echo "  $(GREEN)✓$(RESET) .github/prompts -> .ai/commands"; \
	else \
		echo "  $(RED)✗$(RESET) .github/prompts symlink missing or incorrect"; \
	fi
	
	@echo ""
	@echo "$(YELLOW)Cursor rules symlinks:$(RESET)"
	@count=0; \
	for file in .ai/agents/*.md; do \
		basename=$$(basename $$file .md); \
		target=.cursor/rules/$$basename.mdc; \
		if [ -L $$target ]; then \
			count=$$((count + 1)); \
		fi; \
	done; \
	total=$$(ls -1 .ai/agents/*.md 2>/dev/null | wc -l | tr -d ' '); \
	if [ $$count -eq $$total ]; then \
		echo "  $(GREEN)✓$(RESET) All $$total agent symlinks present"; \
	else \
		echo "  $(RED)✗$(RESET) Only $$count/$$total agent symlinks found"; \
	fi
	
	@echo ""
	@echo "$(YELLOW)Project directories:$(RESET)"
	@if [ -d reviews ]; then \
		echo "  $(GREEN)✓$(RESET) reviews/ directory exists"; \
	else \
		echo "  $(RED)✗$(RESET) reviews/ directory missing"; \
	fi
	
	@if [ -d stories ]; then \
		echo "  $(GREEN)✓$(RESET) stories/ directory exists"; \
	else \
		echo "  $(YELLOW)ℹ$(RESET) stories/ directory not created yet (run /plan)"; \
	fi
	
	@echo ""

clean-setup: ## Remove all setup symlinks (use with caution)
	@echo "$(RED)Removing setup symlinks...$(RESET)"
	@echo ""
	@read -p "Are you sure? This will remove all symlinks. [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "$(YELLOW)Removing file symlinks...$(RESET)"; \
		[ -L CLAUDE.md ] && rm CLAUDE.md && echo "  ✓ Removed CLAUDE.md"; \
		echo "$(YELLOW)Removing directory symlinks...$(RESET)"; \
		[ -L .claude ] && rm .claude && echo "  ✓ Removed .claude"; \
		[ -L .qwen ] && rm .qwen && echo "  ✓ Removed .qwen"; \
		[ -L .github/prompts ] && rm .github/prompts && echo "  ✓ Removed .github/prompts"; \
		echo "$(YELLOW)Removing Cursor rules symlinks...$(RESET)"; \
		find .cursor/rules -type l -name "*.mdc" -delete && echo "  ✓ Removed all .mdc symlinks"; \
		echo ""; \
		echo "$(GREEN)✓ Cleanup complete!$(RESET)"; \
		echo "Run '$(YELLOW)make setup$(RESET)' to recreate symlinks."; \
	else \
		echo "$(YELLOW)Cancelled.$(RESET)"; \
	fi
	@echo ""

##@ Development

.PHONY: dev test lint format imports pre-commit

dev: ## Start development environment (TODO)
	@echo "$(YELLOW)TODO: Start development environment$(RESET)"
	@echo "This will start Docker containers for backend services"
	@echo "Commands to add:"
	@echo "  - docker-compose up -d"
	@echo "  - Health checks for all services"

test: ## Run all tests (TODO)
	@echo "$(YELLOW)TODO: Run comprehensive test suite$(RESET)"
	@echo "Commands to add:"
	@echo "  Backend: cd backend && pytest tests/"
	@echo "  Frontend: cd frontend && pnpm test"
	@echo "  E2E: cd frontend && pnpm test:e2e"

lint: ## Run linters (TODO)
	@echo "$(YELLOW)TODO: Run code quality checks$(RESET)"
	@echo "Commands to add:"
	@echo "  Backend: cd backend && ruff check src/"
	@echo "  Frontend: cd frontend && pnpm lint"
	@echo "  Type checking: cd backend && mypy src/"

format: ## Format code (TODO)
	@echo "$(YELLOW)TODO: Format Python and TypeScript code$(RESET)"
	@echo "Commands to add:"
	@echo "  Backend: cd backend && ruff format src/ && black src/"
	@echo "  Frontend: cd frontend && pnpm format"

imports: ## Sort imports (TODO)
	@echo "$(YELLOW)TODO: Sort imports in Python and TypeScript$(RESET)"
	@echo "Commands to add:"
	@echo "  Backend: cd backend && isort src/"
	@echo "  Frontend: imports are handled by ESLint/Biome"

pre-commit: ## Run all pre-commit hooks
	@echo "$(GREEN)Running pre-commit hooks...$(RESET)"
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit run --all-files; \
	else \
		echo "$(RED)Error: pre-commit is not installed$(RESET)"; \
		echo "Install with: pip install pre-commit"; \
		echo "Then setup hooks: pre-commit install"; \
		exit 1; \
	fi

##@ Documentation

.PHONY: docs

docs: ## Open documentation (TODO)
	@echo "$(YELLOW)TODO: Open documentation$(RESET)"
	@echo "This will serve documentation locally"

