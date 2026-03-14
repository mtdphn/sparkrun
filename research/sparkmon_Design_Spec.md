# Sparkmon - DGX Spark Cluster Monitoring System
## Design Specification & Architecture Plan

**Status**: MVP Implemented (Post-MVP Reference)

**Note**: The full design spec below describes the complete vision. The **MVP implementation** simplified this to a single-file approach (`sparkmon.py`) for faster delivery. See `sparkmon_CHANGES.md` for details on what was deferred to post-MVP iterations.

---

## Implementation Status

- ✅ **MVP Complete** (2025-03-11): CLI, web UI, basic metrics collection
- ⏳ **Post-MVP**: Network topology, alerts, persistent storage, process metrics  
**Target**: Optional extension to sparkrun CLI  
**Approach**: Reuse sparkrun methodology, extend for web-based visualization

---

## 1. Overview & Vision

### 1.1 What is Sparkmon?

Sparkmon is a **lightweight, optional monitoring subsystem** for sparkrun that provides:
- **Real-time cluster monitoring**: CPU, GPU, memory, temperature across all nodes
- **Network topology visualization**: InfiniBand/Ethernet topology with traffic indicators
- **Process-level metrics**: Inference workload performance (requests/sec, token throughput)
- **Web-based UI**: Clean, modern dashboard accessible via browser
- **Alerting**: Threshold-based notifications for critical conditions
- **Historical data**: Time-series storage for trend analysis

### 1.2 Design Principles

1. **Reuse sparkrun patterns** - SSH stdin piping, parallel execution, no agents
2. **Optional & non-intrusive** - Runs alongside sparkrun, doesn't block inference jobs
3. **Minimal footprint** - Bash scripts over SSH, no persistent daemons on target nodes
4. **Web-first visualization** - Modern browser UI, no special client required
5. **Cluster-wide view** - Aggregate data from all nodes, show topology and relationships
6. **Context preservation** - Show running jobs, their metrics, and system state together

### 1.3 What Sparkmon is NOT

- ❌ NOT a replacement for sparkrun
- ❌ NOT a full-featured monitoring stack (Prometheus/Grafana)
- ❌ NOT requiring persistent agents or daemons on DGX Sparks
- ❌ NOT real-time sub-second monitoring (2-5s intervals acceptable)
- ❌ NOT replacing Nsight tools for deep profiling

---

## 2. Architecture

### 2.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Sparkmon Web UI (Browser)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ Cluster View │  │ Node Details │  │ Topology Map │  │ Alerts     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Sparkmon Web Server (Flask/FastAPI)                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ REST API: /api/metrics, /api/topo, /api/alerts, /api/jobs      │    │
│  │ WebSocket: Real-time updates (optional)                        │    │
│  │ Static: HTML/CSS/JS dashboard (self-contained)                 │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Sparkmon Collector (sparkrun sparkmon)                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Parallel SSH streams (reuses ClusterMonitor pattern)           │    │
│  │ - System metrics: host_monitor.sh (existing)                   │    │
│  │ - Network topo: ib_detect.sh + lspci (extended)                │    │
│  │ - Inference metrics: HTTP /v1/metrics polling                  │    │
│  │ - Process metrics: /proc/<pid> from sparkrun_serve.pid         │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                     │
│                                    ▼                                     │
│                          ┌──────────────────┐                           │
│                          │ Metrics Store    │                           │
│                          │ - JSON snapshots │                           │
│                          │ - Time-series    │                           │
│                          │ (optional SQLite)│                           │
│                          └──────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Remote DGX Spark Nodes                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ SSH stdin piping (no files copied)                              │   │
│  │ - host_monitor.sh → CPU/GPU/memory/temp                         │   │
│  │ - network_detect.sh → IB topology, IPs                          │   │
│  │ - process_monitor.sh → /proc/<pid> metrics                      │   │
│  │ - inference_poll.sh → HTTP /v1/metrics                          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ Running Workloads                                                 │   │
│  │ - Container: sparkrun_{hash}_solo/_head/_worker                  │   │
│  │ - PID file: /tmp/sparkrun_serve.pid                              │   │
│  │ - Log file: /tmp/sparkrun_serve.log                              │   │
│  │ - Metrics endpoint: http://localhost:8000/metrics (vLLM/SGLang)  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Directory Structure

