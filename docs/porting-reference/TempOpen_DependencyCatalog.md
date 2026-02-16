# TempOpen — Dependency Catalog

> **Source:** `main.ps1`, line 15119  
> **Purpose:** Creates a new temporary file in the pslib temp directory with a UUID-based name and returns the absolute path to it  
> **Audience:** AI-first, Human-second  

---

## 1. External PsLib Functions Called

| Function | Defined At | Called From | Purpose |
|---|---|---|---|
| `Vbs` | main.ps1:16412 | Top-level body | Verbose/logging output handler. Called with `-Caller`, `-Status` (i), `-Message`, `-Verbosity` to log the creation of the temp file |

---

## 2. External Variables Loaded

| Variable | Defined At | Type | Description |
|---|---|---|---|
| `$D_PSLIB_TEMP` | main.ps1:17400 | `[System.String]` | The absolute path to the pslib temporary file directory (`C:\bin\pslib\temp`). Used as the base directory for all temp file creation |
| `$Sep` | main.ps1:17383 | `[System.Char]` | Directory separator character (`[System.IO.Path]::DirectorySeparatorChar`). Used to construct the full temp file path |

---

## 3. External Binaries / Executables Invoked

| Binary | Notes |
|---|---|
| *(none)* | This function is entirely PowerShell/.NET-based and does not invoke any external executables. |

---

## 4. Parameters

| Parameter | Type | Alias(es) | Default | Description |
|---|---|---|---|---|
| `Type` | `[System.String]` | `t`, `TempType` | `'tmp'` | The file extension for the new temp file. Leading dots are stripped automatically |
| `Name` | `[System.String]` | `n`, `TempName` | `'x'` | A descriptive prefix substring embedded in the temp file name for identification |
| `PathOnly` | `[System.Boolean]` | `p` | `$false` | If `$true`, returns the computed file path without actually creating the file |
| `Verbosity` | `[System.Boolean]` | `v` | `$false` | Controls whether verbose/log messages are printed to the console |

---

## 5. Internal Sub-Functions

This function defines no internal sub-functions.

---

## 6. Internal Logic Summary

**File Name Generation:**

The temp file name is constructed using the following template:

```
.{UUID}-{Name}-{UnixTimeMs}.{Type}
```

Where:
- Leading dot (`.`) makes the file hidden on Unix-like systems
- `{UUID}` is a GUID with hyphens removed (`[System.GUID]::NewGuid().ToString().Replace('-','')`)
- `{Name}` is the user-specified descriptive prefix (default: `"x"`)
- `{UnixTimeMs}` is the current Unix time in milliseconds
- `{Type}` is the file extension (default: `"tmp"`)

**Historical Note:** The function was updated on 2024-10-27 to use UUIDs instead of Unix timestamps as the primary uniqueness component, due to an actual name collision that occurred during concurrent script executions.

**Path Construction:**

The full path is: `$D_PSLIB_TEMP` + `$Sep` + file name

**File Creation:**

Unless `-PathOnly` is `$true`, the file is created via `New-Item -ItemType File -Force`. The output of `New-Item` is suppressed via `| Out-Null`.

---

## 7. .NET Types and Methods Used

| Type / Method | Usage |
|---|---|
| `[System.GUID]::NewGuid()` | Generating UUID for temp file name uniqueness |
| `[DateTimeOffset]::Now.ToUnixTimeMilliseconds()` | Generating timestamp component for temp file name |

---

## 8. PowerShell Built-in Cmdlets Used

| Cmdlet | Usage Context |
|---|---|
| `New-Item` | Creating the temp file (`-ItemType File`, `-Force`, `-Path`) |
| `Select-Object` | Extracting `$PWD` path (`-Expand Path`) — though `$HereNow` is computed but unused in this function |

---

## 9. Return Value

Returns a `[System.String]` containing the absolute path to the newly created (or hypothetical, if `-PathOnly`) temporary file.

---

## 10. Companion Function: TempClose

`TempOpen` is designed to be used in conjunction with `TempClose` (main.ps1:15044). The expected usage pattern is:

```powershell
$MyTempFile = (TempOpen -Type json -Name "myProject")
# ... use $MyTempFile ...
TempClose -Target $MyTempFile
```

The docstring explicitly warns that failing to call `TempClose` will leave orphaned temp files in the pslib temp directory.

---

## 11. Call Graph

```
TempOpen
├── [validates and normalizes Type parameter]
├── [validates and normalizes Name parameter]
├── [generates UUID and timestamp]
├── [constructs file name and full path]
├── (PathOnly=$false) → New-Item (create file)
│   └── Vbs ◄── external pslib (info: "Creating new temp file")
└── return file path string
```
