# Sparkrun Architecture

> Last updated: March 2026

## High-Level Overview

**sparkrun** is a Python CLI tool (Python 3.12+) for launching, managing, and stopping Docker-based LLM inference workloads on NVIDIA DGX Spark systems. It orchestrates containers over SSH from a control machine — no Slurm or Kubernetes required.

Each DGX Spark has one GPU with 128 GB unified memory, so tensor parallelism maps directly to node count (`--tp 2` = 2 hosts). sparkrun handles the full lifecycle: recipe resolution, container image distribution, model syncing, InfiniBand detection, multi-node clustering, health checks, benchmarking, and monitoring.

### Design Philosophy

- **SSH-first orchestration**: All remote operations use stdin piping (`ssh host bash -s`). No files are copied to remote hosts; scripts are generated as Python strings and streamed.
- **Plugin-based runtimes**: Runtimes (vLLM, SGLang, llama.cpp, TRT-LLM) are SAF plugins discovered via Python entry points — extensible without core changes.
- **Recipe-driven configuration**: YAML recipes define model + runtime + container + defaults. A VPD config chain (CLI overrides -> recipe defaults -> runtime defaults) resolves all parameters.
- **Separation of concerns**: Clear boundaries between CLI presentation, core domain logic, orchestration primitives, and runtime-specific behavior.

---

## System Architecture Diagram

```
                          ┌─────────────────────────────────────────┐
                          │            User / CI / CC Plugin        │
                          └────────────────┬────────────────────────┘
                                           │
                          ┌────────────────▼────────────────────────┐
                          │          CLI Layer (Click)              │
                          │  run | stop | logs | setup | cluster   │
                          │  recipe | registry | benchmark | tune  │
                          │  proxy | monitor                       │
                          └───┬──────────┬──────────┬──────────────┘
                              │          │          │
              ┌───────────────▼──┐   ┌───▼────┐  ┌─▼──────────────┐
              │   Core Domain    │   │Runtime │  │  Benchmarking  │
              │  Recipe/Registry │   │Plugins │  │  Framework     │
              │  Config/Cluster  │   │(SAF)   │  │  (SAF)         │
              │  Bootstrap/Hosts │   └───┬────┘  └───┬────────────┘
              └───────┬──────────┘       │           │
                      │          ┌───────▼───────────▼──────────┐
                      │          │    Orchestration Layer       │
                      └──────────►  SSH | Docker | IB | Sudo   │
                                 │  Distribution | Scripts     │
                                 │  Hooks | Job Metadata       │
                                 │  Networking                 │
                                 └──────────────┬──────────────┘
                                                │
                      ┌─────────────────────────▼──────────────────┐
                      │           Support Modules                  │
                      │  Models (download/distribute/VRAM)         │
                      │  Containers (pull/distribute/sync)         │
                      │  Tuning (MoE kernels, sync)                │
                      │  Builders (eugr, docker-pull)              │
                      │  Proxy (LiteLLM gateway)                   │
                      │  Monitoring (host metrics, TUI)            │
                      └────────────────────────────────────────────┘
```

---

## Source Layout

```
src/sparkrun/
├── cli/                # Click CLI command package
├── core/               # Domain models, bootstrap, business logic
├── runtimes/           # Runtime plugins (vLLM, SGLang, llama.cpp, TRT-LLM)
├── orchestration/      # SSH, Docker, IB, script execution, networking
├── models/             # HuggingFace model download and distribution
├── containers/         # Container image distribution (docker save/load)
├── tuning/             # Triton fused MoE kernel tuning
├── benchmarking/       # Benchmark framework plugins (llama-benchy)
├── builders/           # Container image build plugins (eugr, docker-pull)
├── proxy/              # LiteLLM-based unified inference gateway
├── scripts/            # Embedded bash scripts (26 scripts)
├── utils/              # Shared helpers (coerce_value, formatters, etc.)
├── __init__.py         # Package version
└── __main__.py         # Entry point: calls cli.main()
```

---

## In-Depth Component Review

### 1. CLI Layer (`cli/`)

**Purpose**: User-facing command-line interface built with Click. Split from a monolithic `cli.py` into a package for maintainability.

