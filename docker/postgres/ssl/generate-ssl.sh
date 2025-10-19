#!/bin/bash
# JEEX Idea PostgreSQL SSL Certificate Generation
# This script generates self-signed certificates for PostgreSQL TLS encryption

set -euo pipefail

# Error handling with proper logging
error_exit() {
    echo "ERROR: $1" >&2
    exit 1
}

# Validate directory existence
validate_directories() {
    if [[ ! -d "/docker-entrypoint-initdb.d" ]]; then
        error_exit "Docker entrypoint directory not found"
    fi
}

# Check openssl availability
check_dependencies() {
    if ! command -v openssl >/dev/null 2>&1; then
        error_exit "OpenSSL is required but not installed"
    fi
}

# Directory configuration
SSL_DIR="/docker-entrypoint-initdb.d/ssl"
CERT_DIR="/var/lib/postgresql/ssl"

# Validate environment and dependencies
validate_directories
check_dependencies

# Create SSL directory with error handling
mkdir -p "$CERT_DIR" || error_exit "Failed to create SSL directory: $CERT_DIR"

# Generate private key with error handling
openssl genrsa -out "$CERT_DIR/server.key" 2048 || error_exit "Failed to generate server private key"

# Generate certificate signing request
openssl req -new -key "$CERT_DIR/server.key" -out "$CERT_DIR/server.csr" -subj "/C=US/ST=CA/L=San Francisco/O=JEEX Idea/OU=Development/CN=postgres" || error_exit "Failed to generate certificate signing request"

# Generate self-signed certificate (valid for 1 year)
openssl x509 -req -in "$CERT_DIR/server.csr" -signkey "$CERT_DIR/server.key" -out "$CERT_DIR/server.crt" -days 365 || error_exit "Failed to generate server certificate"

# Generate CA certificate (for client verification)
openssl genrsa -out "$CERT_DIR/ca.key" 2048 || error_exit "Failed to generate CA private key"
openssl req -new -x509 -key "$CERT_DIR/ca.key" -out "$CERT_DIR/ca.crt" -days 365 -subj "/C=US/ST=CA/L=San Francisco/O=JEEX Idea/OU=Development/CN=JEEX-CA" || error_exit "Failed to generate CA certificate"

# Set proper permissions with error handling
chown postgres:postgres "$CERT_DIR"/* || error_exit "Failed to set ownership on SSL files"
chmod 600 "$CERT_DIR/server.key" || error_exit "Failed to set permissions on server key"
chmod 644 "$CERT_DIR/server.crt" || error_exit "Failed to set permissions on server certificate"
chmod 644 "$CERT_DIR/ca.crt" || error_exit "Failed to set permissions on CA certificate"
chmod 600 "$CERT_DIR/ca.key" || error_exit "Failed to set permissions on CA key"

# Remove CSR file (no longer needed)
rm -f "$CERT_DIR/server.csr" || error_exit "Failed to remove CSR file"

echo "PostgreSQL SSL certificates generated successfully"
echo "Files created:"
echo "  - Server certificate: $CERT_DIR/server.crt"
echo "  - Server private key: $CERT_DIR/server.key"
echo "  - CA certificate: $CERT_DIR/ca.crt"
echo "  - CA private key: $CERT_DIR/ca.key"