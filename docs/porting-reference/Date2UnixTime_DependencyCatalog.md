# Date2UnixTime — Dependency Catalog

> **Source:** `main.ps1`, line 2517  
> **Purpose:** Converts a formatted date string to a Unix timestamp (milliseconds since epoch) with optional or auto-detected format codes  
> **Audience:** AI-first, Human-second  

---

## 1. External PsLib Functions Called

| Function | Defined At | Called From | Purpose |
|---|---|---|---|
| `Date2FormatCode` | main.ps1:2374 | Top-level body | Attempts to determine a date-time format code from a raw date string. Called when no explicit `-Format` parameter is provided. Returns a format code string or `$null` |
| `Vbs` | main.ps1:16412 | Top-level body | Verbose/logging output handler. Called with `-Caller`, `-Status` (e), `-Message`, `-Verbosity` |

### Dependency Note: `Date2FormatCode`

`Date2FormatCode` is a separate top-level pslib function (defined at main.ps1:2374) that analyzes the structure of a date string and returns a matching .NET date-time format code. It is the primary means by which `Date2UnixTime` auto-detects the format of an input date string when no explicit `-Format` is specified. If `Date2FormatCode` fails to detect a format, `Date2UnixTime` falls back to its own internal format-guessing logic via the `Date2UnixTimeSquash` → `Date2UnixTimeCountDigits` → `Date2UnixTimeFormatCode` chain.

---

## 2. External Variables Loaded

| Variable | Defined At | Type | Description |
|---|---|---|---|
| *(none)* | — | — | This function does not reference any script-level or global variables. All state is derived from its own parameters. |

---

## 3. External Binaries / Executables Invoked

| Binary | Notes |
|---|---|
| *(none)* | This function is entirely .NET-based and does not invoke any external executables. |

---

## 4. Parameters

| Parameter | Type | Alias(es) | Default | Description |
|---|---|---|---|---|
| `Date` | `[System.String]` | `d`, `i`, `in`, `inputdate` | `$null` | The date string to convert (e.g., `"2021-12-31 23:59:59"`) |
| `Format` | `[System.String]` | `f`, `formatstring` | `$null` | An explicit .NET date-time format code (e.g., `"yyyy-MM-dd HH:mm:ss"`). If omitted, the function auto-detects the format |
| `Help` | `[Switch]` | `h` | `$false` | Print detailed help text and return |
| `Verbosity` | `[System.Boolean]` | `v` | `$true` | Controls whether verbose/log messages are printed to the console |

---

## 5. Internal Sub-Functions (Defined Within Date2UnixTime)

| Function | Line | Purpose |
|---|---|---|
| `Date2UnixTimeCountDigits` | main.ps1:2577 | Counts the number of numeric characters (digits) in the input date string using regex matching |
| `Date2UnixTimeFormatCode` | main.ps1:2595 | Maps a digit count (4–20) to a .NET date-time format code string via a switch statement. Returns `$null` for out-of-range counts |
| `Date2UnixTimeSquash` | main.ps1:2626 | Strips all non-numeric characters from the input date string using regex replacement (`-replace '[^\d]', ''`) |

---

## 6. Internal Logic Summary

The function follows a three-stage process:

**Stage 1 — Input Validation:** Checks that a non-empty `-Date` parameter was provided. Returns an error via `Vbs` if missing.

**Stage 2 — Format Code Resolution:** If an explicit `-Format` is provided, it is used directly and the date string is passed through unchanged. Otherwise, the function first attempts format detection via the external `Date2FormatCode` function. If that returns `$null`, the function falls back to its own internal pipeline: the date string is stripped of non-numeric characters (`Date2UnixTimeSquash`), digits are counted (`Date2UnixTimeCountDigits`), and the count is mapped to a format code (`Date2UnixTimeFormatCode`). Additional edge-case handling includes rejecting dates with fewer than 4 digits, truncating dates longer than 20 digits, and trimming odd-count digit strings by one character to produce an even count.

**Stage 3 — Conversion:** The resolved date string and format code are passed to `[DateTimeOffset]::ParseExact()` and the result is converted to Unix time in milliseconds via `.ToUnixTimeMilliseconds()`.

---

## 7. .NET Types and Methods Used

| Type / Method | Usage |
|---|---|
| `[DateTimeOffset]::ParseExact()` | Parses the date string using the resolved format code |
| `.ToUnixTimeMilliseconds()` | Converts the parsed `DateTimeOffset` to Unix epoch milliseconds |
| `[int64]` | Cast for the final return value |

---

## 8. PowerShell Built-in Cmdlets Used

| Cmdlet | Usage Context |
|---|---|
| `Get-Help` | Displaying function help when `-Help` is specified |

---

## 9. Return Value

Returns an `[int64]` representing the Unix timestamp in **milliseconds** since the Unix epoch (1970-01-01T00:00:00Z). Returns nothing (implicit `$null`) if the input date is empty or has fewer than 4 numeric characters.

---

## 10. Call Graph

```
Date2UnixTime
├── [validates Date parameter is non-empty]
│   └── Vbs ◄── external pslib (on error)
├── [Format code resolution]
│   ├── (Format provided) → use as-is
│   └── (Format not provided)
│       ├── Date2FormatCode ◄── external pslib
│       └── (Date2FormatCode returned $null) → fallback:
│           ├── Date2UnixTimeSquash (internal)
│           ├── Date2UnixTimeCountDigits (internal)
│           │   └── Vbs ◄── external pslib (on <4 digits error)
│           └── Date2UnixTimeFormatCode (internal)
└── [DateTimeOffset]::ParseExact() → .ToUnixTimeMilliseconds()
```