**Entry point**: `__init__.py` defines the `main` Click group, registers all subcommands, and provides top-level aliases (`list`, `show`, `search`, `status`).

| Module | Purpose |
|--------|---------|
| `__init__.py` | Main Click group, command registration, aliases |
| `_common.py` | Shared infrastructure: logging, Click parameter types (`RECIPE_NAME`, `REGISTRY_NAME`, `RUNTIME_NAME`, `CLUSTER_NAME`, `PROFILE_NAME`), decorators (`host_options`, `dry_run_option`), host resolution, recipe loading, VRAM display |
| `_run.py` | `run` command — launches inference workloads with full lifecycle |
| `_stop_logs.py` | `stop` and `logs` commands |
| `_setup.py` | `setup` group — shell completion, SSH mesh, model/container sync, permissions, cache, networking |
| `_cluster.py` | `cluster` group — CRUD for saved cluster definitions, cluster status |
| `_recipe.py` | `recipe` group — list/show/search recipes |
| `_registry.py` | `registry` group — add/remove/enable/disable/update registries, benchmark profiles |
| `_benchmark.py` | `benchmark` group — run benchmark profiles |
| `_tune.py` | `tune` group — Triton MoE kernel tuning |
| `_proxy.py` | `proxy` group — LiteLLM gateway management, model load/unload, aliases |
| `_monitor_tui.py` | Textual TUI for cluster monitoring dashboard |

**Key design decisions**:
- `_common.py` is the largest CLI file (783 lines), serving as shared infrastructure. It centralizes host resolution logic, recipe loading with error handling, and custom Click parameter types with tab completion support (including `@registry/recipe` syntax).
- Lazy imports are used throughout — modules like `sparkrun.core.bootstrap` are imported inside command functions to keep CLI startup fast.
- All commands support `--dry-run` via a shared decorator.
- Host resolution follows a priority chain: CLI `--hosts` -> `--hosts-file` -> `--cluster` -> default config.

**Observation**: `_common.py` is the largest CLI module — it contains parameter types, decorators, host resolution, recipe loading, VRAM display, and various helper functions. Consider whether some of this could be split (e.g., parameter types into their own module) if it continues to grow.

---

### 2. Core Domain (`core/`)

**Purpose**: Core business logic and domain models. All imports use `sparkrun.core.*` paths.

| Module | Key Classes/Functions |
|--------|----------------------|
| `bootstrap.py` | `init_sparkrun()`, `get_runtime()` — SAF plugin initialization, runtime/benchmarking/builder discovery |
| `config.py` | `SparkrunConfig` — reads `~/.config/sparkrun/config.yaml`, cache dir resolution |
| `recipe.py` | `Recipe` class, `find_recipe()`, v1->v2 migration, VPD config chain, validation |
| `registry.py` | `RegistryManager` — git-based recipe registry with sparse checkouts, manifest discovery, shared clones |
| `cluster_manager.py` | `ClusterManager` — named cluster CRUD (YAML files), cluster status queries |
| `hosts.py` | Host resolution priority chain, `is_local_host()` detection |
| `pending_ops.py` | PID-based lock files for in-progress operations |
| `benchmark_profiles.py` | Benchmark profile discovery, resolution, rendering |
| `monitoring.py` | `ClusterMonitor`, `MonitorSample` — parallel SSH monitoring streams with watchdog |

#### Recipe System

The recipe system is the core domain object. Key aspects:

- **Recipe class**: Wraps YAML recipe data with typed properties (`model`, `runtime`, `container`, `command`, `defaults`, `env`, `min_nodes`, `max_nodes`, `pre_exec`, `post_exec`, `post_commands`, `builder`, etc.).
- **VPD config chain**: Uses `vpd_chain()` to create a layered config: CLI overrides -> recipe defaults -> runtime defaults. The `arg_substitute()` function renders `{key}` placeholders in command templates.
- **Format versions**: v1 (eugr-style with `build_args`/`mods`) and v2 (sparkrun native). Auto-detection and migration from v1 to v2.
- **Runtime inference**: When no explicit `runtime` is set, the system infers it from the `command` prefix (regex-based detection of `vllm serve`, `sglang serve`, `llama-server`, `trtllm-serve`).
- **Recipe resolution**: `find_recipe()` searches bundled recipes, local `./recipes/`, user config recipes, and git-cloned registries.
- **Validation**: Warns on unknown keys, validates `min_nodes`/`max_nodes` constraints, checks for trailing-space line continuations in commands.

