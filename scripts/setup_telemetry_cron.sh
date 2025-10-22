#!/bin/bash

# Setup cron job for automatic telemetry cleanup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLEANUP_SCRIPT="$SCRIPT_DIR/cleanup_telemetry.sh"

echo "🔧 Setting up automatic telemetry cleanup..."

# Validate cleanup script exists
if [[ ! -f "$CLEANUP_SCRIPT" ]]; then
    echo "❌ Error: Cleanup script not found at $CLEANUP_SCRIPT" >&2
    exit 1
fi

# Make sure cleanup script is executable
if ! chmod +x "$CLEANUP_SCRIPT"; then
    echo "❌ Error: Failed to make cleanup script executable: $CLEANUP_SCRIPT" >&2
    exit 1
fi

# Create log directory if it doesn't exist
LOG_DIR="${SCRIPT_DIR}/../tmp"
mkdir -p "$LOG_DIR"

# Create cron job to run cleanup every 5 minutes with log rotation
# Log rotation: keep only last 10MB of logs
CRON_ENTRY="*/5 * * * * $CLEANUP_SCRIPT >> $LOG_DIR/cleanup.log 2>&1 && tail -c 10M $LOG_DIR/cleanup.log > $LOG_DIR/cleanup.log.tmp && mv $LOG_DIR/cleanup.log.tmp $LOG_DIR/cleanup.log"

# Add to crontab if not already exists
if ! crontab -l 2>/dev/null | grep -F "$CLEANUP_SCRIPT"; then
    # Get current crontab (handle case where no crontab exists)
    current_cron=$(crontab -l 2>/dev/null || echo "")

    # Add new entry and install
    if ! (echo "$current_cron"; echo "$CRON_ENTRY") | crontab -; then
        echo "❌ Error: Failed to install cron job" >&2
        exit 1
    fi
    echo "✅ Cron job added for automatic telemetry cleanup (every 5 minutes)"
else
    echo "ℹ️  Cron job already exists"
fi

echo "📋 Current cron jobs:"
if crontab -l 2>/dev/null | grep -q "telemetry"; then
    crontab -l 2>/dev/null | grep "telemetry" || echo "  Error: Could not read cron jobs"
else
    echo "  No telemetry cron jobs found"
fi

echo ""
echo "🔍 To see cleanup logs: tail -f $LOG_DIR/cleanup.log"
echo "🛑 To remove cron job: crontab -e (delete the telemetry line)"
echo ""