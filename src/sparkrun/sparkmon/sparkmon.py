"""Sparkmon MVP - Single file implementation.

Provides CLI commands, metrics collection, and web server for monitoring
DGX Spark clusters. Reuses sparkrun's ClusterMonitor infrastructure.
"""

import collections
import logging
import click
import threading
import time
from typing import Optional

try:
    import flask
except ImportError:
    flask = None  # type: ignore[assignment]

from sparkrun.core.monitoring import ClusterMonitor, parse_monitor_line, HostMonitorState

logger = logging.getLogger(__name__)


# Re-use the shared host_options decorator from the main CLI.
# Import lazily in functions that need it for config/host resolution.
def _host_options(f):
    """Host-targeting options matching the main CLI: --hosts, --hosts-file, --cluster."""
    f = click.option("--cluster", "cluster_name", default=None,
                     help="Use a saved cluster by name")(f)
    f = click.option("--hosts-file", default=None,
                     help="File with hosts (one per line, # comments)")(f)
    f = click.option("--hosts", "-H", default=None,
                     help="Comma-separated host list")(f)
    return f


def _resolve_sparkmon_hosts(ctx, hosts, hosts_file, cluster_name):
    """Resolve hosts and SSH kwargs for sparkmon commands.

    Returns:
        Tuple of ``(host_list, ssh_kwargs)``.
    """
    from sparkrun.cli._common import _resolve_hosts_or_exit
    from sparkrun.core.config import SparkrunConfig
    from sparkrun.orchestration.primitives import build_ssh_kwargs

    config = SparkrunConfig()

    try:
        host_list, _ = _resolve_hosts_or_exit(hosts, hosts_file, cluster_name, config)
    except SystemExit:
        raise

    if not host_list:
        click.echo("Error: No hosts specified. Use --hosts or --cluster.", err=True)
        ctx.exit(1)

    ssh_kwargs = build_ssh_kwargs(config)
    return host_list, ssh_kwargs


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class SparkmonCollector(ClusterMonitor):
    """Simplified collector storing metrics in memory.
    
    Extends sparkrun's ClusterMonitor to collect system metrics from
    multiple hosts via SSH and store them in memory for the web UI.
    """
    
    def __init__(self, hosts: list[str], ssh_kwargs: dict, interval: int = 2, max_samples: int = 60):
        super().__init__(hosts, ssh_kwargs, interval)
        self.max_samples = max_samples
        self.metrics: dict[str, collections.deque] = {
            host: collections.deque(maxlen=max_samples) for host in hosts
        }
        self._started = False

    def _reader(self, host: str, proc) -> None:
        """Override to store parsed metrics in memory."""
        try:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                sample = parse_monitor_line(line)
                if sample:
                    metric = {
                        'timestamp': sample.timestamp,
                        'hostname': sample.hostname,
                        'gpu_util_pct': sample.gpu_util_pct,
                        'gpu_mem_used_pct': sample.gpu_mem_used_pct,
                        'gpu_temp_c': sample.gpu_temp_c,
                        'cpu_usage_pct': sample.cpu_usage_pct,
                        'mem_used_pct': sample.mem_used_pct,
                        'mem_used_mb': sample.mem_used_mb,
                        'mem_total_mb': sample.mem_total_mb,
                        'sparkrun_jobs': sample.sparkrun_jobs,
                        'gpu_power_w': sample.gpu_power_w,
                        'gpu_power_limit_w': sample.gpu_power_limit_w,
                    }
                    self.metrics[host].append(metric)
        except Exception:
            logger.debug("Reader error for host %s", host, exc_info=True)


# ---------------------------------------------------------------------------
# Web Server
# ---------------------------------------------------------------------------

_web_app: Optional[flask.Flask] = None


def _require_flask():
    """Raise a clear error if Flask is not installed."""
    if flask is None:
        raise click.ClickException(
            "Flask is required for sparkmon web features. "
            "Install with: pip install sparkrun[monitoring]"
        )


def create_web_app(collector=None):
    """Create and configure the Flask web application."""
    _require_flask()
    global _web_app

    app = flask.Flask(__name__, static_folder='web', static_url_path='')
    app.config["collector"] = collector

    @app.route('/')
    def index():
        """Serve the main dashboard."""
        return app.send_static_file('index.html')

    @app.route('/api/metrics')
    def get_metrics():
        """Get current metrics from all hosts."""
        coll = flask.current_app.config.get("collector")
        if not coll:
            return flask.jsonify({'error': 'monitoring not started'}), 400
        return flask.jsonify({host: list(samples) for host, samples in coll.metrics.items()})

    @app.route('/api/status')
    def get_status():
        """Get monitoring status."""
        coll = flask.current_app.config.get("collector")
        if not coll:
            return flask.jsonify({'running': False})
        return flask.jsonify({
            'running': True,
            'hosts': list(coll.metrics.keys()),
            'interval': coll.interval,
            'total_hosts': len(coll.hosts),
        })

    @app.route('/api/health')
    def health():
        """Health check endpoint."""
        return flask.jsonify({'status': 'ok'})

    _web_app = app
    return app


