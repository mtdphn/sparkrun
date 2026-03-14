# Update Plan: Post-Review Fixes

Based on a review of recent additions (sparkmon, launcher refactor, proxy enhancements, Architecture.md, research docs).

---

## Phase 1: Critical Fixes

Bugs and safety issues that should be addressed immediately.

### 1.1 Fix `export` command import bug

**File:** `src/sparkrun/sparkmon/sparkmon.py` (lines 332-345)

**Problem:** The `export` command references `SparkrunConfig` and `build_ssh_kwargs` without importing them. The `start` and `status` commands import these inside their function bodies (lazy import pattern), but `export` does not. Calling `sparkrun sparkmon export` will crash with `NameError`.

**Fix:** Add the missing lazy imports inside the `export` function:

```python
from sparkrun.core.config import SparkrunConfig
from sparkrun.orchestration.primitives import build_ssh_kwargs
```

### 1.2 Fix thread safety in SparkmonCollector

**File:** `src/sparkrun/sparkmon/sparkmon.py`

**Problem:** Multiple thread-safety issues:

- `self.metrics[host]` (a plain `list`) is appended to from SSH reader threads and read from Flask request handler threads concurrently with no synchronization.
- The list trimming on line 59 (`self.metrics[host] = self.metrics[host][-self.max_samples:]`) replaces the list object entirely. A concurrent reader could see a partially-constructed list or hold a reference to the old (now-stale) list.
- Global `_collector_ref` is written from the CLI thread and read from Flask handler threads without synchronization.

**Fix:**

- Replace `list` with `collections.deque(maxlen=max_samples)`. Deque is thread-safe for single-producer append and consumer iteration. The `maxlen` parameter handles trimming automatically, eliminating the dangerous reassignment.
- Pass the collector to Flask via `app.config["collector"]` instead of using a module-level global. Access it in route handlers via `flask.current_app.config["collector"]`.

### 1.3 Fix silent exception swallowing

**File:** `src/sparkrun/sparkmon/sparkmon.py` (line 62)

**Problem:** `except Exception: pass` in `_reader()` silently discards all errors, including broken SSH connections, malformed output, and unexpected exceptions. Debugging issues in production becomes impossible.

**Fix:** Log the exception at `debug` level, consistent with error handling patterns elsewhere in the codebase:

```python
except Exception:
    logger.debug("Reader error for host %s", host, exc_info=True)
```

### 1.4 Fix file handle leaks in ProxyEngine

**File:** `src/sparkrun/proxy/engine.py` (lines 210-211, 283-284)

**Problem:** In both `start()` (non-foreground path) and `start_autodiscover()`, a log file is opened but never closed. The file descriptor leaks for the lifetime of the sparkrun process.

```python
log_file = open(log_path, "w")         # opened
proc = subprocess.Popen(..., stdout=log_file, ...)  # passed to subprocess
# log_file is never closed
```

**Fix:** Close the file handle after `Popen` since the subprocess inherits the fd:

```python
log_file = open(log_path, "w")
proc = subprocess.Popen(..., stdout=log_file, ...)
log_file.close()
```

In `start_autodiscover`, also close `log_file` in the success path (currently only closed in the `except` branch).

---

## Phase 2: Test Coverage for Sparkmon

Sparkmon is the only subsystem shipped without any tests. The rest of the codebase maintains ~0.84:1 test-to-source ratio.

### 2.1 Create `tests/test_sparkmon.py`

**Target:** ~400 lines of tests covering the 478-line sparkmon module.

**Test cases:**

| Area | Tests |
|------|-------|
| `SparkmonCollector` | Metric storage and deque trimming; verify `max_samples` is respected; mock SSH subprocess stdout to feed CSV lines; verify `parse_monitor_line` integration |
| Flask API routes | Use Flask test client to test `/api/metrics` (returns stored metrics), `/api/status` (returns host count, interval, running state), `/api/health` (returns 200) |
| Flask error states | `/api/metrics` when no collector is set returns 400 |
| `generate_mock_metrics` | Returns dict with all expected keys; values are within expected ranges |
| CLI `start` | Mock `_resolve_hosts_or_exit`, `build_ssh_kwargs`, and `SparkmonCollector`; verify collector is started with correct args |
| CLI `status` | Mock collector; verify table output formatting |
| CLI `export` | Mock collector; verify JSON output structure; verify `--output` writes to file |
| CLI `demo` | Verify `MockCollector` is created; verify mock data generation runs |

