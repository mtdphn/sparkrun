"""Tests for sparkmon — DGX Spark cluster monitoring system."""

from __future__ import annotations

import collections
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from sparkrun.sparkmon.sparkmon import (
    SparkmonCollector,
    create_web_app,
    generate_mock_metrics,
    sparkmon,
)
from sparkrun.core.monitoring import MONITOR_COLUMNS


# =====================================================================
# Helpers
# =====================================================================

def _make_csv_line(**overrides) -> str:
    """Build a valid host_monitor.sh CSV line (27 fields).

    All fields default to placeholder values.  Pass keyword overrides
    matching MONITOR_COLUMNS names to set specific fields.
    """
    defaults = {
        "timestamp": "2026-03-13T12:00:00",
        "hostname": "gx10-test",
        "uptime_sec": "12345",
        "cpu_load_1m": "1.0",
        "cpu_load_5m": "0.8",
        "cpu_load_15m": "0.5",
        "cpu_usage_pct": "25.0",
        "cpu_freq_mhz": "3500",
        "cpu_temp_c": "45",
        "mem_total_mb": "128000",
        "mem_used_mb": "64000",
        "mem_available_mb": "64000",
        "mem_used_pct": "50.0",
        "swap_total_mb": "0",
        "swap_used_mb": "0",
        "gpu_name": "GH200",
        "gpu_util_pct": "75.0",
        "gpu_mem_used_mb": "64000",
        "gpu_mem_total_mb": "131072",
        "gpu_mem_used_pct": "48.8",
        "gpu_temp_c": "62",
        "gpu_power_w": "200",
        "gpu_power_limit_w": "300",
        "gpu_clock_mhz": "1500",
        "gpu_mem_clock_mhz": "1200",
        "sparkrun_jobs": "1",
        "sparkrun_job_names": "sparkrun_abc_solo",
    }
    defaults.update(overrides)
    return ",".join(defaults[col] for col in MONITOR_COLUMNS)


def _make_mock_proc(lines: list[str]):
    """Create a mock subprocess.Popen with stdout yielding *lines*."""
    proc = MagicMock()
    proc.stdout = iter(lines)
    return proc


# =====================================================================
# SparkmonCollector
# =====================================================================

