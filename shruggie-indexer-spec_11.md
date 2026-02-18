## 11. Logging and Diagnostics

This section defines the logging and diagnostics system that replaces the original's `Vbs` function — the single most widely-called function in the pslib library. It specifies the logger naming hierarchy, log level mapping to CLI flags, session identifiers, output destinations, log message formatting, and the progress reporting system that feeds the CLI and GUI progress displays.

The logging system is the implementation of two concerns that earlier sections defined in contract form: §4.5 (Error Handling Strategy) established the four error severity tiers (fatal, item-level, field-level, diagnostic) and their behavioral consequences. §8.7 defined the CLI flags (`-v`, `--quiet`) that control logging verbosity. This section provides the concrete `logging`-framework wiring that connects those contracts to runtime behavior.

**Module location:** There is no dedicated logging module in the source package layout (§3.2). Logging configuration is performed in the CLI entry point (`cli/main.py`), the GUI entry point (`gui/app.py`), and optionally by API consumers. Individual modules obtain their loggers at import time via `logging.getLogger(__name__)` — no centralized logging module is needed beyond Python's built-in `logging` package. The one logging-specific artifact is the `SessionFilter` class (§11.4), which is defined in the CLI module where it is used and does not require its own file.

> **Deviation from original:** The original `Vbs` function is a 130-line PowerShell function with six internal sub-functions (`VbsFunctionStackTotalDepth`, `VbsLogPath`, `VbsLogRealityCheck`, `VbsLogWrite`, `VbsUpdateFunctionStack`, `VbsUpdateFunctionStackExtractNumber`) that manually constructs log entries, manages log file creation, compresses call stacks, and formats colorized console output. It is called explicitly by every function in the pslib library, requiring each caller to pass a `Caller` string, a `Status` shorthand, and a `Verbosity` flag through the call chain. The port replaces all of this with Python's standard `logging` framework — which provides named loggers, hierarchical level filtering, pluggable formatters and handlers, and automatic caller identification — eliminating 100% of the `Vbs` implementation and 100% of the manual call-stack bookkeeping that pervaded every function in the original.

### 11.1. Logging Architecture

#### Design principles

The logging system follows four principles that govern all implementation decisions:

**Principle 1 — Standard library only.** The core logging system uses Python's `logging` module exclusively. No third-party logging libraries (e.g., `structlog`, `loguru`) are required. Optional enhancements like `rich.logging.RichHandler` for colorized console output are welcome as extras but MUST NOT be assumed. A bare `pip install shruggie-indexer` provides full logging functionality.

**Principle 2 — stderr for logs, stdout for data.** All log output is directed to `sys.stderr`. The `sys.stdout` stream is reserved exclusively for JSON output (§6.9, §8.3). This separation is critical: it allows `shruggie-indexer /path | jq .` to work correctly even at maximum verbosity — the JSON stream on stdout is never contaminated by log messages. The original's `Vbs` function conflates log output and console output through `Write-Host`, which writes to the PowerShell host stream rather than stdout or stderr — a distinction that only matters in specific piping scenarios. The port's explicit stderr routing is cleaner and follows Unix convention.

**Principle 3 — No mandatory file logging.** The original writes to monthly log files (`YYYY_MM.log`) in a hardcoded directory (`C:\bin\pslib\logs`) on every invocation, regardless of verbosity settings. The port does not write log files by default. Console (stderr) output is the sole default destination. File logging is available if a consumer configures it programmatically via the standard `logging.FileHandler`, but the tool does not create log files, log directories, or manage log rotation as part of its normal operation. This is a deliberate simplification: a CLI tool that silently writes to the filesystem on every invocation is surprising behavior, and the original's log directory path was a Windows-specific hardcoded constant that would not port cleanly to cross-platform use.

**Principle 4 — Logging and progress are separate systems.** The original's `Vbs` function handles both diagnostic logging and user-facing progress reporting (e.g., `"[42/100 (42%)] Processing photo.jpg"`), interleaving them into the same output channel. The port separates these concerns entirely: the `logging` framework handles diagnostic messages (warnings, errors, debug trace), while the `ProgressEvent` callback system (§9.4, §11.6) handles user-facing progress reporting. They share an output destination in the CLI (both appear on stderr), but they are architecturally independent — the progress system can drive a GUI progress bar, a `tqdm` progress bar, or be disabled entirely, without affecting diagnostic logging.

