# Vector Database Integration Tests

Comprehensive integration tests for vector database project and language isolation, validating critical security requirements REQ-003 and REQ-008.

## Overview

These tests ensure bulletproof data isolation in the vector database system:

- **Project Isolation**: No cross-project data leakage
- **Language Isolation**: No cross-language contamination
- **Filter Enforcement**: Mandatory server-side filtering
- **Security Boundaries**: Protection against bypass attempts
- **Data Integrity**: Proper tagging and retrieval

## Test Categories

### 1. Isolation Tests (`test_vector_isolation.py`)

Validates **REQ-008: Multi-Tenant Data Isolation** with zero tolerance for data leakage:

- **Project Isolation Tests**
  - Strict project separation with 3 test projects
  - Cross-language content within same project
  - Bypass attempt validation

- **Language Isolation Tests**
  - Strict language separation (en, ru, es)
  - Same project with multiple languages
  - No cross-language contamination

- **Filter Enforcement Tests**
  - Mandatory project_id and language filters
  - Server-side filter validation
  - Client bypass prevention

- **Data Integrity Tests**
  - Proper vector tagging on upsert
  - Isolation-bound point retrieval
  - Context validation

### 2. Security Tests (`test_vector_security.py`)

Security-focused testing with attack simulation:

- **Filter Bypass Attempts**
  - Missing filter parameters
  - Invalid format attacks
  - Cross-project access attempts

- **Injection Protection**
  - SQL injection attempts
  - XSS attack vectors
  - Path traversal attempts

- **Boundary Conditions**
  - Extreme parameter values
  - Resource exhaustion attempts
  - Edge case handling

- **Data Leakage Detection**
  - Sensitive content isolation
  - Unauthorized access prevention
  - Security event logging

## Requirements Validation

The tests validate these critical requirements from `stories/setup-vector-database/requirements.md`:

### REQ-003: Server-Side Filter Enforcement
✅ **ALL** searches include mandatory project_id AND language filters
✅ Missing filters result in immediate rejection
✅ Filters cannot be bypassed or modified by clients

### REQ-008: Multi-Tenant Data Isolation
✅ **ZERO** tolerance for cross-project data leakage
✅ **ZERO** tolerance for cross-language contamination
✅ Strict boundary enforcement with defense-in-depth

### Security Requirements (SEC-001, SEC-002, SEC-003)
✅ Absolute filter enforcement without exceptions
✅ Network isolation through API boundaries
✅ Comprehensive security event logging

## Usage

### Prerequisites

1. **Vector Service Running**:
   ```bash
   cd /path/to/jeex-idea
   make dev-up
   ```

2. **Python Environment**:
   ```bash
   cd backend
   pip install -r requirements-test.txt
   ```

### Quick Start

#### Run All Tests
```bash
# Run comprehensive test suite
python tests/integration/run_vector_isolation_tests.py

# With verbose output
python tests/integration/run_vector_isolation_tests.py --verbose

# Save detailed report
python tests/integration/run_vector_isolation_tests.py --output report.json
```

#### Run Specific Categories
```bash
# Isolation tests only
python tests/integration/run_vector_isolation_tests.py --category isolation

# Security tests only
python tests/integration/run_vector_isolation_tests.py --category security
```

#### Run with pytest Directly
```bash
# All isolation tests
pytest tests/integration/test_vector_isolation.py -v

# All security tests
pytest tests/integration/test_vector_security.py -v

# Specific test
pytest tests/integration/test_vector_isolation.py::test_project_isolation_strict_separation -v
```

### Test Configuration

Configuration is in `tests/integration/conftest.py`:

```python
INTEGRATION_TEST_CONFIG = {
    "vector_service_url": "http://localhost:5210",
    "timeout": 30.0,
    "max_retries": 3,
    "test_timeout": 300.0,
    "performance_test_vectors": 1000,
    "isolation_test_projects": 3,
    "vectors_per_project": 30,
}
```

### Custom Vector Service URL
```bash
python tests/integration/run_vector_isolation_tests.py --base-url http://localhost:5210
```

## Test Data

### Generated Test Fixtures

Tests use `tests/fixtures/vector_test_data.py` to generate realistic test data:

- **3 Test Projects**: Different languages (en, ru, es)
- **90+ Vectors**: Realistic content in multiple languages
- **Sensitive Content**: Security-sensitive data for leakage testing
- **Performance Data**: 1000+ vectors for load testing

### Test Content

Each language contains domain-specific content:

**English (en)**:
- Machine learning algorithms
- Neural network architectures
- Natural language processing

**Russian (ru)**:
- Machine learning and deep learning content
- Neural networks and architectures
- Natural language processing

**Spanish (es)**:
- Machine learning and automation content
- Neural networks research
- Natural language processing applications

## Test Results Interpretation

### Success Criteria

