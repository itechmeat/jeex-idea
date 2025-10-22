.PHONY: help setup verify-setup clean-setup lint lint-fix format check pre-commit markdown-lint markdown-fix backend-lint backend-fix backend-format sql-lint sql-fix security-scan dev dev-up dev-down dev-logs dev-shell dev-shell-service dev-restart dev-status verify-docker verify-postgresql dev-setup db-shell db-migrate db-migrate-create db-migrate-downgrade db-migrate-history db-migrate-current db-health db-metrics db-reset db-backup qdrant-init qdrant-health qdrant-stats qdrant-reset qdrant-shell qdrant-logs redis-health redis-stats redis-shell redis-logs redis-cli test test-backend test-phase4 test-phase4-integration test-phase4-rollback test-phase4-performance test-coverage test-quick test-unit-vector test-integration-vector test-vector-all test-performance test-performance-quick test-performance-integration docs
.DEFAULT_GOAL := help

# Use bash for advanced shell features (read -p, [[ ... ]], etc.)
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

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

verify-docker: ## Verify Docker setup is configured correctly
	@echo "$(GREEN)Verifying Docker development environment...$(RESET)"
	@./scripts/verify-docker-setup.sh

verify-postgresql: ## Verify PostgreSQL setup and configuration
	@echo "$(GREEN)Verifying PostgreSQL setup...$(RESET)"
	@./scripts/verify-postgresql-setup.sh

dev-setup: ## Setup development environment
	@echo "$(GREEN)Setting up development environment...$(RESET)"
	@if [ ! -f .env ]; then \
		echo "$(YELLOW)Creating .env from template...$(RESET)"; \
		cp .env.template .env; \
		echo "$(YELLOW)Please edit .env file with your configuration$(RESET)"; \
	else \
		echo "$(GREEN).env file already exists$(RESET)"; \
	fi
	@echo "$(GREEN)Development environment setup complete!$(RESET)"

dev-up: ## Start all development services
	@echo "$(GREEN)Starting JEEX Idea development environment...$(RESET)"
	@echo ""
	@if [ ! -f .env ]; then \
		echo "$(RED)Error: .env file not found$(RESET)"; \
		echo "Run '$(YELLOW)make dev-setup$(RESET)' first"; \
		exit 1; \
	fi
	docker-compose up --build -d
	@echo ""
	@echo "$(GREEN)Waiting for services to be healthy...$(RESET)"
	@sleep 10
	@make dev-status

dev-down: ## Stop all development services
	@echo "$(YELLOW)Stopping JEEX Idea development environment...$(RESET)"
	docker-compose down
	@echo "$(GREEN)All services stopped$(RESET)"

dev-logs: ## Show logs from all services
	@echo "$(GREEN)Showing logs from all services...$(RESET)"
	docker-compose logs -f --tail=100

dev-logs-service: ## Show logs from specific service (usage: make dev-logs-service SERVICE=api)
	@if [ -z "$(SERVICE)" ]; then \
		echo "$(RED)Error: SERVICE parameter is required$(RESET)"; \
		echo "Usage: make dev-logs-service SERVICE=api"; \
		exit 1; \
	fi
	@echo "$(GREEN)Showing logs from $(SERVICE)...$(RESET)"
	docker-compose logs -f --tail=100 $(SERVICE)

dev-shell: ## Open shell in API container
	@echo "$(GREEN)Opening shell in API container...$(RESET)"
	docker-compose exec api bash

dev-shell-service: ## Open shell in specific service (usage: make dev-shell-service SERVICE=postgres)
	@if [ -z "$(SERVICE)" ]; then \
		echo "$(RED)Error: SERVICE parameter is required$(RESET)"; \
		echo "Usage: make dev-shell-service SERVICE=postgres"; \
		exit 1; \
	fi
	@echo "$(GREEN)Opening shell in $(SERVICE) container...$(RESET)"
	docker-compose exec $(SERVICE) sh

dev-restart: ## Restart all development services
	@echo "$(YELLOW)Restarting JEEX Idea development environment...$(RESET)"
	docker-compose restart
	@sleep 5
	@make dev-status

dev-rebuild: ## Rebuild and restart all development services
	@echo "$(YELLOW)Stopping JEEX Idea development environment...$(RESET)"
	docker-compose down
	@echo "$(GREEN)Rebuilding and starting all services...$(RESET)"
	docker-compose up --build -d
	@echo ""
	@echo "$(GREEN)Waiting for services to be healthy...$(RESET)"
	@sleep 10
	@make dev-status