#### How logging is configured

Logging configuration happens exactly once per invocation, at the entry point layer — before the core indexing engine is called. Each entry point is responsible for configuring the logging system appropriate to its context:

**CLI (`cli/main.py`).** The `main()` function calls `configure_logging()` (a private function within the CLI module) after parsing arguments but before constructing `IndexerConfig` or calling `index_path()`. The function creates a `StreamHandler` on `sys.stderr`, attaches a `Formatter` and the `SessionFilter` (§11.4), and sets the root logger level based on the `-v`/`-q` flags.

**GUI (`gui/app.py`).** The application's `__init__` method configures a `logging.Handler` subclass that enqueues log records into the same `queue.Queue` used by the progress display (§10.5). The handler formats records identically to the CLI formatter but routes them to the GUI's log stream textbox rather than stderr. The log level is controlled by the Settings panel's Verbosity combobox (§10.4).

**API consumers.** Library consumers who `import shruggie_indexer` are responsible for configuring their own logging. The library's `core/` modules emit log records through their per-module loggers (§11.2) but do not install any handlers. If the consumer does not configure logging, Python's `logging.lastResort` handler (a `StreamHandler` on stderr with WARNING level) provides minimal output. This is the correct default behavior for a library — the library should never configure the root logger or install handlers, because doing so would interfere with the consuming application's logging setup.

```python
# Illustrative — not the exact implementation.
# cli/main.py

def configure_logging(verbose_count: int, quiet: bool, session_id: str) -> None:
    """Configure the logging system for CLI invocation."""
    if quiet:
        level = logging.CRITICAL
    else:
        level = {0: logging.WARNING, 1: logging.INFO}.get(verbose_count, logging.DEBUG)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s  %(session_id)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    handler.addFilter(SessionFilter(session_id))

    # Configure the package root logger — not the global root logger.
    package_logger = logging.getLogger("shruggie_indexer")
    package_logger.setLevel(level)
    package_logger.addHandler(handler)

    # Prevent propagation to the root logger, which may have
    # handlers installed by the consuming environment.
    package_logger.propagate = False
```

> **Critical implementation note:** The CLI configures the `shruggie_indexer` package logger, not the root logger (`logging.getLogger()`). Configuring the root logger would affect all loggers in the process, including those from third-party libraries (`click`, `urllib3`, etc.), which is both intrusive and noisy. By scoping the handler to the `shruggie_indexer` namespace, only log records from the indexer's own modules are captured. Third-party library logging is left to the consumer's own configuration. The `propagate = False` setting prevents double-logging if a consumer has also configured a root handler.

### 11.2. Logger Naming Hierarchy

Every module in the `shruggie_indexer` package obtains its logger via `logging.getLogger(__name__)` as the first executable statement after imports. This produces a dotted-name logger hierarchy that mirrors the package structure:

```
shruggie_indexer                    # package root (configured by CLI/GUI)
shruggie_indexer.core.traversal     # filesystem traversal
shruggie_indexer.core.paths         # path resolution
shruggie_indexer.core.hashing       # hash computation
shruggie_indexer.core.timestamps    # timestamp extraction
shruggie_indexer.core.exif          # exiftool invocation
shruggie_indexer.core.sidecar       # sidecar discovery/parsing
shruggie_indexer.core.entry         # entry construction orchestrator
shruggie_indexer.core.serializer    # JSON output
shruggie_indexer.core.rename        # file rename operations
shruggie_indexer.config.loader      # configuration loading
shruggie_indexer.cli.main           # CLI entry point
shruggie_indexer.gui.app            # GUI entry point
```

**Why `__name__` and not manual names:** The original's `Vbs` function requires every caller to pass a `Caller` string containing a manually-maintained colon-delimited call stack (e.g., `"MakeIndex:MakeObject:GetFileExif"`). This approach has three problems: it is error-prone (callers can pass incorrect or stale stack strings), it couples every function to the logging interface (every function must accept and forward the `Caller` parameter), and it requires the `VbsUpdateFunctionStack` compression function to keep log lines from becoming unwieldy during deep recursion.

Python's `logging.getLogger(__name__)` solves all three problems: logger names are derived automatically from the module's fully-qualified import path, no parameter passing is needed, and the hierarchy is structurally correct by construction. The `%(name)s` format token in the handler's formatter produces the logger name in every log record, providing equivalent traceability to the original's `Caller` field without any manual bookkeeping.

