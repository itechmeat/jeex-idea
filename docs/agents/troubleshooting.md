# Agent Framework Troubleshooting (MVP)

## Common Issues

- Missing CrewAI dependency: ensure `crewai>=0.186.1` in `backend/requirements.txt`.
- OpenTelemetry metrics errors: initialize OTEL before vector/agent imports.
- Redis connection failures: verify Redis config and `redis_service` initialization.

## Isolation Errors

- Project access denied: confirm `user_id` owns the `project_id`.
- Language mismatch: ensure project `language` matches request `language`.

## Circuit Breaker

- Breaker open: wait `AGENT_CIRCUIT_BREAKER_TIMEOUT_SECONDS` or reduce failure rate.

## Database

- Migration missing: ensure `007_agent_framework_setup` applied; column `duration_ms` exists.

## Telemetry

- Missing spans: verify `agents/telemetry.py` used and OTEL exporter is configured.