dev-status: ## Show status of all services
	@echo "$(GREEN)JEEX Idea Development Environment Status$(RESET)"
	@echo "======================================"
	@echo ""
	docker-compose ps
	@echo ""
	@echo "$(GREEN)Service URLs$(RESET)"
	@echo "============"
	@echo "API:        http://localhost:5210"
	@echo "API Docs:   http://localhost:5210/docs"
	@echo "PostgreSQL: localhost:5220"
	@echo "Qdrant:     http://localhost:5230"
	@echo "Redis:      localhost:5240"
	@echo "OTel:       http://localhost:8888/metrics"
	@echo ""

dev: dev-up ## Alias for dev-up

##@ Database

db-shell: ## Open PostgreSQL shell
	@echo "$(GREEN)Opening PostgreSQL shell...$(RESET)"
	docker-compose exec postgres psql -U jeex_user -d jeex_idea

db-migrate: ## Run database migrations
	@echo "$(GREEN)Running database migrations...$(RESET)"
	@docker-compose exec api alembic upgrade head

db-migrate-create: ## Create new database migration (usage: make db-migrate-create MSG="add_user_table")
	@if [ -z "$(MSG)" ]; then \
		echo "$(RED)Error: MSG parameter is required$(RESET)"; \
		echo "Usage: make db-migrate-create MSG=\"add_user_table\""; \
		exit 1; \
	fi
	@echo "$(GREEN)Creating database migration: $(MSG)$(RESET)"
	@docker-compose exec api alembic revision --autogenerate -m "$(MSG)"

db-migrate-downgrade: ## Downgrade database by one migration
	@echo "$(YELLOW)Downgrading database by one migration...$(RESET)"
	@docker-compose exec api alembic downgrade -1

db-migrate-history: ## Show migration history
	@echo "$(GREEN)Migration history:$(RESET)"
	@docker-compose exec api alembic history

db-migrate-current: ## Show current migration version
	@echo "$(GREEN)Current migration:$(RESET)"
	@docker-compose exec api alembic current

db-health: ## Check database health
	@echo "$(GREEN)Checking database health...$(RESET)"
	@curl -s http://localhost:5210/database | python3 -m json.tool || echo "Database health check failed"

db-metrics: ## Get database performance metrics
	@echo "$(GREEN)Database performance metrics:$(RESET)"
	@curl -s http://localhost:5210/database/metrics | python3 -m json.tool || echo "Database metrics collection failed"

db-reset: ## Reset database (WARNING: This will delete all data)
	@echo "$(RED)WARNING: This will delete all data in the database$(RESET)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "$(YELLOW)Resetting database...$(RESET)"; \
		docker-compose exec postgres psql -U jeex_user -d jeex_idea -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"; \
		docker-compose exec postgres psql -U jeex_user -d jeex_idea -c "GRANT ALL ON SCHEMA public TO jeex_user;"; \
		echo "$(GREEN)Database reset complete$(RESET)"; \
	else \
		echo "$(YELLOW)Cancelled$(RESET)"; \
	fi

db-backup: ## Backup database
	@echo "$(GREEN)Creating database backup...$(RESET)"
	@mkdir -p backups
	docker-compose exec postgres pg_dump -U jeex_user jeex_idea > backups/jeex-idea-backup-$$(date +%Y%m%d-%H%M%S).sql
	@echo "$(GREEN)Backup created in backups/ directory$(RESET)"

##@ Vector Database (Qdrant)

qdrant-init: ## Initialize Qdrant collection and indexes
	@echo "$(GREEN)Initializing Qdrant collection...$(RESET)"
	@curl -s -X PUT "http://localhost:5230/collections/jeex_memory" \
		-H "Content-Type: application/json" \
		-d '{"vectors": {"size": 1536, "distance": "Cosine", "hnsw_config": {"m": 0, "payload_m": 16, "ef_construct": 100}}}' || echo "Collection may already exist"
	@echo "$(YELLOW)Creating payload indexes...$(RESET)"
	@# Create project_id index
	@curl -s -X PUT "http://localhost:5230/collections/jeex_memory/index" \
		-H "Content-Type: application/json" \
		-d '{"field_name": "project_id", "field_schema": "keyword"}' || true
	@# Create language index
	@curl -s -X PUT "http://localhost:5230/collections/jeex_memory/index" \
		-H "Content-Type: application/json" \
		-d '{"field_name": "language", "field_schema": "keyword"}' || true
	@# Create type index
	@curl -s -X PUT "http://localhost:5230/collections/jeex_memory/index" \
		-H "Content-Type: application/json" \
		-d '{"field_name": "type", "field_schema": "keyword"}' || true
	@# Create created_at index
	@curl -s -X PUT "http://localhost:5230/collections/jeex_memory/index" \
		-H "Content-Type: application/json" \
		-d '{"field_name": "created_at", "field_schema": "datetime"}' || true
	@# Create importance index
	@curl -s -X PUT "http://localhost:5230/collections/jeex_memory/index" \
		-H "Content-Type: application/json" \
		-d '{"field_name": "importance", "field_schema": "float"}' || true
	@echo "$(GREEN)Qdrant collection initialized$(RESET)"

