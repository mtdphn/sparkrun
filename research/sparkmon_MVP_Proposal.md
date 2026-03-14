# Sparkmon MVP Proposal

**Minimum Viable Product** - Deliver core value in 1-2 weeks

---

## Executive Summary

The MVP focuses on **real-time system monitoring** with a **simple web UI**, reusing maximum sparkrun infrastructure. We defer complex features (topology, alerts, storage) to post-MVP iterations.

**Timeline**: 10-14 days  
**Code**: ~800 lines (vs. 2200 for full spec)  
**Value**: Immediate visibility into cluster health during inference runs

---

## MVP Scope

### ✅ IN SCOPE (MVP Features)

| Feature | Description | Priority |
|---------|-------------|----------|
| **Basic CLI** | `sparkrun sparkmon start/stop/status` | Critical |
| **System Metrics Collection** | CPU, GPU, memory, temperature (reuse `host_monitor.sh`) | Critical |
| **Simple Web UI** | Single-page dashboard with real-time charts | Critical |
| **Multi-Host Support** | Monitor 2-8 DGX Spark nodes in parallel | Critical |
| **Real-Time Updates** | WebSocket or polling for live data | Critical |
| **Node Table** | Tabular view of all hosts with current metrics | High |
| **GPU Utilization Chart** | Line chart showing GPU usage over time | High |
| **Memory Chart** | Stacked bar showing RAM usage | Medium |

### ❌ OUT OF SCOPE (Post-MVP)

| Feature | Reason for Deferral |
|---------|---------------------|
| Network topology visualization | Complex D3.js work, not essential for basic monitoring |
| Alert system | Can be added after core monitoring works |
| Time-series storage (SQLite) | Start with in-memory, add persistence later |
| Process-level metrics | Nice-to-have, not critical for cluster health |
| Inference server metrics polling | Add after system metrics are stable |
| Logs streaming | Separate feature, can use `sparkrun logs` instead |
| Historical comparison | Post-MVP analytics feature |
| Mobile-responsive design | Desktop-first for MVP |
| Dark/light theme toggle | Single theme for MVP |

---

## MVP Architecture

### Simplified Data Flow

```
Browser (http://localhost:8080)
        │
        ▼
Flask Web Server (single file)
        │
        ├─→ REST API: /api/metrics (current snapshot)
        └─→ WebSocket: /ws (push updates every 2s)
              │
              ▼
        SparkmonCollector (extends ClusterMonitor)
              │
              ├─→ SSH streams to all hosts
              └─→ Parse host_monitor.sh CSV output
                    │
                    ▼
              Remote DGX Spark Nodes
```

### Key Differences from Full Spec

| Full Spec | MVP |
|-----------|-----|
| Separate `collector.py`, `web_server.py`, `storage.py`, `alerts.py` | Single `sparkmon.py` file (~400 lines) |
| JSONL/SQLite time-series storage | In-memory dict (last 60 samples per host) |
| Network topology detection | None (skip for MVP) |
| Process metrics scripts | None (reuse `host_monitor.sh` only) |
| Inference metrics polling | None (add post-MVP) |
| Alert manager | None (add post-MVP) |
| Vue.js + Chart.js + D3.js | Vanilla JS + Chart.js only |
| Multiple script files | Single `host_monitor.sh` reuse |

---

## MVP File Structure

```
src/
├── sparkrun/                         # Existing
│   └── ...
└── sparkmon/                         # NEW: MVP package
    ├── __init__.py                  # ~10 lines
    ├── sparkmon.py                  # ~400 lines (CLI + Collector + Web Server)
    └── web/
        ├── index.html               # ~200 lines (single HTML file)
        └── app.js                   # ~200 lines (vanilla JS + Chart.js)
```

**Total**: ~800 lines (vs. 2200 for full spec)

---

## MVP Implementation Plan

### Week 1: Core Infrastructure (Days 1-5)