**Per-module logger pattern:** Every `core/` module follows this pattern:

```python
# core/hashing.py
import logging

logger = logging.getLogger(__name__)

def hash_file(path: Path, compute_sha512: bool = False) -> HashSet:
    logger.debug("Hashing file: %s", path)
    # ...
    logger.debug("Hash complete for %s: md5=%s", path, result.md5)
    return result
```

The `logger` variable is module-level, created once at import time. It is not a global mutable state concern (§4.4) because `logging.getLogger()` returns the same logger instance for the same name on every call — it is effectively a singleton lookup, and the logger's configuration (level, handlers) is controlled by the entry point, not by the module.

#### Logger hierarchy and level inheritance

Python's `logging` framework uses dot-separated names to form a hierarchy. Setting the level on `shruggie_indexer` (the package root logger) propagates to all child loggers — `shruggie_indexer.core.hashing`, `shruggie_indexer.core.exif`, etc. — unless a child logger has an explicitly overridden level. This hierarchy enables the `-vv` vs. `-vvv` distinction defined in §8.7:

| CLI flag | Package root level | Effect |
|----------|-------------------|--------|
| (none) | `WARNING` | Only warnings and errors from any module. |
| `-v` | `INFO` | Progress-level messages: items processed, output destinations, implication chain activations. |
| `-vv` | `DEBUG` | Detailed internal state from all modules: hash values, exiftool commands, sidecar regex matches, config resolution steps. |
| `-vvv` | `DEBUG` + specific loggers re-enabled | Maximum verbosity. Same as `-vv` but also enables loggers that are silenced at `-vv` for noise reduction (see below). |

#### The `-vv` vs. `-vvv` distinction

At `-vv` (DEBUG), all modules emit their DEBUG messages. This is already verbose — large directory trees can produce thousands of per-file hash and timestamp log lines. The `-vvv` level provides a further increase by re-enabling two categories of messages that are suppressed at `-vv` for readability:

1. **Per-item timing data.** `core/entry.py` can emit the elapsed wall-clock time for each item's entry construction. At `-vv`, these are suppressed (the per-file overhead of `time.perf_counter()` calls and log formatting is undesirable for most debugging scenarios). At `-vvv`, they are enabled.

2. **Exiftool raw output.** `core/exif.py` can emit the complete JSON string returned by `exiftool` for each file. At `-vv`, only the filtered/processed result is logged. At `-vvv`, the raw subprocess output is also logged.

This distinction is implemented not through custom log levels (which would violate the standard `logging` API) but through a naming convention: the noisy loggers use a `.trace` suffix on their name — e.g., `shruggie_indexer.core.entry.trace`, `shruggie_indexer.core.exif.trace`. At `-vv`, these trace loggers are explicitly set to `WARNING` (silenced). At `-vvv`, they inherit the package root's `DEBUG` level (active).

```python
# Illustrative — inside configure_logging()
if verbose_count == 2:
    # -vv: silence trace loggers specifically
    logging.getLogger("shruggie_indexer.core.entry.trace").setLevel(logging.WARNING)
    logging.getLogger("shruggie_indexer.core.exif.trace").setLevel(logging.WARNING)
# At verbose_count >= 3 (-vvv), no per-logger overrides — everything is DEBUG.
```

The `.trace` logger pattern is purely a convention — no separate `trace` modules exist. The trace loggers are obtained via `logging.getLogger(__name__ + ".trace")` within the module that uses them:

```python
# core/entry.py
import logging

logger = logging.getLogger(__name__)
trace_logger = logging.getLogger(__name__ + ".trace")

def build_file_entry(path: Path, config: IndexerConfig) -> IndexEntry:
    t0 = time.perf_counter()
    # ...
    elapsed = time.perf_counter() - t0
    trace_logger.debug("Entry construction for %s took %.3fs", path.name, elapsed)
```

> **Improvement over original:** The original's binary `$Verbosity` boolean provides only two states: all output or file-only output. The port's graduated three-level model (`WARNING` → `INFO` → `DEBUG` → `DEBUG+trace`) gives users practical control over log volume without requiring them to filter log files after the fact.

### 11.3. Log Levels and CLI Flag Mapping

#### Standard level usage

The port uses Python's five standard log levels with consistent semantic meanings across all modules. No custom log levels are defined.