qdrant-health: ## Check Qdrant service and collection health
	@echo "$(GREEN)Checking Qdrant health...$(RESET)"
	@echo "$(YELLOW)Service Health:$(RESET)"
	@curl -s http://localhost:5230/health | python3 -m json.tool || echo "Service unhealthy"
	@echo ""
	@echo "$(YELLOW)Collection Status:$(RESET)"
	@curl -s http://localhost:5230/collections/jeex_memory | python3 -m json.tool || echo "Collection not found"

qdrant-stats: ## Display collection statistics
	@echo "$(GREEN)Qdrant collection statistics:$(RESET)"
	@curl -s http://localhost:5230/collections/jeex_memory | python3 -c "import sys, json; data = json.load(sys.stdin); \
result = data.get('result', {}); \
print(f'Collection: {result.get(\"config\", {}).get(\"params\", {}).get(\"vectors\", {}).get(\"size\", \"unknown\")}D'); \
print(f'Points: {result.get(\"points_count\", 0):,}'); \
print(f'Segments: {result.get(\"segments_count\", 0)}'); \
print(f'Disk Usage: {result.get(\"disk_data_size\", 0) / 1024 / 1024:.2f} MB'); \
print(f'RAM Usage: {result.get(\"ram_data_size\", 0) / 1024 / 1024:.2f} MB'); \
print(f'Status: {result.get(\"status\", \"unknown\")}') " || echo "Failed to get statistics"

qdrant-reset: ## Delete and recreate collection (development only)
	@echo "$(RED)WARNING: This will delete all vector data$(RESET)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "$(YELLOW)Deleting collection...$(RESET)"; \
		curl -s -X DELETE http://localhost:5230/collections/jeex_memory || true; \
		echo "$(GREEN)Recreating collection...$(RESET)"; \
		make qdrant-init; \
	else \
		echo "$(YELLOW)Cancelled$(RESET)"; \
	fi

qdrant-shell: ## Open Python shell with Qdrant client initialized
	@echo "$(GREEN)Opening Python shell with Qdrant client...$(RESET)"
	@docker-compose exec api python3 -c "import sys; from qdrant_client import QdrantClient; client = QdrantClient(url='http://qdrant:6333'); print('Qdrant client initialized'); print('Available collections:', [c.name for c in client.get_collections().collections]); print('Use the client variable to interact with Qdrant'); print('Example: client.get_collection(\"jeex_memory\")'); print(''); (exec(open('/dev/tty').read()) if sys.stdin.isatty() else print('Non-interactive environment - connection info printed above'))"

qdrant-logs: ## Tail Qdrant container logs
	@echo "$(GREEN)Showing Qdrant container logs...$(RESET)"
	@docker-compose logs -f --tail=100 qdrant

##@ Redis Cache and Queue Service

redis-health: ## Check Redis service health and connectivity
	@if [ -z "$(REDIS_PASSWORD)" ]; then \
		echo "$(RED)Error: REDIS_PASSWORD environment variable is required$(RESET)"; \
		echo "Please set REDIS_PASSWORD in your environment"; \
		exit 1; \
	fi
	@echo "$(GREEN)Checking Redis health...$(RESET)"
	@echo "$(YELLOW)Service Health:$(RESET)"
	@docker-compose exec redis redis-cli -a $(REDIS_PASSWORD) ping || echo "Redis unhealthy"
	@echo ""
	@echo "$(YELLOW)Service Info:$(RESET)"
	@docker-compose exec redis redis-cli -a $(REDIS_PASSWORD) info server | grep -E "redis_version|uptime_in_days|connected_clients|used_memory_human" || echo "Failed to get info"