```
src/
├── sparkrun/                         # Main orchestration CLI
│   ├── cli/                         # Click CLI package
│   ├── core/                        # Core data models
│   ├── orchestration/               # SSH, Docker, etc.
│   └── ...                          # Other sparkrun modules
└── sparkmon/                        # NEW: Monitoring subsystem (peer to sparkrun)
    ├── __init__.py                  # Package init
    ├── cli.py                       # CLI commands (sparkrun sparkmon)
    ├── collector.py                 # Metrics collection (extends ClusterMonitor)
    ├── web_server.py                # Flask/FastAPI web server
    ├── web/                         # Static web UI
    │   ├── index.html              # Main dashboard
    │   ├── app.js                  # Vue.js/React application
    │   ├── styles.css              # Styling
    │   └── topology.js             # Network topology visualization
    ├── scripts/                     # Monitoring scripts
    │   ├── network_topo.sh         # NEW: Network topology detection
    │   ├── process_metrics.sh      # NEW: Process-level metrics
    │   ├── inference_metrics.sh    # NEW: HTTP metrics polling
    │   └── host_monitor.sh         # EXISTING: Reused as-is
    └── storage.py                   # Metrics persistence (JSON/SQLite)
```

**Rationale**: `sparkmon` lives at the same level as `sparkrun` in `src/` to keep the monitoring subsystem modular and independent while still being part of the same project. This makes it easier to:
- Test sparkmon independently
- Potentially extract it as a separate package later
- Keep sparkrun's core package cleaner

### 2.3 Component Responsibilities

| Component | Responsibility | Reuses sparkrun? |
|-----------|---------------|------------------|
| **CLI (`cli.py`)** | `sparkrun sparkmon start/stop/status`, `--web`, `--interval` | Yes (Click patterns) |
| **Collector (`collector.py`)** | Parallel SSH streams, metric aggregation, WebSocket push | Yes (`ClusterMonitor`) |
| **Web Server (`web_server.py`)** | REST API, static file serving, WebSocket management | No (new) |
| **Web UI (`web/`)** | Dashboard, topology map, alerts, node details | No (new) |
| **Scripts (`scripts/`)** | Remote metric collection via SSH stdin | Yes (`host_monitor.sh`) |
| **Storage (`storage.py`)** | Time-series storage, snapshots, export | Partial (cache dir pattern) |

---

## 3. Data Collection Strategy

### 3.1 System Metrics (Existing)

**Source**: `scripts/host_monitor.sh` (already exists)  
**Frequency**: 2-5 second intervals  
**Method**: SSH stdin pipe, CSV output  
**Metrics**:
- CPU: load averages, usage %, frequency, temperature
- Memory: total/used/available, swap
- GPU: utilization, memory, temperature, power, clocks
- Sparkrun jobs: container count, names

**Reuse**: 100% - no changes needed

### 3.2 Network Topology (New)

**Source**: `scripts/network_topo.sh` (new)  
**Frequency**: On-demand (topology rarely changes)  
**Method**: SSH stdin pipe, JSON output  
**Metrics**:
- InfiniBand detection (existing `ib_detect.sh` logic)
- NIC types (ConnectX-7, Ethernet)
- IP addresses (management + IB fast-path)
- Network interfaces and speeds
- Inter-node connectivity matrix

**Script Pattern**:
```bash
#!/bin/bash
# network_topo.sh - Detect network topology
# Output: JSON with interfaces, IPs, speeds, IB status

echo "{"
echo "  'hostname': '$(hostname)',"
echo "  'interfaces': ["

# Loop through network interfaces
for iface in $(ip -o link show | awk -F': ' '{print $2}' | grep -v lo); do
    # Get IP, speed, type
    ip_addr=$(ip -4 addr show $iface | grep -oP '(?<=inet\s)\d+\.\d+\.\d+\.\d+')
    speed=$(ethtool $iface 2>/dev/null | grep Speed | cut -d: -f2 | tr -d ' ')
    echo "    {'name': '$iface', 'ip': '$ip_addr', 'speed': '$speed'},"
done

echo "  ],"
echo "  'infiniband': $(test -d /sys/class/infiniband && echo true || echo false),"
echo "  'ib_ips': $(ib_ips 2>/dev/null | tr '\n' ',' | sed 's/,$//')"
echo "}"
```

### 3.3 Process-Level Metrics (New)

**Source**: `scripts/process_metrics.sh` (new)  
**Frequency**: 2-5 second intervals  
**Method**: SSH stdin pipe, parse `/proc/<pid>`  
**Metrics**:
- Read PID from `/tmp/sparkrun_serve.pid`
- CPU time (user/system)
- Memory RSS/Virtual
- Thread count
- File descriptors
- Network connections (ports listening)