**Patterns:** Follow existing test conventions:
- Use `unittest.mock.patch` for SSH/config mocking
- Use `click.testing.CliRunner` for CLI command tests
- Import paths use `sparkrun.sparkmon.sparkmon`

---

## Phase 3: Dependency and Integration Cleanup

### 3.1 Make Flask an optional dependency

**Files:** `pyproject.toml`, `src/sparkrun/sparkmon/sparkmon.py`

**Problem:** Flask is listed as a hard dependency in `pyproject.toml` (`flask>=3.0`), but sparkmon is described as an "optional monitoring subsystem" in its README. Every sparkrun user pays the install cost of Flask and its transitive dependencies (Werkzeug, Jinja2, MarkupSafe, etc.) even if they never use monitoring.

**Fix:**

- Move `flask>=3.0` from `dependencies` to `[project.optional-dependencies]` under a `monitoring` extra.
- Add a graceful import check at the top of `sparkmon.py`:
  ```python
  try:
      import flask
  except ImportError:
      flask = None
  ```
- In commands that need Flask (`start`, `demo`), check and exit with a clear message:
  ```python
  if flask is None:
      click.echo("Error: Flask is required for sparkmon. Install with: pip install sparkrun[monitoring]", err=True)
      ctx.exit(1)
  ```
- Update the sparkmon README to consistently reference `pip install sparkrun[monitoring]`.

### 3.2 Deduplicate node-trimming logic

**Files:** `src/sparkrun/cli/_run.py` (lines 139-182), `src/sparkrun/cli/_proxy.py` (lines 496-522), `src/sparkrun/cli/_common.py`

**Problem:** The node count validation, `compute_required_nodes`, `_apply_node_trimming`, and `max_nodes` enforcement logic is duplicated between the `run` command and `proxy load` command. Any bug fix or behavior change must be applied in both places.

**Fix:** Extract a shared helper in `_common.py`:

```python
def _validate_and_trim_hosts(
    host_list: list[str],
    recipe,
    overrides: dict,
    runtime,
    solo: bool,
) -> tuple[list[str], bool]:
    """Validate node count and trim host list.

    Returns:
        Tuple of (trimmed_host_list, is_solo).
    """
```

Both `run` and `proxy load` call this helper instead of duplicating the logic.

### 3.3 Align sparkmon CLI with shared host_options

**Files:** `src/sparkrun/sparkmon/sparkmon.py`, `src/sparkrun/cli/_common.py`

**Problem:** Sparkmon manually defines `--hosts`, `--cluster`, `--ssh-user`, `--ssh-key` options on each command, duplicating the `host_options` decorator from `_common.py`. This creates inconsistency:
- Other commands get `--hosts-file` support; sparkmon doesn't.
- Other commands resolve SSH user from cluster definitions; sparkmon only uses explicit `--ssh-user`.
- The option names and help text may drift.

**Fix:** Use the `host_options` decorator from `_common.py` on sparkmon commands. For SSH user/key overrides, use the existing resolution chain (`_resolve_hosts_or_exit` + `build_ssh_kwargs`).

---

## Phase 4: Code Hygiene

### 4.1 Remove commented-out proxy discover command

**File:** `src/sparkrun/cli/_proxy.py` (lines 239-297)

**Problem:** ~60 lines of commented-out code for the `proxy discover` command with a `# NOTE: not deleting yet` comment. Commented-out code is noise; git preserves history.

**Fix:** Delete the entire commented block.

### 4.2 Fix proxy load race condition

**File:** `src/sparkrun/cli/_proxy.py` (line 562)

