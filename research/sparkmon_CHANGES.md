# Sparkmon Implementation Changes

This document tracks changes made during implementation that differ from the original design.

---

## Change 1: Package Structure

### Original Design
```
src/
├── sparkrun/                    # Main package
└── sparkmon/                    # Peer package (separate)
```

**Rationale**: Keep monitoring subsystem modular and independent

### Final Implementation
```
src/sparkrun/
├── cli/
│   └── _sparkmon.py            # Wrapper import
└── sparkmon/                   # Subpackage (inside sparkrun)
```

**Rationale**: Avoid circular import issues, standard Python pattern

### Impact
- **Files affected**: All documentation, import paths
- **Code changes**: Added `cli/_sparkmon.py` wrapper, updated `__main__.py`
- **User impact**: None - CLI commands work the same way
- **Benefit**: Simpler, no circular imports, works both as CLI and module

---

## Change 2: Implementation Approach

### Original Design
- Separate files: `collector.py`, `web_server.py`, `storage.py`, `alerts.py`
- Modular architecture from the start

### Final Implementation (MVP)
- Single file: `sparkmon.py` (~350 lines)
- All functionality in one file (CLI + Collector + Web Server)
- `web/` directory for static files only

**Rationale**: Faster MVP, easier to test, can refactor later

### Impact
- **Code size**: ~350 lines (vs. estimated 800 for modular)
- **Benefit**: Delivered in 1 day vs. 10-14 days estimated
- **Trade-off**: Will need refactoring for post-MVP features

---

## Change 3: Web Framework

### Original Design
- Vue.js + Chart.js + D3.js (multiple libraries)

### Final Implementation
- Vanilla JS + Chart.js only
- No Vue.js (too complex for MVP)
- No D3.js (deferred to post-MVP)

**Rationale**: Simpler, good enough for MVP charts

### Impact
- **Code size**: ~400 lines HTML/JS (vs. estimated 800)
- **Benefit**: Faster development, easier to maintain
- **Trade-off**: No topology visualization (post-MVP)

---

## Change 4: Storage

### Original Design
- JSONL + optional SQLite from the start

### Final Implementation (MVP)
- In-memory only
- No persistent storage

**Rationale**: MVP doesn't need history yet

### Impact
- **Code size**: Saved ~150 lines
- **Benefit**: Simpler, faster to implement
- **Trade-off**: Metrics lost on restart (acceptable for MVP)

---

## Summary

| Aspect | Original Design | Final Implementation | Impact |
|--------|----------------|---------------------|--------|
| Package structure | Peer package | Subpackage | ✅ Simpler, no circular imports |
| Code organization | Modular (4 files) | Single file | ✅ Faster MVP, can refactor later |
| Web framework | Vue.js + Chart.js + D3.js | Vanilla JS + Chart.js | ✅ Simpler, good enough |
| Storage | JSONL + SQLite | In-memory only | ✅ MVP scope appropriate |
| Timeline | 10-14 days | 1 day | ✅ Delivered 10x faster |

**Conclusion**: All changes were pragmatic decisions that maintained the core value proposition while significantly reducing complexity and delivery time. The architecture can be evolved in post-MVP iterations as needed.