class TestSparkmonCollector:
    """Tests for SparkmonCollector metric storage."""

    def test_init_creates_deques(self):
        """Metrics dict is initialized with deque per host."""
        hosts = ["host-a", "host-b"]
        collector = SparkmonCollector(hosts, ssh_kwargs={}, interval=2, max_samples=30)

        assert set(collector.metrics.keys()) == {"host-a", "host-b"}
        for d in collector.metrics.values():
            assert isinstance(d, collections.deque)
            assert d.maxlen == 30

    def test_reader_stores_parsed_metrics(self):
        """_reader parses CSV lines and appends metric dicts to the deque."""
        hosts = ["host-a"]
        collector = SparkmonCollector(hosts, ssh_kwargs={}, interval=2, max_samples=60)

        line1 = _make_csv_line(gpu_util_pct="80.0", cpu_usage_pct="30.0")
        line2 = _make_csv_line(gpu_util_pct="90.0", cpu_usage_pct="40.0")
        proc = _make_mock_proc([line1, line2])

        collector._reader("host-a", proc)

        assert len(collector.metrics["host-a"]) == 2
        first = collector.metrics["host-a"][0]
        assert first["gpu_util_pct"] == "80.0"
        assert first["cpu_usage_pct"] == "30.0"
        assert first["hostname"] == "gx10-test"

        second = collector.metrics["host-a"][1]
        assert second["gpu_util_pct"] == "90.0"

    def test_reader_skips_empty_lines(self):
        """Empty and whitespace-only lines are ignored."""
        hosts = ["host-a"]
        collector = SparkmonCollector(hosts, ssh_kwargs={}, interval=2)

        line = _make_csv_line()
        proc = _make_mock_proc(["", "   ", line, ""])

        collector._reader("host-a", proc)
        assert len(collector.metrics["host-a"]) == 1

    def test_reader_skips_malformed_lines(self):
        """Lines with wrong field count are ignored."""
        hosts = ["host-a"]
        collector = SparkmonCollector(hosts, ssh_kwargs={}, interval=2)

        valid = _make_csv_line()
        malformed = "only,three,fields"
        proc = _make_mock_proc([malformed, valid])

        collector._reader("host-a", proc)
        assert len(collector.metrics["host-a"]) == 1

    def test_deque_maxlen_enforced(self):
        """Deque automatically trims old samples beyond max_samples."""
        hosts = ["host-a"]
        collector = SparkmonCollector(hosts, ssh_kwargs={}, interval=2, max_samples=3)

        lines = [_make_csv_line(gpu_util_pct=str(i)) for i in range(10)]
        proc = _make_mock_proc(lines)

        collector._reader("host-a", proc)

        assert len(collector.metrics["host-a"]) == 3
        # Should contain the last 3 samples
        assert collector.metrics["host-a"][0]["gpu_util_pct"] == "7"
        assert collector.metrics["host-a"][2]["gpu_util_pct"] == "9"

    def test_reader_logs_exceptions(self):
        """Exceptions in _reader are logged, not swallowed silently."""
        hosts = ["host-a"]
        collector = SparkmonCollector(hosts, ssh_kwargs={}, interval=2)

        # Proc whose stdout raises on iteration
        proc = MagicMock()
        proc.stdout = MagicMock()
        proc.stdout.__iter__ = MagicMock(side_effect=OSError("broken pipe"))

        with patch("sparkrun.sparkmon.sparkmon.logger") as mock_logger:
            collector._reader("host-a", proc)
            mock_logger.debug.assert_called_once()
            assert "host-a" in str(mock_logger.debug.call_args)

    def test_metric_dict_has_expected_keys(self):
        """Each stored metric dict contains all expected fields."""
        hosts = ["host-a"]
        collector = SparkmonCollector(hosts, ssh_kwargs={}, interval=2)

        proc = _make_mock_proc([_make_csv_line()])
        collector._reader("host-a", proc)

        metric = collector.metrics["host-a"][0]
        expected_keys = {
            "timestamp", "hostname",
            "gpu_util_pct", "gpu_mem_used_pct", "gpu_temp_c",
            "cpu_usage_pct", "mem_used_pct", "mem_used_mb", "mem_total_mb",
            "sparkrun_jobs", "gpu_power_w", "gpu_power_limit_w",
        }
        assert expected_keys.issubset(metric.keys())


# =====================================================================
# Flask web app
# =====================================================================

class TestWebApp:
    """Tests for the Flask web application and API routes."""

    @pytest.fixture(autouse=True)
    def reset_web_app(self):
        """Reset the module-level _web_app global between tests."""
        import sparkrun.sparkmon.sparkmon as mod
        mod._web_app = None
        yield
        mod._web_app = None

    def _make_collector_with_data(self):
        """Create a collector with pre-populated metrics."""
        hosts = ["host-a", "host-b"]
        collector = SparkmonCollector(hosts, ssh_kwargs={}, interval=2, max_samples=60)

        for host in hosts:
            proc = _make_mock_proc([_make_csv_line(hostname=host)])
            collector._reader(host, proc)

        return collector

    def test_health_endpoint(self):
        """GET /api/health returns 200 with status ok."""
        app = create_web_app()
        client = app.test_client()

        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}

    def test_metrics_without_collector_returns_400(self):
        """GET /api/metrics returns 400 when no collector is set."""
        app = create_web_app(collector=None)
        client = app.test_client()

        resp = client.get("/api/metrics")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_metrics_with_collector(self):
        """GET /api/metrics returns host metrics as JSON lists."""
        collector = self._make_collector_with_data()
        app = create_web_app(collector=collector)
        client = app.test_client()

        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "host-a" in data
        assert "host-b" in data
        # Should be serialized as lists (not deques)
        assert isinstance(data["host-a"], list)
        assert len(data["host-a"]) == 1
        assert data["host-a"][0]["hostname"] == "host-a"

    def test_status_without_collector(self):
        """GET /api/status returns running=False when no collector."""
        app = create_web_app(collector=None)
        client = app.test_client()

        resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.get_json()["running"] is False

    def test_status_with_collector(self):
        """GET /api/status returns host info when collector is active."""
        collector = self._make_collector_with_data()
        app = create_web_app(collector=collector)
        client = app.test_client()

        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["running"] is True
        assert set(data["hosts"]) == {"host-a", "host-b"}
        assert data["total_hosts"] == 2
        assert data["interval"] == 2

    def test_index_serves_html(self):
        """GET / serves the dashboard HTML."""
        app = create_web_app()
        client = app.test_client()

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"sparkmon" in resp.data