#### Day 1: Setup & CLI Skeleton
- [ ] Create `src/sparkrun/sparkmon/` directory
- [ ] Create `src/sparkrun/sparkmon/__init__.py`
- [ ] Implement CLI skeleton in `sparkmon.py`:
  ```python
  @click.group()
  def sparkmon():
      """Monitor DGX Spark cluster metrics."""
      pass
  
  @sparkmon.command("start")
  @click.option("--web", is_flag=True)
  @click.option("--interval", default=2)
  @click.option("--port", default=8080)
  def start(web, interval, port):
      # Placeholder
      pass
  ```
- [ ] Register with sparkrun CLI in `src/sparkrun/cli/__init__.py`
- [ ] Test: `sparkrun sparkmon --help`

#### Day 2: Collector Implementation
- [ ] Implement `SparkmonCollector` class (extends `ClusterMonitor`):
  ```python
  class SparkmonCollector(ClusterMonitor):
      def __init__(self, hosts, ssh_kwargs, interval=2):
          super().__init__(hosts, ssh_kwargs, interval)
          self.metrics = {}  # {host: [samples]}
      
      def _reader(self, host, proc):
          # Override to store metrics in memory
          # Parse CSV from host_monitor.sh
          pass
  ```
- [ ] Test: Run collector on single host, verify metrics stored

#### Day 3: Flask Web Server
- [ ] Implement Flask app in same `sparkmon.py`:
  ```python
  app = Flask(__name__)
  
  @app.route('/')
  def index():
      return send_from_directory('web', 'index.html')
  
  @app.route('/api/metrics')
  def get_metrics():
      return jsonify(collector.metrics)
  
  @app.route('/ws')
  def websocket():
      # Simple polling fallback if WebSocket too complex
      pass
  ```
- [ ] Test: `curl http://localhost:8080/api/metrics`

#### Day 4: Basic HTML Dashboard
- [ ] Create `src/sparkrun/sparkmon/web/index.html`:
  - Header with cluster info
  - Node table (host, GPU%, CPU%, Mem%, Temp)
  - GPU utilization chart (Chart.js)
- [ ] Use CDN for Chart.js (no build step)
- [ ] Test: Open in browser, see static data

#### Day 5: Real-Time Updates
- [ ] Implement JavaScript polling:
  ```javascript
  setInterval(async () => {
      const resp = await fetch('/api/metrics');
      const data = await resp.json();
      updateTable(data);
      updateChart(data);
  }, 2000);
  ```
- [ ] Connect to Flask backend
- [ ] Test: Watch metrics update in browser

### Week 2: Polish & Testing (Days 6-10)

#### Day 6: Multi-Host Support
- [ ] Test with 2+ hosts
- [ ] Verify parallel SSH streams work
- [ ] Handle SSH failures gracefully
- [ ] Show error states in UI

#### Day 7: Chart Improvements
- [ ] Add memory usage chart
- [ ] Add temperature chart (optional)
- [ ] Configure auto-scaling, colors
- [ ] Smooth updates (no flicker)

#### Day 8: CLI Integration
- [ ] Implement `sparkrun sparkmon stop`
- [ ] Implement `sparkrun sparkmon status`
- [ ] Add `--cluster` option to use named clusters
- [ ] Test full workflow

#### Day 9: Error Handling
- [ ] Handle SSH connection failures
- [ ] Handle missing hosts
- [ ] Handle nvidia-smi failures
- [ ] Show user-friendly error messages

#### Day 10: Documentation & Testing
- [ ] Write `src/sparkrun/sparkmon/README.md`
- [ ] Test on real cluster (2-4 nodes)
- [ ] Fix bugs
- [ ] Performance test (CPU overhead)

---

## MVP Code Examples

### `src/sparkrun/sparkmon/sparkmon.py` (Core Structure)

