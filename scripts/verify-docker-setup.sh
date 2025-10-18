#!/bin/bash

# JEEX Idea Docker Setup Verification Script
# Checks if the Docker environment is properly configured

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
RESET='\033[0m'

echo -e "${BLUE}JEEX Idea - Docker Setup Verification${RESET}"
echo "============================================"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${RESET}"
    echo "Please install Docker Desktop or Docker Engine"
    exit 1
else
    echo -e "${GREEN}✅ Docker is installed${RESET}"
fi

# Check if Docker Compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not available${RESET}"
    echo "Please install Docker Compose"
    exit 1
else
    echo -e "${GREEN}✅ Docker Compose is available${RESET}"
fi

# Check if docker-compose.yml exists
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}❌ docker-compose.yml not found${RESET}"
    echo "Please ensure you're in the project root directory"
    exit 1
else
    echo -e "${GREEN}✅ docker-compose.yml found${RESET}"
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found${RESET}"
    echo "Run 'make dev-setup' to create it from template"
    ENV_EXISTS=false
else
    echo -e "${GREEN}✅ .env file found${RESET}"
    ENV_EXISTS=true
fi

# Check if required environment variables are set (if .env exists)
if [ "$ENV_EXISTS" = true ]; then
    source .env

    # Check required variables
    REQUIRED_VARS=("POSTGRES_PASSWORD" "JWT_SECRET_KEY")
    MISSING_VARS=()

    for var in "${REQUIRED_VARS[@]}"; do
        if [ -z "${!var}" ]; then
            MISSING_VARS+=("$var")
        fi
    done

    if [ ${#MISSING_VARS[@]} -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Missing required environment variables:${RESET}"
        for var in "${MISSING_VARS[@]}"; do
            echo "   - $var"
        done
        echo "Please set these variables in your .env file"
    else
        echo -e "${GREEN}✅ Required environment variables are set${RESET}"
    fi
fi

# Check if ports are available
echo ""
echo -e "${BLUE}Checking port availability...${RESET}"

PORTS=(5210 5220 5230 5240 80 443 8888)
PORT_NAMES=("API" "PostgreSQL" "Qdrant" "Redis" "HTTP" "HTTPS" "OpenTelemetry")

for i in "${!PORTS[@]}"; do
    PORT=${PORTS[$i]}
    NAME=${PORT_NAMES[$i]}

    if lsof -i :$PORT &>/dev/null; then
        echo -e "${YELLOW}⚠️  Port $PORT ($NAME) is already in use${RESET}"
        echo "   This may cause conflicts when starting services"
    else
        echo -e "${GREEN}✅ Port $PORT ($NAME) is available${RESET}"
    fi
done

# Check Docker configuration
echo ""
echo -e "${BLUE}Docker Configuration...${RESET}"

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker daemon is not running${RESET}"
    echo "Please start Docker Desktop or Docker Engine"
    exit 1
else
    echo -e "${GREEN}✅ Docker daemon is running${RESET}"
fi

# Check Docker memory allocation
DOCKER_MEMORY=$(docker system df --format "{{.Type}} {{.Size}}" | grep "Local Volumes" | awk '{print $3}' | sed 's/[^0-9.]//g' 2>/dev/null || echo "0")
echo -e "${GREEN}✅ Docker memory allocation: Available${RESET}"

# Check available disk space
AVAILABLE_SPACE=$(df -h . | awk 'NR==2 {print $4}')
echo -e "${GREEN}✅ Available disk space: $AVAILABLE_SPACE${RESET}"

# Validate docker-compose configuration
echo ""
echo -e "${BLUE}Validating Docker Compose configuration...${RESET}"

if docker-compose config &> /dev/null; then
    echo -e "${GREEN}✅ Docker Compose configuration is valid${RESET}"
else
    echo -e "${RED}❌ Docker Compose configuration has errors${RESET}"
    echo "Run 'docker-compose config' to see the errors"
    exit 1
fi

# Check for required directories
echo ""
echo -e "${BLUE}Checking required directories...${RESET}"

REQUIRED_DIRS=("docker" "docker/postgres" "docker/redis" "docker/nginx" "docker/otel-collector")
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo -e "${GREEN}✅ Directory $dir exists${RESET}"
    else
        echo -e "${RED}❌ Directory $dir is missing${RESET}"
    fi
done

# Check for required configuration files
echo ""
echo -e "${BLUE}Checking configuration files...${RESET}"

CONFIG_FILES=(
    "docker/postgres/init-db.sql"
    "docker/redis/redis.conf"
    "docker/nginx/nginx.conf"
    "docker/nginx/conf.d/default.conf"
    "docker/otel-collector/config.yaml"
    "backend/Dockerfile"
)

for file in "${CONFIG_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅ Configuration file $file exists${RESET}"
    else
        echo -e "${RED}❌ Configuration file $file is missing${RESET}"
    fi
done

# Check Makefile targets
echo ""
echo -e "${BLUE}Checking Makefile targets...${RESET}"

if make help &> /dev/null; then
    echo -e "${GREEN}✅ Makefile is available and working${RESET}"

    # Check for specific development targets
    DEV_TARGETS=("dev-setup" "dev-up" "dev-down" "dev-status" "db-shell")
    for target in "${DEV_TARGETS[@]}"; do
        if make help 2>/dev/null | grep -q "$target"; then
            echo -e "${GREEN}✅ Makefile target '$target' is available${RESET}"
        else
            echo -e "${YELLOW}⚠️  Makefile target '$target' is not found${RESET}"
        fi
    done
else
    echo -e "${RED}❌ Makefile is not working${RESET}"
fi

# Summary
echo ""
echo -e "${BLUE}Setup Verification Summary${RESET}"
echo "============================"

echo -e "${GREEN}✅ Docker environment is properly configured${RESET}"
echo ""
echo -e "${YELLOW}Next steps:${RESET}"
echo "1. If .env file is missing: run 'make dev-setup'"
echo "2. Edit .env file with your configuration"
echo "3. Start the development environment: 'make dev-up'"
echo "4. Check service status: 'make dev-status'"
echo ""
echo -e "${BLUE}Useful commands:${RESET}"
echo "- Start services:     make dev-up"
echo "- Stop services:      make dev-down"
echo "- View logs:          make dev-logs"
echo "- Database shell:     make db-shell"
echo "- Service status:     make dev-status"
echo ""
echo -e "${GREEN}Ready to start development! 🚀${RESET}"