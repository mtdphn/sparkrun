# Sparkmon - Quick Start Guide

This document provides a quick overview of the sparkmon monitoring system for developers and users.

---

## What is Sparkmon?

Sparkmon is an **optional monitoring subsystem** for sparkrun that provides:

- **Real-time metrics**: CPU, GPU, memory, temperature across all cluster nodes
- **Network topology**: Visual map of InfiniBand/Ethernet connections with traffic indicators
- **Web dashboard**: Clean UI accessible via browser (no special client needed)
- **Alerting**: Threshold-based notifications for critical conditions
- **Historical data**: Time-series storage for trend analysis

---

## Quick Commands

### Start Monitoring with Web UI

```bash
# Monitor a named cluster
sparkrun sparkmon start --cluster=my-cluster --web --port=8080

# Monitor specific hosts
sparkrun sparkmon start --hosts=gx10-1a2b,gx10-3c4d --web --port=8080

# Custom sampling interval (5 seconds)
sparkrun sparkmon start --cluster=my-cluster --web --interval=5
```

### Access the Dashboard

Open your browser to: `http://localhost:8080`

### Stop Monitoring

```bash
sparkrun sparkmon stop
```

### View Status

```bash
sparkrun sparkmon status
```

### Export Metrics

```bash
# Export last 5 minutes of data
sparkrun sparkmon export --cluster=my-cluster --duration=300 --output=metrics.json
```

### Configure Alerts

```bash
# Add GPU temperature alert
sparkrun sparkmon alert add --gpu-temp=70

# List all alerts
sparkrun sparkmon alert list

# Remove an alert
sparkrun sparkmon alert remove gpu_temp_70
```

---

## Dashboard Overview

The web dashboard shows:

1. **Cluster Summary**: Total hosts, active jobs, cluster status
2. **GPU Utilization Chart**: Real-time line chart across all nodes
3. **Memory Usage**: Stacked bar chart showing RAM usage
4. **Network Topology**: Interactive map showing nodes and connections
5. **Node Table**: Detailed metrics for each host
6. **Inference Metrics**: Requests/sec, tokens/sec, latency
7. **Alerts Panel**: Active warnings and notifications

---

## Architecture at a Glance

```
Browser (http://localhost:8080)
        │
        ▼
Sparkmon Web Server (Flask)
        │
        ▼
Sparkmon Collector (SSH streams)
        │
        ├─→ host_monitor.sh → CPU/GPU/memory/temp
        ├─→ network_topo.sh → Network topology
        ├─→ process_metrics.sh → Process-level metrics
        └─→ inference_metrics.sh → HTTP /v1/metrics
        │
        ▼
Remote DGX Spark Nodes (via SSH)
```

---

## Reused sparkrun Components

Sparkmon leverages existing sparkrun infrastructure:

- **SSH Execution**: `sparkrun/orchestration/ssh.py` - stdin piping, no agents
- **Parallel Streams**: `sparkrun/core/monitoring.py` - `ClusterMonitor` class
- **CLI Patterns**: `sparkrun/cli/_common.py` - Click decorators
- **Config/Cache**: `sparkrun/core/config.py` - Settings and state paths
- **Host Monitoring**: `sparkrun/scripts/host_monitor.sh` - System metrics

---

## New Components

The following are new for sparkmon (in `src/sparkrun/sparkmon/`):

- **`src/sparkrun/sparkmon/`** - Monitoring package (peer to sparkrun)
  - `collector.py` - Extended monitor with inference metrics
  - `web_server.py` - Flask web server
  - `web/` - Vue.js dashboard
  - `scripts/` - Network topology, process, inference scripts
  - `storage.py` - JSONL time-series storage
  - `alerts.py` - Alert rule management

---

## Configuration

### Default Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Sampling Interval | 2s | How often to collect metrics |
| Web Port | 8080 | Port for web UI |
| Cache Directory | `~/.cache/sparkrun/metrics/` | Where to store metrics |
| Alert Cooldown | 300s | Minimum time between duplicate alerts |

### Environment Variables

```bash
# Override sampling interval
export SPARKMON_INTERVAL=5

# Override web port
export SPARKMON_PORT=9090

# Enable SQLite storage
export SPARKMON_SQLITE=1
```

---

## Troubleshooting

### Web UI Won't Load

```bash
# Check if server is running
curl http://localhost:8080

# Check logs
tail -f ~/.cache/sparkrun/logs/sparkmon.log
```

### SSH Connections Fail

```bash
# Test SSH connectivity
ssh gx10-1a2b hostname

# Check SSH key setup
sparkrun setup ssh-mesh
```

### No Metrics Showing

```bash
# Check if sparkrun jobs are running
sparkrun cluster status

# Verify monitoring is active
sparkrun sparkmon status
```

### High CPU Usage on Control Machine

```bash
# Increase sampling interval
sparkrun sparkmon start --interval=5

# Reduce number of monitored hosts
```

---

## Performance Considerations

- **Control Machine**: <5% CPU overhead, ~50MB RAM
- **Target Nodes**: No persistent daemons (SSH scripts only)
- **Network**: ~1KB per host per second (minimal bandwidth)
- **Storage**: ~1MB per hour per host (JSONL format)

---

## Next Steps

1. **Read the full design spec**: `research/sparkmon_Design_Spec.md`
2. **Set up development environment**: `uv pip install -e ".[dev]"`
3. **Implement Phase 1**: Core collector and CLI
4. **Test on single node**: Verify metrics collection
5. **Scale to cluster**: Test with 2+ nodes

---

**Document Version**: 1.0  
**Last Updated**: 2025-03-11