**Script Pattern**:
```bash
#!/bin/bash
# process_metrics.sh - Get metrics for sparkrun serve process
# Output: CSV with process-level metrics

PIDFILE="/tmp/sparkrun_serve.pid"
if [ ! -f "$PIDFILE" ]; then
    echo "N/A,N/A,N/A,N/A,N/A,N/A"
    exit 0
fi

PID=$(cat "$PIDFILE")
if ! kill -0 "$PID" 2>/dev/null; then
    echo "N/A,N/A,N/A,N/A,N/A,N/A"
    exit 0
fi

# Read /proc/<pid>/stat, /statm, /status, /fd, /net
STAT=$(cat /proc/$PID/stat 2>/dev/null)
STATM=$(cat /proc/$PID/statm 2>/dev/null)
STATUS=$(cat /proc/$PID/status 2>/dev/null)

# Extract fields (utime, stime, rss, threads, fds)
UTIME=$(echo "$STAT" | awk '{print $14}')
STIME=$(echo "$STAT" | awk '{print $15}')
RSS=$(echo "$STATM" | awk '{print $2}')
THREADS=$(echo "$STATUS" | grep Threads | awk '{print $2}')
FDs=$(ls /proc/$PID/fd 2>/dev/null | wc -l)

echo "$UTIME,$STIME,$RSS,$THREADS,$FDs,$PID"
```

### 3.4 Inference Metrics (New)

**Source**: `scripts/inference_metrics.sh` (new)  
**Frequency**: 5-10 second intervals  
**Method**: HTTP polling of `/v1/metrics` or `/metrics`  
**Metrics**:
- Requests per second
- Token throughput (input/output)
- Queue depth
- Latency (p50, p95, p99)
- Cache hit rate (vLLM)
- GPU utilization (from inference server, not nvidia-smi)

**Script Pattern**:
```bash
#!/bin/bash
# inference_metrics.sh - Poll inference server metrics
# Output: JSON with inference-specific metrics

PORT="${1:-8000}"
URL="http://localhost:$PORT/v1/metrics"

# Try vLLM metrics endpoint
RESPONSE=$(curl -s --max-time 2 "$URL" 2>/dev/null)
if [ -z "$RESPONSE" ]; then
    # Try SGLang or fallback
    URL="http://localhost:$PORT/metrics"
    RESPONSE=$(curl -s --max-time 2 "$URL" 2>/dev/null)
fi

if [ -z "$RESPONSE" ]; then
    echo '{"error": "no response"}'
    exit 0
fi

# Parse Prometheus-style metrics or JSON
# Extract: requests_total, tokens_total, queue_size, latency_p99
echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # Normalize to standard format
    print(json.dumps({
        'requests_per_sec': data.get('requests_per_sec', 0),
        'tokens_per_sec': data.get('tokens_per_sec', 0),
        'queue_size': data.get('queue_size', 0),
        'latency_p99_ms': data.get('latency_p99_ms', 0),
    }))
except:
    print('{\"error\": \"parse failed\"}')
"
```

### 3.5 Data Aggregation

**Collector Pattern** (extends `ClusterMonitor`):

```python
# src/sparkrun/sparkmon/collector.py

from sparkrun.core.monitoring import ClusterMonitor, HostMonitorState

class SparkmonCollector(ClusterMonitor):
    """Extended monitor with network, process, and inference metrics."""
    
    def __init__(self, hosts, ssh_kwargs, interval=2, port=8000):
        super().__init__(hosts, ssh_kwargs, interval)
        self.port = port
        self.topology = {}  # Network topology (cached)
        self.inference_metrics = {}  # Per-host inference metrics
        
    def start(self):
        """Start system monitor + inference metric collectors."""
        # Start base system monitoring (host_monitor.sh)
        super().start()
        
        # Start inference metrics polling (HTTP)
        self._start_inference_polling()
        
        # Fetch network topology (one-time)
        self._fetch_topology()
    
    def _start_inference_polling(self):
        """Start HTTP polling for inference metrics on each host."""
        from threading import Thread
        import requests
        
        def poll_host(host):
            while True:
                try:
                    url = f"http://{host}:{self.port}/v1/metrics"
                    resp = requests.get(url, timeout=5)
                    if resp.status_code == 200:
                        self.inference_metrics[host] = resp.json()
                except:
                    pass
                time.sleep(5)  # 5s interval
        
        for host in self.hosts:
            Thread(target=poll_host, args=(host,), daemon=True).start()
    
    def _fetch_topology(self):
        """Fetch network topology from all hosts."""
        from sparkrun.scripts import read_script
        from sparkrun.orchestration.ssh import run_remote_scripts_parallel
        
        script = read_script("network_topo.sh")
        results = run_remote_scripts_parallel(
            self.hosts, script,
            ssh_user=self.ssh_kwargs.get("ssh_user"),
            ssh_key=self.ssh_kwargs.get("ssh_key"),
            timeout=30,
        )
        
        # Parse JSON results and build topology matrix
        for result in results:
            if result.success:
                self.topology[result.host] = json.loads(result.stdout)
```

