# Sparkmon Implementation Checklist

Track progress through the implementation phases.

---

## Phase 1: Core Infrastructure

### Directory Structure
- [ ] Create `src/sparkrun/sparkmon/` directory (subpackage of sparkrun)
- [ ] Create `src/sparkrun/sparkmon/__init__.py`
- [ ] Create `src/sparkrun/sparkmon/web/` directory
- [ ] Create `src/sparkrun/sparkmon/scripts/` directory

### Scripts
- [ ] Create `scripts/network_topo.sh` - Network topology detection
- [ ] Create `scripts/process_metrics.sh` - Process-level metrics
- [ ] Create `scripts/inference_metrics.sh` - HTTP metrics polling
- [ ] Test scripts on single node

### Collector
- [ ] Implement `src/sparkrun/sparkmon/sparkmon.py` - `SparkmonCollector` class
  - [ ] Extend `ClusterMonitor` from `sparkrun.core.monitoring`
  - [ ] Add `_start_inference_polling()` method
  - [ ] Add `_fetch_topology()` method
  - [ ] Add `_start_process_monitoring()` method

### CLI
- [ ] Implement `src/sparkrun/sparkmon/cli.py` - Click commands
  - [ ] `sparkmon start` - Start monitoring
  - [ ] `sparkmon stop` - Stop monitoring
  - [ ] `sparkmon status` - Show status
  - [ ] Add to `sparkrun/cli/__init__.py` command registry (subcommand)

### Testing
- [ ] Test on single node (localhost)
- [ ] Test on 2-node cluster
- [ ] Verify SSH reconnection logic
- [ ] Verify metrics collection accuracy

---

## Phase 2: Web UI

### Web Server
- [ ] Implement `web_server.py` - Flask application
  - [ ] REST API: `/api/metrics` - Current metrics
  - [ ] REST API: `/api/topology` - Network topology
  - [ ] REST API: `/api/jobs` - Running jobs
  - [ ] REST API: `/api/alerts` - Active alerts
  - [ ] WebSocket: `/ws/metrics` - Real-time updates
  - [ ] Static file serving for `web/` directory

### Web UI - HTML Structure
- [ ] Create `web/index.html`
  - [ ] Header with cluster info
  - [ ] Main dashboard layout
  - [ ] Chart containers
  - [ ] Node table
  - [ ] Alerts panel

### Web UI - JavaScript
- [ ] Create `web/app.js`
  - [ ] Vue.js application initialization
  - [ ] WebSocket connection management
  - [ ] Metrics data binding
  - [ ] Auto-refresh logic

### Charts
- [ ] Integrate Chart.js
  - [ ] GPU utilization chart
  - [ ] Memory usage chart
  - [ ] Temperature chart
  - [ ] Configure real-time updates

### Styling
- [ ] Create `web/styles.css`
  - [ ] Responsive layout
  - [ ] Dark/light theme
  - [ ] Node table styling
  - [ ] Alert styling

### Testing
- [ ] Test web UI in browser
- [ ] Test real-time updates
- [ ] Test with multiple hosts
- [ ] Test error handling (no metrics)

---

## Phase 3: Topology & Advanced Features

### Network Topology Visualization
- [ ] Integrate vis-network or D3.js
- [ ] Create `web/topology.js`
  - [ ] Parse topology data from API
  - [ ] Render nodes and edges
  - [ ] Add interactivity (click, hover)
  - [ ] Animate traffic flow

### Node Drill-Down
- [ ] Implement node detail view
  - [ ] Click node to see details
  - [ ] Show process metrics
  - [ ] Show inference metrics
  - [ ] Logs viewer

### Logs Streaming
- [ ] Implement log streaming via WebSocket
  - [ ] `/ws/logs/{host}/{container}`
  - [ ] Display in web UI
  - [ ] Auto-scroll, pause controls

### Testing
- [ ] Test topology rendering
- [ ] Test with IB and Ethernet networks
- [ ] Test node drill-down
- [ ] Test log streaming

---

## Phase 4: Storage & Alerts

### Storage Layer
- [ ] Implement `storage.py`
  - [ ] JSONL file storage
  - [ ] SQLite optional backend
  - [ ] `save_snapshot()` method
  - [ ] `get_history()` method
  - [ ] Retention policy