| Level | Numeric | Usage | Example messages |
|-------|---------|-------|-----------------|
| `CRITICAL` | 50 | Fatal conditions that prevent the tool from operating at all. Only used for startup failures. The CLI exits immediately after a CRITICAL log. | `"Configuration file is malformed TOML: {path}"`, `"Target path does not exist: {path}"` |
| `ERROR` | 40 | Item-level failures that cause an item to be skipped or populated with degraded fields. The tool continues processing remaining items. | `"Permission denied reading file: {path}"`, `"exiftool returned non-zero for {path}: {stderr}"`, `"Failed to parse sidecar JSON: {path}"` |
| `WARNING` | 30 | Conditions that do not prevent processing but indicate unexpected or suboptimal behavior. The user should be aware but no action is required. | `"exiftool not found on PATH; EXIF extraction disabled for this invocation"`, `"--rename implies --inplace; enabling in-place output"`, `"Skipping dangling symlink: {path}"`, `"3 items failed during indexing"` |
| `INFO` | 20 | Progress milestones, operational decisions, and summary information. Useful for understanding what the tool did without drowning in per-item detail. | `"Indexing directory: {path} (recursive)"`, `"Discovered 1,247 items"`, `"Output written to: {outfile}"`, `"Elapsed time: 12.4s"` |
| `DEBUG` | 10 | Per-item internal state, intermediate values, and decision traces. Useful for diagnosing why a specific file produced unexpected output. | `"Hashing file: {path}"`, `"md5={hash}, sha256={hash}"`, `"Sidecar match: {pattern} → {type}"`, `"Extension '{ext}' failed validation; using empty string"` |

#### Mapping to error severity tiers

The error severity tiers defined in §4.5 map to log levels as follows:

| Severity tier (§4.5) | Log level | Behavioral consequence |
|-----------------------|-----------|----------------------|
| Fatal | `CRITICAL` | Abort invocation. Exit with non-zero code. |
| Item-level | `ERROR` | Skip item or populate with degraded fields. Continue processing. |
| Field-level | `WARNING` or `ERROR` | Populate affected field with `null`. Continue processing current item. `WARNING` when the condition is expected (e.g., exiftool unavailable); `ERROR` when unexpected (e.g., exiftool crash on a specific file). |
| Diagnostic | `DEBUG` | No effect on output. Trace information for debugging. |

#### CLI flag mapping (summary)

This table consolidates the CLI flag → log level mapping defined in §8.7 with the detailed level semantics above:

| CLI flags | Effective level | What the user sees on stderr |
|-----------|----------------|------------------------------|
| (default) | `WARNING` | Only warnings and errors. Silent for normal operation. |
| `-v` | `INFO` | Progress milestones, summary stats, implication chain messages. |
| `-vv` | `DEBUG` (trace loggers silenced) | Per-item detail: hashes, timestamps, sidecar matches, exiftool invocations. |
| `-vvv` | `DEBUG` (all) | Maximum detail: per-item timing, raw exiftool JSON, config resolution trace. |
| `-q` | `CRITICAL` | Fatal errors only. Overrides `-v` if both are specified. |

### 11.4. Session Identifiers

Each invocation of `shruggie-indexer` — whether from the CLI, GUI, or API — generates a unique session identifier. The session ID is a 32-character lowercase hexadecimal string derived from a UUID4:

```python
import uuid

session_id = uuid.uuid4().hex  # e.g., "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
```

The session ID is generated once, at the start of the invocation, before any processing begins. It is immutable for the duration of the invocation.

#### Purpose

The session ID serves two functions:

1. **Log correlation.** When multiple invocations run concurrently (e.g., parallel indexing jobs in a CI pipeline), or when log output from multiple invocations is aggregated into a shared sink, the session ID uniquely identifies which log lines belong to which invocation. This is the same role served by the original's `$LibSessionID` (a GUID generated once per pslib session).

2. **Output provenance.** The session ID MAY be included in the JSON output metadata in future schema versions (post-MVP) to link an index entry back to the invocation that produced it. For the MVP, the session ID is logging-only.

#### Injection mechanism

The session ID is injected into log records via a `logging.Filter`, not a `logging.LoggerAdapter`. The Filter approach is preferred because it works transparently with all loggers in the hierarchy without requiring every module to use a special adapter class:

