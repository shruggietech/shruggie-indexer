# Vbs — Dependency Catalog

> **Source:** `main.ps1`, line 16412  
> **Purpose:** Structured logging and colorized verbosity output handler used throughout the pslib library as the centralized logging facility  
> **Audience:** AI-first, Human-second  

---

## 1. External PsLib Functions Called

| Function | Defined At | Called From | Purpose |
|---|---|---|---|
| *(none)* | — | — | `Vbs` is a leaf-level function in the pslib dependency graph. It does not call any other pslib functions. It is the terminal logging endpoint that virtually every other pslib function routes its verbose and log output through. |

### Role in the Library

`Vbs` is the most widely-called function in the pslib library. It serves as the universal logging handler and is invoked by every function cataloged in this project (Base64DecodeString, Date2UnixTime, DirectoryId, FileId, MetaFileRead, TempOpen, TempClose) as well as by MakeIndex and its sub-functions. It has zero upstream pslib dependencies, making it the foundational infrastructure function of the library.

---

## 2. External Variables Loaded

| Variable | Defined At | Type | Description |
|---|---|---|---|
| `$D_PSLIB_LOGS` | main.ps1:17399 | `[System.String]` | The absolute path to the pslib log directory (`C:\bin\pslib\logs`). Used as the default value for the `-LogDir` parameter. Log files are written to this directory |
| `$LibSessionID` | main.ps1:17387 | `[System.String]` | A GUID (hyphens removed) generated once at script load time. Used as the default value for the `-VbsSessionID` parameter. Embedded in every log entry to identify the session |

---

## 3. External Binaries / Executables Invoked

| Binary | Notes |
|---|---|
| *(none)* | This function is entirely PowerShell/.NET-based and does not invoke any external executables. |

---

## 4. Parameters

| Parameter | Type | Alias(es) | Default | Description |
|---|---|---|---|---|
| `Message` | `[System.String]` | *(none)* | *(none)* | The log message body. Defaults to `'...'` if empty |
| `Caller` | `[System.String]` | *(none)* | *(none)* | The name of the calling function or colon-delimited call stack (e.g., `"MakeIndex:MakeObject:GetFileExif"`) |
| `Status` | `[System.String]` | *(none)* | *(none)* | The severity level of the message. Accepted values (case-insensitive): `i`/`inf`/`info`, `e`/`err`/`error`, `c`/`crit`/`critical`, `w`/`warn`/`warning`, `d`/`deb`/`debug`, `s`/`success`/`ok`/`done`/`complete`/`g`/`good`, `x`/`u`/`unknown` |
| `LogDir` | `[System.String]` | `LogDirectory` | `$D_PSLIB_LOGS` | Directory where log files are written |
| `LibName` | `[System.String]` | `LibraryName` | `"pslib"` | Library name prefix used in log entry formatting |
| `VbsSessionID` | `[System.String]` | *(none)* | `$LibSessionID` | Session identifier embedded in each log entry |
| `Verbosity` | `[System.Boolean]` | `v` | *(none)* | If `$true`, the message is both written to the log file AND printed to the console. If `$false`, the message is only written to the log file |

---

## 5. Internal Sub-Functions (Defined Within Vbs)

| Function | Line | Purpose | Nesting |
|---|---|---|---|
| `VbsFunctionStackTotalDepth` | main.ps1:16491 | Calculates the total depth of the function call stack string. Each non-numbered function counts as 1; numbered functions (e.g., `MakeObject(3)`) count as the numeric suffix value. Returns an `[int]` | Top-level internal |
| `VbsLogPath` | main.ps1:16517 | Derives the path to the current monthly log file based on the current date. Format: `YYYY_MM.log` in the log directory | Top-level internal |
| `VbsLogRealityCheck` | main.ps1:16529 | Ensures the log directory and log file exist, creating them if necessary via `New-Item` | Top-level internal |
| `VbsLogWrite` | main.ps1:16545 | Writes a string to the log file via `Add-Content` | Top-level internal |
| `VbsUpdateFunctionStack` | main.ps1:16558 | Compresses and updates a colon-delimited function call stack by collapsing consecutive duplicate function names into counted entries (e.g., `A:A:A` → `A(3)`). Used to produce readable stack traces in log entries | Top-level internal |
| `VbsUpdateFunctionStackExtractNumber` | main.ps1:16567 | Extracts the numeric suffix from a function name string (e.g., `"MakeObject(3)"` → `2`). Returns `[int]0` if no suffix or suffix is less than 2 | Nested inside `VbsUpdateFunctionStack` |

---

## 6. Internal Logic Summary

**Log Entry Construction:**

Each log entry is assembled from four fields:

1. **Timestamp (`$t`):** Dual-format Unix milliseconds and human-readable ISO datetime with timezone offset. Format: `{UnixMs}|{yyyy-MM-dd HH:mm:ss.fffzzz}|`