✅ **All Tests Pass**: No security violations detected
✅ **Zero Data Leakage**: No cross-project or cross-language access
✅ **Filter Enforcement**: All mandatory filters properly applied
✅ **Security Score ≥ 95%**: No critical security issues

### Security Score Calculation

- **Base Score**: 100 points
- **Critical Issues**: -25 points each
- **Security Issues**: -5 points each
- **Minimum Passing**: 95 points

### Performance Metrics

Tests track key performance indicators:

- **Response Time**: Mean, P95, P99 latency
- **Search Performance**: Query execution time
- **Throughput**: Requests per second
- **Resource Usage**: Memory and CPU impact

### Sample Successful Output

```
================================================================================
VECTOR DATABASE ISOLATION TEST RESULTS
================================================================================

📊 Test Execution Summary:
   Total Tests: 13
   Passed: 13
   Failed: 0
   Skipped: 0
   Success Rate: 100.0%
   Duration: 45.23s

🔒 Security Assessment:
   Security Score: 100.0/100
   Security Issues: 0

✅ Requirements Coverage:
   REQ-003: ✅ COVERED
   REQ-008: ✅ COVERED
   SEC-001: ✅ COVERED
   PERF-001: ✅ COVERED
   PERF-002: ✅ COVERED

⚡ Performance Metrics:
   Mean Response Time: 23.45ms
   P95 Response Time: 67.89ms
   P99 Response Time: 123.45ms

🎯 Overall Status: ✅ SUCCESS

🎉 All tests passed - isolation requirements satisfied!
```

## Integration with CI/CD

### GitHub Actions

```yaml
name: Vector Isolation Tests

on: [push, pull_request]

jobs:
  vector-tests:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install Dependencies
      run: |
        cd backend
        pip install -r requirements.txt
        pip install -r requirements-test.txt

    - name: Start Services
      run: make dev-up

    - name: Run Isolation Tests
      run: |
        cd backend
        python tests/integration/run_vector_isolation_tests.py \
          --output isolation-report.json \
          --verbose

    - name: Upload Test Report
      uses: actions/upload-artifact@v3
      with:
        name: isolation-test-report
        path: backend/isolation-report.json
```

### Docker Integration

```dockerfile
# Test stage
FROM python:3.11-slim as test

WORKDIR /app
COPY requirements-test.txt .
RUN pip install -r requirements-test.txt

COPY . .
RUN python backend/tests/integration/run_vector_isolation_tests.py --category all
```

## Troubleshooting

### Common Issues

#### Service Not Available
```
❌ Cannot connect to vector service - ensure it's running
```
**Solution**: Start the development environment:
```bash
make dev-up
```

#### Test Timeouts
```
⏰ Test timeout after 300 seconds
```
**Solution**: Increase timeout in `conftest.py` or check vector service performance.

#### Isolation Test Failures
```
❌ Data leakage detected between projects
```
**Critical**: This indicates a serious security issue. Review filter enforcement implementation.

#### Permission Issues
```
🔒 Access denied during cleanup
```
**Expected**: Cleanup failures are normal due to isolation mechanisms.

### Debug Mode

Run tests with maximum verbosity:
```bash
python tests/integration/run_vector_isolation_tests.py \
  --verbose \
  --category isolation
```

### Test Data Issues

Regenerate test fixtures if needed:
```python
from tests.fixtures.vector_test_data import VectorTestDataGenerator

generator = VectorTestDataGenerator(random_seed=42)
test_data = generator.generate_isolation_test_scenarios()
```

## Contributing

### Adding New Tests

1. **Isolation Tests**: Add to `test_vector_isolation.py`
2. **Security Tests**: Add to `test_vector_security.py`
3. **Fixtures**: Update `vector_test_data.py` if needed
4. **Configuration**: Modify `conftest.py` for new test patterns

### Test Naming Convention

- **Project Isolation**: `test_project_isolation_*`
- **Language Isolation**: `test_language_isolation_*`
- **Security Tests**: `test_*_security` or `test_*_protection`
- **Data Integrity**: `test_data_integrity_*`

### Security Test Guidelines

- Always use realistic sensitive content for leakage testing
- Test both positive (should work) and negative (should fail) scenarios
- Include defense-in-depth validation
- Log security events for audit trails

## References

- **Requirements**: `stories/setup-vector-database/requirements.md`
- **Design**: `stories/setup-vector-database/design.md`
- **API**: `backend/app/api/endpoints/vector.py`
- **Domain**: `backend/app/services/vector/domain/entities.py`
- **Repository**: `backend/app/services/vector/repositories/qdrant_repository.py`

## Support

For issues with the integration tests:

1. Check vector service is running: `make dev-status`
2. Review test logs for specific error messages
3. Verify configuration in `conftest.py`
4. Check requirements.md for implementation details

Remember: **Security is critical** - any isolation test failure must be addressed immediately.