def run_web_server(port: int = 8080, bind: str = "127.0.0.1", collector=None):
    """Run the Flask web server."""
    global _web_app
    if not _web_app:
        _web_app = create_web_app(collector=collector)
    _web_app.run(host=bind, port=port, debug=False, threaded=True)


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

@click.group()
def sparkmon():
    """Monitor DGX Spark cluster metrics.
    
    Real-time monitoring of CPU, GPU, memory, and temperature across
    multiple DGX Spark nodes via SSH. Provides a web-based dashboard
    for visualization.
    
    Examples:
        # Start monitoring with web UI
        sparkrun sparkmon start --web --hosts=gx10-1a2b,gx10-3c4d
        
        # Use a named cluster
        sparkrun sparkmon start --web --cluster=my-cluster
        
        # Custom interval and port
        sparkrun sparkmon start --web --interval=5 --port=9090
        
        # Check status
        sparkrun sparkmon status
        
        # Stop monitoring
        sparkrun sparkmon stop
    """
    pass


@sparkmon.command("start")
@click.option("--web", is_flag=True, help="Start web UI server")
@click.option("--interval", "-i", default=2, help="Sampling interval in seconds")
@click.option("--port", "-p", default=8080, help="Web UI port (default: 8080)")
@click.option("--bind", default="127.0.0.1", help="Web UI bind address (default: 127.0.0.1)")
@_host_options
@click.pass_context
def start(ctx, web: bool, interval: int, port: int, bind: str,
          hosts: Optional[str], hosts_file: Optional[str], cluster_name: Optional[str]):
    """Start cluster monitoring.

    Launches parallel SSH streams to collect system metrics from all
    specified hosts. If --web is provided, starts a web dashboard at
    http://localhost:<port>.
    """
    host_list, ssh_kwargs = _resolve_sparkmon_hosts(ctx, hosts, hosts_file, cluster_name)

    click.echo(f"Starting monitoring on {len(host_list)} host(s): {', '.join(host_list)}")
    click.echo(f"Sampling interval: {interval}s")

    # Start collector
    collector = SparkmonCollector(host_list, ssh_kwargs, interval)
    collector.start()

    click.echo("Collector started...")

    if web:
        # Start web server in background thread
        def start_server():
            click.echo(f"Starting web UI at http://{bind}:{port}")
            run_web_server(port, bind=bind, collector=collector)

        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        # Give server time to start
        time.sleep(1)
        click.echo("Web UI available at http://{}:{}".format(bind, port))
        click.echo("Press Ctrl-C to stop monitoring")

    # Block until Ctrl-C
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
        collector.stop()
        click.echo("Monitoring stopped.")


@sparkmon.command("stop", hidden=True)
def stop():
    """Stop monitoring.

    Note: This is a placeholder. In the MVP, monitoring is stopped
    by pressing Ctrl-C in the start process.
    """
    click.echo("To stop monitoring, use Ctrl-C in the start process.")
    click.echo("Persistent monitoring management (systemd, etc.) will be added in a future release.")


@sparkmon.command("status")
@_host_options
@click.pass_context
def status(ctx, hosts: Optional[str], hosts_file: Optional[str],
           cluster_name: Optional[str]):
    """Show monitoring status and latest metrics.

    Fetches the latest metrics from all hosts and displays a summary.
    """
    host_list, ssh_kwargs = _resolve_sparkmon_hosts(ctx, hosts, hosts_file, cluster_name)

    # Quick one-shot collection
    click.echo(f"Collecting metrics from {len(host_list)} host(s)...")
    
    collector = SparkmonCollector(host_list, ssh_kwargs, interval=2)
    collector.start()
    
    # Wait for first sample
    time.sleep(3)
    
    # Display status
    click.echo("\n{:<20} {:>8} {:>10} {:>10} {:>10} {:>8}".format(
        "Host", "GPU%", "GPU Mem%", "GPU Temp", "CPU%", "Status"))
    click.echo("-" * 70)
    
    for host, samples in collector.metrics.items():
        if samples:
            latest = samples[-1]
            gpu = latest.get('gpu_util_pct', 'N/A') or 'N/A'
            gpu_mem = latest.get('gpu_mem_used_pct', 'N/A') or 'N/A'
            gpu_temp = latest.get('gpu_temp_c', 'N/A') or 'N/A'
            cpu = latest.get('cpu_usage_pct', 'N/A') or 'N/A'
            status = "OK"
        else:
            gpu = gpu_mem = gpu_temp = cpu = "N/A"
            status = "ERROR"
        
        click.echo("{:<20} {:>8} {:>10} {:>10} {:>10} {:>8}".format(
            host[:20], gpu, gpu_mem, gpu_temp, cpu, status))
    
    collector.stop()