```python
"""Sparkmon MVP - Single file implementation."""

import click
import flask
import threading
import time
from sparkrun.core.monitoring import ClusterMonitor, parse_monitor_line

# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class SparkmonCollector(ClusterMonitor):
    """Simplified collector storing metrics in memory."""
    
    def __init__(self, hosts, ssh_kwargs, interval=2, max_samples=60):
        super().__init__(hosts, ssh_kwargs, interval)
        self.max_samples = max_samples
        self.metrics = {host: [] for host in hosts}
    
    def _reader(self, host, proc):
        """Override to store parsed metrics."""
        for raw_line in proc.stdout:
            sample = parse_monitor_line(raw_line)
            if sample:
                self.metrics[host].append({
                    'timestamp': sample.timestamp,
                    'gpu_util_pct': sample.gpu_util_pct,
                    'gpu_mem_used_pct': sample.gpu_mem_used_pct,
                    'gpu_temp_c': sample.gpu_temp_c,
                    'cpu_usage_pct': sample.cpu_usage_pct,
                    'mem_used_pct': sample.mem_used_pct,
                })
                # Trim old samples
                if len(self.metrics[host]) > self.max_samples:
                    self.metrics[host] = self.metrics[host][-self.max_samples:]

# ---------------------------------------------------------------------------
# Web Server
# ---------------------------------------------------------------------------

app = flask.Flask(__name__)
collector = None

@app.route('/')
def index():
    return flask.send_from_directory('web', 'index.html')

@app.route('/api/metrics')
def get_metrics():
    if not collector:
        return flask.jsonify({'error': 'not started'}), 400
    return flask.jsonify(collector.metrics)

@app.route('/api/status')
def get_status():
    if not collector:
        return flask.jsonify({'running': False})
    return flask.jsonify({
        'running': True,
        'hosts': list(collector.metrics.keys()),
        'interval': collector.interval,
    })

def run_web_server(port=8080):
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def sparkmon():
    """Monitor DGX Spark cluster metrics."""
    pass

@sparkmon.command("start")
@click.option("--web", is_flag=True, help="Start web UI")
@click.option("--interval", "-i", default=2, help="Sampling interval (seconds)")
@click.option("--port", "-p", default=8080, help="Web UI port")
@click.option("--cluster", "-c", default=None, help="Use named cluster")
@click.option("--hosts", "-H", default=None, help="Comma-separated hosts")
@click.pass_context
def start(ctx, web, interval, port, cluster, hosts):
    """Start cluster monitoring."""
    from sparkrun.cli._common import _resolve_hosts_or_exit
    
    # Resolve hosts
    hosts_list = _resolve_hosts_or_exit(ctx, cluster, hosts)
    ssh_kwargs = {k: v for k, v in ctx.params.items() 
                  if k in ['ssh_user', 'ssh_key', 'ssh_options'] and v}
    
    # Start collector
    global collector
    collector = SparkmonCollector(hosts_list, ssh_kwargs, interval)
    collector.start()
    
    if web:
        # Start web server in background
        thread = threading.Thread(target=run_web_server, kwargs={'port': port}, daemon=True)
        thread.start()
        click.echo(f"Web UI available at http://localhost:{port}")
    
    # Block until Ctrl-C
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        collector.stop()
        click.echo("\nMonitoring stopped.")

@sparkmon.command("stop")
def stop():
    """Stop monitoring."""
    global collector
    if collector:
        collector.stop()
        collector = None
    click.echo("Monitoring stopped.")

@sparkmon.command("status")
def status():
    """Show monitoring status."""
    global collector
    if collector:
        click.echo(f"Running: True")
        click.echo(f"Hosts: {len(collector.metrics)}")
        for host, samples in collector.metrics.items():
            if samples:
                latest = samples[-1]
                click.echo(f"  {host}: GPU {latest['gpu_util_pct']}%, "
                          f"Mem {latest['mem_used_pct']}%, "
                          f"Temp {latest['gpu_temp_c']}°C")
    else:
        click.echo("Not running")
```