redis-stats: ## Display Redis performance and memory statistics
	@if [ -z "$(REDIS_PASSWORD)" ]; then \
		echo "$(RED)Error: REDIS_PASSWORD environment variable is required$(RESET)"; \
		echo "Please set REDIS_PASSWORD in your environment"; \
		exit 1; \
	fi
	@echo "$(GREEN)Redis performance statistics:$(RESET)"
	@docker-compose exec redis redis-cli -a $(REDIS_PASSWORD) info memory | grep -E "used_memory_human|used_memory_peak_human|maxmemory_human" || echo "Failed to get memory info"
	@echo ""
	@echo "$(YELLOW)Connection Stats:$(RESET)"
	@docker-compose exec redis redis-cli -a $(REDIS_PASSWORD) info clients | grep -E "connected_clients|blocked_clients" || echo "Failed to get client info"
	@echo ""
	@echo "$(YELLOW)Command Stats:$(RESET)"
	@docker-compose exec redis redis-cli -a $(REDIS_PASSWORD) info stats | grep -E "total_commands_processed|total_connections_received|keyspace_hits|keyspace_misses" || echo "Failed to get command stats"

redis-shell: ## Open Redis CLI shell
	@if [ -z "$(REDIS_PASSWORD)" ]; then \
		echo "$(RED)Error: REDIS_PASSWORD environment variable is required$(RESET)"; \
		echo "Please set REDIS_PASSWORD in your environment"; \
		exit 1; \
	fi
	@echo "$(GREEN)Opening Redis CLI shell...$(RESET)"
	@docker-compose exec redis redis-cli -a $(REDIS_PASSWORD)

redis-logs: ## Tail Redis container logs
	@echo "$(GREEN)Showing Redis container logs...$(RESET)"
	@docker-compose logs -f --tail=100 redis

redis-cli: ## Execute Redis CLI command (usage: make redis-cli CMD="INFO")
	@if [ -z "$(CMD)" ]; then \
		echo "$(RED)Error: CMD parameter is required$(RESET)"; \
		echo "Usage: make redis-cli CMD=\"INFO\""; \
		exit 1; \
	fi
	@if [ -z "$(REDIS_PASSWORD)" ]; then \
		echo "$(RED)Error: REDIS_PASSWORD environment variable is required$(RESET)"; \
		echo "Please set REDIS_PASSWORD in your environment"; \
		exit 1; \
	fi
	@echo "$(GREEN)Executing Redis command: $(CMD)$(RESET)"
	@docker-compose exec redis redis-cli -a $(REDIS_PASSWORD) $(CMD)

test: ## Run all tests
	@echo "$(GREEN)Running comprehensive test suite...$(RESET)"
	@$(MAKE) lint
	@$(MAKE) test-backend

test-backend: ## Run backend tests
	@echo "$(GREEN)Running backend tests...$(RESET)"
	@cd backend && python3 -m pytest tests/ -v

test-phase4: ## Run Phase 4 integration and testing suite
	@echo "$(GREEN)Running Phase 4 Integration and Testing Suite...$(RESET)"
	@echo ""
	@cd backend && python tests/test_phase4_runner.py

test-phase4-integration: ## Run Phase 4 integration tests only
	@echo "$(GREEN)Running Phase 4 Integration Tests...$(RESET)"
	@cd backend && python -m pytest tests/test_phase4_integration.py -v

test-phase4-rollback: ## Run Phase 4 migration rollback tests
	@echo "$(GREEN)Running Phase 4 Migration Rollback Tests...$(RESET)"
	@cd backend && python -m pytest tests/test_migration_rollback.py -v

test-phase4-performance: ## Run Phase 4 performance and load tests
	@echo "$(GREEN)Running Phase 4 Performance and Load Tests...$(RESET)"
	@cd backend && python -m pytest tests/test_performance_load.py -v

test-coverage: ## Run tests with coverage report
	@echo "$(GREEN)Running tests with coverage...$(RESET)"
	@cd backend && python -m pytest tests/ --cov=app --cov-report=html --cov-report=term-missing

test-quick: ## Run quick tests (excluding performance tests)
	@echo "$(GREEN)Running quick tests...$(RESET)"
	@cd backend && python -m pytest tests/ -v -k "not performance and not load"

test-unit-vector: ## Run vector database unit tests
	@echo "$(GREEN)Running vector database unit tests...$(RESET)"
	@cd backend && source venv/bin/activate && python -m pytest tests/unit/services/vector/ -v

