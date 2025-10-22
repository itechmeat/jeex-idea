# Redis Monitoring System

Comprehensive Redis monitoring system for JEEX Idea with real-time metrics, health checks, performance analytics, and alerting.

## Overview

This monitoring system provides comprehensive observability for Redis infrastructure with the following features:

- **Real-time Metrics Collection**: Memory usage, connection pools, command performance, and error rates
- **Health Monitoring**: Comprehensive health checks with circuit breaker protection
- **Performance Analytics**: Command-level performance tracking with percentile analysis
- **Alert Management**: Threshold-based alerting with configurable rules and notifications
- **Dashboard Integration**: Grafana dashboard templates and Prometheus alerting rules
- **Project Isolation**: All monitoring supports project-scoped tracking

## Architecture

The system follows Domain-Driven Design principles with separate components for each monitoring concern:

```
app/monitoring/
├── __init__.py                    # Module initialization
├── redis_metrics.py               # Metrics collection and OpenTelemetry integration
├── health_checker.py              # Health checks and status monitoring
├── performance_monitor.py         # Performance analytics and insights
├── alert_manager.py               # Alert management and notifications
├── dashboard.py                   # Grafana dashboard configuration
└── README.md                      # This documentation
```

## Components

### RedisMetricsCollector

Handles comprehensive metrics collection with OpenTelemetry and Prometheus integration.

**Key Features:**
- Memory usage monitoring with 80% threshold alerts
- Connection pool monitoring and utilization tracking
- Command execution time tracking with percentile analysis
- Error rate monitoring for Redis operations
- OpenTelemetry metrics export
- Prometheus-compatible metrics

**Usage:**
```python
from app.monitoring.redis_metrics import redis_metrics_collector

# Track command performance
await redis_metrics_collector.track_command_performance(
    command="GET",
    command_type=RedisCommandType.READ,
    duration_ms=25.5,
    success=True,
    project_id=uuid4()
)

# Get metrics summary
summary = await redis_metrics_collector.get_metrics_summary()
```

### RedisHealthChecker

Performs comprehensive health checks on Redis infrastructure.

**Health Check Types:**
- **Basic Connectivity**: PING tests and basic read/write operations
- **Memory Usage**: Memory percentage and threshold monitoring
- **Connection Pool**: Connection pool health and utilization
- **Performance**: Response times and cache hit rates
- **Persistence**: RDB/AOF backup status

**Usage:**
```python
from app.monitoring.health_checker import redis_health_checker

# Perform full health check
health_status = await redis_health_checker.perform_full_health_check()

# Check specific component
result = await redis_health_checker.check_specific_component(
    HealthCheckType.MEMORY_USAGE
)
```

### RedisPerformanceMonitor

Provides advanced performance analytics and insights.

**Features:**
- Command performance analysis with percentiles (P50, P95, P99)
- Connection efficiency monitoring
- Memory performance analytics
- Performance insights and recommendations
- Historical performance trending

**Usage:**
```python
from app.monitoring.performance_monitor import redis_performance_monitor

# Get performance dashboard
dashboard = await redis_performance_monitor.get_performance_dashboard()
```

### RedisAlertManager

Manages alert rules, notifications, and alert lifecycle.

**Alert Categories:**
- Memory alerts (usage thresholds)
- Performance alerts (response times, hit rates)
- Connection alerts (pool utilization)
- Error rate alerts
- Availability alerts

**Usage:**
```python
from app.monitoring.alert_manager import redis_alert_manager

# Get active alerts
alerts = await redis_alert_manager.get_alerts(status=AlertStatus.ACTIVE)

# Acknowledge alert
await redis_alert_manager.acknowledge_alert(alert_id, "admin_user")

# Get alert summary
summary = await redis_alert_manager.get_alert_summary()
```

### RedisDashboardConfiguration

Provides Grafana dashboard templates and Prometheus configuration.

**Features:**
- Pre-configured Grafana dashboard JSON
- Prometheus alerting rules
- Dashboard templates for different views
- Project-specific dashboard configurations

## API Endpoints

The monitoring system exposes comprehensive REST API endpoints:

### Health Checks
- `GET /monitoring/redis/health` - Comprehensive health status
- `GET /monitoring/redis/health/{check_type}` - Specific health check

