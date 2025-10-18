# Design Document — Story "Setup Docker Development Environment"

## Overview

This story establishes the foundational Docker development environment for JEEX Idea, creating the containerized infrastructure necessary for all subsequent development work. The implementation will create a complete development stack with all core services, networking, health checks, and development tooling configured according to the architectural specifications.

The scope includes creating docker-compose configuration with PostgreSQL 18, Redis 6.4.0+, Qdrant 1.15.4+, Nginx reverse proxy, OpenTelemetry collector, and the API service foundation. All services will be configured with appropriate networking, volumes, health checks, and development-specific optimizations.

## Current State Analysis

Currently, the project exists as a conceptual design with documentation but lacks any runnable development environment. No Docker configuration exists, and there are no containerized services. The project structure includes documentation files outlining the architecture and specifications, but no implementation infrastructure.

The absence of a development environment prevents any backend development, testing, or integration work. All subsequent stories depend on having a functional containerized development stack.

## Proposed Architecture

### High-Level Docker Architecture

The development environment will use Docker Compose to orchestrate multiple services in isolated containers with dedicated networking. The architecture follows a separation of concerns approach with distinct services for each functional component:

- **Reverse Proxy Layer**: Nginx handling TLS termination, compression, and request routing
- **Application Layer**: FastAPI backend service with hot reload capabilities
- **Data Layer**: PostgreSQL for primary storage, Qdrant for vector search, Redis for caching
- **Observability Layer**: OpenTelemetry collector for distributed tracing and metrics

### Network Architecture

Three distinct networks will be created:

1. **jeex-frontend**: For frontend-to-backend communication
2. **jeex-backend**: Internal service-to-service communication
3. **jeex-data**: Database and cache service isolation

This network design provides security boundaries while allowing necessary service communication.

### Volume Strategy

Persistent data will be managed through named volumes:

- `postgres_data`: PostgreSQL data persistence
- `qdrant_data`: Qdrant vector storage persistence
- `redis_data`: Redis cache persistence
- `otel_logs`: OpenTelemetry log storage

## Components and Interfaces

### Nginx Reverse Proxy

**Responsibilities**: TLS termination, request routing, compression, static file serving, security headers

**Configuration**:

- HTTP/HTTPS on ports 80/443
- Upstream routing to API service on port 8000
- Security headers (CORS, CSP, HSTS)
- Gzip compression for API responses
- Health check endpoint at `/health`

**Interface**: Acts as entry point for all external traffic, routing requests to appropriate backend services.

### PostgreSQL Database

**Responsibilities**: Primary data storage, document versions, user management, project metadata

**Configuration**:

- PostgreSQL 18 with UUID v7 support
- Connection pooling via PgBouncer
- Database: `jeex_idea`
- User: `jeex_user` with secure password
- Health checks on port 5432

**Interface**: Standard PostgreSQL interface on port 5220 (external) and 5432 (internal).

### Qdrant Vector Database

**Responsibilities**: Vector embeddings storage, semantic search, project memory

**Configuration**:

- Qdrant 1.15.4+ with optimized HNSW configuration
- Single collection with payload filtering
- Project + language scoped memory isolation
- Performance optimizations for multi-tenant access

**Interface**: HTTP API on port 5230 (external) and 6333 (internal).

### Redis Cache

**Responsibilities**: Caching, session storage, rate limiting, message queuing

**Configuration**:

- Redis 6.4.0+ with max memory policies
- Persistence with periodic snapshots
- Connection pooling configuration
- Health checks on port 6379

**Interface**: Redis protocol on port 5240 (external) and 6379 (internal).

### OpenTelemetry Collector

**Responsibilities**: Distributed tracing, metrics collection, log aggregation

**Configuration**:

- OTLP receivers (gRPC, HTTP)
- Prometheus metrics exporter
- Logging exporters
- Service discovery configuration
- Health checks on multiple ports

**Interface**: OTLP endpoints on ports 4317 (gRPC) and 4318 (HTTP), metrics on 8888.

### API Service Foundation

**Responsibilities**: FastAPI application foundation, middleware configuration

**Configuration**:

- FastAPI 0.119.0+ with async support
- Development server with hot reload
- Environment-based configuration
- Health check endpoints
- OpenAPI documentation

**Interface**: HTTP API on port 5210 (external) and 8000 (internal).

## Data Models

### Environment Configuration

```yaml
# Environment variables structure
environment:
  # Database configuration
  DATABASE_URL: postgresql://jeex_user:${POSTGRES_PASSWORD}@postgres:5432/jeex_idea

  # Vector database
  QDRANT_URL: http://qdrant:6333
  QDRANT_COLLECTION: jeex_memory

  # Cache configuration
  REDIS_URL: redis://redis:6379

  # API configuration
  API_HOST: 0.0.0.0
  API_PORT: 8000
  ENVIRONMENT: development

  # Security
  SECRET_KEY: ${JWT_SECRET_KEY}
  CORS_ORIGINS: http://localhost:5200

  # Observability
  OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317
  OTEL_SERVICE_NAME: jeex-idea-api
```

