#!/bin/bash

# JEEX Idea Development SSL Certificate Setup Script
# Generates self-signed SSL certificates for development use

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

# Configuration
SSL_DIR="docker/nginx/ssl"
CERT_NAME="jeex-dev"
KEY_FILE="${SSL_DIR}/${CERT_NAME}.key"
CERT_FILE="${SSL_DIR}/${CERT_NAME}.crt"
CSR_FILE="${SSL_DIR}/${CERT_NAME}.csr"

echo -e "${GREEN}JEEX Idea - Development SSL Certificate Setup${RESET}"
echo "=================================================="

# Check if OpenSSL is available
if ! command -v openssl &> /dev/null; then
    echo -e "${RED}Error: OpenSSL is not installed${RESET}"
    echo "Please install OpenSSL and try again"
    exit 1
fi

# Create SSL directory if it doesn't exist
if [ ! -d "$SSL_DIR" ]; then
    echo -e "${YELLOW}Creating SSL directory...${RESET}"
    mkdir -p "$SSL_DIR"
fi

# Check if certificates already exist
if [ -f "$KEY_FILE" ] && [ -f "$CERT_FILE" ]; then
    echo -e "${YELLOW}SSL certificates already exist!${RESET}"
    echo "Files found:"
    echo "  - Private key: $KEY_FILE"
    echo "  - Certificate: $CERT_FILE"

    read -p "Do you want to regenerate them? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}Using existing certificates${RESET}"
        exit 0
    fi

    echo -e "${YELLOW}Removing existing certificates...${RESET}"
    rm -f "$KEY_FILE" "$CERT_FILE" "$CSR_FILE"
fi

echo -e "${YELLOW}Generating private key...${RESET}"
openssl genrsa -out "$KEY_FILE" 2048

echo -e "${YELLOW}Generating certificate signing request...${RESET}"
openssl req -new -key "$KEY_FILE" -out "$CSR_FILE" -subj "/C=US/ST=Development/L=Local/O=JEEX/CN=localhost"

echo -e "${YELLOW}Generating self-signed certificate...${RESET}"
openssl x509 -req -days 365 -in "$CSR_FILE" -signkey "$KEY_FILE" -out "$CERT_FILE"

# Clean up CSR
rm -f "$CSR_FILE"

# Set appropriate permissions
chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

echo -e "${GREEN}SSL certificates generated successfully!${RESET}"
echo ""
echo "Generated files:"
echo "  - Private key: $KEY_FILE"
echo "  - Certificate: $CERT_FILE"
echo ""
echo "Certificate details:"
openssl x509 -in "$CERT_FILE" -text -noout | grep -A 2 "Subject:"
echo ""
echo -e "${YELLOW}Note: These certificates are for development only!${RESET}"
echo "Do not use them in production environments."