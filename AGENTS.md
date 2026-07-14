# AGENTS.md — AIMEBackend

## Project Overview

AI-powered input method backend (AIME) for Windows. Lua frontend (RIME) communicates via TCP socket with Python backend that uses a local LLM (Qwen2.5-1.5B-Instruct) for context-aware candidate word selection and generation.

**Architecture:** Lua frontend ↔ TCP socket (127.0.0.1:5000) ↔ Python backend (llama-cpp-python + UIAutomation + SQLite)

## Key Commands

```bash
# Install dependencies (uv is the package manager)
uv sync

# Run the backend
uv run python main.py

# Run tests
uv run python etc/test/test_context_probe.py

# Lint
uv run ruff check .
uv run ruff format .
```

## Python Version

**Required:** 3.12 (pinned in `.python-version`)

## Package Manager

Use `uv` (not pip). Dependencies are in `pyproject.toml`, lockfile is `uv.lock`.

**Critical:** `llama-cpp-python` is installed from a local wheel file (path in `pyproject.toml` → `[tool.uv.sources]`). If the wheel is missing, build with CUDA support:

```powershell
$env:CMAKE_ARGS="-DGGML_CUDA=on"
$env:CMAKE_ARGS = "-DGGML_CUDA=on -DCMAKE_C_COMPILER=D:/mingw64/bin/gcc.exe -DCMAKE_CXX_COMPILER=D:/mingw64/bin/g++.exe"
```

## Platform Constraints

- **Windows-only:** Uses `uiautomation`, `pywin32`, `pythoncom` (COM initialization)
- **GPU required:** Model runs with `n_gpu_layers=-1` (full GPU offload)
- **Model file:** Must exist at path configured in `config/config.yaml` → `model.path`

## Module Structure

```
main.py                    → Entry point (signal handling + graceful shutdown)
config/                    → YAML config loader (singleton + dataclass)
config/config.yaml         → All runtime configuration
core/
  shutdown.py              → threading.Event-based global shutdown signal
  logger.py                → Async logging (QueueHandler + QueueListener)
  context/uia_context.py   → UIA watchdog thread (500ms poll, 3-tier waterfall)
  inference/__init__.py    → 2-phase inference (Phase1: select, Phase2: generate)
  memory/__init__.py       → SQLite L1 cache + async correction capture + LRU cleanup
  pinyin/__init__.py       → Pinyin conversion, collision validation, Chinese extraction
  server/__init__.py       → TCP socket server (HTTP/1.1 simplified)
lua/candidate_collection.lua → RIME Lua filter (candidate rerank + correction capture + circuit breaker)
```

## Config System

All configuration is in `config/config.yaml` and loaded as dataclasses (`AppConfig`).

**Hot reload:** Call `reload_config()` to refresh from disk.

**Key config sections:**
- `model` — LLM path, context window, GPU layers
- `server` — TCP host/port/buffer
- `context` — UIA poll interval, max chars, timeout
- `inference` — Temperature, max tokens, pinyin threshold, stop tokens
- `memory` — SQLite path, max records, age days, cleanup interval
- `logging` — Level, file rotation settings

## Threading Model

- **Main thread:** Signal handling + TCP server event loop
- **Watchdog thread:** UIA context polling (500ms interval)
- **Memory writer thread:** Async SQLite writes (batch flush)
- **Debug thread:** Context status printing (2s interval)

All threads check `is_shutdown()` and use `wait_shutdown()` for interruptible sleep.

## Inference Pipeline

Request flow: `TCP recv → JSON parse → context read → L1 cache query → Phase1 selection → Phase2 generation → candidate rerank → response`

- **L1 Cache:** SQLite lookup by (context_hash, pinyin) — ms级 hit skips model inference
- **Phase1:** Select best candidate from top-5 native candidates
- **Phase2:** Generate new word if Phase1 missed (requires pinyin length ≥ 3, must pass collision check at 60% threshold)
- **Rerank:** logprobs-based scoring of candidates using top-20 token probabilities

## Gotchas

1. **COM threading:** Each thread that uses UIA must call `pythoncom.CoInitialize()` first
2. **Thread safety:** `GLOBAL_CONTEXT` is protected by `CONTEXT_LOCK` (threading.Lock)
3. **Config paths:** Model file path in config is absolute — must match local filesystem
4. **SQLite WAL mode:** Memory module uses WAL journal mode for concurrent read/write
5. **Shutdown order:** Memory module must shutdown before logger (flush pending writes)
6. **Python `v` → `u`:** Pinyin input replaces 'v' with 'ü' (line 248 in inference/__init__.py)

## Testing

Tests are in `etc/test/` and require Windows + active UIA focus (manual verification).

- `test_context_probe.py` — A/B comparison of UIA context fetch strategies
- `test_uia.py` — UIA interface tests
- `test_word_com.py` — Word COM interface tests (legacy, deprecated)

**No automated test suite** — tests are manual diagnostic tools.

## Code Style

- **Formatter/Linter:** Ruff (`ruff check`, `ruff format`)
- **Docstrings:** PEP 257 style (Chinese comments are common in this codebase)
- **Type hints:** Used throughout (Python 3.12 syntax)
- **Naming:** snake_case for functions/variables, PascalCase for classes

## Entry Points

- **Start backend:** `python main.py`
- **TCP endpoint:** `127.0.0.1:5000` (HTTP POST, JSON body)
- **Request types:** `rerank` (AI inference) and `correction` (record user correction)