---

## 4. Web Interface

### 4.1 Technology Stack

**Backend**:
- **Flask** (lightweight) or **FastAPI** (async, WebSocket support)
- Single Python file, no external dependencies beyond sparkrun
- Serves static files + REST API + WebSocket

**Frontend**:
- **Vue.js 3** (CDN, no build step) or **Alpine.js** (lighter)
- **Chart.js** or **ApexCharts** for graphs
- **D3.js** or **vis-network** for topology visualization
- Single `index.html` file (self-contained)

**Why this stack?**
- No Node.js/build tools required
- Works offline (all JS/CSS embedded or CDN with fallback)
- Simple deployment (just start Flask server)
- Matches sparkrun's "minimal dependencies" philosophy

### 4.2 Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Sparkmon - DGX Spark Cluster Monitor                    [Refresh] [⚙]  │
├─────────────────────────────────────────────────────────────────────────┤
│  CLUSTER: my-cluster    HOSTS: 4    JOBS: 2    STATUS: ● Running       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │ GPU Utilization  │  │ Memory Usage     │  │ Network Topology     │  │
│  │                  │  │                  │  │                      │  │
│  │ [Line Chart]     │  │ [Stacked Bar]    │  │ [Interactive Map]    │  │
│  │                  │  │                  │  │   Node1 --- Node2    │  │
│  │ 100% ┤▓▓▓▓▓░░░░░│  │ 128GB ┤▓▓▓░░░░░░│  │     |      |         │  │
│  │  50% ┤▓▓▓░░░░░░░│  │  64GB ┤▓▓░░░░░░░│  │   Node3 --- Node4    │  │
│  │   0% └──────────┘  │  0GB └──────────┘  │                      │  │
│  │  0m   5m   10m     │  0m   5m   10m     │  IB: Enabled         │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Node Details                                                     │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │ Host       │ GPU    │ CPU    │ Mem    │ Temp   │ Jobs           │  │
│  ├────────────┼────────┼────────┼────────┼────────┼────────────────┤  │
│  │ gx10-1a2b  │ 78%    │ 45%    │ 64GB   │ 62°C   │ sparkrun_abc   │  │
│  │ gx10-3c4d  │ 82%    │ 52%    │ 71GB   │ 65°C   │ sparkrun_abc   │  │
│  │ gx10-5e6f  │ 12%    │ 18%    │ 32GB   │ 48°C   │ (idle)         │  │
│  │ gx10-7g8h  │ 15%    │ 22%    │ 35GB   │ 50°C   │ (idle)         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Inference Metrics                                                │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │ Requests/sec: 145   Tokens/sec: 2,340   Queue: 12   Latency: 45ms│  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Alerts                                                           │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │ ⚠ gx10-3c4d: GPU temp 65°C (threshold: 60°C)                    │  │
│  │ ℹ sparkrun_abc: Starting (waiting for port 8000)                │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Key Features

#### 4.3.1 Cluster Overview
- Aggregate stats across all nodes
- Total GPU/CPU/memory utilization
- Active jobs count
- Cluster health status

#### 4.3.2 Network Topology Map
- Interactive graph showing nodes and connections
- Color-coded by link type (IB = blue, Ethernet = green)
- Animated traffic flow (thickness = bandwidth usage)
- Click node to see details

**Implementation** (D3.js or vis-network):
```javascript
// topology.js
const nodes = [
  {id: 'gx10-1a2b', label: 'gx10-1a2b', gpu: '78%', ip: '192.168.11.13'},
  {id: 'gx10-3c4d', label: 'gx10-3c4d', gpu: '82%', ip: '192.168.11.14'},
  // ...
];

const edges = [
  {from: 'gx10-1a2b', to: 'gx10-3c4d', label: 'IB 100Gbps', color: 'blue'},
  {from: 'gx10-1a2b', to: 'gx10-5e6f', label: 'IB 100Gbps', color: 'blue'},
  // ...
];

// Render with vis-network
const network = new vis.Network(container, {nodes, edges}, options);
```

#### 4.3.3 Time-Series Charts
- GPU utilization over time
- Memory usage trends
- Temperature history
- Network traffic

