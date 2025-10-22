# Telemetry Management for JEEX Idea

## Overview

This document describes the smart telemetry management system implemented for the JEEX Idea MVP observability stack.

## Architecture

### File Exporter Configuration

- **Path**: `/tmp/telemetry.json` (mapped to `./tmp/telemetry.json` in project)
- **Data Types**: Traces and Logs only (Metrics go to Prometheus)
- **Collection**: Real-time from all services (API, Database, Redis, Qdrant)
- **Format**: OpenTelemetry JSON format

### Smart Management Features

1. **Automated Cleanup**
   - Runs every 5 minutes via cron job
   - Rotates files when they exceed 10MB
   - Keeps only 2 most recent compressed files
   - Compresses old files with gzip

2. **Size Monitoring**
   - Real-time size tracking via `make telemetry-status`
   - Automatic rotation to prevent disk space issues
   - Configurable size limits (5MB for MVP)

3. **Git Integration**
   - All telemetry files excluded from Git via `.gitignore`
   - Temporary files patterns included
   - No accidental commits of large telemetry data

## Usage

### Check Telemetry Status

```bash
make telemetry-status
```

### Manual Cleanup

```bash
make telemetry-cleanup
```

### Setup Automatic Cleanup

```bash
make telemetry-setup
```

### View Cleanup Logs

```bash
tail -f ./tmp/cleanup.log
```

## Configuration

### OpenTelemetry Collector (`otel-collector-config.yaml`)

```yaml
exporters:
  file:
    path: /tmp/telemetry.json  # Inside container
    # Only traces and logs (no metrics to file)

service:
  pipelines:
    traces:
      exporters: [debug, file]    # Include file export
    metrics:
      exporters: [prometheus, debug]  # No file export for metrics
    logs:
      exporters: [debug, file]    # Include file export
```

### Cron Job Setup

```bash
*/5 * * * * /path/to/scripts/cleanup_telemetry.sh >> ./tmp/cleanup.log 2>&1
```

### Git Ignore Configuration

```gitignore
# Temporary and telemetry files (NEVER commit these!)
/tmp/
*.telemetry.json
telemetry.json*
otel-*.json
```

## File Structure

```
project/
├── tmp/
│   ├── telemetry.json          # Current telemetry file
│   ├── telemetry_20241022_1630.json.gz  # Rotated files
│   └── cleanup.log            # Cleanup operation logs
├── scripts/
│   ├── cleanup_telemetry.sh    # Smart cleanup script
│   └── setup_telemetry_cron.sh # Cron setup script
└── .gitignore                  # Excludes telemetry files
```

## Monitoring and Alerts

### Size Thresholds

- **Warning**: File > 5MB (triggers rotation)
- **Critical**: Directory > 50MB (manual intervention required)

### Automation Rules

- **Rotation**: At 10MB file size
- **Retention**: 2 compressed files maximum
- **Cleanup**: Files older than 60 minutes removed

## Troubleshooting

### Collector Not Writing to File

1. Check collector health: `curl http://localhost:8888/health`
2. Verify configuration: `docker-compose logs otel-collector`
3. Check volume mounts in `docker-compose.yml`

### Large Telemetry Files

1. Run manual cleanup: `make telemetry-cleanup`
2. Check collection frequency (might need sampling)
3. Verify file exporter isn't collecting metrics

### Cleanup Script Not Working

1. Check cron job: `crontab -l | grep telemetry`
2. Review logs: `tail -f ./tmp/cleanup.log`
3. Test manually: `./scripts/cleanup_telemetry.sh`

## Performance Impact

### Collection Overhead

- **Traces**: ~3% performance overhead
- **File I/O**: Minimal (async writes)
- **Cleanup**: Negligible (runs every 5 minutes)

### Disk Usage

- **Normal**: < 1MB for light usage
- **Heavy**: < 20MB with automatic cleanup
- **Maximum**: Configurable via rotation settings

## Future Enhancements

### Production Considerations

1. **External Storage**: Use S3 or similar for file exporter
2. **Advanced Sampling**: Implement intelligent trace sampling
3. **Monitoring Integration**: Alert on collection failures
4. **Data Retention**: Implement tiered storage policies

### Scalability Options

1. **Multiple Collectors**: Horizontal scaling for high throughput
2. **Batch Processing**: Optimize export batch sizes
3. **Compression**: Implement real-time compression
4. **Streaming**: Use streaming exporters for real-time processing

## Security Notes

- **No Sensitive Data**: All telemetry sanitized via processors
- **Access Control**: File permissions set to 644
- **Audit Trail**: Cleanup operations logged
- **Data Isolation**: Project-based filtering enforced
