# Vector Database Performance Testing Suite

Comprehensive performance benchmarking suite for the JEEX vector database system, validating requirements from the "Setup Vector Database" story.

## 📋 Requirements Validation

This performance testing suite validates the following requirements:

- **REQ-007**: Query Performance Optimization - P95 latency < 100ms
- **PERF-001**: Search Performance - P95 < 100ms at 100K vectors
- **PERF-002**: Indexing Performance - Batch upsert ≥ 200 vectors/second
- **SCALE-002**: Concurrent Query Capacity - ≥ 100 QPS

## 🏗️ Architecture

```
tests/performance/
├── test_vector_performance.py    # Core performance benchmark tests
├── benchmark_runner.py           # Main benchmark orchestrator
├── performance_reporter.py       # Results analysis and visualization
├── config.py                     # Centralized configuration
├── requirements.txt              # Performance testing dependencies
└── README.md                     # This file
```

### Core Components

1. **VectorPerformanceBenchmark**: Main benchmarking engine
2. **PerformanceBenchmarkRunner**: Orchestrates test execution
3. **PerformanceReporter**: Generates comprehensive reports
4. **PerformanceMonitor**: System resource monitoring
5. **VectorDataGenerator**: Realistic test data generation

## 🚀 Quick Start

### Prerequisites

1. **Qdrant Running**: Ensure Qdrant is running on localhost:5230
2. **Python 3.11+**: Required for the vector database system
3. **Dependencies**: Install performance testing dependencies

```bash
# Install performance testing dependencies
cd backend
pip install -r tests/performance/requirements.txt
```

### Running Benchmarks

#### Option 1: Complete Benchmark Suite
```bash
# Run full benchmark suite
python -m tests.performance.benchmark_runner

# Run with custom output directory
python -m tests.performance.benchmark_runner --output-dir my_results

# Run quick benchmark suite (CI/CD mode)
python -m tests.performance.benchmark_runner --quick
```

#### Option 2: Individual Test Categories
```bash
# Run only search performance tests
pytest tests/performance/test_vector_performance.py::TestVectorPerformance::test_search_performance_scaling -v -m performance

# Run all performance tests with pytest
pytest tests/performance/ -v -m performance --asyncio-mode=auto

# Run with coverage
pytest tests/performance/ -v --cov=app.services.vector -m performance
```

#### Option 3: Docker Environment
```bash
# Run benchmarks in development environment
make test-performance

# Or using docker-compose directly
docker-compose exec api python -m tests.performance.benchmark_runner
```

## 📊 Benchmark Categories

### 1. Search Performance (`test_search_performance_scaling`)
- **Purpose**: Validate REQ-007 and PERF-001 requirements
- **Metrics**: P50, P95, P99 latency across dataset sizes
- **Dataset Sizes**: 1K, 10K, 50K, 100K vectors
- **Target**: P95 latency < 100ms

### 2. Upsert Performance (`test_upsert_performance_batch_sizes`)
- **Purpose**: Validate PERF-002 requirement
- **Metrics**: Throughput (vectors/second) across batch sizes
- **Batch Sizes**: 10, 50, 100 vectors per batch
- **Target**: ≥ 200 vectors/second

### 3. Concurrent Search (`test_concurrent_search_capacity`)
- **Purpose**: Validate SCALE-002 requirement
- **Metrics**: QPS (queries per second) at different concurrency levels
- **Concurrency Levels**: 1, 10, 50, 100 concurrent queries
- **Target**: ≥ 100 QPS

### 4. Filter Performance (`test_filter_performance`)
- **Purpose**: Validate search performance with mandatory filters
- **Metrics**: Latency overhead with project/language/document filters
- **Filter Combinations**: Project + Language + Type + Importance
- **Target**: Filter overhead < 20ms

### 5. Scaling Analysis (`benchmark_concurrent_search`)
- **Purpose**: Analyze performance scaling characteristics
- **Metrics**: Latency and resource usage vs dataset size
- **Analysis**: Memory usage, CPU utilization, scaling factors
- **Target**: Linear or sub-linear performance degradation

## 📈 Performance Targets

| Metric | Target | Requirement |
|--------|--------|-------------|
| Search P95 Latency | < 100ms | REQ-007, PERF-001 |
| Search P99 Latency | < 200ms | Best practice |
| Upsert Throughput | ≥ 200 vectors/s | PERF-002 |
| Concurrent QPS | ≥ 100 queries/s | SCALE-002 |
| Memory Usage | < 1GB for 100K vectors | Scalability |
| CPU Usage | < 80% under load | Resource efficiency |

## 📋 Configuration

### Environment Configuration
The performance suite supports different environments:

```python
# Development (default)
config = PerformanceTestConfig("development")

# CI/CD (quick mode)
config = PerformanceTestConfig("ci")

# Production (comprehensive)
config = PerformanceTestConfig("production")
```

### Quick Mode Configuration
For CI/CD environments, enable quick mode:
- Reduced dataset sizes: [1K, 5K] instead of [1K, 10K, 50K, 100K]
- Fewer iterations: 3 instead of 10
- Disabled charts and reports