#### Registry System (largest source file)

The registry system manages collections of recipes from remote git repos:

- **Sparse checkouts**: Clones only the recipe subdirectory, not the full repo.
- **Shared clones**: Multiple registries pointing to the same URL share a single clone at `_url_<hash>/` with per-registry symlinks. Sparse checkout paths are the union of all subpaths.
- **Manifest discovery**: On first run, clones default registry URLs, reads `.sparkrun/registry.yaml` manifests, and merges with fallback defaults.
- **Reserved names**: Prefixes like `sparkrun`, `official`, `arena` are restricted to allowed GitHub organizations.
- **Tab completion**: `RecipeNameType.shell_complete()` supports `@registry/recipe` syntax.

**Observation**: `registry.py` is the largest source file. The complexity of manifest discovery, shared clone management, fallback merging, and reserved name enforcement all live in one module. The sparse checkout logic with symlinks and union path computation is particularly intricate. This is the most complex single module and a potential maintenance concern.

#### Monitoring System

A newer addition providing real-time cluster monitoring:

- `ClusterMonitor` manages parallel SSH subprocesses that run `host_monitor.sh` on remote hosts.
- Each host streams CSV metrics (CPU, memory, GPU utilization, temperature, power, sparkrun jobs).
- A background watchdog thread detects stale connections and reconnects automatically.
- Feeds into either the Textual TUI (`_monitor_tui.py`) or a plain-text streaming fallback.

---

### 3. Runtime Plugin System (`runtimes/`)

**Architecture**: All runtimes extend `RuntimePlugin` (base.py, 959 lines), which itself extends SAF's `Plugin` class. Discovered via Python entry points defined in `pyproject.toml`.

```
RuntimePlugin (base.py)
├── VllmDistributedRuntime (vllm_distributed.py)
├── VllmRayRuntime (vllm_ray.py)
│   └── EugrVllmRayRuntime (eugr_vllm_ray.py)
├── SglangRuntime (sglang.py)
├── LlamaCppRuntime (llama_cpp.py)
└── TrtllmRuntime (trtllm.py)
```

| Runtime | Clustering Strategy | Multi-Node Mechanism |
|---------|--------------------|-----------------------|
| vllm-distributed | `native` | Each node runs serve independently with `--node-rank` |
| vllm-ray | `ray` | Starts Ray cluster, exec serve on head |
| eugr-vllm | `ray` (inherited) | Extends VllmRayRuntime with eugr container builds |
| sglang | `native` | Each node runs serve with `--node-rank` |
| llama-cpp | `native/rpc` | Workers run `rpc-server`, head connects via `--rpc` |
| trtllm | `native` | MPI orchestration with custom rsh wrapper via `docker exec` |

#### Base Class Design

The base `RuntimePlugin` provides substantial shared orchestration:

- **Solo mode**: Full container lifecycle (cleanup, launch, health check, log streaming) for single-node deployments.
- **Cluster orchestration**: Dispatches to the appropriate strategy based on `cluster_strategy()` return value:
  - `"ray"` — Ray head/worker pattern
  - `"native"` — Independent per-node containers with coordinated launch
- **Hook execution**: Pre/post-exec hooks via the hooks system.
- **Health checking**: Polls container health endpoint with configurable timeout and interval.
- **Flag generation**: `build_flags_from_map()` and `strip_flags_from_command()` — generic helpers for constructing and manipulating CLI flag strings from config dicts.
- **Banner/connection info**: Pretty-printed launch summaries with host/port/model information.

**Observation**: The base class is quite large. It encodes the orchestration logic for both solo and cluster modes, plus shared helpers. The cluster dispatch (`_run_cluster` vs `_run_solo`) pattern is clean, but the volume of shared orchestration code in the base could make it harder for new runtime implementors to understand the full lifecycle.

#### TRT-LLM Runtime (newest runtime)

Notable for its unique multi-node approach:
- Uses MPI (`mpirun`) with a **custom rsh wrapper script** that routes through host-level SSH + `docker exec` into worker containers.
- Avoids installing openssh-server inside containers.
- Generates extra LLM API config YAML and writes it into containers.
- The rsh wrapper is dynamically generated with host-to-container IP mappings.