test-integration-vector: ## Run vector database integration tests
	@echo "$(GREEN)Running vector database integration tests...$(RESET)"
	@cd backend && python -m pytest tests/integration/test_vector_integration.py -v

test-vector-all: ## Run all vector database tests
	@echo "$(GREEN)Running all vector database tests...$(RESET)"
	@$(MAKE) test-unit-vector
	@$(MAKE) test-integration-vector

lint: ## Run all linting checks
	@echo "🔍 Running all linting checks..."
	@$(MAKE) backend-lint
	@$(MAKE) markdown-lint
	@$(MAKE) sql-lint
	@echo "✅ All lint checks completed"

format: ## Format all code
	@echo "✨ Formatting all code..."
	@$(MAKE) backend-format
	@$(MAKE) markdown-fix
	@echo "✅ Code formatting completed"

markdown-lint: ## Run markdown linting checks
	@echo "📋 Running markdown linting..."
	@if command -v npx >/dev/null 2>&1; then \
		npx markdownlint-cli2; \
	else \
		echo "$(YELLOW)markdownlint-cli2 not available, trying global installation...$(RESET)"; \
		if command -v markdownlint-cli2 >/dev/null 2>&1; then \
			markdownlint-cli2; \
		else \
			echo "$(RED)Error: markdownlint-cli2 not found$(RESET)"; \
			echo "Install with: npm install -g markdownlint-cli2"; \
			exit 1; \
		fi; \
	fi
	@echo "✅ Markdown linting completed!"

markdown-fix: ## Fix markdown formatting issues
	@echo "📋 Fixing markdown issues..."
	@if command -v npx >/dev/null 2>&1; then \
		npx markdownlint-cli2 --fix || echo "$(YELLOW)⚠ Some markdown issues could not be auto-fixed$(RESET)"; \
	else \
		echo "$(YELLOW)markdownlint-cli2 not available, trying global installation...$(RESET)"; \
		if command -v markdownlint-cli2 >/dev/null 2>&1; then \
			markdownlint-cli2 --fix || echo "$(YELLOW)⚠ Some markdown issues could not be auto-fixed$(RESET)"; \
		else \
			echo "$(RED)Error: markdownlint-cli2 not found$(RESET)"; \
			echo "Install with: npm install -g markdownlint-cli2"; \
			exit 1; \
		fi; \
	fi
	@echo "✅ Markdown fixes completed!"

lint-fix: ## Fix all linting issues
	@echo "🔧 Fixing all linting issues..."
	@$(MAKE) backend-fix
	@echo "📋 Fixing markdown..."
	@$(MAKE) markdown-fix
	@echo "✅ All lint fixes completed"

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

##@ Code Quality (Backend)

backend-lint: ## Run backend linting checks
	@echo "🐍 Checking backend Python linting..."
	@cd backend && python -m ruff check app --extend-ignore E501,B904,BLE001,G201,ANN001,ANN002,ANN003,ANN201,ANN202,ANN205,RUF012,S101,S104,S105,S107,SIM102,SIM103,UP038,C901,RUF001
	@echo "🐍 Checking backend Python formatting..."
	@cd backend && ruff format . --check
	@echo "🐍 Checking backend Python types..."
	@cd backend && python -m mypy app/

backend-fix: ## Fix backend linting issues
	@echo "🐍 Fixing backend Python linting..."
	@cd backend && python -m ruff check app --fix --extend-ignore E501,B904,BLE001,G201,ANN001,ANN002,ANN003,ANN201,ANN202,ANN205,RUF012,S101,S104,S105,S107,SIM102,SIM103,UP038,C901,RUF001
	@echo "🐍 Fixing backend Python formatting..."
	@cd backend && ruff format .

backend-format: ## Format backend Python code
	@echo "🐍 Formatting backend Python code..."
	@cd backend && ruff format .

check: ## Run type checks
	@echo "🔍 Running type checks..."
	@echo "🐍 Python type checking..."
	@cd backend && mypy app/

# SQL linting commands
sql-lint: ## Run SQL linting
	@echo "🗃️ Running SQL linting..."
	@if command -v sqlfluff >/dev/null 2>&1; then \
		cd backend && python -m sqlfluff lint .; \
	else \
		echo "$(YELLOW)SQLFluff not installed, skipping SQL linting$(RESET)"; \
		echo "Install with: pip install sqlfluff"; \
	fi
	@echo "✅ SQL linting completed!"

