"""Sparkmon MVP - Single file implementation.

Provides CLI commands, metrics collection, and web server for monitoring
DGX Spark clusters. Reuses sparkrun's ClusterMonitor infrastructure.
"""

import click
import flask
import threading
import time
from typing import Optional

from sparkrun.core.monitoring import ClusterMonitor, parse_monitor_line, HostMonitorState


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
        self.metrics: dict[str, list[dict]] = {host: [] for host in hosts}
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
                    # Trim old samples to prevent memory growth
                    if len(self.metrics[host]) > self.max_samples:
                        self.metrics[host] = self.metrics[host][-self.max_samples:]
        except Exception as e:
            # Handle stream errors gracefully
            pass


# ---------------------------------------------------------------------------
# Web Server
# ---------------------------------------------------------------------------

_web_app: Optional[flask.Flask] = None
_collector_ref: Optional[SparkmonCollector] = None


def create_web_app():
    """Create and configure the Flask web application."""
    global _web_app
    
    app = flask.Flask(__name__, static_folder='web', static_url_path='')
    
    @app.route('/')
    def index():
        """Serve the main dashboard."""
        return app.send_static_file('index.html')
    
    @app.route('/api/metrics')
    def get_metrics():
        """Get current metrics from all hosts."""
        global _collector_ref
        if not _collector_ref:
            return flask.jsonify({'error': 'monitoring not started'}), 400
        return flask.jsonify(_collector_ref.metrics)
    
    @app.route('/api/status')
    def get_status():
        """Get monitoring status."""
        global _collector_ref
        if not _collector_ref:
            return flask.jsonify({'running': False})
        return flask.jsonify({
            'running': True,
            'hosts': list(_collector_ref.metrics.keys()),
            'interval': _collector_ref.interval,
            'total_hosts': len(_collector_ref.hosts),
        })
    
    @app.route('/api/health')
    def health():
        """Health check endpoint."""
        return flask.jsonify({'status': 'ok'})
    
    _web_app = app
    return app


def run_web_server(port: int = 8080):
    """Run the Flask web server."""
    global _web_app
    if not _web_app:
        _web_app = create_web_app()
    # Run with threaded=True to handle concurrent requests
    _web_app.run(host='0.0.0.0', port=port, debug=False, threaded=True)


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
@click.option("--cluster", "-c", default=None, help="Use named cluster definition")
@click.option("--hosts", "-H", default=None, help="Comma-separated list of hosts")
@click.option("--ssh-user", default=None, help="SSH username")
@click.option("--ssh-key", default=None, help="Path to SSH private key")
@click.pass_context
def start(ctx, web: bool, interval: int, port: int, cluster: Optional[str],
          hosts: Optional[str], ssh_user: Optional[str], ssh_key: Optional[str]):
    """Start cluster monitoring.
    
    Launches parallel SSH streams to collect system metrics from all
    specified hosts. If --web is provided, starts a web dashboard at
    http://localhost:<port>.
    """
    from sparkrun.cli._common import _resolve_hosts_or_exit
    from sparkrun.core.config import SparkrunConfig
    from sparkrun.orchestration.primitives import build_ssh_kwargs
    
    # Load config
    config = SparkrunConfig()
    
    # Resolve hosts
    try:
        host_list, _ = _resolve_hosts_or_exit(hosts, None, cluster, config)
    except SystemExit:
        raise
    
    if not host_list:
        click.echo("Error: No hosts specified. Use --hosts or --cluster.", err=True)
        ctx.exit(1)
    
    # Build SSH kwargs from config
    ssh_kwargs = build_ssh_kwargs(config)
    
    # Override with CLI options if provided
    if ssh_user:
        ssh_kwargs['ssh_user'] = ssh_user
    if ssh_key:
        ssh_kwargs['ssh_key'] = ssh_key
    
    click.echo(f"Starting monitoring on {len(host_list)} host(s): {', '.join(host_list)}")
    click.echo(f"Sampling interval: {interval}s")
    
    # Start collector
    global _collector_ref
    _collector_ref = SparkmonCollector(host_list, ssh_kwargs, interval)
    _collector_ref.start()
    
    click.echo("Collector started...")
    
    if web:
        # Start web server in background thread
        def start_server():
            click.echo(f"Starting web UI at http://localhost:{port}")
            run_web_server(port)
        
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()
        
        # Give server time to start
        time.sleep(1)
        click.echo("Web UI available at http://localhost:{}".format(port))
        click.echo("Press Ctrl-C to stop monitoring")
    
    # Block until Ctrl-C
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
        if _collector_ref:
            _collector_ref.stop()
        click.echo("Monitoring stopped.")


@sparkmon.command("stop")
def stop():
    """Stop monitoring.
    
    Note: This is a placeholder. In the MVP, monitoring is stopped
    by pressing Ctrl-C in the start process.
    """
    click.echo("To stop monitoring, use Ctrl-C in the start process.")
    click.echo("Persistent monitoring management (systemd, etc.) will be added in a future release.")


