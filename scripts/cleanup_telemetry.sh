#!/bin/bash

# Smart telemetry cleanup script for JEEX Idea
# Rotates and cleans old telemetry files to prevent disk space issues
set -euo pipefail

# Use environment variable or command line argument, fallback to relative path
TELEMETRY_DIR="${1:-${TELEMETRY_DIR:-./tmp}}"
MAX_SIZE_MB=10
MAX_FILES=3
COMPRESS_OLDER_THAN=60  # minutes

echo "🧹 Smart telemetry cleanup started at $(date)"

# Create directory if it doesn't exist
mkdir -p "$TELEMETRY_DIR"

# Function to get file size in MB (cross-platform compatible)
get_file_size_mb() {
    if [[ -f "$1" ]]; then
        # Try macOS/BSD stat first, then GNU stat (Linux), fallback to ls
        size_bytes=$(stat -f%z "$1" 2>/dev/null || stat -c%s "$1" 2>/dev/null || ls -ln "$1" 2>/dev/null | awk '{print $5}' || echo "0")
        echo "$size_bytes" | awk '{printf "%.0f", $1/1024/1024}' || echo 0
    else
        echo 0
    fi
}

# Check current telemetry file
CURRENT_FILE="$TELEMETRY_DIR/telemetry.json"
if [[ -f "$CURRENT_FILE" ]]; then
    SIZE_MB=$(get_file_size_mb "$CURRENT_FILE")
    echo "📊 Current telemetry.json size: ${SIZE_MB}MB"

    # If file is too large, rotate it
    if [[ $SIZE_MB -gt $MAX_SIZE_MB ]]; then
        echo "🔄 Rotating large telemetry file (${SIZE_MB}MB > ${MAX_SIZE_MB}MB)"

        # Create timestamp for rotation
        TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

        # Compress and move old file (with error checking)
        if gzip -c "$CURRENT_FILE" > "$TELEMETRY_DIR/telemetry_${TIMESTAMP}.json.gz"; then
            # Only truncate if compression succeeded
            > "$CURRENT_FILE"
            echo "✅ Rotated to telemetry_${TIMESTAMP}.json.gz"
        else
            echo "❌ Error: Failed to compress telemetry file" >&2
            exit 1
        fi
    fi
fi

# Clean up old compressed files
echo "🗑️  Cleaning up old compressed files..."
find "$TELEMETRY_DIR" -name "telemetry_*.json.gz" -type f | \
    sort -r | \
    tail -n +$((MAX_FILES + 1)) | \
    while read -r file; do
        echo "🗑️  Removing old file: $(basename "$file")"
        rm -f "$file"
    done

# Clean up files older than specified time
echo "🕒 Cleaning up files older than ${COMPRESS_OLDER_THAN} minutes..."
find "$TELEMETRY_DIR" -name "telemetry_*.json.gz" -type f -mmin +$COMPRESS_OLDER_THAN -delete 2>/dev/null

# Show current status
echo ""
echo "📋 Current telemetry files:"
ls -lh "$TELEMETRY_DIR"/telemetry* 2>/dev/null || echo "  No telemetry files found"

# Calculate total size
TOTAL_SIZE=$(du -sm "$TELEMETRY_DIR" 2>/dev/null | cut -f1 || echo 0)
echo "📦 Total telemetry directory size: ${TOTAL_SIZE}MB"

echo "✨ Smart telemetry cleanup completed at $(date)"
echo ""