### `src/sparkrun/sparkmon/web/index.html` (MVP Dashboard)

```html
<!DOCTYPE html>
<html>
<head>
    <title>Sparkmon - Cluster Monitor</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #00d4ff; }
        .container { max-width: 1200px; margin: 0 auto; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }
        .card { background: #16213e; border-radius: 8px; padding: 15px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 8px; text-align: left; border-bottom: 1px solid #0f3460; }
        th { color: #00d4ff; }
        .status-ok { color: #00ff88; }
        .status-error { color: #ff4757; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔥 Sparkmon - DGX Spark Cluster Monitor</h1>
        
        <div class="grid">
            <div class="card">
                <h3>GPU Utilization</h3>
                <canvas id="gpuChart"></canvas>
            </div>
            <div class="card">
                <h3>Memory Usage</h3>
                <canvas id="memChart"></canvas>
            </div>
        </div>
        
        <div class="card" style="margin-top: 20px;">
            <h3>Node Details</h3>
            <table id="nodeTable">
                <thead>
                    <tr>
                        <th>Host</th>
                        <th>GPU%</th>
                        <th>GPU Mem%</th>
                        <th>GPU Temp</th>
                        <th>CPU%</th>
                        <th>Mem%</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody><!-- Populated by JS --></tbody>
            </table>
        </div>
    </div>
    
    <script>
        // Chart.js setup
        const gpuCtx = document.getElementById('gpuChart').getContext('2d');
        const gpuChart = new Chart(gpuCtx, {
            type: 'line',
            data: { labels: [], datasets: [] },
            options: { 
                animation: false,
                scales: { y: { beginAtZero: true, max: 100, ticks: { color: '#eee' } },
                         x: { ticks: { color: '#eee' } } }
            }
        });
        
        const memCtx = document.getElementById('memChart').getContext('2d');
        const memChart = new Chart(memCtx, {
            type: 'bar',
            data: { labels: [], datasets: [] },
            options: { 
                animation: false,
                scales: { y: { beginAtZero: true, max: 100, ticks: { color: '#eee' } },
                         x: { ticks: { color: '#eee' } } }
            }
        });
        
        // Poll for metrics
        async function updateMetrics() {
            try {
                const resp = await fetch('/api/metrics');
                const data = await resp.json();
                
                // Update table
                const tbody = document.querySelector('#nodeTable tbody');
                tbody.innerHTML = '';
                const hosts = Object.keys(data);
                
                // Initialize charts with hosts
                if (gpuChart.datasets.length === 0) {
                    hosts.forEach(host => {
                        gpuChart.datasets.push({
                            label: host,
                            data: [],
                            borderColor: `hsl(${Math.random() * 360}, 70%, 50%)`,
                            fill: false,
                            tension: 0.3
                        });
                        memChart.datasets.push({
                            label: host,
                            data: [],
                            backgroundColor: `hsl(${Math.random() * 360}, 70%, 50%)`
                        });
                    });
                }
                
                hosts.forEach(host => {
                    const samples = data[host];
                    const latest = samples[samples.length - 1] || {};
                    
                    // Table row
                    const row = tbody.insertRow();
                    row.innerHTML = `
                        <td>${host}</td>
                        <td>${latest.gpu_util_pct || 'N/A'}%</td>
                        <td>${latest.gpu_mem_used_pct || 'N/A'}%</td>
                        <td>${latest.gpu_temp_c || 'N/A'}°C</td>
                        <td>${latest.cpu_usage_pct || 'N/A'}%</td>
                        <td>${latest.mem_used_pct || 'N/A'}%</td>
                        <td class="status-ok">●</td>
                    `;
                    
                    // Update charts
                    const labels = samples.map(s => s.timestamp.slice(11)); // HH:MM:SS
                    gpuChart.datasets.find(d => d.label === host).data = 
                        samples.map(s => parseFloat(s.gpu_util_pct) || 0);
                    memChart.datasets.find(d => d.label === host).data = 
                        samples.map(s => parseFloat(s.mem_used_pct) || 0);
                });
                
                gpuChart.update('none');
                memChart.update('none');
            } catch (err) {
                console.error('Failed to fetch metrics:', err);
            }
        }
        
        // Initial load and polling
        updateMetrics();
        setInterval(updateMetrics, 2000);
    </script>
</body>
</html>
```