---

### 4. Orchestration Layer (`orchestration/`)

**Purpose**: All remote execution primitives. This is the "infrastructure" layer — the only code that actually talks to remote machines.

| Module | Purpose |
|--------|---------|
| `ssh.py` | `RemoteResult`, `build_ssh_cmd()`, `run_remote_script()`, `run_remote_scripts_parallel()`, `run_rsync_parallel()`, `stream_remote_logs()`, `run_remote_command()` |
| `docker.py` | Pure command-string generators (no execution): `docker_run_cmd`, `docker_exec_cmd`, `docker_stop_cmd`, `generate_node_container_name`, cluster ID generation |
| `primitives.py` | Higher-level composition: `build_ssh_kwargs()`, `build_volumes()`, `merge_env()`, `detect_infiniband()`, `detect_host_ip()`, `is_container_running()`, `resolve_nccl_env()`, `run_script_on_host()`, `cleanup_containers()` |
| `distribution.py` | Orchestrates pre-launch resource distribution: IB detection, container image sync, model sync |
| `hooks.py` | Pre/post lifecycle hook execution (pre_exec, post_exec, post_commands) with template rendering |
| `infiniband.py` | IB detection script generation, NCCL env var computation, IB IP mapping |
| `networking.py` | ConnectX-7 NIC detection, IP assignment planning, CX7 configuration |
| `scripts.py` | `generate_container_launch_script()`, `read_script()` for embedded bash scripts |
| `sudo.py` | `run_with_sudo_fallback()` — tries non-interactive sudo, falls back to password |
| `job_metadata.py` | Persistent job metadata (cluster_id -> recipe mapping) in `~/.cache/sparkrun/jobs/` |

#### SSH Execution Model

The SSH module is the second-largest source file. Key design:

- **Stdin piping**: Scripts are generated as Python strings and piped to `ssh host bash -s`. No SCP, no temp files on remote hosts.
- **Parallelism**: `run_remote_scripts_parallel()` and `run_rsync_parallel()` use `ThreadPoolExecutor` for concurrent multi-host operations.
- **Log streaming**: `stream_remote_logs()` tails container logs in real-time, with reconnection support.
- **Rsync integration**: `run_rsync_parallel()` orchestrates parallel rsync transfers with SSH key/options passthrough.

**Observation**: `ssh.py` is the largest orchestration module — basic SSH commands, parallel execution, rsync, log streaming, and remote command execution. The module is cohesive (all SSH-related), but its size suggests it could benefit from internal organization (e.g., separating the log streaming subsystem).

#### Hooks System

A lifecycle hook system supporting:
- **`pre_exec`**: Commands run inside containers before the serve command (on all nodes).
- **`post_exec`**: Commands run inside the head container after server health check passes.
- **`post_commands`**: Commands run on the control machine after server is healthy.
- **File injection**: `copy` commands support local-to-container, remote-to-container, and cross-host delegated copy via rsync.
- **Template rendering**: Uses VPD's `arg_substitute()` for `{key}` placeholder substitution with runtime context (head_host, port, base_url, etc.).

#### Networking

Handles ConnectX-7 NIC configuration for high-speed inter-node communication:
- NIC detection via remote script execution.
- IP assignment planning with conflict avoidance.
- CX7 configuration script generation.
- Host key distribution for SSH mesh setup.

---

### 5. Model & Container Distribution

#### Models (`models/`)

| Module | Purpose |
|--------|---------|
| `download.py` | HuggingFace Hub `snapshot_download` wrapper, GGUF selective quant download (colon syntax: `repo:quant`) |
| `distribute.py` | Orchestrates model sync from control machine to target hosts |
| `sync.py` | Low-level rsync operations for model files |
| `vram.py` | VRAM estimation based on parameter count, dtype, quantization, with HF auto-detection |

#### Containers (`containers/`)

| Module | Purpose |
|--------|---------|
| `registry.py` | Local image pull (`docker pull`) |
| `distribute.py` | Stream via `docker save \| ssh docker load`, checks image IDs to skip up-to-date hosts |
| `sync.py` | Image sync status checking |