### Alert Manager
- [ ] Implement `alerts.py`
  - [ ] `AlertRule` dataclass
  - [ ] `AlertManager` class
  - [ ] Default alert rules
  - [ ] Cooldown logic

### CLI - Alerts
- [ ] Add `sparkmon alert add` command
- [ ] Add `sparkmon alert list` command
- [ ] Add `sparkmon alert remove` command

### CLI - Export
- [ ] Add `sparkmon export` command
  - [ ] JSON format
  - [ ] CSV format
  - [ ] Time range selection

### WebSocket Notifications
- [ ] Push alerts to web UI via WebSocket
- [ ] Display in alerts panel
- [ ] Sound/notification options

### Testing
- [ ] Test storage (write/read)
- [ ] Test alert triggering
- [ ] Test alert cooldown
- [ ] Test export functionality

---

## Phase 5: Polish & Documentation

### Error Handling
- [ ] Add try/catch to all async operations
- [ ] Add retry logic for SSH failures
- [ ] Add graceful degradation
- [ ] Add user-friendly error messages

### UI/UX Improvements
- [ ] Responsive design (mobile-friendly)
- [ ] Dark mode toggle
- [ ] Loading states
- [ ] Empty states (no data)
- [ ] Tooltips and help text

### Performance Optimization
- [ ] Profile collector performance
- [ ] Optimize WebSocket updates
- [ ] Implement data sampling for long histories
- [ ] Lazy load charts

### Documentation
- [ ] Write README.md for sparkmon
- [ ] Add docstrings to all functions
- [ ] Update `CLAUDE.md` with sparkmon info
- [ ] Create user guide
- [ ] Create developer guide

### Tests
- [ ] Unit tests for collector
- [ ] Unit tests for storage
- [ ] Unit tests for alerts
- [ ] Integration tests for CLI
- [ ] E2E tests for web UI

### Final Testing
- [ ] Test on 4-node cluster
- [ ] Test on 8-node cluster
- [ ] Test with vLLM runtime
- [ ] Test with SGLang runtime
- [ ] Test with mixed runtimes
- [ ] Load test (high frequency updates)

---

## Documentation Files to Create

- [ ] `src/sparkrun/sparkmon/README.md` - Package overview
- [ ] `research/sparkmon_Design_Spec.md` - ✅ Done
- [ ] `research/sparkmon_Quick_Start.md` - ✅ Done
- [ ] `research/sparkmon_Implementation_Checklist.md` - This file
- [ ] `docs/sparkmon.md` - User documentation

---

## Documentation Files to Update

- [ ] `CLAUDE.md` - Add sparkmon section
- [ ] `pyproject.toml` - Add sparkmon entry point
- [ ] `cli/__init__.py` - Register sparkmon command
- [ ] `research/sparkun-Design_Architecture.md` - Reference sparkmon

---

## Success Criteria Checklist

### Functional
- [ ] Monitor 2-8 nodes simultaneously
- [ ] Update metrics every 2-5 seconds
- [ ] Display GPU/CPU/memory/temperature
- [ ] Show network topology
- [ ] Web UI accessible via browser
- [ ] Alert on configurable thresholds
- [ ] Export metrics to file
- [ ] Non-intrusive to inference jobs

### Non-Functional
- [ ] <5% CPU overhead on control machine
- [ ] No persistent daemons on target nodes
- [ ] Auto-reconnect on SSH failures
- [ ] Single command to start
- [ ] Works with all sparkrun runtimes

---

## Notes

### Phase 1 Completion Criteria
- [ ] `sparkrun sparkmon start --hosts=x,x` works
- [ ] Metrics visible in logs
- [ ] No crashes after 1 hour

### Phase 2 Completion Criteria
- [ ] Web UI loads at `localhost:8080`
- [ ] Charts update in real-time
- [ ] Node table shows data

### Phase 3 Completion Criteria
- [ ] Topology map renders
- [ ] Nodes are clickable
- [ ] Logs stream correctly

### Phase 4 Completion Criteria
- [ ] Metrics persist to disk
- [ ] Alerts trigger on threshold
- [ ] Export produces valid file

### Phase 5 Completion Criteria
- [ ] All tests pass
- [ ] Documentation complete
- [ ] No critical bugs

---

**Last Updated**: 2025-03-11  
**Status**: Not Started