### Service Health Models

Each service implements standardized health check responses:

```json
{
  "status": "healthy|unhealthy",
  "timestamp": "2025-01-15T10:30:00Z",
  "version": "1.0.0",
  "dependencies": {
    "database": "healthy|unhealthy",
    "redis": "healthy|unhealthy",
    "qdrant": "healthy|unhealthy"
  },
  "checks": [
    {
      "name": "database_connection",
      "status": "pass|fail",
      "duration_ms": 15
    }
  ]
}
```

## Error Handling Strategy

### Service Startup Dependencies

Services will implement proper dependency management and graceful degradation:

1. **Database Dependencies**: API service waits for PostgreSQL health checks before starting
2. **Cache Fallbacks**: Redis unavailability results in degraded mode with direct database access
3. **Vector Search Fallbacks**: Qdrant unavailability disables semantic search features
4. **Observability Fallbacks**: OpenTelemetry collector unavailability doesn't block application startup

### Health Check Implementation

Each service will implement comprehensive health checks:

- **Liveness Checks**: Service is running and responsive
- **Readiness Checks**: Service dependencies are available
- **Startup Checks**: Service has completed initialization
- **Dependency Checks**: External service connectivity verification

### Error Recovery

- **Automatic Restart**: Failed containers automatically restart with exponential backoff
- **Circuit Breakers**: Failed dependencies trigger circuit breakers to prevent cascade failures
- **Graceful Shutdown**: Services handle SIGTERM signals for clean shutdown

## Architecture Diagrams

### Docker Compose Service Architecture

```mermaid
graph TB
    subgraph "Host Machine"
        DEV[Developer]
        BROWSER[Browser :5200]
        POSTGRES_CLIENT[DB Client :5220]
        QDRANT_UI[Qdrant UI :5230]
        REDIS_CLI[Redis CLI :5240]
        API_CLIENT[API Client :5210]
        OTEL_UI[Otel UI :8888]
    end

    subgraph "Docker Network: jeex-frontend"
        NGINX[Nginx :80,443]
    end

    subgraph "Docker Network: jeex-backend"
        API[FastAPI :8000]
        OTEL[OpenTelemetry Collector]
    end

    subgraph "Docker Network: jeex-data"
        POSTGRES[PostgreSQL :5432]
        QDRANT[Qdrant :6333]
        REDIS[Redis :6379]
    end

    subgraph "Docker Volumes"
        PG_VOL[(postgres_data)]
        QD_VOL[(qdrant_data)]
        RD_VOL[(redis_data)]
        OTEL_VOL[(otel_logs)]
    end

    %% External connections
    BROWSER -.->|:5200| NGINX
    POSTGRES_CLIENT -.->|:5220| POSTGRES
    QDRANT_UI -.->|:5230| QDRANT
    REDIS_CLI -.->|:5240| REDIS
    API_CLIENT -.->|:5210| API
    OTEL_UI -.->|:8888| OTEL

    %% Service communication
    NGINX --> API
    API --> POSTGRES
    API --> QDRANT
    API --> REDIS
    API -.->|traces| OTEL

    %% Volume connections
    POSTGRES --> PG_VOL
    QDRANT --> QD_VOL
    REDIS --> RD_VOL
    OTEL --> OTEL_VOL

    %% Network boundaries
    NGINX -.->|frontend| API
    API -.->|backend| POSTGRES
    API -.->|backend| QDRANT
    API -.->|backend| REDIS
```

### Service Health Check Flow

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant DC as Docker Compose
    participant N as Nginx
    participant API as FastAPI
    participant PG as PostgreSQL
    participant Q as Qdrant
    participant R as Redis
    participant O as OTel Collector

    Dev->>DC: docker-compose up --build
    DC->>PG: Start PostgreSQL
    DC->>Q: Start Qdrant
    DC->>R: Start Redis
    DC->>O: Start OTel Collector

    PG->>PG: Health check initialization
    Q->>Q: Health check initialization
    R->>R: Health check initialization
    O->>O: Health check initialization

    PG-->>DC: Healthy
    Q-->>DC: Healthy
    R-->>DC: Healthy
    O-->>DC: Healthy

    DC->>API: Start API Service
    API->>PG: Check database connection
    API->>Q: Check vector database
    API->>R: Check cache connection
    API->>O: Check telemetry

    PG-->>API: Connection OK
    Q-->>API: Connection OK
    R-->>API: Connection OK
    O-->>API: Connection OK

    API-->>DC: Ready
    DC->>N: Start Nginx
    N->>API: Check upstream health
    API-->>N: Healthy
    N-->>DC: Ready

    DC-->>Dev: All services running
    Dev->>N: http://localhost
    N->>API: Proxy request
    API-->>N: Response
    N-->>Dev: Web interface