---

## Success Criteria (MVP)

### Functional
- [ ] `sparkrun sparkmon start --web --hosts=x,x` works
- [ ] Web UI loads at `http://localhost:8080`
- [ ] GPU utilization chart updates in real-time
- [ ] Node table shows current metrics for all hosts
- [ ] `sparkrun sparkmon stop` works
- [ ] Works on 2-4 node cluster

### Non-Functional
- [ ] <5% CPU overhead on control machine
- [ ] No crashes after 1 hour of continuous monitoring
- [ ] Graceful handling of SSH failures
- [ ] Clean shutdown on Ctrl-C

### Code Quality
- [ ] All code in `src/sparkrun/sparkmon/` (single file + web)
- [ ] Reuses `ClusterMonitor` from sparkrun
- [ ] No new dependencies beyond Flask
- [ ] README with usage instructions

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Flask installation issues | Use `uv pip install flask`, document in README |
| WebSocket complexity too high | Use simple polling (every 2s) instead |
| Chart.js performance issues | Limit to 60 data points, use `update('none')` |
| SSH failures break collector | `ClusterMonitor` already has auto-reconnect |
| Web UI too slow with many hosts | Limit to 8 hosts for MVP, optimize later |

---

## Post-MVP Roadmap

### Iteration 1 (Week 3-4)
- [ ] Add `sparkrun sparkmon export` (JSONL storage)
- [ ] Add alert rules (`sparkrun sparkmon alert add`)
- [ ] Improve UI (better charts, responsive design)

### Iteration 2 (Week 5-6)
- [ ] Network topology visualization (D3.js)
- [ ] Process-level metrics
- [ ] Inference server metrics polling

### Iteration 3 (Week 7-8)
- [ ] SQLite time-series storage
- [ ] Historical comparison
- [ ] Performance regression detection

---

## Resource Requirements

### Development
- **1 developer** (familiar with sparkrun codebase)
- **10-14 days** (full-time)
- **Test cluster**: 2-4 DGX Spark nodes

### Dependencies
- **Flask** (web server) - `uv pip install flask`
- **Chart.js** (CDN, no install)
- **Existing sparkrun infrastructure** (already installed)

### Infrastructure
- Control machine with SSH access to DGX Sparks
- Web browser for testing UI
- Optional: Docker container for isolated testing

---

## Decision Points

### Q: Why single file instead of modular?
**A**: Faster MVP, easier to test, can refactor later once we understand the domain better.

### Q: Why polling instead of WebSocket?
**A**: Simpler implementation, good enough for 2-second updates, avoids async complexity.

### Q: Why in-memory storage?
**A**: MVP doesn't need history yet, can add SQLite later without changing core logic.

### Q: Why Chart.js over D3.js?
**A**: Much simpler API, good enough for line/bar charts, D3 overkill for MVP.

---

## Conclusion

The MVP delivers **real value in 2 weeks** by focusing on core monitoring functionality:
- ✅ Real-time system metrics
- ✅ Multi-host support
- ✅ Web-based dashboard
- ✅ Minimal code (~800 lines)
- ✅ Maximum reuse of sparkrun patterns

Post-MVP iterations can add topology, alerts, storage, and advanced features once the foundation is solid.

**Recommendation**: Approve MVP scope and begin Phase 1 implementation immediately.

---

**Document Version**: 1.0  
**Last Updated**: 2025-03-11  
**Status**: Ready for Approval