```python
class SessionFilter(logging.Filter):
    """Inject the session ID into every log record."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = self.session_id  # type: ignore[attr-defined]
        return True
```

The filter is attached to the handler (not to individual loggers), so it applies to every log record that reaches the handler regardless of which module emitted it. The `session_id` attribute is then available in the formatter via `%(session_id)s`.

> **Deviation from original:** The original's `$LibSessionID` is a global variable that each `Vbs` call receives as the `$VbsSessionID` parameter (defaulting to the global). This means the session ID flows through the parameter chain — every function that calls `Vbs` either passes it explicitly or relies on the global default. The port eliminates this parameter entirely. No `core/` module function accepts or passes a session ID — the `SessionFilter` injects it transparently at the handler level. This is a structural improvement that removes one parameter from every function signature in the call chain.

#### Lifecycle

| Entry point | Where generated | How injected |
|-------------|----------------|--------------|
| CLI | In `main()`, before `configure_logging()` is called. | Passed to `SessionFilter` constructor, which is attached to the stderr handler. |
| GUI | In `ShruggiIndexerApp.__init__()`, once at application startup. A new session ID is generated for each indexing operation (not per-application-launch), matching the semantics of "one session = one invocation." | Attached to the GUI's queue-based log handler via the same `SessionFilter`. The session ID is updated when a new indexing job starts. |
| API | Not generated by the library. API consumers are responsible for their own logging configuration. If a consumer wants session IDs, they configure their own `SessionFilter`. The library's `core/` modules never read or depend on the session ID — it is purely a logging-layer concern. |

### 11.5. Log Output Destinations

#### CLI destinations

The CLI has a single log output destination: a `logging.StreamHandler` attached to `sys.stderr`. There is no file handler, no network handler, and no syslog handler configured by default.

**Log message format (CLI):**

```
2026-02-15 14:30:02  a1b2c3d4  WARNING   shruggie_indexer.core.exif  exiftool not found on PATH; EXIF extraction disabled
2026-02-15 14:30:02  a1b2c3d4  INFO      shruggie_indexer.core.traversal  Discovered 1,247 items in /path/to/target
2026-02-15 14:30:03  a1b2c3d4  DEBUG     shruggie_indexer.core.hashing  Hashing file: photo.jpg (md5=A8A8...)
```

Format string:

```python
fmt = "%(asctime)s  %(session_id)s  %(levelname)-8s  %(name)s  %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"
```

**Format field descriptions:**