---

### 6. Builder Plugin System (`builders/`)

A plugin system for container image preparation, registered via SAF entry points:

| Builder | Purpose |
|---------|---------|
| `base.py` | `BuilderPlugin` abstract base class |
| `docker_pull.py` | Standard `docker pull` builder |
| `eugr.py` | eugr-style container builds with mod support, converts recipe `mods` to `pre_exec` hook entries |

---

### 7. Proxy System (`proxy/`)

A unified OpenAI-compatible gateway powered by LiteLLM. This is a relatively self-contained subsystem.

| Module | Purpose |
|--------|---------|
| `__init__.py` | Constants (default port 4000, bind host, master key) |
| `config.py` | `ProxyConfig` — proxy settings and alias management |
| `discovery.py` | `DiscoveredEndpoint` dataclass, endpoint discovery from job metadata + health checks |
| `engine.py` | `ProxyEngine` — LiteLLM subprocess lifecycle, config generation, management API calls |
| `loader.py` | `load_model()` / `unload_model()` — orchestrates sparkrun run/stop + proxy registration |

**Architecture**: The proxy discovers running inference endpoints by scanning `~/.cache/sparkrun/jobs/*.yaml` metadata, health-checks them via `GET /v1/models`, generates a LiteLLM config, and launches `uvx litellm` as a managed subprocess.

**CLI surface**: `sparkrun proxy start|stop|status|models|load|unload` + `sparkrun proxy alias add|remove|list`.

---

### 8. Benchmarking (`benchmarking/`)

| Module | Purpose |
|--------|---------|
| `base.py` | `BenchmarkingPlugin` abstract base class (SAF plugin) |
| `llama_benchy.py` | `LlamaBenchyFramework` — llama-benchy benchmark runner with result export |

Benchmark profiles are YAML files in registries that define workload parameters. The CLI `benchmark run` command resolves profiles, starts inference if needed, runs the benchmark, and exports results.

---

### 9. Tuning (`tuning/`)

| Module | Purpose |
|--------|---------|
| `_common.py` | Shared tuning internals — container launch, config extraction, result processing |
| `sglang.py` | SGLang-specific Triton MoE kernel tuning |
| `vllm.py` | vLLM-specific tuning |
| `sync.py` | Sync tuning configs from registries, runtime name normalization |
| `distribute.py` | Distribute tuning configs to target hosts |

The tuning subsystem runs Triton fused MoE kernel tuning on DGX Spark and auto-mounts resulting configs in subsequent inference runs.

---

### 10. Utilities (`utils/`)

| Module | Purpose |
|--------|---------|
| `__init__.py` | `coerce_value()`, `suppress_noisy_loggers()`, `resolve_ssh_user()`, `is_valid_ip()`, `parse_kv_output()`, `load_yaml()` |
| `cli_formatters.py` | Presentation-layer formatting for recipe tables and CLI output |

---

### 11. Embedded Scripts (`scripts/`)

26 bash scripts embedded as package data, read at runtime via `read_script()`:

| Category | Scripts | Purpose |
|----------|---------|---------|
| Container | `container_launch.sh`, `exec_serve_*.sh` | Container lifecycle |
| Model sync | `model_distribute.sh`, `model_sync.sh`, `model_sync_gguf.sh` | Model file distribution |
| Image sync | `image_distribute.sh`, `image_sync.sh` | Container image distribution |
| IB/Network | `ib_detect.sh`, `ip_detect.sh`, `cx7_configure.sh`, `cx7_detect.sh` | InfiniBand and network setup |
| SSH | `mesh_ssh_keys.sh` | SSH key distribution |
| Cache/Perms | `clear_cache*.sh`, `fix_permissions*.sh` | System maintenance |
| Ray | `ray_head.sh`, `ray_worker.sh` | Ray cluster setup |
| Monitoring | `host_monitor.sh` | CSV metric streaming |
| Benchmarks | `sglang_clone_benchmarks.sh`, `vllm_clone_benchmarks.sh` | Benchmark repo cloning |
| Other | `earlyoom_install*.sh`, `sglang_patch_common_utils.py` | System setup, patches |

---

## Plugin System (SAF)