**Problem:** After `launch_inference`, the proxy load command does `time.sleep(2)` and then immediately tries to discover and health-check the new endpoint. This is a race condition — 2 seconds may not be enough for model loading (which can take minutes for large models).

**Fix:** Use the same health-check polling pattern as the `run` command:

```python
from sparkrun.orchestration.primitives import wait_for_healthy

health_url = "http://%s:%d/v1/models" % (head_host, result.serve_port)
healthy = wait_for_healthy(health_url, max_retries=120, retry_interval=5, dry_run=dry_run)
```

Then discover and register only after health check passes.

### 4.3 Add --bind option to sparkmon web server

**File:** `src/sparkrun/sparkmon/sparkmon.py` (line 120)

**Problem:** The Flask server binds to `0.0.0.0` unconditionally, exposing the monitoring dashboard to all network interfaces. On shared machines this may be undesirable.

**Fix:**

- Add `--bind` / `--host` option to `start` and `demo` commands (default: `127.0.0.1`).
- Pass the bind address to `run_web_server()`.
- Matches the proxy's existing `--host` option pattern.

### 4.4 Make sparkmon stop command functional or hidden

**File:** `src/sparkrun/sparkmon/sparkmon.py` (lines 232-240)

**Problem:** The `stop` command is a placeholder that prints "use Ctrl-C." It's listed alongside working commands, which is confusing.

**Fix:** Either:

- **(A) Implement it** using the same PID-file pattern as `ProxyEngine`: write PID to `~/.cache/sparkrun/sparkmon/state.yaml` on start, send SIGTERM on stop.
- **(B) Hide it** until implemented: `@sparkmon.command("stop", hidden=True)`.

Option A is preferred for consistency with the proxy subsystem.

---

## Phase 5: Documentation

### 5.1 Commit Architecture.md

**File:** `Architecture.md` (currently untracked)

**Problem:** High-quality architectural documentation sitting as an untracked file.

**Fix:**

- Remove specific line counts (e.g., "`_common.py` | 783") — replace with `~N` approximations or remove entirely. These go stale quickly.
- Add a "Last updated" note at the top.
- `git add Architecture.md` and commit.

### 5.2 Clean up research directory

**Directory:** `research/` (11 files, ~120KB)

**Problem:** Implementation process artifacts (design specs, checklists, PR descriptions) for sparkmon shipped in the main branch. These are useful during development but are not project documentation.

**Fix:** Options in order of preference:

1. Delete from main branch (preserved in git history via commit `485b4dc`).
2. Move to `docs/internal/` with a README noting these are historical development artifacts.
3. Add `research/` to `.gitignore` to prevent future accumulation.

---

## Phase 6: Launcher Interface Polish (Low Priority)

### 6.1 Generalize runtime-specific kwargs

**File:** `src/sparkrun/core/launcher.py` (lines 64-67)

**Problem:** `launch_inference()` has four runtime-specific keyword arguments (`ray_port`, `dashboard_port`, `dashboard`, `init_port`) baked into its generic signature. As new runtimes are added, this list will grow.

**Fix:** Replace with a single pass-through dict:

```python
def launch_inference(
    *,
    # ... generic params ...
    runtime_kwargs: dict[str, Any] | None = None,
) -> LaunchResult:
```

Callers build the dict:

```python
runtime_kwargs = {}
if ray_port is not None:
    runtime_kwargs["ray_port"] = ray_port
# ...
result = launch_inference(..., runtime_kwargs=runtime_kwargs)
```

`launch_inference` passes it through: `runtime.run(..., **runtime_kwargs)`.

---

## Execution Priority

| Phase | Scope | Risk if Deferred |
|-------|-------|-----------------|
| **1** | Critical fixes | Crashes, data races, resource leaks in shipped code |
| **2** | Sparkmon tests | Regressions go undetected; only untested subsystem |
| **3** | Dependency/integration | Flask bloat for all users; duplicated logic drifts |
| **4** | Code hygiene | Dead code, race conditions, security defaults |
| **5** | Documentation | Untracked useful docs; repo clutter |
| **6** | Interface polish | Manageable tech debt; can wait for next runtime addition |