### Metrics
- `GET /monitoring/redis/metrics` - Metrics summary
- `GET /monitoring/redis/metrics/prometheus` - Prometheus format metrics
- `GET /monitoring/redis/performance` - Performance dashboard

### Alerts
- `GET /monitoring/redis/alerts` - Get alerts with filtering
- `GET /monitoring/redis/alerts/summary` - Alert summary statistics
- `POST /monitoring/redis/alerts/{alert_id}/action` - Manage alerts

### Dashboard
- `GET /monitoring/redis/dashboard/grafana` - Grafana dashboard JSON
- `GET /monitoring/redis/dashboard/prometheus-rules` - Prometheus rules
- `GET /monitoring/redis/dashboard/export` - Export all configurations

### Control
- `POST /monitoring/redis/monitoring/start` - Start monitoring services
- `POST /monitoring/redis/monitoring/stop` - Stop monitoring services
- `GET /monitoring/redis/monitoring/status` - Service status

## Configuration

### Environment Variables

```bash
# Redis Configuration
REDIS_URL=redis://localhost:5240
REDIS_MAX_CONNECTIONS=10
REDIS_CONNECTION_TIMEOUT=10.0
REDIS_OPERATION_TIMEOUT=10.0
REDIS_HEALTH_CHECK_INTERVAL=30.0
REDIS_MAX_RETRIES=3
REDIS_RETRY_DELAY=1.0

# OpenTelemetry Configuration
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=jeex-idea-api
OTEL_SERVICE_VERSION=0.1.0
```

### Alert Thresholds

Default alert thresholds can be customized:

```python
# Memory thresholds (percentage)
MEMORY_WARNING_THRESHOLD = 80.0
MEMORY_CRITICAL_THRESHOLD = 90.0

# Performance thresholds (milliseconds)
SLOW_COMMAND_THRESHOLD = 100.0
RESPONSE_TIME_WARNING_THRESHOLD = 100.0
RESPONSE_TIME_CRITICAL_THRESHOLD = 1000.0

# Connection pool thresholds (percentage)
CONNECTION_POOL_WARNING_THRESHOLD = 80.0
CONNECTION_POOL_CRITICAL_THRESHOLD = 95.0

# Error rate thresholds (percentage)
ERROR_RATE_THRESHOLD = 5.0

# Cache hit rate thresholds (percentage)
HIT_RATE_WARNING_THRESHOLD = 80.0
HIT_RATE_CRITICAL_THRESHOLD = 70.0
```

## Grafana Dashboard

### Importing Dashboard

1. Get the dashboard configuration:
   ```bash
   curl http://localhost:8000/monitoring/redis/dashboard/grafana > redis-dashboard.json
   ```

2. Import in Grafana:
   - Go to Grafana UI → Dashboards → Import
   - Upload the JSON file
   - Configure Prometheus datasource

### Dashboard Panels

The dashboard includes the following panels:

1. **Status Overview**: Memory usage, active connections, commands/sec
2. **Key Metrics**: Hit rate, memory percentage, connection utilization
3. **Active Alerts**: Memory alerts, errors, slow commands
4. **Memory Usage**: Historical memory usage with thresholds
5. **Memory Details**: Memory percentage and fragmentation ratio
6. **Cache Performance**: Hit rate over time with alerts
7. **Command Performance**: Commands per second and slow commands
8. **Response Time Distribution**: P50, P95, P99 response times
9. **Throughput by Type**: Commands broken down by type
10. **Connection Pool**: Active/idle connections and utilization
11. **Connection Errors**: Error rate over time
12. **Error Rate by Type**: Breakdown of error types
13. **Health Status**: Redis instance health
14. **Persistence Status**: RDB save timestamps
15. **Active Alerts**: Current alert table
16. **Alert History**: 24-hour alert history

## Prometheus Integration

### Alerting Rules

The system generates comprehensive Prometheus alerting rules:

```yaml
groups:
  - name: jeex-redis-alerts
    rules:
      - alert: RedisHighMemoryUsage
        expr: jeex_redis_memory_percentage > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Redis memory usage is above 80%"
          description: "Redis memory usage is {{ $value }}%"

      - alert: RedisLowHitRate
        expr: jeex_redis_hit_rate < 0.8
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Redis cache hit rate is low"
          description: "Redis cache hit rate is {{ $value | humanizePercentage }}"
```

