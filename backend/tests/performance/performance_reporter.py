"""
Performance reporter for vector database benchmark results.

Generates comprehensive reports including:
- HTML performance dashboard
- CSV data exports
- Trend analysis and regression detection
- Performance visualizations
- Executive summary reports
"""

import json
import csv
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import pandas as pd


@dataclass
class PerformanceTrend:
    """Represents performance trend analysis over time."""

    metric_name: str
    current_value: float
    baseline_value: float
    trend_direction: str  # 'improving', 'degrading', 'stable'
    trend_percentage: float
    significance_level: str  # 'high', 'medium', 'low'


class PerformanceReporter:
    """
    Generates comprehensive performance reports from benchmark results.

    Creates multiple report formats including HTML dashboard, CSV exports,
    trend analysis, and performance visualizations.
    """

    def __init__(self, output_dir: Path):
        """
        Initialize performance reporter.

        Args:
            output_dir: Directory to save generated reports
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)

        # Configure plotting style
        plt.style.use("seaborn-v0_8")
        sns.set_palette("husl")

        # Performance targets for trend analysis
        self.targets = {
            "search_p95_latency_ms": 100.0,
            "upsert_throughput_vectors_per_second": 200.0,
            "concurrent_qps": 100.0,
            "memory_usage_mb": 1000.0,
        }

    async def generate_html_report(self, results: Dict[str, Any]) -> str:
        """
        Generate comprehensive HTML performance dashboard.

        Args:
            results: Benchmark results dictionary

        Returns:
            Path to generated HTML report
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_file = self.output_dir / f"performance_dashboard_{timestamp}.html"

        # Generate HTML content
        html_content = self._generate_html_dashboard(results)

        # Write HTML file
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Generate supporting assets
        await self._generate_performance_charts(results, timestamp)

        print(f"📊 HTML dashboard generated: {html_file}")
        return str(html_file)

    async def generate_csv_report(self, results: Dict[str, Any]) -> str:
        """
        Generate CSV export of all benchmark results.

        Args:
            results: Benchmark results dictionary

        Returns:
            Path to generated CSV file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = self.output_dir / f"benchmark_results_{timestamp}.csv"

        # Flatten results for CSV export
        flat_results = self._flatten_results_for_csv(results)

        # Write CSV file
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            if flat_results:
                writer = csv.DictWriter(f, fieldnames=flat_results[0].keys())
                writer.writeheader()
                writer.writerows(flat_results)

        print(f"📈 CSV report generated: {csv_file}")
        return str(csv_file)

    async def generate_trend_analysis(self, results: Dict[str, Any]) -> str:
        """
        Generate trend analysis report comparing with historical data.

        Args:
            results: Current benchmark results

        Returns:
            Path to generated trend analysis report
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trend_file = self.output_dir / f"trend_analysis_{timestamp}.json"

        # Load historical data if available
        historical_data = await self._load_historical_data()

        # Analyze trends
        trends = self._analyze_performance_trends(results, historical_data)

        # Generate trend report
        trend_report = {
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "current_results": results,
            "historical_baseline": historical_data,
            "trends": trends,
            "recommendations": self._generate_recommendations(trends),
        }

        # Save trend analysis
        with open(trend_file, "w", encoding="utf-8") as f:
            json.dump(trend_report, f, indent=2, default=str)

        # Update historical data with current results
        await self._update_historical_data(results)

        print(f"📉 Trend analysis generated: {trend_file}")
        return str(trend_file)

    def _generate_html_dashboard(self, results: Dict[str, Any]) -> str:
        """Generate HTML dashboard content."""

        html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vector Database Performance Dashboard</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f7;
            color: #1d1d1f;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 {
            margin: 0;
            font-size: 2.5em;
            font-weight: 600;
        }
        .header .timestamp {
            margin-top: 10px;
            opacity: 0.9;
            font-size: 1.1em;
        }
        .summary-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f9fafb;
        }
        .card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            border-left: 4px solid #667eea;
        }
        .card h3 {
            margin: 0 0 10px 0;
            color: #4b5563;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .card .value {
            font-size: 2em;
            font-weight: bold;
            color: #1d1d1f;
            margin-bottom: 5px;
        }
        .card .unit {
            color: #6b7280;
            font-size: 0.9em;
        }
        .card.success { border-left-color: #10b981; }
        .card.warning { border-left-color: #f59e0b; }
        .card.error { border-left-color: #ef4444; }
        .content {
            padding: 30px;
        }
        .section {
            margin-bottom: 40px;
        }
        .section h2 {
            color: #1d1d1f;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }
        .requirements-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .requirement {
            background: #f9fafb;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #ddd;
        }
        .requirement.passed { border-left-color: #10b981; background: #f0fdf4; }
        .requirement.failed { border-left-color: #ef4444; background: #fef2f2; }
        .requirement h4 {
            margin: 0 0 10px 0;
            color: #1d1d1f;
        }
        .requirement .status {
            font-weight: bold;
            font-size: 1.1em;
        }
        .requirement.passed .status { color: #059669; }
        .requirement.failed .status { color: #dc2626; }
        .requirement .details {
            margin-top: 10px;
            font-size: 0.9em;
            color: #6b7280;
        }
        .chart-container {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            margin-bottom: 20px;
        }
        .chart-container h3 {
            margin: 0 0 15px 0;
            color: #1d1d1f;
        }
        .table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .table th {
            background: #f3f4f6;
            padding: 15px;
            text-align: left;
            font-weight: 600;
            color: #1d1d1f;
            border-bottom: 2px solid #e5e7eb;
        }
        .table td {
            padding: 15px;
            border-bottom: 1px solid #f3f4f6;
        }
        .table tr:hover {
            background: #f9fafb;
        }
        .performance-metric {
            font-weight: 600;
        }
        .performance-good { color: #059669; }
        .performance-warning { color: #d97706; }
        .performance-bad { color: #dc2626; }
        .footer {
            background: #f9fafb;
            padding: 20px;
            text-align: center;
            color: #6b7280;
            border-top: 1px solid #e5e7eb;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Vector Database Performance Dashboard</h1>
            <div class="timestamp">Generated on {timestamp}</div>
        </div>

        <div class="summary-cards">
            {summary_cards}
        </div>

        <div class="content">
            <div class="section">
                <h2>📋 Requirements Validation</h2>
                <div class="requirements-grid">
                    {requirements_validation}
                </div>
            </div>

            <div class="section">
                <h2>🔍 Search Performance</h2>
                {search_performance_section}
            </div>

            <div class="section">
                <h2>📝 Upsert Performance</h2>
                {upsert_performance_section}
            </div>

            <div class="section">
                <h2>⚡ Concurrent Performance</h2>
                {concurrent_performance_section}
            </div>

            <div class="section">
                <h2>📈 Scaling Analysis</h2>
                {scaling_analysis_section}
            </div>
        </div>

        <div class="footer">
            <p>Generated by JEEX Vector Database Performance Benchmark Suite</p>
        </div>
    </div>
</body>
</html>
        """

        # Generate summary cards
        summary_cards = self._generate_summary_cards(results)

        # Generate requirements validation
        requirements_validation = self._generate_requirements_cards(results)

        # Generate performance sections
        search_performance = self._generate_performance_table(
            results.get("results", {}).get("search_performance", []),
            "Search Performance Metrics",
        )

        upsert_performance = self._generate_performance_table(
            results.get("results", {}).get("upsert_performance", []),
            "Upsert Performance Metrics",
        )

        concurrent_performance = self._generate_performance_table(
            results.get("results", {}).get("concurrent_search", []),
            "Concurrent Search Performance",
        )

        scaling_analysis = self._generate_scaling_analysis_section(results)

        return html_template.format(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            summary_cards=summary_cards,
            requirements_validation=requirements_validation,
            search_performance_section=search_performance,
            upsert_performance_section=upsert_performance,
            concurrent_performance_section=concurrent_performance,
            scaling_analysis_section=scaling_analysis,
        )

    def _generate_summary_cards(self, results: Dict[str, Any]) -> str:
        """Generate summary cards HTML."""
        summary = results.get("summary", {})
        highlights = summary.get("performance_highlights", {})

        cards = []

        # Total benchmarks card
        cards.append(f"""
        <div class="card">
            <h3>Total Benchmarks</h3>
            <div class="value">{summary.get("total_benchmarks", 0)}</div>
            <div class="unit">executed</div>
        </div>
        """)

        # Success rate card
        total = summary.get("total_benchmarks", 1)
        successful = summary.get("successful_benchmarks", 0)
        success_rate = (successful / total) * 100
        cards.append(f"""
        <div class="card success">
            <h3>Success Rate</h3>
            <div class="value">{success_rate:.1f}%</div>
            <div class="unit">{successful}/{total} successful</div>
        </div>
        """)

        # Best search latency card
        if "best_search_p95" in highlights:
            latency = highlights["best_search_p95"]
            status_class = (
                "success"
                if latency <= self.targets["search_p95_latency_ms"]
                else "warning"
            )
            cards.append(f"""
            <div class="card {status_class}">
                <h3>Best Search P95</h3>
                <div class="value">{latency:.1f}</div>
                <div class="unit">milliseconds</div>
            </div>
            """)

        # Best upsert throughput card
        if "best_upsert_throughput" in highlights:
            throughput = highlights["best_upsert_throughput"]
            status_class = (
                "success"
                if throughput >= self.targets["upsert_throughput_vectors_per_second"]
                else "warning"
            )
            cards.append(f"""
            <div class="card {status_class}">
                <h3>Best Upsert Rate</h3>
                <div class="value">{throughput:.0f}</div>
                <div class="unit">vectors/second</div>
            </div>
            """)

        # Best QPS card
        if "best_qps" in highlights:
            qps = highlights["best_qps"]
            status_class = (
                "success" if qps >= self.targets["concurrent_qps"] else "warning"
            )
            cards.append(f"""
            <div class="card {status_class}">
                <h3>Best QPS</h3>
                <div class="value">{qps:.0f}</div>
                <div class="unit">queries/second</div>
            </div>
            """)

        return "\n".join(cards)

    def _generate_requirements_cards(self, results: Dict[str, Any]) -> str:
        """Generate requirements validation cards HTML."""
        validation = results.get("requirements_validation", {})
        cards = []

        requirements_info = {
            "req_007_query_performance": {
                "title": "REQ-007: Query Performance",
                "description": "P95 latency < 100ms",
                "target": "100ms",
            },
            "perf_001_search_performance": {
                "title": "PERF-001: Search Performance",
                "description": "P95 < 100ms at 100K vectors",
                "target": "100ms",
            },
            "perf_002_indexing_performance": {
                "title": "PERF-002: Indexing Performance",
                "description": "Batch upsert ≥ 200 vectors/second",
                "target": "200 vectors/s",
            },
            "scale_002_concurrent_capacity": {
                "title": "SCALE-002: Concurrent Capacity",
                "description": "≥ 100 QPS",
                "target": "100 QPS",
            },
        }

        for req_key, req_info in requirements_info.items():
            req_result = validation.get(req_key, {"passed": False, "details": []})
            status_class = "passed" if req_result["passed"] else "failed"
            status_text = "✅ PASS" if req_result["passed"] else "❌ FAIL"

            details_html = ""
            if req_result["details"]:
                details_html = "<div class='details'>"
                for detail in req_result["details"]:
                    details_html += f"• {detail}<br>"
                details_html += "</div>"

            cards.append(f"""
            <div class="requirement {status_class}">
                <h4>{req_info["title"]}</h4>
                <div class="status">{status_text}</div>
                <div class="details">{req_info["description"]} (Target: {req_info["target"]})</div>
                {details_html}
            </div>
            """)

        return "\n".join(cards)

    def _generate_performance_table(
        self, performance_data: List[Dict[str, Any]], title: str
    ) -> str:
        """Generate performance metrics table HTML."""
        if not performance_data:
            return f"<p>No {title.lower()} data available.</p>"

        # Start table
        table_html = f'<table class="table"><thead><tr><th>Dataset Size</th><th>P50 Latency</th><th>P95 Latency</th><th>P99 Latency</th><th>Throughput</th><th>Errors</th></tr></thead><tbody>'

        for result in performance_data:
            dataset_size = result.get("dataset_size", "N/A")
            p50 = result.get("latency_p50", 0)
            p95 = result.get("latency_p95", 0)
            p99 = result.get("latency_p99", 0)
            throughput = result.get("throughput", 0)
            errors = result.get("error_count", 0)

            # Style performance metrics based on targets
            p95_class = self._get_performance_class(
                p95, self.targets["search_p95_latency_ms"], False
            )
            throughput_class = self._get_performance_class(
                throughput, self.targets["upsert_throughput_vectors_per_second"], True
            )

            table_html += f"""
            <tr>
                <td>{dataset_size:,}</td>
                <td class="performance-metric">{p50:.1f}ms</td>
                <td class="performance-metric {p95_class}">{p95:.1f}ms</td>
                <td class="performance-metric">{p99:.1f}ms</td>
                <td class="performance-metric {throughput_class}">{throughput:.1f}</td>
                <td>{errors}</td>
            </tr>
            """

        table_html += "</tbody></table>"
        return f"<h3>{title}</h3>{table_html}"

    def _generate_scaling_analysis_section(self, results: Dict[str, Any]) -> str:
        """Generate scaling analysis section HTML."""
        scaling_data = results.get("results", {}).get("scaling_analysis", {})
        search_scaling = scaling_data.get("search_scaling", [])

        if not search_scaling:
            return "<p>No scaling analysis data available.</p>"

        # Generate scaling table
        table_html = '<table class="table"><thead><tr><th>Dataset Size</th><th>P95 Latency</th><th>Throughput</th><th>Memory Usage</th></tr></thead><tbody>'

        for data in search_scaling:
            dataset_size = data.get("dataset_size", "N/A")
            latency = data.get("latency_p95", 0)
            throughput = data.get("throughput", 0)
            memory = data.get("memory_usage_mb", 0)

            latency_class = self._get_performance_class(
                latency, self.targets["search_p95_latency_ms"], False
            )

            table_html += f"""
            <tr>
                <td>{dataset_size:,}</td>
                <td class="performance-metric {latency_class}">{latency:.1f}ms</td>
                <td class="performance-metric">{throughput:.1f}</td>
                <td class="performance-metric">{memory:.1f}MB</td>
            </tr>
            """

        table_html += "</tbody></table>"

        return f"<h3>Search Performance Scaling</h3>{table_html}"

    def _get_performance_class(
        self, value: float, target: float, higher_is_better: bool
    ) -> str:
        """Get CSS class for performance value based on target."""
        if higher_is_better:
            if value >= target:
                return "performance-good"
            elif value >= target * 0.8:
                return "performance-warning"
            else:
                return "performance-bad"
        else:
            if value <= target:
                return "performance-good"
            elif value <= target * 1.2:
                return "performance-warning"
            else:
                return "performance-bad"

    def _flatten_results_for_csv(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Flatten nested results structure for CSV export."""
        flat_results = []

        # Process search performance results
        search_results = results.get("results", {}).get("search_performance", [])
        for result in search_results:
            flat_result = {
                "category": "search_performance",
                "dataset_size": result.get("dataset_size"),
                "operation": result.get("operation"),
                "duration_ms": result.get("duration_ms"),
                "throughput": result.get("throughput"),
                "latency_p50": result.get("latency_p50"),
                "latency_p95": result.get("latency_p95"),
                "latency_p99": result.get("latency_p99"),
                "error_count": result.get("error_count"),
                "memory_usage_mb": result.get("memory_usage_mb"),
                "cpu_usage_percent": result.get("cpu_usage_percent"),
            }
            flat_results.append(flat_result)

        # Process upsert performance results
        upsert_results = results.get("results", {}).get("upsert_performance", [])
        for result in upsert_results:
            flat_result = {
                "category": "upsert_performance",
                "batch_size": result.get("additional_data", {}).get("batch_size"),
                "dataset_size": result.get("dataset_size"),
                "operation": result.get("operation"),
                "duration_ms": result.get("duration_ms"),
                "throughput": result.get("throughput"),
                "latency_p50": result.get("latency_p50"),
                "latency_p95": result.get("latency_p95"),
                "latency_p99": result.get("latency_p99"),
                "error_count": result.get("error_count"),
                "memory_usage_mb": result.get("memory_usage_mb"),
                "cpu_usage_percent": result.get("cpu_usage_percent"),
            }
            flat_results.append(flat_result)

        # Process concurrent search results
        concurrent_results = results.get("results", {}).get("concurrent_search", [])
        for result in concurrent_results:
            flat_result = {
                "category": "concurrent_search",
                "concurrency": result.get("additional_data", {}).get("concurrency"),
                "dataset_size": result.get("dataset_size"),
                "operation": result.get("operation"),
                "duration_ms": result.get("duration_ms"),
                "throughput": result.get("throughput"),
                "latency_p50": result.get("latency_p50"),
                "latency_p95": result.get("latency_p95"),
                "latency_p99": result.get("latency_p99"),
                "error_count": result.get("error_count"),
                "memory_usage_mb": result.get("memory_usage_mb"),
                "cpu_usage_percent": result.get("cpu_usage_percent"),
            }
            flat_results.append(flat_result)

        return flat_results

    async def _generate_performance_charts(
        self, results: Dict[str, Any], timestamp: str
    ):
        """Generate performance visualization charts."""
        try:
            # Create charts directory
            charts_dir = self.output_dir / "charts"
            charts_dir.mkdir(exist_ok=True)

            # Search performance chart
            search_data = results.get("results", {}).get("search_performance", [])
            if search_data:
                self._create_search_performance_chart(
                    search_data, charts_dir / f"search_performance_{timestamp}.png"
                )

            # Upsert performance chart
            upsert_data = results.get("results", {}).get("upsert_performance", [])
            if upsert_data:
                self._create_upsert_performance_chart(
                    upsert_data, charts_dir / f"upsert_performance_{timestamp}.png"
                )

            # Scaling analysis chart
            scaling_data = (
                results.get("results", {})
                .get("scaling_analysis", {})
                .get("search_scaling", [])
            )
            if scaling_data:
                self._create_scaling_analysis_chart(
                    scaling_data, charts_dir / f"scaling_analysis_{timestamp}.png"
                )

        except ImportError:
            # Matplotlib not available, skip chart generation
            print("⚠️ Matplotlib not available, skipping chart generation")
        except Exception as e:
            print(f"⚠️ Warning: Could not generate charts: {e}")

    def _create_search_performance_chart(
        self, data: List[Dict[str, Any]], output_path: Path
    ):
        """Create search performance visualization."""
        try:
            dataset_sizes = [d["dataset_size"] for d in data]
            p95_latencies = [d["latency_p95"] for d in data]

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(dataset_sizes, p95_latencies, marker="o", linewidth=2, markersize=8)
            ax.axhline(
                y=self.targets["search_p95_latency_ms"],
                color="r",
                linestyle="--",
                label="Target (100ms)",
            )
            ax.fill_between(
                dataset_sizes,
                0,
                self.targets["search_p95_latency_ms"],
                alpha=0.1,
                color="green",
            )

            ax.set_xlabel("Dataset Size (vectors)")
            ax.set_ylabel("P95 Latency (ms)")
            ax.set_title("Search Performance Scaling")
            ax.set_xscale("log")
            ax.grid(True, alpha=0.3)
            ax.legend()

            plt.tight_layout()
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
            plt.close()
        except Exception as e:
            print(f"⚠️ Could not create search performance chart: {e}")

    def _create_upsert_performance_chart(
        self, data: List[Dict[str, Any]], output_path: Path
    ):
        """Create upsert performance visualization."""
        try:
            batch_sizes = [d["additional_data"]["batch_size"] for d in data]
            throughputs = [d["throughput"] for d in data]

            fig, ax = plt.subplots(figsize=(10, 6))
            bars = ax.bar(batch_sizes, throughputs, alpha=0.7)
            ax.axhline(
                y=self.targets["upsert_throughput_vectors_per_second"],
                color="r",
                linestyle="--",
                label="Target (200 vectors/s)",
            )

            # Color bars based on performance
            for bar, throughput in zip(bars, throughputs):
                if throughput >= self.targets["upsert_throughput_vectors_per_second"]:
                    bar.set_color("green")
                else:
                    bar.set_color("orange")

            ax.set_xlabel("Batch Size")
            ax.set_ylabel("Throughput (vectors/second)")
            ax.set_title("Upsert Performance by Batch Size")
            ax.legend()
            ax.grid(True, alpha=0.3)

            plt.tight_layout()
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
            plt.close()
        except Exception as e:
            print(f"⚠️ Could not create upsert performance chart: {e}")

    def _create_scaling_analysis_chart(
        self, data: List[Dict[str, Any]], output_path: Path
    ):
        """Create scaling analysis visualization."""
        try:
            dataset_sizes = [d["dataset_size"] for d in data]
            latencies = [d["latency_p95"] for d in data]
            memory_usage = [d["memory_usage_mb"] for d in data]

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10))

            # Latency scaling
            ax1.plot(
                dataset_sizes,
                latencies,
                marker="o",
                linewidth=2,
                markersize=8,
                color="blue",
                label="P95 Latency",
            )
            ax1.axhline(
                y=self.targets["search_p95_latency_ms"],
                color="r",
                linestyle="--",
                label="Target (100ms)",
            )
            ax1.set_ylabel("P95 Latency (ms)")
            ax1.set_title("Search Latency Scaling")
            ax1.set_xscale("log")
            ax1.grid(True, alpha=0.3)
            ax1.legend()

            # Memory usage scaling
            ax2.plot(
                dataset_sizes,
                memory_usage,
                marker="s",
                linewidth=2,
                markersize=8,
                color="green",
                label="Memory Usage",
            )
            ax2.set_xlabel("Dataset Size (vectors)")
            ax2.set_ylabel("Memory Usage (MB)")
            ax2.set_title("Memory Usage Scaling")
            ax2.set_xscale("log")
            ax2.grid(True, alpha=0.3)
            ax2.legend()

            plt.tight_layout()
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
            plt.close()
        except Exception as e:
            print(f"⚠️ Could not create scaling analysis chart: {e}")

    async def _load_historical_data(self) -> Dict[str, Any]:
        """Load historical benchmark data for trend analysis."""
        try:
            # Look for recent historical data files
            historical_files = list(self.output_dir.glob("trend_analysis_*.json"))
            if historical_files:
                # Sort by modification time and get the most recent
                latest_file = max(historical_files, key=lambda f: f.stat().st_mtime)
                with open(latest_file, "r") as f:
                    return json.load(f)
        except Exception:
            pass

        return {}

    def _analyze_performance_trends(
        self, current_results: Dict[str, Any], historical_data: Dict[str, Any]
    ) -> List[PerformanceTrend]:
        """Analyze performance trends compared to historical baseline."""
        trends = []

        # Extract current metrics
        current_summary = current_results.get("summary", {}).get(
            "performance_highlights", {}
        )

        # Analyze search latency trend
        if (
            "best_search_p95" in current_summary
            and "current_results" in historical_data
        ):
            current_latency = current_summary["best_search_p95"]
            historical_summary = (
                historical_data.get("current_results", {})
                .get("summary", {})
                .get("performance_highlights", {})
            )

            if "best_search_p95" in historical_summary:
                baseline_latency = historical_summary["best_search_p95"]
                trend = self._calculate_trend(
                    current_latency, baseline_latency, "search_p95_latency"
                )
                trends.append(trend)

        return trends

    def _calculate_trend(
        self, current: float, baseline: float, metric_name: str
    ) -> PerformanceTrend:
        """Calculate trend between current and baseline values."""
        if baseline == 0:
            return PerformanceTrend(
                metric_name=metric_name,
                current_value=current,
                baseline_value=baseline,
                trend_direction="stable",
                trend_percentage=0.0,
                significance_level="low",
            )

        change_percentage = ((current - baseline) / baseline) * 100

        # Determine trend direction based on metric type
        if "latency" in metric_name:
            # Lower is better for latency
            if change_percentage < -5:
                direction = "improving"
            elif change_percentage > 5:
                direction = "degrading"
            else:
                direction = "stable"
        else:
            # Higher is better for throughput and other metrics
            if change_percentage > 5:
                direction = "improving"
            elif change_percentage < -5:
                direction = "degrading"
            else:
                direction = "stable"

        # Determine significance level
        abs_change = abs(change_percentage)
        if abs_change > 20:
            significance = "high"
        elif abs_change > 10:
            significance = "medium"
        else:
            significance = "low"

        return PerformanceTrend(
            metric_name=metric_name,
            current_value=current,
            baseline_value=baseline,
            trend_direction=direction,
            trend_percentage=change_percentage,
            significance_level=significance,
        )

    def _generate_recommendations(self, trends: List[PerformanceTrend]) -> List[str]:
        """Generate performance recommendations based on trend analysis."""
        recommendations = []

        for trend in trends:
            if trend.trend_direction == "degrading" and trend.significance_level in [
                "high",
                "medium",
            ]:
                if "latency" in trend.metric_name:
                    recommendations.append(
                        f"Search latency is degrading by {abs(trend.trend_percentage):.1f}% "
                        f"({trend.current_value:.1f}ms vs {trend.baseline_value:.1f}ms). "
                        "Consider optimizing HNSW parameters or increasing indexing resources."
                    )
                elif "throughput" in trend.metric_name:
                    recommendations.append(
                        f"Throughput is degrading by {abs(trend.trend_percentage):.1f}% "
                        f"({trend.current_value:.1f} vs {trend.baseline_value:.1f}). "
                        "Review batch size configurations and resource allocation."
                    )

        if not recommendations:
            recommendations.append(
                "Performance is stable or improving. Continue current configuration."
            )

        return recommendations

    async def _update_historical_data(self, results: Dict[str, Any]):
        """Update historical data with current results."""
        try:
            # Save current results as the latest historical data
            historical_file = self.output_dir / "latest_results.json"
            with open(historical_file, "w") as f:
                json.dump(results, f, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Warning: Could not update historical data: {e}")


# Standalone execution for testing
if __name__ == "__main__":
    import asyncio

    async def test_reporter():
        """Test the performance reporter with sample data."""
        reporter = PerformanceReporter(Path("test_reports"))

        # Sample results
        sample_results = {
            "summary": {
                "total_benchmarks": 10,
                "successful_benchmarks": 9,
                "performance_highlights": {
                    "best_search_p95": 85.2,
                    "best_upsert_throughput": 245.0,
                    "best_qps": 120.0,
                },
            },
            "results": {
                "search_performance": [
                    {
                        "dataset_size": 1000,
                        "latency_p95": 85.2,
                        "latency_p50": 65.1,
                        "latency_p99": 120.5,
                        "throughput": 15.2,
                        "error_count": 0,
                    }
                ],
                "upsert_performance": [
                    {
                        "dataset_size": 1000,
                        "batch_size": 50,
                        "latency_p95": 150.0,
                        "throughput": 245.0,
                        "error_count": 0,
                    }
                ],
            },
            "requirements_validation": {
                "req_007_query_performance": {"passed": True, "details": []},
                "perf_002_indexing_performance": {"passed": True, "details": []},
            },
        }

        # Generate reports
        await reporter.generate_html_report(sample_results)
        await reporter.generate_csv_report(sample_results)
        await reporter.generate_trend_analysis(sample_results)

        print("✅ Test reports generated successfully")

    asyncio.run(test_reporter())