### HNSW Configuration
The tests use the HNSW configuration from the story:
- `m=0`: Number of bi-directional links
- `payload_m=16`: Payload index size
- `ef_construct=100`: Index build accuracy
- `full_scan_threshold=10000`: Switch to full scan threshold

## 📊 Reports and Output

### Generated Reports

1. **HTML Dashboard**: Interactive performance dashboard
   - File: `performance_dashboard_YYYYMMDD_HHMMSS.html`
   - Contains: Summary cards, requirements validation, performance tables

2. **CSV Export**: Raw data for further analysis
   - File: `benchmark_results_YYYYMMDD_HHMMSS.csv`
   - Contains: All benchmark metrics in tabular format

3. **Trend Analysis**: Performance regression detection
   - File: `trend_analysis_YYYYMMDD_HHMMSS.json`
   - Contains: Historical comparison and trend indicators

4. **Performance Charts**: Visual performance analysis
   - Directory: `charts/`
   - Contains: PNG charts for performance scaling

### Report Structure
```
performance_results/
├── performance_dashboard_20231020_143022.html
├── benchmark_results_20231020_143022.csv
├── trend_analysis_20231020_143022.json
├── benchmark_summary_20231020_143022.json
└── charts/
    ├── search_performance_20231020_143022.png
    ├── upsert_performance_20231020_143022.png
    └── scaling_analysis_20231020_143022.png
```

## 🔍 Performance Monitoring

### Resource Monitoring
The suite monitors system resources during benchmarks:
- **Memory Usage**: RSS memory consumption
- **CPU Usage**: Process CPU percentage
- **Disk I/O**: Storage read/write operations
- **Network Latency**: Qdrant communication overhead

### Statistical Analysis
- **Percentiles**: P50, P95, P99 latency measurements
- **Throughput**: Operations per second calculations
- **Error Rates**: Failed operation tracking
- **Resource Efficiency**: Performance per resource unit

## 🚨 Performance Alerts

### Threshold-Based Alerts
The system generates alerts for performance regressions:
- **Critical**: 2x degradation from targets
- **Warning**: 1.5x degradation from targets
- **Info**: Performance changes exceeding 10%

### Regression Detection
- Compares current results with historical baselines
- Uses statistical significance testing
- Requires minimum 3 historical samples
- Flags degradations with 80% confidence

## 🔧 Troubleshooting

### Common Issues

#### Qdrant Connection Failed
```bash
# Check if Qdrant is running
docker-compose ps qdrant

# Restart Qdrant if needed
docker-compose restart qdrant
```

#### Performance Tests Failing
```bash
# Check system resources
docker stats

# Monitor Qdrant logs
docker-compose logs -f qdrant

# Run with verbose output
pytest tests/performance/ -v -s
```

#### Memory Issues
```bash
# Reduce dataset sizes for testing
python -m tests.performance.benchmark_runner --quick

# Monitor memory usage
docker stats --format "table {{.Container}}\t{{.MemUsage}}"
```

### Performance Tuning

#### HNSW Optimization
```python
# For faster search (higher memory usage)
hnsw_config.m = 16
hnsw_config.ef_construct = 200

# For lower memory usage (slower search)
hnsw_config.m = 8
hnsw_config.ef_construct = 64
```

#### Batch Size Optimization
- **Small batches (10-50)**: Lower latency, higher overhead
- **Medium batches (50-100)**: Balanced performance
- **Large batches (100+)**: Higher throughput, higher latency

## 📝 Development Guidelines

### Adding New Benchmarks

1. **Create Test Method**:
```python
async def test_new_benchmark_category(self, performance_setup):
    repository, search_service, collection_name = performance_setup
    benchmark = VectorPerformanceBenchmark(repository, search_service)

    metrics = await benchmark.benchmark_new_feature(...)

    # Validate against targets
    assert metrics.throughput >= TARGET_VALUE
```

2. **Add to Benchmark Runner**:
```python
suite_results["results"]["new_category"] = await self._run_new_benchmarks(benchmark)
```

3. **Update Configuration**:
```python
BENCHMARK_CATEGORIES["new_category"] = {
    "description": "...",
    "requirements": ["NEW-001"],
    "metrics": ["throughput", "latency"],
}
```

### Performance Best Practices

1. **Warmup**: Always include warmup iterations
2. **Isolation**: Use isolated test collections
3. **Cleanup**: Clean up test data after completion
4. **Statistics**: Use statistical analysis for reliability
5. **Resources**: Monitor resource usage during tests

## 📚 Reference Documentation

- [Vector Database Implementation](../../../app/services/vector/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [HNSW Algorithm](https://arxiv.org/abs/1603.09320)
- [Pytest Benchmarking](https://pytest-benchmark.readthedocs.io/)

## 🤝 Contributing

1. **Fork** the repository
2. **Create** a feature branch
3. **Add** performance tests for new features
4. **Validate** against performance targets
5. **Submit** a pull request with performance impact analysis

## 📄 License

This performance testing suite is part of the JEEX project and follows the same license terms.