@sparkmon.command("export")
@_host_options
@click.option("--duration", "-d", default=60, help="Duration in seconds to collect")
@click.option("--output", "-o", default=None, help="Output file path (default: stdout)")
@click.pass_context
def export(ctx, hosts: Optional[str], hosts_file: Optional[str],
           cluster_name: Optional[str], duration: int, output: Optional[str]):
    """Export metrics to a file.

    Collects metrics for the specified duration and outputs as JSON.
    """
    import json

    host_list, ssh_kwargs = _resolve_sparkmon_hosts(ctx, hosts, hosts_file, cluster_name)

    click.echo(f"Collecting metrics for {duration} seconds from {len(host_list)} host(s)...")
    
    collector = SparkmonCollector(host_list, ssh_kwargs, interval=2, max_samples=duration//2 + 10)
    collector.start()
    
    # Wait for collection
    time.sleep(duration)
    
    # Prepare export data
    export_data = {
        'cluster': cluster_name or 'manual',
        'hosts': host_list,
        'duration_sec': duration,
        'interval_sec': 2,
        'samples': {host: list(samples) for host, samples in collector.metrics.items()},
    }
    
    # Output
    json_str = json.dumps(export_data, indent=2)
    
    if output:
        with open(output, 'w') as f:
            f.write(json_str)
        click.echo(f"Metrics exported to {output}")
    else:
        click.echo(json_str)
    
    collector.stop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    sparkmon()


# ---------------------------------------------------------------------------
# Mock Data Generator (for testing without real DGX Spark nodes)
# ---------------------------------------------------------------------------

def generate_mock_metrics(host: str) -> dict:
    """Generate realistic mock metrics for testing."""
    import random
    from datetime import datetime
    
    return {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'hostname': host,
        'gpu_util_pct': str(random.uniform(45, 95)),
        'gpu_mem_used_pct': str(random.uniform(50, 90)),
        'gpu_temp_c': str(random.uniform(55, 75)),
        'cpu_usage_pct': str(random.uniform(20, 60)),
        'mem_used_pct': str(random.uniform(40, 70)),
        'mem_used_mb': str(random.randint(32000, 64000)),
        'mem_total_mb': '128000',
        'sparkrun_jobs': str(random.randint(1, 3)),
    }


# Add mock mode to start command
@sparkmon.command("demo")
@click.option("--hosts", "-H", default="node1,node2,node3", help="Comma-separated mock host names")
@click.option("--port", "-p", default=8080, help="Web UI port")
@click.option("--bind", default="127.0.0.1", help="Web UI bind address (default: 127.0.0.1)")
def demo(hosts: str, port: int, bind: str):
    """Start demo mode with mock data (no real DGX Spark nodes needed)."""
    host_list = [h.strip() for h in hosts.split(",") if h.strip()]

    click.echo(f"Starting DEMO mode on {len(host_list)} mock host(s): {', '.join(host_list)}")

    # Create a simple mock collector
    class MockCollector:
        def __init__(self, hosts):
            self.hosts = hosts
            self.metrics = {host: collections.deque(maxlen=60) for host in hosts}
            self.interval = 2
            self._started = False

        def start(self):
            self._started = True
            click.echo("Mock collector started...")

        def stop(self):
            self._started = False
            click.echo("Mock collector stopped.")

    collector = MockCollector(host_list)

    # Start web server
    def start_server():
        # Add mock data in background
        def add_mock_data():
            while collector._started:
                for host in host_list:
                    mock = generate_mock_metrics(host)
                    collector.metrics[host].append(mock)
                time.sleep(2)

        mock_thread = threading.Thread(target=add_mock_data, daemon=True)
        mock_thread.start()

        click.echo(f"Demo web UI available at http://{bind}:{port}")
        run_web_server(port, bind=bind, collector=collector)

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    time.sleep(1)
    click.echo("Press Ctrl-C to stop demo mode")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nShutting down demo...")
        collector.stop()