```

## Security Considerations

### Container Security

- **Non-root Users**: All containers run as non-root users
- **Minimal Base Images**: Use Alpine or distroless images where possible
- **Secrets Management**: Environment variables for sensitive data, no hardcoded secrets
- **Resource Limits**: CPU and memory limits prevent resource exhaustion
- **Read-only Filesystems**: Where possible, use read-only filesystems

### Network Security

- **Network Segmentation**: Separate networks for different service tiers
- **Port Exposure**: Only necessary ports exposed to host
- **Internal Communication**: Service-to-service communication through internal networks
- **Firewall Rules**: Container networking rules restrict traffic flow

### Data Security

- **Volume Permissions**: Proper permissions on mounted volumes
- **Data Encryption**: Database encryption at rest and in transit
- **Backup Strategy**: Regular backup procedures for persistent data
- **Access Control**: Database access limited to specific users and networks

## Performance Considerations

### Database Optimization

- **Connection Pooling**: PgBouncer for PostgreSQL connection management
- **Query Optimization**: Proper indexing strategies from architecture specifications
- **Resource Allocation**: Appropriate memory and CPU limits
- **Caching Strategy**: Redis caching for frequently accessed data

### Container Performance

- **Resource Limits**: Balanced CPU and memory allocation
- **Startup Optimization**: Efficient container startup sequences
- **Health Check Frequency**: Optimized health check intervals
- **Logging Strategy**: Structured logging with appropriate log levels

### Development Experience

- **Hot Reload**: FastAPI hot reload for rapid development
- **Volume Mounts**: Source code mounted for live editing
- **Debug Support**: Debug ports exposed for development
- **Local Development**: Optimized for local development workflows

## Implementation Sequence

### Phase 1: Foundation Infrastructure

1. **Create Docker network configuration**
2. **Set up PostgreSQL container with persistence**
3. **Configure Redis container with optimization**
4. **Establish Qdrant vector database container**
5. **Implement volume management and permissions**

### Phase 2: Service Integration

1. **Deploy OpenTelemetry collector**
2. **Configure Nginx reverse proxy**
3. **Set up API service foundation**
4. **Implement service health checks**
5. **Establish inter-service networking**

### Phase 3: Development Tooling

1. **Configure environment variables and secrets**
2. **Set up development scripts and Makefile targets**
3. **Implement logging and monitoring**
4. **Create development documentation**
5. **Validate service connectivity and health**

## Traceability Matrix

| Design Component         | Requirements         | Tasks         |
| ------------------------ | -------------------- | ------------- |
| Docker Compose Structure | INFRA-001, INFRA-002 | Task 1.1, 1.2 |
| PostgreSQL Configuration | INFRA-003, INFRA-004 | Task 1.3, 1.4 |
| Redis Configuration      | INFRA-005, INFRA-006 | Task 1.5, 2.1 |
| Qdrant Configuration     | INFRA-007, INFRA-008 | Task 1.6, 2.2 |
| Nginx Reverse Proxy      | INFRA-009, INFRA-010 | Task 2.3, 2.4 |
| Health Checks            | INFRA-011, INFRA-012 | Task 2.5, 3.1 |
| Network Security         | INFRA-013, INFRA-014 | Task 3.2, 3.3 |
| Development Tooling      | INFRA-015, INFRA-016 | Task 3.4, 3.5 |

## Risks & Mitigations

### Technical Risks

**Risk**: Container startup failures due to dependency ordering
**Mitigation**: Implement proper health checks and wait strategies in docker-compose

**Risk**: Port conflicts on local development machine
**Mitigation**: Use dedicated port ranges (5200-5300) and provide configuration overrides

**Risk**: Volume permission issues on different host operating systems
**Mitigation**: Use named volumes with proper UID/GID configuration

**Risk**: Resource exhaustion during development
**Mitigation**: Implement resource limits and monitoring

### Development Risks

**Risk**: Complex setup process discourages new developers
**Mitigation**: Provide simple Makefile targets and comprehensive documentation

**Risk**: Inconsistent environments across different machines
**Mitigation**: Containerization ensures consistent environments

**Risk**: Difficulty debugging containerized services
**Mitigation**: Provide debugging tools and log aggregation

### Operational Risks

**Risk**: Data loss during container restarts
**Mitigation**: Proper volume configuration and backup strategies

**Risk**: Security vulnerabilities in base images
**Mitigation**: Regular updates and security scanning

**Risk**: Performance issues in development environment
**Mitigation**: Resource monitoring and optimization guidelines