| Field | Token | Description |
|-------|-------|-------------|
| Timestamp | `%(asctime)s` | Local wall-clock time in `YYYY-MM-DD HH:MM:SS` format. Seconds-level precision is sufficient for CLI diagnostics. The original's dual-format timestamp (Unix milliseconds + ISO datetime) is not replicated — the Unix millisecond timestamp added no diagnostic value for console output and was a relic of the machine-readable log file format. |
| Session ID | `%(session_id)s` | First 8 characters of the 32-character session ID. The abbreviated form balances identifiability with line length — 8 hex characters provide ~4 billion unique values, which is sufficient to distinguish concurrent invocations. The full 32-character ID is available in the `LogRecord` attribute for any consumer that configures a custom formatter. |
| Level | `%(levelname)-8s` | Left-aligned, padded to 8 characters for visual column alignment. |
| Logger name | `%(name)s` | The fully-qualified dotted logger name. Provides equivalent traceability to the original's `Caller` field without manual call-stack management. |
| Message | `%(message)s` | The log message body, formatted via `%`-style string interpolation (Python's `logging` default). |

**Deliberate omission: the original's `pslib({CompressedStack}):` prefix.** The original wraps every log message in a prefix like `pslib(MakeIndex:MakeObject(3)):` that identifies both the library name and the compressed call stack. The port replaces this with the logger name (`%(name)s`), which provides the module path but not the function name or recursion depth. The function name is available via `%(funcName)s` if needed, but it is excluded from the default format because it adds visual noise without improving most debugging scenarios — the module name is almost always sufficient to locate the relevant code. Consumers who need function-level detail can reconfigure the formatter.

#### GUI destinations

The GUI uses a custom `logging.Handler` subclass that serializes log records into the `queue.Queue` shared with the progress display system (§10.5). The main thread's 50ms polling timer dequeues records and appends them to the log stream textbox.

**Log message format (GUI):**

```
14:30:02  WARNING   exiftool not found on PATH; EXIF extraction disabled
14:30:02  INFO      Discovered 1,247 items in /path/to/target
14:30:03  DEBUG     Hashing file: photo.jpg
```

Format string:

```python
fmt = "%(asctime)s  %(levelname)-8s  %(message)s"
datefmt = "%H:%M:%S"
```

The GUI format is more compact than the CLI format: the session ID is omitted (the GUI runs one invocation at a time, so correlation is unnecessary), the logger name is omitted (the log stream textbox is already contextualized by the running operation), and the timestamp uses time-only format (the date is visible in the system clock). The GUI SHOULD apply level-based color coding to log messages in the textbox: `ERROR` and `CRITICAL` in red, `WARNING` in yellow/amber, `INFO` in the default text color, and `DEBUG` in a muted gray. This replaces the original's `Write-Host -ForegroundColor` colorization with the GUI's own text styling.

#### Optional: colorized CLI output

If `rich` is installed (it is listed as a recommended third-party package in §12.3), the CLI MAY use `rich.logging.RichHandler` instead of the plain `StreamHandler` to produce colorized, column-aligned log output on terminals that support ANSI escape codes. The detection and fallback logic:

```python
# Illustrative — inside configure_logging()
try:
    from rich.logging import RichHandler
    handler = RichHandler(
        console=rich.console.Console(stderr=True),
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
    )
except ImportError:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=..., datefmt=...))
```

This is strictly optional. The core logging system works identically with or without `rich`. The `SessionFilter` is attached to whichever handler is constructed.

> **Deviation from original:** The original's `Vbs` function hardcodes console colors per severity level (Gray for INFO, DarkRed for ERROR, Magenta for CRITICAL, DarkYellow for WARNING, DarkCyan for DEBUG, DarkGreen for SUCCESS, DarkGray for UNKNOWN) via `Write-Host -ForegroundColor`. The port delegates colorization to `rich` when available, which uses its own color scheme appropriate to the terminal's color capabilities (256-color, truecolor, or no-color fallback). The original's `SUCCESS` and `UNKNOWN` status levels do not have direct Python `logging` equivalents — success messages are logged at `INFO` level, and the "unknown" status (which the original used as a fallback for unrecognized status strings) has no counterpart because the port does not accept freeform status strings.

### 11.6. Progress Reporting

Progress reporting is the user-facing system that communicates "what is the tool doing right now and how far along is it?" to the CLI and GUI. It is architecturally separate from diagnostic logging (Principle 4, §11.1) — they are produced by different systems, serve different audiences, and can be independently disabled.

#### Architecture

Progress reporting flows through the `ProgressEvent` callback system defined in §9.4. The core engine (`build_directory_entry()`) invokes the `progress_callback` at defined intervals during directory traversal. The callback receives a `ProgressEvent` dataclass instance containing the current phase, item counts, current path, and an optional human-readable message. The caller — CLI, GUI, or API consumer — decides how to present this information.

```
Core engine                   Callback             Consumer
───────────                   ────────             ────────
build_directory_entry()  ──►  progress_callback()  ──►  CLI: tqdm bar / log message
                                                   ──►  GUI: progress bar + log textbox
                                                   ──►  API: custom handler
```

This architecture decouples the engine from all presentation concerns. The engine does not know whether progress is displayed as a terminal progress bar, a GUI widget, a log message, or nothing at all. It simply invokes the callback if one is provided.

#### CLI progress reporting

The CLI's progress presentation depends on the verbosity level and available third-party packages:

**Default behavior (no `-v` flag, `tqdm` not installed).** No progress output. The tool runs silently until completion (only warnings/errors appear on stderr). This matches the Unix convention of silent-unless-broken.

**With `-v` (INFO level).** Progress milestones are emitted as log messages to stderr: discovery count, completion percentage at 25%/50%/75%/100% intervals, and the final summary (total items, elapsed time). These are standard `INFO`-level log records from the entry orchestrator — not a separate progress display. They interleave naturally with any warnings or errors.

```
2026-02-15 14:30:02  a1b2c3d4  INFO      shruggie_indexer.core.entry  Indexing: /path/to/target (recursive)
2026-02-15 14:30:02  a1b2c3d4  INFO      shruggie_indexer.core.entry  Discovered 1,247 items
2026-02-15 14:30:05  a1b2c3d4  INFO      shruggie_indexer.core.entry  Progress: 312/1,247 (25%)
2026-02-15 14:30:08  a1b2c3d4  INFO      shruggie_indexer.core.entry  Progress: 624/1,247 (50%)
2026-02-15 14:30:11  a1b2c3d4  INFO      shruggie_indexer.core.entry  Progress: 936/1,247 (75%)
2026-02-15 14:30:14  a1b2c3d4  INFO      shruggie_indexer.core.entry  Progress: 1,247/1,247 (100%)
2026-02-15 14:30:14  a1b2c3d4  INFO      shruggie_indexer.core.entry  Completed in 12.4s (3 warnings)
```

**With `tqdm` installed and `-v` active.** The CLI MAY display a `tqdm` progress bar on stderr instead of percentage log lines. `tqdm` is listed as a recommended optional dependency (§12.3). The progress callback feeds `tqdm.update()` calls, and `tqdm.write()` is used for log messages to avoid disrupting the progress bar. This is strictly optional enhancement — the log-based progress reporting described above is the baseline behavior.

**With `-q` (quiet mode).** No progress output of any kind. The `progress_callback` is still invoked (it has negligible overhead), but the CLI's callback implementation ignores all events.

#### GUI progress reporting

The GUI's progress display system is defined in detail in §10.5. In summary: the `progress_callback` enqueues `ProgressEvent` objects into a `queue.Queue`, which the main thread drains on a 50ms timer to update the progress bar widget, the status text, and the log stream textbox. The GUI provides richer feedback than the CLI — a visual progress bar, a live item count, and a scrollable log stream — because the GUI context warrants it and the event-loop architecture supports it.

#### Progress callback implementation pattern

The CLI constructs a progress callback that bridges `ProgressEvent` data to its chosen display mechanism. The following illustrative example shows the log-based implementation:

```python
# Illustrative — inside cli/main.py

def make_progress_callback(
    logger: logging.Logger,
    milestone_pct: tuple[int, ...] = (25, 50, 75, 100),
) -> Callable[[ProgressEvent], None]:
    """Create a CLI progress callback that emits log messages at milestones."""
    last_milestone = 0

    def callback(event: ProgressEvent) -> None:
        nonlocal last_milestone

        if event.phase == "discovery" and event.items_total is not None:
            logger.info("Discovered %s items", f"{event.items_total:,}")
            return

        if event.phase == "processing" and event.items_total:
            pct = int(event.items_completed / event.items_total * 100)
            for m in milestone_pct:
                if pct >= m > last_milestone:
                    logger.info(
                        "Progress: %s/%s (%d%%)",
                        f"{event.items_completed:,}",
                        f"{event.items_total:,}",
                        pct,
                    )
                    last_milestone = m
                    break

        # Forward any embedded log messages from the engine.
        if event.message and event.level:
            level = getattr(logging, event.level.upper(), logging.INFO)
            logger.log(level, "%s", event.message)

    return callback
```

#### Elapsed time reporting

At the end of every invocation (CLI and GUI), the tool logs the total elapsed wall-clock time. The timer starts immediately before `index_path()` is called and stops immediately after it returns (or raises). The elapsed time is logged at `INFO` level.

```python
t0 = time.perf_counter()
try:
    entry = index_path(target, config, progress_callback=callback)
finally:
    elapsed = time.perf_counter() - t0
    logger.info("Elapsed time: %.1fs", elapsed)
```

The original computes elapsed time using `(Get-Date) - $TimeStart` and formats it as `H:M:S.ms`. The port uses `time.perf_counter()` for sub-millisecond precision and formats the result as seconds with one decimal place for typical invocations, or `MM:SS` for invocations exceeding 60 seconds. The formatting is a presentation detail — the `perf_counter()` value is the authoritative measurement.

#### Item failure summary

When one or more items fail during processing (item-level or field-level errors, §4.5), the CLI logs a summary at `WARNING` level after the elapsed time:

```
2026-02-15 14:30:14  a1b2c3d4  WARNING   shruggie_indexer.core.entry  3 items encountered errors during indexing
```

The per-item errors were already logged individually as `ERROR` or `WARNING` messages during processing. The summary provides a quick indication that the output is incomplete, without requiring the user to scroll through the full log to discover whether any errors occurred. The count of failed items also determines the exit code: if `failed_items > 0`, the CLI exits with `PARTIAL_FAILURE` (exit code 1, §8.10).
