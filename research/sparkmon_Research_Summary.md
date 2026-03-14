# Sparkmon Research Summary

This document summarizes the research and planning done for the sparkmon monitoring system.

---

## What We Learned

### 1. sparkrun Architecture (Reused Patterns)

**SSH-First, Agentless Design**
- All remote operations use `ssh host bash -s` with stdin piping
- No files ever copied to remote hosts
- Scripts generated as Python strings, piped directly
- Perfect for monitoring - lightweight, no persistent daemons

**Parallel Execution Pattern**
```python
# From orchestration/ssh.py
with ThreadPoolExecutor(max_workers=len(hosts)) as executor:
    futures = {executor.submit(run_remote_script, host, script): host for host in hosts}
    for future in as_completed(futures):
        results.append(future.result())
```
- Used throughout sparkrun for multi-host operations
- Perfect for monitoring - collect from all nodes simultaneously

**Existing Monitoring Infrastructure**
- `core/monitoring.py` - `ClusterMonitor` class already does parallel SSH streams
- `scripts/host_monitor.sh` - Already collects CPU/GPU/memory/temp
- CSV output, 2-second intervals, staleness detection, auto-reconnect
- **100% reusable** - just extend the class

**CLI Architecture**
- Click-based commands in `cli/` package
- Shared decorators in `cli/_common.py`
- Pattern: `sparkrun <group> <command> --options`
- Easy to add: `sparkrun sparkmon start --web`

### 2. DGX Spark Tools (/opt/nvidia)

**System Management Tools**
- `dgx-oobe/` - Out-of-box experience (WiFi hotspot, setup)
- `dgx-dashboard/` - Administration interface
- `spark-mlnx-firmware-manager/` - Mellanox firmware updates
- `dgx-spark-mlnx-hotplug/` - PCIe hotplug handling

**Performance Profiling Tools**
- `nsight-systems/2025.3.2/` - System-wide profiling (nsys)
  - Timeline view, CPU/GPU/system events
  - CUPTI libraries, eBPF support
  - ARM64/SBSA platform support
- `nsight-compute/2025.3.1/` - GPU kernel profiling (ncu)
  - Microarchitecture analysis, occupancy, memory
  - Performance rules, roofline model
  - ARM64/SBSA platform support

**Telemetry Services**
- `dgx-telemetry/` - General telemetry client (NVIDIA)
- `dgx-sol/` - Speed of Light telemetry (system metrics)
- Both use SQLite for local storage, send to NVIDIA endpoints

**Key Insight**: These are **system-level tools** for DGX Spark management. sparkmon operates at a **different layer** - workload orchestration monitoring. They complement rather than compete.

### 3. Network Topology

**InfiniBand Detection** (from `orchestration/infiniband.py`)
```bash
# Existing script pattern
ib_devices=$(ls /sys/class/infiniband 2>/dev/null)
if [ -n "$ib_devices" ]; then
    # Parse IB IPs, configure NCCL
fi
```
- DGX Sparks have Mellanox ConnectX-7 adapters
- Two PCIe domains (0000 and 0002)
- Fast-path IPs for data transfer
- **Reused in sparkmon** for topology visualization

**Network Stack**
- Management network (Ethernet) - SSH, Docker registry
- InfiniBand network - Fast data transfer, NCCL
- Optional: WiFi hotspot (OOBE only)

### 4. Process & Inference Metrics

**Process Metrics** (from `/proc/<pid>`)
- CPU time (utime/stime)
- Memory RSS/Virtual
- Thread count, file descriptors
- Network connections
- **Accessible via SSH** - no agent needed

**Inference Server Metrics**
- vLLM: `/v1/metrics` (Prometheus format)
- SGLang: `/metrics` endpoint
- Requests/sec, tokens/sec, queue depth, latency
- **Accessible via HTTP** - simple curl polling

---

## Design Decisions

### Why Extend ClusterMonitor?

**Option A: Build from Scratch** ❌
- Duplicate SSH stream management
- Duplicate staleness detection
- Duplicate parallel execution

**Option B: Extend ClusterMonitor** ✅
- Reuse existing SSH infrastructure
- Reuse auto-reconnect logic
- Just add new metric sources
- Minimal code, proven patterns

### Why Flask/FastAPI for Web Server?

**Option A: Full Stack (Node.js + Express)** ❌
- Requires Node.js installation
- Build tools, npm dependencies
- Overkill for simple dashboard

**Option B: Flask/FastAPI** ✅
- Python-only (sparkrun already uses Python)
- Minimal dependencies
- Built-in dev server
- WebSocket support (FastAPI)
- Serves static files

### Why Vue.js/Alpine.js for Frontend?

**Option A: React + Webpack** ❌
- Build toolchain required
- Complex setup
- Large bundle size

**Option B: Vue.js via CDN** ✅
- No build step
- Simple reactive binding
- Small footprint
- Easy to embed in single HTML file

### Why JSONL + SQLite Storage?

**Option A: Prometheus/InfluxDB** ❌
- Requires external server
- Complex setup
- Overkill for local monitoring

**Option B: JSONL files** ✅
- Human-readable
- Easy to parse
- Append-only (simple)

**Option C: JSONL + SQLite (Hybrid)** ✅✅
- JSONL for simplicity
- SQLite for querying
- Optional (can start with just JSONL)

### Why 2-5 Second Intervals?

**Option A: Sub-second** ❌
- High overhead on control machine
- Too much data storage
- Unnecessary for cluster monitoring

**Option B: 2-5 seconds** ✅
- Good balance of freshness vs overhead
- ~1KB per host per second
- Human-perceptible changes
- Matches `host_monitor.sh` default

---

## What We're NOT Doing

