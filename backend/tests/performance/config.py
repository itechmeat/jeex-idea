"""
Performance testing configuration.

Centralizes all performance test parameters, targets, and environment settings
for the vector database benchmark suite.
"""

from dataclasses import dataclass
from typing import Dict, List, Any
from pathlib import Path


@dataclass
class PerformanceTargets:
    """Performance target values from requirements specification."""

    # Search performance targets (REQ-007, PERF-001)
    search_p95_latency_ms: float = 100.0
    search_p99_latency_ms: float = 200.0
    search_p50_latency_ms: float = 50.0

    # Upsert performance targets (PERF-002)
    upsert_throughput_vectors_per_second: float = 200.0
    upsert_p95_latency_ms: float = 500.0

    # Concurrent query targets (SCALE-002)
    concurrent_qps: float = 100.0
    concurrent_p95_latency_ms: float = 150.0

    # Resource usage targets
    max_memory_usage_mb: float = 1024.0  # 1GB for 100K vectors
    max_cpu_usage_percent: float = 80.0

    # Scaling targets
    max_latency_degradation_factor: float = 2.0  # Latency shouldn't more than double


@dataclass
class TestConfiguration:
    """Configuration for performance test execution."""

    # Dataset sizes for scaling tests
    dataset_sizes: List[int] = None

    # Batch sizes for upsert testing
    batch_sizes: List[int] = None

    # Concurrency levels for load testing
    concurrency_levels: List[int] = None

    # Test execution parameters
    warmup_iterations: int = 3
    benchmark_iterations: int = 10
    timeout_seconds: int = 30

    # Vector configuration (matching OpenAI embeddings)
    vector_dimension: int = 1536
    embedding_range: tuple = (-1.0, 1.0)

    # Test data parameters
    max_content_length: int = 1000
    metadata_field_count: int = 5
    importance_range: tuple = (0.3, 1.0)

    # Resource monitoring
    monitoring_interval_seconds: float = 0.5
    enable_detailed_profiling: bool = False

    # Quick test mode (for CI/CD)
    quick_mode: bool = False
    quick_dataset_sizes: List[int] = None
    quick_iterations: int = 3

    def __post_init__(self):
        """Initialize default values if not provided."""
        if self.dataset_sizes is None:
            self.dataset_sizes = [1000, 10000, 50000, 100000]

        if self.batch_sizes is None:
            self.batch_sizes = [10, 50, 100]

        if self.concurrency_levels is None:
            self.concurrency_levels = [1, 10, 50, 100]

        if self.quick_dataset_sizes is None:
            self.quick_dataset_sizes = [1000, 5000]


@dataclass
class EnvironmentConfiguration:
    """Environment-specific configuration for performance testing."""

    # Qdrant connection settings
    qdrant_host: str = "localhost"
    qdrant_port: int = 5230
    qdrant_timeout: int = 30

    # Test isolation
    test_collection_prefix: str = "jeex_benchmark_"
    max_test_collections: int = 10

    # Output configuration
    results_directory: str = "performance_results"
    enable_charts: bool = True
    enable_html_reports: bool = True
    enable_csv_exports: bool = True
    enable_trend_analysis: bool = True

    # Cleanup settings
    cleanup_test_data: bool = True
    retention_days: int = 7


@dataclass
class HNSWConfiguration:
    """HNSW index configuration for optimal performance."""

    # Current configuration from the story
    m: int = 0  # Number of bi-directional links
    payload_m: int = 16  # Payload index size
    ef_construct: int = 100  # Index build time/accuracy tradeoff
    full_scan_threshold: int = 10000
    indexing_threshold: int = 20000

    # Optimization parameters
    ef_runtime: int = 64  # Search time/accuracy tradeoff
    max_indexing_threads: int = 4