2. **Session ID (`$x`):** The `VbsSessionID` GUID followed by a pipe delimiter.

3. **Status (`$s`):** Normalized from shorthand input to a bracketed tag. The verbose version (`$sV`) uses a fixed-width padded format for console alignment. Each status level has an associated console color:

   | Input | Log Tag | Console Color |
   |---|---|---|
   | `i`, `inf`, `info` | `[INFO]` | Gray |
   | `e`, `err`, `error` | `[ERROR]` | DarkRed |
   | `c`, `crit`, `critical` | `[ERROR][CRITICAL]` | Magenta |
   | `w`, `warn`, `warning` | `[WARN]` | DarkYellow |
   | `d`, `deb`, `debug` | `[DEBUG]` | DarkCyan |
   | `s`, `success`, `ok`, `done`, `g`, `good` | `[INFO][SUCCESS]` | DarkGreen |
   | `x`, `u`, `unknown` (or missing) | `[INFO][UNKNOWN]` | DarkGray |

4. **Caller (`$c`):** Processed through `VbsUpdateFunctionStack` to compress the call stack. The final log-format wraps the stack in `pslib(...):`; the verbose-format uses `pslib({depth}):` where `{depth}` is the total stack depth.

5. **Message (`$m`):** The raw message string. Defaults to `'...'` if empty.

**Output Channels:**

Two output strings are produced: `$o` (machine-readable, written to log file) and `$oV` (human-readable, colorized, printed to console). When `$Verbosity` is `$false`, only the log file is written. When `$true`, both outputs are produced.

**Log File Management:**

Log files are named by month (`YYYY_MM.log`) and stored in `$D_PSLIB_LOGS`. The `VbsLogRealityCheck` sub-function ensures both the directory and file exist before writing, creating them via `New-Item` if missing.

**Call Stack Compression:**

The `VbsUpdateFunctionStack` function is a key feature that transforms raw colon-delimited call stacks into compact representations. For example: `MakeIndex:MakeObject:MakeObject:MakeObject` → `MakeIndex:MakeObject(3)`. This prevents log lines from becoming excessively long during deeply recursive operations like `MakeDirectoryIndexRecursiveLogic`.

---

## 7. .NET Types and Methods Used

| Type / Method | Usage |
|---|---|
| `[DateTimeOffset]::Now.ToUnixTimeMilliseconds()` | Generating Unix epoch milliseconds for the timestamp field |
| `[System.TimeSpan]::FromMilliseconds()` | Converting Unix ms back to a TimeSpan for human-readable date formatting |
| `Get-Date 01.01.1970` | Establishing the Unix epoch base date for timestamp calculation |

---

## 8. PowerShell Built-in Cmdlets Used

| Cmdlet | Usage Context |
|---|---|
| `Add-Content` | Writing log entries to the monthly log file (`-Path`, `-Value`) |
| `Get-Date` | Establishing the epoch base date; formatting the human-readable timestamp (`-UFormat "%Y_%m"` for log file naming) |
| `New-Item` | Creating log directory and log file if they don't exist (`-ItemType Directory/File`, `-Path`, `-Force`) |
| `Test-Path` | Checking existence of log directory and log file (`-LiteralPath`, `-PathType Container/Leaf`) |
| `Write-Host` | Printing colorized verbose output to the console (`-ForegroundColor`) |

---

## 9. Return Value

This function does not return a value. All code paths terminate with `return` (no value). The function's purpose is side-effect-driven: writing to log files and optionally printing to the console.

---

## 10. Log File Format

**File naming:** `YYYY_MM.log` (one file per month)

**Entry format (machine-readable):**
```
{UnixMs}|{yyyy-MM-dd HH:mm:ss.fffzzz}|{SessionGUID}|{StatusTags}{LibName}({CompressedStack}): {Message}
```

**Entry format (console/verbose):**
```
{yyyy-MM-dd HH:mm:ss.fffzzz} {SessionGUID} {PaddedStatus} {LibName}({StackDepth}): {Message}
```

---

## 11. Call Graph

```
Vbs
├── [construct timestamp field]
│   ├── [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
│   └── [System.TimeSpan]::FromMilliseconds()
├── [construct session ID field]
├── [normalize Status to tag and color]
├── [process Caller field]
│   ├── [split on ':' to detect sub-function stacks]
│   └── VbsUpdateFunctionStack (compress stack)
│       └── VbsUpdateFunctionStackExtractNumber (extract numeric suffixes)
├── VbsFunctionStackTotalDepth (compute depth for verbose format)
├── [construct message field]
├── VbsLogPath (derive log file path from current date)
├── VbsLogRealityCheck (ensure log dir and file exist)
│   └── New-Item (create if missing)
├── (Verbosity=$false) → VbsLogWrite only
│   └── Add-Content (write to log file)
└── (Verbosity=$true) → VbsLogWrite + Write-Host
    ├── Add-Content (write to log file)
    └── Write-Host (colorized console output)
```