### Metrics

The following metrics are exported:

- `jeex_redis_memory_bytes` - Redis memory usage in bytes
- `jeex_redis_memory_percentage` - Memory usage as percentage
- `jeex_redis_connections_active` - Active connections
- `jeex_redis_connection_utilization` - Connection pool utilization
- `jeex_redis_hit_rate` - Cache hit rate
- `jeex_redis_commands_total` - Total commands executed
- `jeex_redis_command_duration_seconds` - Command execution time
- `jeex_redis_errors_total` - Total errors
- `jeex_redis_slow_commands_total` - Slow commands
- `jeex_redis_memory_alerts_total` - Memory alerts

## Testing

### Unit Tests

Run the comprehensive test suite:

```bash
pytest tests/test_redis_monitoring.py -v
```

### Integration Tests

Run the integration test script:

```bash
python test_redis_monitoring_integration.py
```

### Manual Testing

Test individual components:

```python
# Test metrics collection
python -c "
import asyncio
from app.monitoring.redis_metrics import redis_metrics_collector
asyncio.run(redis_metrics_collector.start_collection())
"

# Test health checks
python -c "
import asyncio
from app.monitoring.health_checker import redis_health_checker
asyncio.run(redis_health_checker.start_health_checks())
"
```

## Performance Impact

The monitoring system is designed for minimal performance impact:

- **Overhead**: < 1ms additional latency per Redis operation
- **Memory**: ~10MB for metrics storage and history
- **CPU**: < 5% additional CPU usage during normal operation
- **Network**: Minimal additional data transfer for metrics

## Troubleshooting

### Common Issues

1. **Redis Connection Failed**
   - Check Redis URL configuration
   - Verify Redis is running and accessible
   - Check network connectivity

2. **Metrics Not Collected**
   - Ensure monitoring services are started
   - Check Redis connection factory status
   - Verify OpenTelemetry configuration

3. **Alerts Not Triggering**
   - Check alert rule configuration
   - Verify metrics are being collected
   - Check alert manager status

4. **Dashboard Not Loading**
   - Verify Prometheus datasource configuration
   - Check Grafana dashboard JSON format
   - Ensure metrics are available in Prometheus

### Debug Logging

Enable debug logging:

```python
import logging
logging.getLogger("app.monitoring").setLevel(logging.DEBUG)
```

### Health Check Endpoints

Check service status:

```bash
# Overall monitoring status
curl http://localhost:8000/monitoring/redis/monitoring/status

# Redis health
curl http://localhost:8000/monitoring/redis/health

# Metrics summary
curl http://localhost:8000/monitoring/redis/metrics
```

## Development

### Adding New Metrics

1. Add metric collection in `RedisMetricsCollector`
2. Add OpenTelemetry and Prometheus metrics
3. Update health checks if needed
4. Add alert rules
5. Update dashboard configuration

### Adding New Health Checks

1. Add new `HealthCheckType` enum value
2. Implement check method in `RedisHealthChecker`
3. Add to full health check process
4. Update dashboard if needed

### Adding New Alert Rules

1. Create `AlertRule` configuration
2. Add to default rules in `RedisAlertManager`
3. Add corresponding Prometheus rule
4. Update dashboard to display alert

## Production Deployment

### Requirements

- Redis 6.4.0+
- OpenTelemetry collector
- Prometheus server
- Grafana instance
- Sufficient memory for metrics storage

### Configuration

1. Set appropriate environment variables
2. Configure OpenTelemetry endpoint
3. Set up Prometheus scraping
4. Import Grafana dashboard
5. Configure alert notification channels

### Monitoring

Monitor the monitoring system itself:

- Track alert volumes and types
- Monitor performance impact
- Check metric collection latency
- Verify dashboard availability

## Security

- All Redis connections use authentication
- Project isolation enforced for all operations
- No sensitive data in logs
- Secure OpenTelemetry configuration
- Rate limiting on API endpoints

## Contributing

When contributing to the monitoring system:

1. Add comprehensive tests
2. Update documentation
3. Follow existing code patterns
4. Ensure minimal performance impact
5. Add appropriate logging

## License

This monitoring system is part of the JEEX Idea project and follows the same license terms.