# =====================================================================
# generate_mock_metrics
# =====================================================================

class TestGenerateMockMetrics:
    """Tests for the mock metrics generator."""

    def test_returns_expected_keys(self):
        """Mock metrics dict contains all required keys."""
        mock = generate_mock_metrics("test-host")
        expected_keys = {
            "timestamp", "hostname",
            "gpu_util_pct", "gpu_mem_used_pct", "gpu_temp_c",
            "cpu_usage_pct", "mem_used_pct", "mem_used_mb", "mem_total_mb",
            "sparkrun_jobs",
        }
        assert expected_keys.issubset(mock.keys())

    def test_hostname_matches(self):
        """Mock metrics hostname matches the input."""
        mock = generate_mock_metrics("my-node")
        assert mock["hostname"] == "my-node"

    def test_values_are_strings(self):
        """All values are strings (matching real monitor output)."""
        mock = generate_mock_metrics("node-1")
        for key, value in mock.items():
            assert isinstance(value, str), f"{key} should be str, got {type(value)}"

    def test_timestamp_format(self):
        """Timestamp ends with Z (UTC marker)."""
        mock = generate_mock_metrics("node-1")
        assert mock["timestamp"].endswith("Z")


# =====================================================================
# CLI commands
# =====================================================================

class TestSparkmonCLI:
    """Tests for sparkmon CLI commands."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_sparkmon_help(self, runner):
        """sparkmon --help shows the group help text."""
        result = runner.invoke(sparkmon, ["--help"])
        assert result.exit_code == 0
        assert "Monitor DGX Spark cluster metrics" in result.output

    def test_start_help(self, runner):
        """sparkmon start --help shows start options."""
        result = runner.invoke(sparkmon, ["start", "--help"])
        assert result.exit_code == 0
        assert "--web" in result.output
        assert "--interval" in result.output
        assert "--port" in result.output
        assert "--bind" in result.output

    def test_stop_shows_placeholder_message(self, runner):
        """sparkmon stop shows the placeholder message."""
        result = runner.invoke(sparkmon, ["stop"])
        assert result.exit_code == 0
        assert "Ctrl-C" in result.output

    def test_status_no_hosts_error(self, runner):
        """sparkmon status without hosts shows an error."""
        with patch("sparkrun.core.config.SparkrunConfig"):
            with patch(
                "sparkrun.cli._common._resolve_hosts_or_exit",
                side_effect=SystemExit(1),
            ):
                result = runner.invoke(sparkmon, ["status", "--hosts", ""])
                # Should exit non-zero when no hosts resolved
                assert result.exit_code != 0 or "Error" in result.output or result.exit_code == 1

    @patch("sparkrun.sparkmon.sparkmon.time.sleep")
    @patch("sparkrun.sparkmon.sparkmon.SparkmonCollector")
    @patch("sparkrun.orchestration.primitives.build_ssh_kwargs", return_value={})
    @patch("sparkrun.core.config.SparkrunConfig")
    @patch("sparkrun.cli._common._resolve_hosts_or_exit", return_value=(["host-a", "host-b"], None))
    def test_status_displays_table(self, mock_resolve, mock_config, mock_ssh, mock_collector_cls, mock_sleep, runner):
        """sparkmon status collects metrics and displays a table."""
        # Set up mock collector with pre-populated metrics
        mock_collector = MagicMock()
        mock_collector.metrics = {
            "host-a": [{"gpu_util_pct": "80.0", "gpu_mem_used_pct": "50.0", "gpu_temp_c": "62", "cpu_usage_pct": "25.0"}],
            "host-b": [],
        }
        mock_collector_cls.return_value = mock_collector

        result = runner.invoke(sparkmon, ["status", "--hosts", "host-a,host-b"])
        assert result.exit_code == 0
        assert "host-a" in result.output
        assert "host-b" in result.output
        assert "OK" in result.output
        assert "ERROR" in result.output  # host-b has no samples
        mock_collector.start.assert_called_once()
        mock_collector.stop.assert_called_once()

    @patch("sparkrun.sparkmon.sparkmon.SparkmonCollector")
    @patch("sparkrun.orchestration.primitives.build_ssh_kwargs", return_value={})
    @patch("sparkrun.core.config.SparkrunConfig")
    @patch("sparkrun.cli._common._resolve_hosts_or_exit", return_value=(["host-a"], None))
    def test_export_outputs_json(self, mock_resolve, mock_config, mock_ssh, mock_collector_cls, runner, tmp_path):
        """sparkmon export writes valid JSON to file."""
        mock_collector = MagicMock()
        mock_collector.metrics = {
            "host-a": collections.deque([
                {"gpu_util_pct": "80.0", "timestamp": "2026-03-13T12:00:00"},
            ], maxlen=60),
        }
        mock_collector_cls.return_value = mock_collector

        output_file = str(tmp_path / "metrics.json")

        with patch("sparkrun.sparkmon.sparkmon.time.sleep"):
            result = runner.invoke(sparkmon, [
                "export", "--hosts", "host-a",
                "--duration", "1", "--output", output_file,
            ])

        assert result.exit_code == 0
        assert "exported" in result.output.lower() or "Collecting" in result.output

        with open(output_file) as f:
            data = json.load(f)
        assert data["hosts"] == ["host-a"]
        assert "samples" in data
        assert isinstance(data["samples"]["host-a"], list)

    @patch("sparkrun.sparkmon.sparkmon.SparkmonCollector")
    @patch("sparkrun.orchestration.primitives.build_ssh_kwargs", return_value={})
    @patch("sparkrun.core.config.SparkrunConfig")
    @patch("sparkrun.cli._common._resolve_hosts_or_exit", return_value=(["host-a"], None))
    def test_export_to_stdout(self, mock_resolve, mock_config, mock_ssh, mock_collector_cls, runner):
        """sparkmon export without --output prints JSON to stdout."""
        mock_collector = MagicMock()
        mock_collector.metrics = {
            "host-a": collections.deque([
                {"gpu_util_pct": "80.0"},
            ], maxlen=60),
        }
        mock_collector_cls.return_value = mock_collector

        with patch("sparkrun.sparkmon.sparkmon.time.sleep"):
            result = runner.invoke(sparkmon, [
                "export", "--hosts", "host-a", "--duration", "1",
            ])

        assert result.exit_code == 0
        # Output should contain valid JSON
        # Find the JSON portion (after the "Collecting..." message)
        lines = result.output.strip().split("\n")
        json_start = next(i for i, l in enumerate(lines) if l.strip().startswith("{"))
        json_text = "\n".join(lines[json_start:])
        data = json.loads(json_text)
        assert "samples" in data

    def test_export_help(self, runner):
        """sparkmon export --help shows export options."""
        result = runner.invoke(sparkmon, ["export", "--help"])
        assert result.exit_code == 0
        assert "--duration" in result.output
        assert "--output" in result.output

    def test_demo_help(self, runner):
        """sparkmon demo --help shows demo options."""
        result = runner.invoke(sparkmon, ["demo", "--help"])
        assert result.exit_code == 0
        assert "--hosts" in result.output
        assert "--port" in result.output
        assert "--bind" in result.output


# =====================================================================
# Deque serialization
# =====================================================================

class TestDequeSerialization:
    """Verify deque-to-list conversion at serialization boundaries."""

    def test_metrics_endpoint_returns_lists(self):
        """The /api/metrics endpoint converts deques to JSON-serializable lists."""
        hosts = ["host-a"]
        collector = SparkmonCollector(hosts, ssh_kwargs={}, interval=2, max_samples=10)

        proc = _make_mock_proc([_make_csv_line(), _make_csv_line()])
        collector._reader("host-a", proc)

        app = create_web_app(collector=collector)
        client = app.test_client()

        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        data = resp.get_json()
        # json.loads would have failed if deque wasn't converted
        assert isinstance(data["host-a"], list)
        assert len(data["host-a"]) == 2

    def test_export_serializes_deque(self):
        """json.dumps on export data works with deque metrics."""
        metrics = {"host-a": collections.deque([{"val": 1}, {"val": 2}], maxlen=10)}
        export_data = {
            "samples": {host: list(samples) for host, samples in metrics.items()},
        }
        # Should not raise TypeError
        result = json.dumps(export_data)
        parsed = json.loads(result)
        assert len(parsed["samples"]["host-a"]) == 2