sparkrun uses [scitrera-app-framework](https://github.com/scitrera/python-app-framework) (SAF) for plugin discovery and lifecycle management. Three extension points are defined:

| Extension Point | Entry Point Group | Plugins |
|-----------------|-------------------|---------|
| `sparkrun.runtime` | `sparkrun.runtimes` | vllm-distributed, vllm-ray, sglang, llama-cpp, eugr-vllm, trtllm |
| `sparkrun.benchmarking` | `sparkrun.benchmarking` | llama-benchy |
| `sparkrun.builder` | `sparkrun.builders` | docker-pull, eugr |

**Bootstrap flow**: `cli/__init__.py` -> `core.bootstrap.init_sparkrun()` -> SAF `init_framework_desktop()` -> `find_types_in_modules()` discovers plugins -> `register_plugin()` for each.

Plugins are registered as **multi-extension plugins** (multiple plugins per extension point). The `is_enabled()` returns `False` to prevent SAF's single-extension cache from interfering with multi-plugin discovery.

---

## Key Data Flows

### `sparkrun run` — Full Lifecycle

```
1. CLI parses args                 (_run.py)
2. SAF bootstrap                   (core/bootstrap.py)
3. Recipe resolution               (core/recipe.py -> core/registry.py)
4. Host resolution                 (cli/_common.py -> core/hosts.py -> core/cluster_manager.py)
5. Runtime plugin lookup           (core/bootstrap.py -> runtimes/)
6. Recipe validation               (recipe.validate() + runtime.validate_recipe())
7. VRAM estimation                 (models/vram.py)
8. Transfer mode resolution        (cli/_common.py)
9. Resource distribution:
   a. IB detection                 (orchestration/infiniband.py)
   b. Container image sync         (containers/)
   c. Model file sync              (models/)
   d. Tuning config sync           (tuning/sync.py)
10. Container launch:
    a. Cleanup old containers      (orchestration/primitives.py)
    b. Generate launch script      (orchestration/scripts.py)
    c. SSH piping to remote        (orchestration/ssh.py)
11. Pre-exec hooks                 (orchestration/hooks.py)
12. Serve command execution        (runtime.generate_command() -> orchestration/ssh.py)
13. Health check polling           (runtime base class)
14. Post-exec hooks                (orchestration/hooks.py)
15. Job metadata persistence       (orchestration/job_metadata.py)
16. Log streaming / detach         (orchestration/ssh.py)
```

### `sparkrun proxy start` — Proxy Lifecycle

```
1. Resolve host filter             (_proxy.py)
2. Discover endpoints              (proxy/discovery.py — scans job metadata YAML)
3. Health check endpoints          (proxy/discovery.py — GET /v1/models)
4. Generate LiteLLM config         (proxy/engine.py)
5. Write config to disk            (proxy/engine.py)
6. Launch uvx litellm subprocess   (proxy/engine.py)
7. Store PID/state for lifecycle   (proxy/engine.py)
```

---

## Configuration & State

### File System Layout

| Path | Purpose | Managed By |
|------|---------|------------|
| `~/.config/sparkrun/config.yaml` | User configuration (cache dir, SSH defaults, etc.) | `core/config.py` |
| `~/.config/sparkrun/clusters/*.yaml` | Named cluster definitions (hosts, SSH user, transfer mode) | `core/cluster_manager.py` |
| `~/.config/sparkrun/registries.yaml` | Custom recipe registry list | `core/registry.py` |
| `~/.cache/sparkrun/registries/` | Git-cloned recipe registries (sparse checkouts) | `core/registry.py` |
| `~/.cache/sparkrun/jobs/*.yaml` | Job metadata (cluster_id -> recipe, host, port mapping) | `orchestration/job_metadata.py` |
| `~/.cache/sparkrun/pending/` | PID lock files for in-progress operations | `core/pending_ops.py` |
| `~/.cache/sparkrun/tuning/` | Tuning config cache | `tuning/sync.py` |
| `~/.cache/huggingface/` | HuggingFace model cache (mounted into containers) | `models/download.py` |

### Configuration Chain (VPD)

Parameter resolution uses a Virtual Path Dict chain with clear precedence:

```
CLI flags (--port, --tp, -o key=value)
    ↓ overrides
Recipe defaults (recipe.yaml -> defaults section)
    ↓ overrides
Runtime defaults (hardcoded in runtime plugins)
```

The VPD `arg_substitute()` function handles `{key}` placeholder rendering in recipe `command` templates.

---

## Testing Architecture

### Overview

- **Framework**: pytest with `pytest-asyncio`
- **~27 test files** with comprehensive coverage
- **No real hosts needed**: All SSH/Docker operations are mocked
- **Isolated state**: `conftest.py` provides an `isolate_stateful` autouse fixture that redirects SAF state to `tmp_path`

### Test Coverage by Module

| Test File | Module Under Test |
|-----------|-------------------|
| `test_cli.py` | CLI commands (run, stop, logs, setup, cluster, status) |
| `test_runtimes.py` | All runtime plugins (command generation, cluster orchestration) |
| `test_recipe.py` | Recipe loading, validation, v1->v2 migration, config chain |
| `test_registry.py` | Registry CRUD, manifest discovery, shared clones, reserved names |
| `test_distribute.py` | Model and container distribution, IB detection |
| `test_benchmark.py` | Benchmark profiles, execution, result export |
| `test_proxy.py` | Proxy discovery, engine lifecycle, management API |
| `test_tuning.py` | MoE kernel tuning, config sync |
| `test_hooks.py` | Pre/post exec hooks, file injection, template rendering |
| `test_builder.py` | Builder plugins (eugr, docker-pull) |
| `test_trtllm_runtime.py` | TRT-LLM specific tests |
| `test_sparkmon.py` | Sparkmon collector, web API, CLI commands, serialization |
| Other files | Bootstrap, config, cluster, Docker, GGUF, hosts, IB, networking, primitives, scripts, SSH, VRAM |

### Test Patterns

- **Fixture-based**: `conftest.py` provides `tmp_recipe_dir`, `cluster_dir`, `hosts_file`, `v` (SAF Variables), and the critical `isolate_stateful` fixture.
- **Mock-heavy**: `unittest.mock.patch` is used extensively to mock SSH execution, Docker commands, file system operations, and HTTP calls.
- **Import paths**: All core imports in tests use `sparkrun.core.*` paths.
- **Bootstrap reset**: The SAF bootstrap singleton (`_variables`) is reset between tests.

---

## Dependencies

| Dependency | Purpose | Usage |
|------------|---------|-------|
| `scitrera-app-framework` (SAF) | Plugin system, lifecycle, variables/config | Runtime, benchmarking, and builder discovery |
| `vpd` | Virtual Path Dict, YAML reading, config chains | Recipe defaults resolution, template rendering |
| `click` | CLI framework | All command definitions |
| `pyyaml` | YAML parsing | Recipes, clusters, registries, job metadata |
| `huggingface_hub` | Model downloading (`snapshot_download`) | Model distribution |
| `textual` | Terminal UI framework | Cluster monitoring TUI |

---

## Companion Packages

### `sparkrun-cc-plugin/`

Claude Code plugin providing slash commands and AI-assisted inference management:
- `/sparkrun:run`, `/sparkrun:stop`, `/sparkrun:status`, `/sparkrun:list`, `/sparkrun:setup`
- Skills: `run`, `setup`, `registry`

### `website/`

Documentation site built with Astro (Starlight theme), deployed to Cloudflare Pages.

---

## Architectural Observations

### Strengths

1. **Clean plugin architecture**: The SAF-based runtime system is well-designed. Adding a new runtime requires implementing `generate_command()`, `resolve_container()`, and optionally `cluster_strategy()` — the base class handles everything else.

2. **SSH stdin piping model**: Elegant approach that avoids file management on remote hosts. Scripts are generated, piped, and forgotten. No cleanup needed.

3. **Comprehensive test suite**: 0.84:1 test-to-source ratio with full mock isolation. The `isolate_stateful` fixture prevents test pollution.

4. **Recipe-driven design**: The VPD config chain is a solid approach to parameter resolution with clear precedence rules.

5. **Dry-run support**: Every command supports `--dry-run`, making it safe to explore behavior without side effects.

6. **Graceful degradation**: Registry initialization falls back to hardcoded defaults if git cloning fails, ensuring offline operation.

### Areas for Attention

1. **Large single files**: Several files exceed 900 lines — `registry.py`, `base.py` (runtime), and `ssh.py`. These are internally cohesive but their size increases cognitive load. `_common.py` in CLI is also growing.

2. **Orchestration complexity**: The base runtime class encodes a significant amount of orchestration logic (solo mode, cluster mode, health checks, hooks, banners). New runtime authors need to understand this entire lifecycle to properly extend the system.

3. **SSH module scope**: `ssh.py` handles basic SSH commands, parallel execution, rsync orchestration, log streaming, and remote command execution. These are all SSH-related but serve different abstraction levels.

4. **Proxy as separate subsystem**: The proxy (`proxy/`) and monitoring (`core/monitoring.py` + `cli/_monitor_tui.py`) systems are relatively self-contained additions. Their integration with the core is well-isolated (only through job metadata and cluster definitions), which is a good pattern.

5. **Builder system maturity**: The builder plugin system exists but only has two implementations (docker-pull and eugr). The eugr builder converts legacy `mods` to `pre_exec` hooks — this bridge pattern works but adds indirection for v1 recipe users.

6. **Version management**: Versions are tracked in `versions.yaml` and synced via `scripts/update-versions.py` to `pyproject.toml` and companion packages. This manual sync step is a potential source of drift if forgotten (though CI checking via `--check` flag mitigates this).

---

## Design Patterns

| Pattern | Location | Purpose |
|---------|----------|---------|
| **Template Method** | `RuntimePlugin.run()` | Solo vs. cluster dispatch — base class defines the lifecycle, subclasses override specific steps |
| **Strategy** | `cluster_strategy()` | Each runtime declares its clustering approach (`"ray"`, `"native"`); base class dispatches accordingly |
| **Factory** | `generate_command()` | Runtimes produce command strings either from structured config or template rendering |
| **Adapter** | `BenchmarkingPlugin` subclasses | Bridges external benchmark tools (llama-benchy) to sparkrun's plugin interface |
| **Chain of Responsibility** | VPD config chain | CLI overrides -> recipe defaults -> runtime defaults, with first-match resolution |
| **Observer/Callback** | `ClusterMonitor` | Watchdog thread monitors SSH streams, triggers reconnection on staleness |
| **Composition** | `orchestration/primitives.py` | Higher-level operations composed from SSH, Docker, and script primitives |

---

## Resource Transfer Modes

sparkrun supports multiple strategies for distributing container images and models to cluster nodes:

| Mode | Flow | Best For |
|------|------|----------|
| `auto` | Selects based on cluster config and network topology | Default — lets sparkrun decide |
| `local` | Control machine pushes directly to all hosts | Small clusters with fast control-plane network |
| `push` | Control machine -> head node -> head distributes to workers | Clusters where IB is available between nodes |
| `delegated` | Each worker pulls independently from external sources | Clusters with direct internet/registry access |

Transfer mode can be set per-cluster in cluster definitions or overridden per-run with `--transfer-mode`.

---

## Container Naming Conventions

| Context | Pattern | Example |
|---------|---------|---------|
| Solo mode | `sparkrun_<name>_solo` | `sparkrun_qwen3-1.7b-vllm_solo` |
| Cluster head | `sparkrun_<12-char-hash>_head` | `sparkrun_a1b2c3d4e5f6_head` |
| Cluster worker | `sparkrun_<12-char-hash>_worker` | `sparkrun_a1b2c3d4e5f6_worker` |
| Native cluster nodes | `sparkrun_<12-char-hash>_node_<rank>` | `sparkrun_a1b2c3d4e5f6_node_0` |

The 12-character cluster ID is a random alphanumeric string generated per launch, used to group related containers and track job metadata.

---

## CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/publish.yml`):

| Job | Trigger | Steps |
|-----|---------|-------|
| **test** | All pushes/PRs | Matrix: Python 3.12 + 3.13, `pytest -v --tb=long -x` |
| **build** | After test passes | `python -m build` (sdist + wheel), upload artifacts |
| **publish** | Version tags (`v*`) or manual dispatch | PyPI via trusted publisher (`pypa/gh-action-pypi-publish`) |

The pipeline ensures version consistency via `scripts/update-versions.py --check` and runs the full test suite across supported Python versions before any release.
