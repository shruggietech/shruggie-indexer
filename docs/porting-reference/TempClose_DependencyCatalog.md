# TempClose — Dependency Catalog

> **Source:** `main.ps1`, line 15044  
> **Purpose:** Deletes a specified temporary file, or optionally purges all temp files from the pslib temp directory  
> **Audience:** AI-first, Human-second  

---

## 1. External PsLib Functions Called

| Function | Defined At | Called From | Purpose |
|---|---|---|---|
| `Vbs` | main.ps1:16412 | Top-level body | Verbose/logging output handler. Called with `-Caller`, `-Status` (i/e/w), `-Message`, `-Verbosity` for info, error, and warning logging |

---

## 2. External Variables Loaded

| Variable | Defined At | Type | Description |
|---|---|---|---|
| `$D_PSLIB_TEMP` | main.ps1:17400 | `[System.String]` | The absolute path to the pslib temporary file directory (`C:\bin\pslib\temp`). Used when `-ForceAll` is `$true` to enumerate and delete all temp files in the directory |

---

## 3. External Binaries / Executables Invoked

| Binary | Notes |
|---|---|
| *(none)* | This function is entirely PowerShell-based and does not invoke any external executables. |

---

## 4. Parameters

| Parameter | Type | Alias(es) | Default | Description |
|---|---|---|---|---|
| `Target` | `[System.String]` | `f`, `fil`, `i`, `in`, `input`, `t`, `tmp`, `temp` | `$null` | The absolute path to the temporary file to delete |
| `ForceAll` | `[System.Boolean]` | `force` | `$false` | If `$true`, ignores the `-Target` parameter and deletes **all** files in `$D_PSLIB_TEMP` recursively |
| `Verbosity` | `[System.Boolean]` | `v` | `$false` | Controls whether verbose/log messages are printed to the console |

---

## 5. Internal Sub-Functions

This function defines no internal sub-functions.

---

## 6. Internal Logic Summary

The function operates in one of three modes based on the parameter values:

**Mode 1 — ForceAll (`-ForceAll $true`):**
Ignores the `-Target` parameter entirely. Enumerates all files in `$D_PSLIB_TEMP` recursively via `Get-ChildItem` with `-Filter "*.*"`. If files are found, each is deleted via `Remove-Item -Force`. If no files exist, an informational message is logged and the function returns.

**Mode 2 — Single Target Deletion (default):**
If `-Target` is provided and the file exists, it is deleted via `Remove-Item -LiteralPath -Force`.

**Mode 3 — Error States:**
If `-ForceAll` is `$false` and `-Target` is `$null`, an error message is logged. If `-Target` is provided but the file does not exist, a warning message is logged (but the function does not throw an error).

---

## 7. .NET Types and Methods Used

| Type / Method | Usage |
|---|---|
| *(none)* | This function uses only PowerShell cmdlets; no .NET types are directly invoked. |

---

## 8. PowerShell Built-in Cmdlets Used

| Cmdlet | Usage Context |
|---|---|
| `Get-ChildItem` | Enumerating temp files when `-ForceAll` is active (`-LiteralPath`, `-Filter "*.*"`, `-Recurse`, `-Force`) |
| `Remove-Item` | Deleting temp files (`-LiteralPath`, `-Force`) |
| `Test-Path` | Validating target file existence before deletion (`-LiteralPath`, `-PathType Leaf`) |

---

## 9. Return Value

This function does not return a value. All code paths terminate with `return` (no value).

---

## 10. Companion Function: TempOpen

`TempClose` is designed to be used in conjunction with `TempOpen` (main.ps1:15119). The expected usage pattern is:

```powershell
$MyTempFile = (TempOpen -Type json -Name "myProject")
# ... use $MyTempFile ...
TempClose -Target $MyTempFile
```

The `TempOpen` docstring explicitly warns that failing to call `TempClose` will leave orphaned temp files in the pslib temp directory. The `-ForceAll` mode provides a way to clean up all orphaned files at once.

---

## 11. Call Graph

```
TempClose
├── (ForceAll=$true)
│   ├── Get-ChildItem on $D_PSLIB_TEMP
│   ├── Vbs ◄── external pslib (info: count or "nothing to do")
│   └── foreach file → Remove-Item
│       └── Vbs ◄── external pslib (info: "Closing temp file")
├── (ForceAll=$false, Target=$null)
│   └── Vbs ◄── external pslib (error: "No input detected")
├── (ForceAll=$false, Target does not exist)
│   └── Vbs ◄── external pslib (warning: "File not found")
└── (ForceAll=$false, Target exists)
    ├── Vbs ◄── external pslib (info: "Closing referenced temp file")
    └── Remove-Item
```
