# Sparkmon - DGX Spark Cluster Monitoring

A lightweight, optional monitoring subsystem for sparkrun that provides real-time visibility into cluster health and performance.

## Features

- **Real-time metrics**: CPU, GPU, memory, temperature across all nodes
- **Web dashboard**: Clean, modern UI accessible via browser
- **Multi-host support**: Monitor 2-8 DGX Spark nodes simultaneously
- **Agentless**: Uses SSH stdin piping (no daemons on target nodes)
- **Reuses sparkrun**: Leverages existing SSH infrastructure and patterns

## Quick Start

### Install Dependencies

```bash
# Install with monitoring support
pip install -e ".[monitoring]"

# Or install flask separately
pip install flask
```

### Start Monitoring

```bash
# Monitor specific hosts with web UI
sparkrun sparkmon start --web --hosts=gx10-1a2b,gx10-3c4d

# Use a named cluster
sparkrun sparkmon start --web --cluster=my-cluster

# Custom interval and port
sparkrun sparkmon start --web --interval=5 --port=9090
```

### Access Dashboard

Open your browser to: `http://localhost:8080`

### Stop Monitoring

Press `Ctrl-C` in the terminal where monitoring is running.

## Commands

### `sparkrun sparkmon start`

Start cluster monitoring.

**Options:**
- `--web`: Start web UI server (default: off)
- `--interval, -i`: Sampling interval in seconds (default: 2)
- `--port, -p`: Web UI port (default: 8080)
- `--cluster, -c`: Use named cluster definition
- `--hosts, -H`: Comma-separated list of hosts
- `--ssh-user`: SSH username
- `--ssh-key`: Path to SSH private key

**Examples:**
```bash
# Start with web UI on specific hosts
sparkrun sparkmon start --web --hosts=gx10-1a2b,gx10-3c4d

# Use named cluster with custom settings
sparkrun sparkmon start --web --cluster=my-cluster --interval=5 --port=9090
```

### `sparkrun sparkmon status`

Show current metrics from all hosts.

**Options:**
- `--cluster, -c`: Use named cluster definition
- `--hosts, -H`: Comma-separated list of hosts

**Example:**
```bash
sparkrun sparkmon status --cluster=my-cluster
```

### `sparkrun sparkmon export`

Export metrics to a JSON file.

**Options:**
- `--cluster, -c`: Use named cluster definition
- `--hosts, -H`: Comma-separated list of hosts
- `--duration, -d`: Duration in seconds to collect (default: 60)
- `--output, -o`: Output file path (default: stdout)

**Example:**
```bash
sparkrun sparkmon export --cluster=my-cluster --duration=120 --output=metrics.json
```

## Dashboard Overview

The web dashboard displays:

1. **Summary Bar**: Total hosts, average GPU usage, average memory usage, active jobs
2. **GPU Utilization Chart**: Real-time line chart across all nodes
3. **Memory Usage Chart**: Memory utilization over time
4. **CPU Usage Chart**: CPU utilization over time
5. **GPU Temperature Chart**: Temperature trends
6. **Node Table**: Detailed metrics for each host

## Architecture

```
Browser (http://localhost:8080)
        │
        ▼
Flask Web Server
        │
        ├─→ REST API: /api/metrics
        └─→ Static files: /web/index.html
              │
              ▼
        SparkmonCollector
              │
              ├─→ SSH streams to all hosts
              └─→ Parse host_monitor.sh CSV output
```

## Requirements

- **Python**: 3.10+
- **Flask**: Required for web UI (`pip install flask`)
- **sparkrun**: Must be installed and configured
- **SSH access**: To all target DGX Spark nodes

## Development

### Running in Development Mode

```bash
cd src/sparkrun
python -m sparkrun.sparkmon start --web --hosts=localhost
```

### Testing

```bash
# Test CLI help
sparkrun sparkmon --help

# Test on single host
sparkrun sparkmon start --web --hosts=localhost --interval=5
```

## Limitations (MVP)

- No persistent storage (metrics lost on restart)
- No alert system
- No network topology visualization
- No process-level metrics
- No inference server metrics polling

These features are planned for future iterations.

## Demo Mode

Test the UI without real DGX Spark nodes:

```bash
# Start demo with mock data
sparkrun sparkmon demo --hosts=node1,node2,node3 --port=8080
```

This generates realistic mock metrics for development and testing.

## License

Same license as sparkrun.