**Implementation** (Chart.js):
```javascript
const ctx = document.getElementById('gpuChart').getContext('2d');
const chart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: ['0m', '1m', '2m', '3m', '4m', '5m'],
    datasets: [
      {label: 'gx10-1a2b', data: [78, 80, 82, 79, 77, 78], borderColor: 'blue'},
      {label: 'gx10-3c4d', data: [82, 84, 85, 83, 81, 82], borderColor: 'green'},
    ]
  },
  options: {
    animation: false,
    scales: {y: {beginAtZero: true, max: 100}}
  }
});

// Update every 2 seconds
setInterval(() => {
  // Fetch new data from /api/metrics
  // Update chart datasets
  chart.update('none');  // Smooth update
}, 2000);
```

#### 4.3.4 Alerts & Notifications
- Configurable thresholds (GPU temp, utilization, memory)
- Real-time alerts via WebSocket
- Alert history
- Email/Slack notifications (optional)

#### 4.3.5 Node Drill-Down
- Click node to see detailed metrics
- Process-level info (PID, CPU time, memory)
- Inference server metrics
- Logs viewer (stream from `/tmp/sparkrun_serve.log`)

---

## 5. CLI Integration

### 5.1 Commands

```bash
# Start monitoring with web UI
sparkrun sparkmon start --web --interval=2 --port=8080

# Start monitoring (headless, just collect metrics)
sparkrun sparkmon start --interval=5

# Stop monitoring
sparkrun sparkmon stop

# Show current monitoring status
sparkrun sparkmon status

# View metrics (terminal TUI, reuses existing monitor)
sparkrun sparkmon view --cluster=my-cluster

# Export metrics to file
sparkrun sparkmon export --format=json --output=metrics.json --duration=300

# Configure alerts
sparkrun sparkmon alert add --gpu-temp=70 --gpu-util=95 --memory=90%
sparkrun sparkmon alert list
sparkrun sparkmon alert remove <id>
```

### 5.2 CLI Implementation

```python
# src/sparkrun/sparkmon/cli.py

import click
from sparkrun.cli._common import CLUSTER_NAME, host_options, _resolve_hosts_or_exit

@click.group()
def sparkmon():
    """Monitor DGX Spark cluster metrics and performance."""
    pass

@sparkmon.command("start")
@click.option("--web", is_flag=True, help="Start web UI server")
@click.option("--interval", "-i", default=2, help="Sampling interval (seconds)")
@click.option("--port", "-p", default=8080, help="Web UI port (if --web)")
@click.option("--cluster", "-c", type=CLUSTER_NAME, help="Use named cluster")
@click.option("--hosts", "-H", default=None, help="Comma-separated host list")
@host_options
@click.pass_context
def sparkmon_start(ctx, web, interval, port, cluster, hosts, **ssh_opts):
    """Start cluster monitoring."""
    from sparkrun.core.monitoring import stream_cluster_monitor
    from sparkrun.sparkmon.collector import SparkmonCollector
    from sparkrun.sparkmon.web_server import run_web_server
    
    # Resolve hosts
    hosts = _resolve_hosts_or_exit(ctx, cluster, hosts)
    ssh_kwargs = {k: v for k, v in ssh_opts.items() if v is not None}
    
    # Start collector
    collector = SparkmonCollector(hosts, ssh_kwargs, interval=interval)
    collector.start()
    
    if web:
        # Start web server in background thread
        import threading
        web_thread = threading.Thread(
            target=run_web_server,
            kwargs={'collector': collector, 'port': port},
            daemon=True
        )
        web_thread.start()
        click.echo(f"Web UI available at http://localhost:{port}")
    
    # Block until Ctrl-C
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        collector.stop()
        click.echo("\nMonitoring stopped.")

@sparkmon.command("stop")
@click.option("--cluster", "-c", type=CLUSTER_NAME, help="Use named cluster")
@click.option("--hosts", "-H", default=None, help="Comma-separated host list")
@host_options
@click.pass_context
def sparkmon_stop(ctx, cluster, hosts, **ssh_opts):
    """Stop cluster monitoring."""
    # Stop monitoring (implementation depends on persistence model)
    click.echo("Monitoring stopped.")

@sparkmon.command("status")
@click.option("--cluster", "-c", type=CLUSTER_NAME, help="Use named cluster")
@click.option("--hosts", "-H", default=None, help="Comma-separated host list")
@host_options
@click.pass_context
def sparkmon_status(ctx, cluster, hosts, **ssh_opts):
    """Show monitoring status."""
    # Check if collector is running, show last metrics
    click.echo("Monitoring status: Active")
    click.echo(f"Hosts: {len(hosts)}")
    # ...
```