@sparkmon.command("status")
@click.option("--cluster", "-c", default=None, help="Use named cluster definition")
@click.option("--hosts", "-H", default=None, help="Comma-separated list of hosts")
@click.option("--ssh-user", default=None, help="SSH username")
@click.option("--ssh-key", default=None, help="Path to SSH private key")
@click.pass_context
def status(ctx, cluster: Optional[str], hosts: Optional[str],
           ssh_user: Optional[str], ssh_key: Optional[str]):
    """Show monitoring status and latest metrics.
    
    Fetches the latest metrics from all hosts and displays a summary.
    """
    from sparkrun.cli._common import _resolve_hosts_or_exit
    from sparkrun.core.config import SparkrunConfig
    from sparkrun.orchestration.primitives import build_ssh_kwargs
    
    # Load config
    config = SparkrunConfig()
    
    # Resolve hosts
    try:
        host_list, _ = _resolve_hosts_or_exit(hosts, None, cluster, config)
    except SystemExit:
        return
    
    if not host_list:
        click.echo("Error: No hosts specified. Use --hosts or --cluster.", err=True)
        ctx.exit(1)
    
    # Build SSH kwargs from config
    ssh_kwargs = build_ssh_kwargs(config)
    
    # Override with CLI options if provided
    if ssh_user:
        ssh_kwargs['ssh_user'] = ssh_user
    if ssh_key:
        ssh_kwargs['ssh_key'] = ssh_key
    
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
@click.option("--cluster", "-c", default=None, help="Use named cluster definition")
@click.option("--hosts", "-H", default=None, help="Comma-separated list of hosts")
@click.option("--duration", "-d", default=60, help="Duration in seconds to collect")
@click.option("--output", "-o", default=None, help="Output file path (default: stdout)")
@click.option("--ssh-user", default=None, help="SSH username")
@click.option("--ssh-key", default=None, help="Path to SSH private key")
@click.pass_context
def export(ctx, cluster: Optional[str], hosts: Optional[str], duration: int,
           output: Optional[str], ssh_user: Optional[str], ssh_key: Optional[str]):
    """Export metrics to a file.
    
    Collects metrics for the specified duration and outputs as JSON.
    """
    import json
    from sparkrun.cli._common import _resolve_hosts_or_exit
    
    # Resolve hosts
    # Load config
    config = SparkrunConfig()
    
    # Resolve hosts
    try:
        host_list, _ = _resolve_hosts_or_exit(hosts, None, cluster, config)
    except SystemExit:
        return
    
    if not host_list:
        click.echo("Error: No hosts specified. Use --hosts or --cluster.", err=True)
        ctx.exit(1)
    
    # Build SSH kwargs from config
    ssh_kwargs = build_ssh_kwargs(config)
    
    # Override with CLI options if provided
    if ssh_user:
        ssh_kwargs['ssh_user'] = ssh_user
    if ssh_key:
        ssh_kwargs['ssh_key'] = ssh_key
    
    click.echo(f"Collecting metrics for {duration} seconds from {len(host_list)} host(s)...")
    
    collector = SparkmonCollector(host_list, ssh_kwargs, interval=2, max_samples=duration//2 + 10)
    collector.start()
    
    # Wait for collection
    time.sleep(duration)
    
    # Prepare export data
    export_data = {
        'cluster': cluster or 'manual',
        'hosts': host_list,
        'duration_sec': duration,
        'interval_sec': 2,
        'samples': collector.metrics,
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
def demo(hosts: str, port: int):
    """Start demo mode with mock data (no real DGX Spark nodes needed)."""
    host_list = [h.strip() for h in hosts.split(",") if h.strip()]
    
    click.echo(f"Starting DEMO mode on {len(host_list)} mock host(s): {', '.join(host_list)}")
    
    global _collector_ref
    
    # Create a simple mock collector
    class MockCollector:
        def __init__(self, hosts):
            self.hosts = hosts
            self.metrics = {host: [] for host in hosts}
            self.interval = 2
            self._started = False
        
        def start(self):
            self._started = True
            click.echo("Mock collector started...")
        
        def stop(self):
            self._started = False
            click.echo("Mock collector stopped.")
    
    _collector_ref = MockCollector(host_list)
    
    # Start web server
    def start_server():
        import threading
        import time
        
        # Add mock data in background
        def add_mock_data():
            while _collector_ref._started:
                for host in host_list:
                    mock = generate_mock_metrics(host)
                    _collector_ref.metrics[host].append(mock)
                    # Keep last 60 samples
                    if len(_collector_ref.metrics[host]) > 60:
                        _collector_ref.metrics[host] = _collector_ref.metrics[host][-60:]
                time.sleep(2)
        
        mock_thread = threading.Thread(target=add_mock_data, daemon=True)
        mock_thread.start()
        
        click.echo(f"Demo web UI available at http://localhost:{port}")
        run_web_server(port)
    
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    time.sleep(1)
    click.echo("Press Ctrl-C to stop demo mode")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nShutting down demo...")
        if _collector_ref:
            _collector_ref.stop()