### Not a Full Monitoring Stack
- ❌ No Prometheus/Graphana replacement
- ❌ No complex alerting rules engine
- ❌ No multi-tenant support
- ✅ Focused on sparkrun cluster monitoring only

### Not Real-Time Sub-Second
- ❌ No 100ms updates
- ❌ No high-frequency trading precision
- ✅ 2-5 second intervals sufficient

### Not Persistent Agents
- ❌ No daemons on DGX Sparks
- ❌ No systemd services for monitoring
- ✅ SSH stdin piping only

### Not Replacing Nsight Tools
- ❌ No deep kernel profiling
- ❌ No CUDA performance analysis
- ✅ High-level metrics, use nsys/ncu for deep dive

---

## Implementation Strategy

### Phase-Based Approach

**Phase 1: Core (Week 1)**
- Reuse `ClusterMonitor`, extend for inference metrics
- Add network topology script
- Basic CLI (`start`, `stop`, `status`)
- **Goal**: Collect metrics, verify on single node

**Phase 2: Web UI (Week 2)**
- Flask server, REST API
- Vue.js dashboard, real-time charts
- **Goal**: View metrics in browser

**Phase 3: Topology (Week 3)**
- Network topology visualization
- Interactive node map
- **Goal**: See cluster connections

**Phase 4: Storage & Alerts (Week 4)**
- JSONL/SQLite persistence
- Alert rules, CLI management
- **Goal**: Historical data, notifications

**Phase 5: Polish (Week 5)**
- Error handling, performance
- Documentation, tests
- **Goal**: Production-ready

---

## Key Files Created (MVP)

| File | Purpose | Lines |
|------|---------|-------|
| `src/sparkrun/sparkmon/__init__.py` | Package init | 10 |
| `src/sparkrun/sparkmon/sparkmon.py` | CLI + Collector + Web Server | 350 |
| `src/sparkrun/sparkmon/web/index.html` | Dashboard | 400 |
| `src/sparkrun/sparkmon/README.md` | Documentation | 200 |
| **Total (MVP)** | | **~960** |

### Directory Structure
```
src/sparkrun/
├── cli/
│   ├── __init__.py
│   └── _sparkmon.py                 # Wrapper for sparkmon import
└── sparkmon/                        # Monitoring subsystem (subpackage)
    ├── __init__.py
    ├── __main__.py                  # Allows: python3 -m sparkrun.sparkmon
    ├── sparkmon.py                  # CLI + Collector + Web Server
    ├── web/
    │   └── index.html               # Dashboard
    └── README.md
```

---

## Success Metrics

### Technical
- ✅ Monitors 2-8 DGX Spark nodes
- ✅ Updates every 2-5 seconds
- ✅ <5% CPU overhead on control machine
- ✅ No agents on target nodes
- ✅ Works with all sparkrun runtimes

### User Experience
- ✅ Single command to start: `sparkrun sparkmon start --web`
- ✅ Web UI loads in browser
- ✅ Real-time updates visible
- ✅ Clear alerts for problems
- ✅ Easy to stop: Ctrl-C or `sparkrun sparkmon stop`

### Code Quality
- ✅ Reuses sparkrun patterns
- ✅ Follows existing style
- ✅ Well-documented
- ✅ Tested (unit + integration)
- ✅ No breaking changes to sparkrun

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| SSH connections drop | Auto-reconnect (already in ClusterMonitor) |
| Web UI slow with many nodes | Virtual scrolling, limit data points |
| Metrics storage grows large | Retention policy, compression |
| Inference endpoint changes | Abstract to plugin, fallback to nvidia-smi |
| User confusion | Clear docs, separate CLI group |

---

## Next Steps

1. **Review Design** - Read `sparkmon_Design_Spec.md`
2. **Approve Phase 1** - Green light to start coding
3. **Set Up Dev Environment** - `uv pip install -e ".[dev]"`
4. **Create Directory Structure** - `mkdir -p src/sparkrun/sparkmon/{web,scripts}`
5. **Implement Collector** - Start with `collector.py`
6. **Test on Single Node** - Verify metrics collection
7. **Iterate** - Add web UI, topology, alerts

---

## References

### Research Documents
- `sparkun-Design_Architecture.md` - sparkrun core architecture
- `nsight-systems.md` - NVIDIA profiling tools
- `nsight-compute.md` - GPU kernel profiler
- `dgx-telemetry.md` - NVIDIA telemetry services

### Source Code
- `src/sparkrun/core/monitoring.py` - ClusterMonitor class
- `src/sparkrun/orchestration/ssh.py` - SSH execution
- `src/sparkrun/scripts/host_monitor.sh` - System metrics
- `src/sparkrun/orchestration/infiniband.py` - IB detection

### Design Documents
- `sparkmon_Design_Spec.md` - Full design specification
- `sparkmon_Quick_Start.md` - User quick-start guide
- `sparkmon_Implementation_Checklist.md` - Phase checklist

---

## Conclusion

sparkmon extends sparkrun's agentless, SSH-first philosophy to provide real-time cluster monitoring with a modern web UI. By reusing existing patterns and adding focused new components, we can deliver a powerful monitoring tool without compromising sparkrun's design principles.

**Key Takeaways**:
- ✅ Reuse `ClusterMonitor` for SSH streams
- ✅ Reuse `host_monitor.sh` for system metrics
- ✅ Add network topology script (new)
- ✅ Add inference metrics polling (new)
- ✅ Flask + Vue.js for web UI (new)
- ✅ JSONL + SQLite for storage (new)
- ✅ Alert manager (new)

**Total Effort**: ~5 weeks, ~2200 lines of code  
**Risk**: Low (reuses proven patterns)  
**Value**: High (real-time visibility into cluster)

---

**Document Version**: 1.0  
**Last Updated**: 2025-03-11  
**Status**: Research Complete, Ready for Implementation