---

## 6. Storage & Persistence

### 6.1 Metrics Storage Options

**Option 1: In-Memory Only** (Simplest)
- Metrics stored in collector state
- Lost on restart
- Good for real-time monitoring only

**Option 2: JSON Snapshots** (Lightweight)
- Append metrics to JSONL files
- `~/.cache/sparkrun/metrics/{cluster_id}.jsonl`
- Easy to parse, human-readable
- No database overhead

**Option 3: SQLite Time-Series** (More robust)
- Lightweight, no server needed
- Query with SQL
- Can store months of data
- Use `sqlite-utils` or raw SQLite

### 6.2 Recommended: JSONL + Optional SQLite

```python
# src/sparkrun/sparkmon/storage.py

import json
from pathlib import Path
from datetime import datetime

class MetricsStorage:
    """Store metrics as JSONL files, optionally with SQLite index."""
    
    def __init__(self, cache_dir: str, use_sqlite: bool = False):
        self.cache_dir = Path(cache_dir) / "metrics"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_sqlite = use_sqlite
        if use_sqlite:
            self._init_sqlite()
    
    def save_snapshot(self, cluster_id: str, snapshot: dict):
        """Save a metrics snapshot (all hosts at one timestamp)."""
        filename = self.cache_dir / f"{cluster_id}.jsonl"
        record = {
            'timestamp': datetime.utcnow().isoformat(),
            'cluster_id': cluster_id,
            'data': snapshot,
        }
        with open(filename, 'a') as f:
            f.write(json.dumps(record) + '\n')
        
        if self.use_sqlite:
            self._insert_sqlite(record)
    
    def get_history(self, cluster_id: str, duration_sec: int = 300):
        """Get metrics for last N seconds."""
        filename = self.cache_dir / f"{cluster_id}.jsonl"
        if not filename.exists():
            return []
        
        # Read last N records (simple approach)
        records = []
        with open(filename) as f:
            for line in f:
                records.append(json.loads(line))
        
        # Filter by timestamp
        # ...
        return records[-(duration_sec // 2):]  # Assume 2s interval
```

---

## 7. Alerting System

### 7.1 Alert Types

| Alert Type | Condition | Default Threshold | Severity |
|------------|-----------|-------------------|----------|
| GPU Temperature | `gpu_temp_c > threshold` | 70°C | Warning |
| GPU Utilization | `gpu_util_pct > threshold` | 95% | Info |
| Memory Usage | `mem_used_pct > threshold` | 90% | Warning |
| CPU Load | `cpu_load_1m > cores * 2` | 16 (8-core) | Info |
| Container Crash | Container not running | N/A | Critical |
| Port Not Ready | Port not listening after N min | 10 min | Warning |

### 7.2 Alert Implementation

```python
# src/sparkrun/sparkmon/alerts.py

from dataclasses import dataclass
from typing import Callable

@dataclass
class AlertRule:
    name: str
    condition: Callable[[dict], bool]  # Takes host sample, returns True if alert
    message: str
    severity: str  # 'info', 'warning', 'critical'
    cooldown_sec: int = 300  # Don't re-alert within this time

class AlertManager:
    def __init__(self):
        self.rules = []
        self.last_alert = {}  # rule_name -> timestamp
    
    def add_rule(self, rule: AlertRule):
        self.rules.append(rule)
    
    def check(self, host: str, sample: dict):
        """Check all rules against a host sample."""
        for rule in self.rules:
            if rule.condition(sample):
                # Check cooldown
                last = self.last_alert.get(rule.name, 0)
                if time.time() - last > rule.cooldown_sec:
                    self._fire_alert(host, rule, sample)
                    self.last_alert[rule.name] = time.time()
    
    def _fire_alert(self, host: str, rule: AlertRule, sample: dict):
        message = rule.message.format(host=host, **sample)
        # Log alert
        # Send notification (WebSocket, email, Slack)
        logger.warning(f"ALERT [{rule.severity.upper()}]: {message}")
```

### 7.3 CLI Alert Management