class PerformanceTestConfig:
    """
    Main configuration class for vector database performance testing.

    Provides centralized access to all configuration parameters and
    validates configuration consistency.
    """

    def __init__(self, environment: str = "development"):
        """
        Initialize performance test configuration.

        Args:
            environment: Environment name (development, staging, production)
        """
        self.environment = environment
        self.targets = PerformanceTargets()
        self.test_config = TestConfiguration()
        self.env_config = EnvironmentConfiguration()
        self.hnsw_config = HNSWConfiguration()

        # Apply environment-specific overrides
        self._apply_environment_overrides()

        # Validate configuration
        self._validate_configuration()

    def _apply_environment_overrides(self):
        """Apply environment-specific configuration overrides."""
        # Validate environment value
        allowed_environments = {"ci", "production", "development"}
        if self.environment not in allowed_environments:
            raise ValueError(
                f"Unsupported environment '{self.environment}'. "
                f"Allowed values: {', '.join(sorted(allowed_environments))}"
            )

        if self.environment == "ci":
            # CI/CD environment - faster tests
            self.test_config.quick_mode = True
            self.test_config.benchmark_iterations = 3
            self.test_config.warmup_iterations = 1
            self.env_config.enable_charts = False
            self.env_config.cleanup_test_data = True

        elif self.environment == "production":
            # Production environment - comprehensive testing
            self.test_config.enable_detailed_profiling = True
            self.env_config.enable_charts = True
            self.env_config.enable_html_reports = True
            self.env_config.cleanup_test_data = False

    def _validate_configuration(self):
        """Validate configuration consistency and requirements."""
        # Validate that quick mode dataset sizes are smaller
        if self.test_config.quick_mode:
            for size in self.test_config.quick_dataset_sizes:
                if size > max(self.test_config.dataset_sizes):
                    raise ValueError(
                        f"Quick dataset size {size} exceeds standard sizes"
                    )

        # Validate HNSW configuration consistency
        if self.hnsw_config.m < 0:
            raise ValueError("HNSW M parameter must be non-negative")

        if self.hnsw_config.ef_construct <= 0:
            raise ValueError("HNSW ef_construct must be positive")

        # Validate performance targets are reasonable
        if self.targets.search_p95_latency_ms >= self.targets.search_p99_latency_ms:
            raise ValueError("P95 latency target should be less than P99")

        if self.targets.concurrent_qps <= 0:
            raise ValueError("Concurrent QPS target must be positive")

    def get_dataset_sizes(self) -> List[int]:
        """Get dataset sizes based on test mode."""
        if self.test_config.quick_mode:
            return self.test_config.quick_dataset_sizes
        return self.test_config.dataset_sizes

    def get_iterations(self) -> int:
        """Get number of iterations based on test mode."""
        if self.test_config.quick_mode:
            return self.test_config.quick_iterations
        return self.test_config.benchmark_iterations

    def get_output_directory(self) -> Path:
        """Get output directory for results."""
        base_dir = Path(self.env_config.results_directory)
        env_dir = base_dir / self.environment
        env_dir.mkdir(parents=True, exist_ok=True)
        return env_dir

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for serialization."""
        return {
            "environment": self.environment,
            "targets": self.targets.__dict__,
            "test_config": self.test_config.__dict__,
            "env_config": self.env_config.__dict__,
            "hnsw_config": self.hnsw_config.__dict__,
        }

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "PerformanceTestConfig":
        """Create configuration from dictionary."""
        # Extract environment from dict or use default
        environment = config_dict.get("environment", "development")

        # Create instance with specific environment
        config = cls(environment=environment)

        # Override configuration components from dict if provided
        if "targets" in config_dict:
            config.targets = PerformanceTargets(**config_dict["targets"])
        if "test_config" in config_dict:
            config.test_config = TestConfiguration(**config_dict["test_config"])
        if "env_config" in config_dict:
            config.env_config = EnvironmentConfiguration(**config_dict["env_config"])
        if "hnsw_config" in config_dict:
            config.hnsw_config = HNSWConfiguration(**config_dict["hnsw_config"])

        # Re-apply environment overrides and validation after setting components
        config._apply_environment_overrides()
        config._validate_configuration()

        return config


# Global configuration instance
DEFAULT_CONFIG = PerformanceTestConfig()


def get_config(environment: str = None) -> PerformanceTestConfig:
    """
    Get performance test configuration.

    Args:
        environment: Optional environment override

    Returns:
        PerformanceTestConfig instance
    """
    if environment:
        return PerformanceTestConfig(environment)
    return DEFAULT_CONFIG


# Performance test data templates
CONTENT_TEMPLATES = [
    "Machine learning algorithms transform data into insights through statistical patterns and computational methods.",
    "Vector databases enable efficient similarity search using high-dimensional embeddings and approximate nearest neighbors.",
    "Project isolation ensures data security by enforcing strict boundaries between different user contexts.",
    "Natural language processing models understand semantic relationships through contextual embeddings.",
    "Distributed systems maintain consistency and availability through coordination protocols and fault tolerance.",
    "Cloud computing provides scalable infrastructure with elastic resource allocation and load balancing.",
    "Artificial intelligence systems learn from training data to make predictions and decisions.",
    "Software architecture patterns guide the design of maintainable and scalable applications.",
    "Database optimization techniques improve query performance through indexing and caching strategies.",
    "Security frameworks protect sensitive data through encryption, authentication, and access control.",
]

TEST_METADATA_SCHEMAS = {
    "technical": ["algorithm", "optimization", "scalability", "performance"],
    "business": ["strategy", "planning", "analysis", "metrics"],
    "research": ["methodology", "experimentation", "validation", "results"],
}

DOCUMENT_TYPES = ["knowledge", "memory", "agent_context"]

LANGUAGES = ["en", "es", "fr", "de", "it", "pt", "ja", "ko"]

# Performance threshold definitions for alerts
PERFORMANCE_THRESHOLDS = {
    "critical": {
        "search_p95_latency_ms": 200.0,
        "upsert_throughput_vectors_per_second": 100.0,
        "concurrent_qps": 50.0,
        "memory_usage_mb": 2048.0,
    },
    "warning": {
        "search_p95_latency_ms": 150.0,
        "upsert_throughput_vectors_per_second": 150.0,
        "concurrent_qps": 75.0,
        "memory_usage_mb": 1536.0,
    },
}


def get_performance_threshold(level: str = "warning") -> Dict[str, float]:
    """
    Get performance threshold values for alerting.

    Args:
        level: Threshold level ("critical", "warning")

    Returns:
        Dictionary of threshold values
    """
    return PERFORMANCE_THRESHOLDS.get(level, PERFORMANCE_THRESHOLDS["warning"])


# Benchmark test categories and descriptions
BENCHMARK_CATEGORIES = {
    "search_performance": {
        "description": "Search latency and throughput performance across dataset sizes",
        "requirements": ["REQ-007", "PERF-001"],
        "metrics": [
            "latency_p50",
            "latency_p95",
            "latency_p99",
            "throughput",
            "error_rate",
        ],
    },
    "upsert_performance": {
        "description": "Batch upsert throughput and latency performance",
        "requirements": ["PERF-002"],
        "metrics": ["throughput", "latency_p95", "batch_efficiency", "error_rate"],
    },
    "concurrent_search": {
        "description": "Concurrent query capacity and scalability",
        "requirements": ["SCALE-002"],
        "metrics": ["qps", "latency_p95", "concurrency_efficiency", "error_rate"],
    },
    "filter_performance": {
        "description": "Search performance with various filter combinations",
        "requirements": ["REQ-007"],
        "metrics": ["latency_p95", "filter_overhead", "selectivity_impact"],
    },
    "scaling_analysis": {
        "description": "Performance scaling analysis with dataset size",
        "requirements": ["PERF-001"],
        "metrics": ["latency_scaling", "memory_scaling", "throughput_scaling"],
    },
}


def get_benchmark_category_info(category: str) -> Dict[str, Any]:
    """
    Get information about a benchmark category.

    Args:
        category: Benchmark category name

    Returns:
        Category information dictionary
    """
    return BENCHMARK_CATEGORIES.get(
        category,
        {
            "description": "Unknown benchmark category",
            "requirements": [],
            "metrics": [],
        },
    )


# Performance regression detection settings
REGRESSION_DETECTION = {
    "min_samples": 3,  # Minimum historical samples for trend analysis
    "regression_threshold": 10.0,  # Percentage change to flag as regression
    "trend_window_days": 30,  # Days to consider for trend analysis
    "alert_on_degradation": True,
    "require_confidence": 0.8,  # Statistical confidence level
}


def get_regression_detection_config() -> Dict[str, Any]:
    """Get regression detection configuration."""
    return REGRESSION_DETECTION.copy()
