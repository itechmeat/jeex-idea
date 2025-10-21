# Docker Safe Restart Command

Safe Docker environment restart with pre-flight checks, health verification, and error monitoring.

## Instructions

Invoke the `tech-devops` agent to safely restart the Docker environment:

### 1. Pre-Flight Checks (MANDATORY)

Run code quality checks BEFORE restart to catch errors early:

```bash
# Backend type checking
cd backend && python -m mypy app/

# Backend linting
cd backend && python -m ruff check app

# Docker compose validation
docker-compose config --quiet
```

**If errors found:** Fix them before proceeding with restart.

### 2. Restart Execution

**Default (rebuild):**

```bash
docker-compose down --remove-orphans
docker-compose up --build -d
sleep 15
```

**Full reset (if volumes need clearing):**

```bash
docker-compose down -v --remove-orphans
docker-compose up --build -d
sleep 20
```

### 3. Health Verification

Check all critical endpoints:

```bash
# Service status
docker-compose ps

# API health
curl -s http://localhost:5210/health | python3 -m json.tool

# Vector health
curl -s http://localhost:5210/api/v1/vector/health | python3 -m json.tool
```

### 4. Log Monitoring

Monitor logs for errors:

```bash
# API logs (most important)
docker-compose logs api --tail 100

# Look for error keywords
docker-compose logs api --tail 100 | grep -iE "error|exception|failed|traceback"
```

**Critical errors to watch for:**

- `ImportError`, `ModuleNotFoundError` → Missing imports
- `TypeError`, `AttributeError` → Code logic errors
- `ValidationError` → Configuration issues
- `UnboundLocalError` → Uninitialized variables
- Database/Qdrant connection errors

### 5. Fix Runtime Errors

If errors detected:

1. Read the file with error
2. Fix the issue
3. Restart affected service: `docker-compose restart api`
4. Verify fix with health checks

### 6. Report

Provide concise report:

```markdown
## Restart Report

**Pre-flight:** [✅ Pass / ❌ Fixed X issues]
**Services:** [X/6 running]
**Health:** [✅ Healthy / ⚠️ Issues found]
**Errors:** [None / List of errors and fixes]
**Status:** [✅ Ready / ❌ Needs attention]
```

## Agent Invocation

Use tech-devops agent:

```yaml
subagent_type: tech-devops
description: Safe Docker restart with verification
prompt: |
  1. PRE-FLIGHT: Run make backend-lint (fix errors if found)
  2. RESTART: docker-compose down --remove-orphans && docker-compose up --build -d
  3. WARMUP: Wait 15 seconds
  4. HEALTH: Check /health and /api/v1/vector/health endpoints
  5. LOGS: Monitor docker-compose logs api --tail 100 for errors
  6. FIX: If runtime errors found, fix and restart affected service
  7. REPORT: Provide status summary
```

Arguments: $ARGUMENTS