```python
@sparkmon.command("alert")
@click.argument("action", type=click.Choice(['add', 'list', 'remove']))
@click.option("--gpu-temp", type=float, help="GPU temperature threshold")
@click.option("--gpu-util", type=float, help="GPU utilization threshold")
@click.option("--memory", type=float, help="Memory usage threshold")
@click.option("--name", default=None, help="Alert rule name")
def sparkmon_alert(action, gpu_temp, gpu_util, memory, name):
    """Manage alert rules."""
    from sparkrun.sparkmon.alerts import AlertManager, AlertRule
    
    mgr = AlertManager()
    # Load existing rules from config
    
    if action == 'add':
        if gpu_temp:
            rule = AlertRule(
                name=name or f"gpu_temp_{gpu_temp}",
                condition=lambda s: float(s.get('gpu_temp_c', 0)) > gpu_temp,
                message="GPU temp {gpu_temp_c}°C on {host} exceeds {gpu_temp}°C",
                severity="warning",
            )
            mgr.add_rule(rule)
        # ...
    
    elif action == 'list':
        for rule in mgr.rules:
            click.echo(f"{rule.name}: {rule.message} ({rule.severity})")
    
    elif action == 'remove':
        # Remove rule by name
        pass
```

---

## 8. Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
- [ ] Create `src/sparkrun/sparkmon/` directory structure
- [ ] Implement `collector.py` (extends `ClusterMonitor`)
- [ ] Add `network_topo.sh` script
- [ ] Add `process_metrics.sh` script
- [ ] Implement basic CLI (`start`, `stop`, `status`)
- [ ] Test on single node

### Phase 2: Web UI (Week 2)
- [ ] Implement `web_server.py` (Flask)
- [ ] Create `web/index.html` with Vue.js
- [ ] Add real-time metrics charts (Chart.js)
- [ ] Add node table with live updates
- [ ] Test web UI locally

### Phase 3: Topology & Advanced Features (Week 3)
- [ ] Implement `topology.js` (D3.js or vis-network)
- [ ] Add network topology visualization
- [ ] Add traffic flow animation
- [ ] Implement node drill-down
- [ ] Add logs streaming

### Phase 4: Storage & Alerts (Week 4)
- [ ] Implement `storage.py` (JSONL + SQLite)
- [ ] Add metrics export (`sparkrun sparkmon export`)
- [ ] Implement `alerts.py` (alert rules)
- [ ] Add CLI for alert management
- [ ] Add WebSocket notifications

### Phase 5: Polish & Documentation (Week 5)
- [ ] Add error handling and retry logic
- [ ] Improve UI/UX (responsive design, dark mode)
- [ ] Write documentation
- [ ] Add tests
- [ ] Performance optimization

---

## 9. Reuse vs. New Code Summary

### 9.1 High-Reuse Components (Existing sparkrun patterns)

| Component | Reuse Strategy | Effort |
|-----------|----------------|--------|
| **SSH Execution** | Import `run_remote_scripts_parallel()` from `sparkrun.orchestration.ssh` | None (already done) |
| **Parallel Streams** | Extend `ClusterMonitor` class from `sparkrun.core.monitoring` | Low (subclass) |
| **Host Monitoring** | Use `host_monitor.sh` as-is (import via `sparkrun.scripts`) | None (already done) |
| **CLI Patterns** | Use Click decorators from `sparkrun.cli._common` | Low (copy patterns) |
| **Config/Cache** | Import `resolve_cache_dir()` from `sparkrun.core.config` | Low (reuse helpers) |
| **Job Metadata** | Read from `~/.cache/sparkrun/jobs/` (same path) | Low (existing files) |

### 9.2 New Components (Need to be built)

| Component | Complexity | Dependencies |
|-----------|------------|--------------|
| **Sparkmon Collector** | Medium | Extends `sparkrun.core.monitoring.ClusterMonitor` |
| **Web Server** | Medium | Flask/FastAPI |
| **Web UI** | Medium-High | Vue.js, Chart.js, D3.js (CDN) |
| **Network Topo Script** | Low | Bash, `ip`, `ethtool`, `lspci` |
| **Process Metrics Script** | Low | Bash, `/proc/<pid>` |
| **Inference Metrics Script** | Low | Bash, `curl`, Python JSON parsing |
| **Storage Layer** | Low-Medium | JSONL, optional SQLite |
| **Alert Manager** | Low | Pure Python |

### 9.3 Estimated Lines of Code

| Component | Python | Bash | HTML/JS | Total |
|-----------|--------|------|---------|-------|
| Collector | 300 | - | - | 300 |
| Web Server | 200 | - | - | 200 |
| Web UI | - | - | 800 | 800 |
| Scripts | - | 400 | - | 400 |
| Storage | 150 | - | - | 150 |
| Alerts | 150 | - | - | 150 |
| CLI | 200 | - | - | 200 |
| **Total** | **1000** | **400** | **800** | **2200** |

---

## 10. Risks & Mitigations