sql-fix: ## Fix SQL issues
	@echo "🗃️ Fixing SQL issues..."
	@if command -v sqlfluff >/dev/null 2>&1; then \
		cd backend && python -m sqlfluff fix .; \
	else \
		echo "$(YELLOW)SQLFluff not installed, skipping SQL fixes$(RESET)"; \
		echo "Install with: pip install sqlfluff"; \
	fi
	@echo "✅ SQL fixes completed!"

# Security scanning
security-scan: ## Run security scan with Bandit
	@echo "🔒 Running security scan with Bandit..."
	@cd backend && mkdir -p reports && python -m bandit -r app/ -f json -o reports/bandit-report.json || true
	@cd backend && python -m bandit -r app/
	@echo "✅ Security scan completed!"

##@ Performance Testing

test-performance: ## Run comprehensive performance benchmark suite
	@echo "$(GREEN)Running comprehensive vector database performance benchmarks...$(RESET)"
	@echo ""
	@if docker-compose ps qdrant | grep -q "Up"; then \
		echo "$(GREEN)✓ Qdrant is running$(RESET)"; \
	else \
		echo "$(RED)✗ Qdrant is not running$(RESET)"; \
		echo "Start Qdrant with: $(YELLOW)make qdrant-init$(RESET) or $(YELLOW)make dev-up$(RESET)"; \
		exit 1; \
	fi
	@cd backend && python -m tests.performance.benchmark_runner

test-performance-quick: ## Run quick performance benchmarks (CI/CD mode)
	@echo "$(GREEN)Running quick performance benchmarks...$(RESET)"
	@echo ""
	@if docker-compose ps qdrant | grep -q "Up"; then \
		echo "$(GREEN)✓ Qdrant is running$(RESET)"; \
	else \
		echo "$(RED)✗ Qdrant is not running$(RESET)"; \
		echo "Start Qdrant with: $(YELLOW)make qdrant-init$(RESET) or $(YELLOW)make dev-up$(RESET)"; \
		exit 1; \
	fi
	@cd backend && python -m tests.performance.benchmark_runner --quick

test-performance-integration: ## Run performance framework integration tests
	@echo "$(GREEN)Running performance framework integration tests...$(RESET)"
	@echo ""
	@if docker-compose ps qdrant | grep -q "Up"; then \
		echo "$(GREEN)✓ Qdrant is running$(RESET)"; \
	else \
		echo "$(RED)✗ Qdrant is not running$(RESET)"; \
		echo "Start Qdrant with: $(YELLOW)make qdrant-init$(RESET) or $(YELLOW)make dev-up$(RESET)"; \
		exit 1; \
	fi
	@cd backend && python -m pytest tests/performance/test_performance_integration.py -v -m performance

##@ Documentation

docs: ## Open documentation (TODO)
	@echo "$(YELLOW)TODO: Open documentation$(RESET)"
	@echo "This will serve documentation locally"

##@ Telemetry Management

telemetry-cleanup: ## Run telemetry cleanup manually
	@echo "$(YELLOW)Running telemetry cleanup...$(RESET)"
	@./scripts/cleanup_telemetry.sh

telemetry-setup: ## Setup automatic telemetry cleanup (cron job)
	@echo "$(YELLOW)Setting up automatic telemetry cleanup...$(RESET)"
	@./scripts/setup_telemetry_cron.sh

telemetry-status: ## Show telemetry files status
	@echo "$(YELLOW)Telemetry files status:$(RESET)"
	@if [ -f ./tmp/telemetry.json ]; then \
		SIZE_BYTES=$$(stat -f%z ./tmp/telemetry.json 2>/dev/null || stat -c%s ./tmp/telemetry.json 2>/dev/null || ls -ln ./tmp/telemetry.json 2>/dev/null | awk '{print $$5}' || echo "0"); \
		SIZE_KB=$$(echo "$$SIZE_BYTES" | awk '{printf "%.0f", $$1/1024}'); \
		if [ "$$SIZE_KB" -lt 1024 ]; then \
			echo "📊 telemetry.json: $${SIZE_KB}KB"; \
		else \
			SIZE_MB=$$(echo "$$SIZE_BYTES" | awk '{printf "%.0f", $$1/1024/1024}'); \
			echo "📊 telemetry.json: $${SIZE_MB}MB"; \
		fi; \
	else \
		echo "ℹ️  No telemetry files found"; \
	fi
	@echo "📁 Total telemetry directory size: $$(du -sh ./tmp 2>/dev/null | cut -f1 || echo "0B")"