### 10.1 Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **SSH connection failures** | Monitor stops updating | Implement auto-reconnect (already in `ClusterMonitor`) |
| **Web UI performance with many nodes** | Slow rendering | Virtual scrolling, limit data points, use Canvas |
| **Metrics storage grows too large** | Disk space issues | Implement retention policy, compression |
| **Inference server metrics endpoint changes** | Breaks monitoring | Abstract to plugin interface, fallback to nvidia-smi |
| **Network topology detection fails** | Incomplete map | Graceful degradation, show what's detected |

### 10.2 Integration Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Conflicts with sparkrun runtimes** | Port conflicts, resource contention | Use separate ports, run at lower priority |
| **User confusion (monitor vs. run)** | Misunderstanding purpose | Clear documentation, separate CLI group |
| **Performance overhead on DGX Sparks** | Slows inference jobs | Lightweight scripts, configurable interval |

---

## 11. Success Criteria

### 11.1 Functional Requirements

- [ ] Monitor 2-8 DGX Spark nodes simultaneously
- [ ] Update metrics every 2-5 seconds
- [ ] Display GPU/CPU/memory/temperature in real-time
- [ ] Show network topology with IB detection
- [ ] Provide web UI accessible from browser
- [ ] Alert on configurable thresholds
- [ ] Export metrics to file (JSON/CSV)
- [ ] Non-intrusive (no impact on inference jobs)

### 11.2 Non-Functional Requirements

- [ ] **Performance**: <5% CPU overhead on control machine
- [ ] **Footprint**: No persistent daemons on target nodes
- [ ] **Reliability**: Auto-reconnect on SSH failures
- [ ] **Usability**: Single command to start (`sparkrun sparkmon start --web`)
- [ ] **Compatibility**: Works with all sparkrun runtimes (vLLM, SGLang, etc.)

---

## 12. Future Enhancements (Post-MVP)

1. **Historical Comparison**: Compare current metrics to baseline runs
2. **Performance Regression Detection**: Alert when throughput drops
3. **Predictive Alerts**: Forecast when resources will be exhausted
4. **Multi-Cluster Support**: Monitor multiple clusters from one UI
5. **Integration with Nsight Tools**: Auto-launch profiling on demand
6. **Prometheus Export**: Export metrics to Prometheus for Grafana dashboards
7. **Mobile App**: Native mobile monitoring app
8. **Team Collaboration**: Share dashboards, export reports

---

## 13. References & Related Work

### 13.1 Sparkrun Documentation

- `research/sparkun-Design_Architecture.md` - Core architecture
- `src/sparkrun/core/monitoring.py` - Existing `ClusterMonitor` implementation
- `src/sparkrun/scripts/host_monitor.sh` - System monitoring script
- `src/sparkrun/orchestration/ssh.py` - SSH execution patterns
- `src/sparkrun/orchestration/primitives.py` - Orchestration helpers

### 13.2 DGX Spark Tools

- `research/nsight-systems.md` - System-wide profiling (nsys)
- `research/nsight-compute.md` - GPU kernel profiling (ncu)
- `research/dgx-telemetry.md` - NVIDIA telemetry service
- `/opt/nvidia/dgx-telemetry/` - Telemetry configuration
- `/opt/nvidia/nsight-systems/` - Profiling tools

### 13.3 External References

- **Prometheus**: Time-series database, alerting
- **Grafana**: Visualization dashboards
- **NVIDIA DCGM**: Data Center GPU Manager (monitoring)
- **Slurm**: Workload scheduler (cluster management patterns)

---

## 14. Conclusion

Sparkmon extends sparkrun's SSH-first, agentless philosophy to provide real-time cluster monitoring with a modern web UI. By reusing existing patterns (`ClusterMonitor`, SSH stdin piping, parallel execution) and adding focused new components (web server, topology visualization, alerting), we can deliver a powerful monitoring tool without compromising sparkrun's design principles.

**Key Advantages**:
- ✅ Optional (opt-in via `sparkrun sparkmon start`)
- ✅ Lightweight (no agents, bash scripts over SSH)
- ✅ Reuses sparkrun patterns (familiar to users)
- ✅ Web UI (no special client needed)
- ✅ Cluster-wide view (topology + metrics)
- ✅ Extensible (add new metrics, alerts, visualizations)

**Next Steps**:
1. Review this design with stakeholders
2. Approve Phase 1 implementation
3. Set up development environment
4. Begin with `collector.py` and CLI scaffolding

---

**Document Version**: 1.0  
**Last Updated**: 2025-03-11  
**Author**: sparkrun team  
**Status**: Design Review
