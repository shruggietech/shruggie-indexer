# Base64DecodeString — Dependency Catalog

> **Source:** `main.ps1`, line 764  
> **Purpose:** Decodes a Base64-encoded string into plaintext with optional URL decoding and configurable encoding type  
> **Audience:** AI-first, Human-second  

---

## 1. External PsLib Functions Called

| Function | Defined At | Called From | Purpose |
|---|---|---|---|
| `Vbs` | main.ps1:16412 | Top-level body | Verbose/logging output handler. Called with `-Caller`, `-Status` (e/w), `-Message`, `-Verbosity` |

This function has a minimal external dependency footprint. It only calls `Vbs` for error/warning logging (e.g., empty input string, unknown encoding type).

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
| `Help` | `[Switch]` | `h` | `$false` | Print detailed help text and return |
| `InputString` | `[System.String]` | `i`, `in`, `str`, `string` | `$null` | The Base64-encoded string to decode |
| `Encoding` | `[System.String]` | `e`, `encode` | `UTF8` | Encoding type: `UTF8` or `ASCII`. Unknown values fall back to UTF8 with a warning |
| `UrlDecode` | `[System.Boolean]` | `u` | `$false` | If `$true`, the decoded output is additionally passed through `[System.Web.HttpUtility]::UrlDecode()` |
| `Verbosity` | `[System.Boolean]` | `v` | `$true` | Controls whether verbose/log messages are printed to the console |

---

## 5. Internal Logic Summary

The function uses a numeric "OpsCode" pattern to select the correct decoding path. The OpsCode is computed by summing two values: one based on the `Encoding` parameter (0 for UTF8, 1 for ASCII) and one based on the `UrlDecode` parameter (0 for `$false`, 10 for `$true`). The resulting OpsCode determines which of four branches executes:

| OpsCode | Encoding | UrlDecode | Action |
|---|---|---|---|
| 0 | UTF8 | No | `[System.Text.Encoding]::UTF8.GetString(FromBase64String(...))` |
| 1 | ASCII | No | `[System.Text.Encoding]::ASCII.GetString(FromBase64String(...))` |
| 10 | UTF8 | Yes | UTF8 decode → `[System.Web.HttpUtility]::UrlDecode(...)` |
| 11 | ASCII | Yes | ASCII decode → `[System.Web.HttpUtility]::UrlDecode(...)` |

---

## 6. Internal Sub-Functions

This function defines no internal sub-functions.

---

## 7. .NET Types and Methods Used

| Type / Method | Usage |
|---|---|
| `[System.Convert]::FromBase64String()` | Core Base64 → byte-array conversion |
| `[System.Text.Encoding]::UTF8.GetString()` | Byte-array → UTF8 string conversion |
| `[System.Text.Encoding]::ASCII.GetString()` | Byte-array → ASCII string conversion |
| `[System.Web.HttpUtility]::UrlDecode()` | URL-decoding of the decoded string output |

---

## 8. PowerShell Built-in Cmdlets Used

| Cmdlet | Usage Context |
|---|---|
| `Get-Help` | Displaying function help when `-Help` is specified |

---

## 9. Return Value

Returns a `[System.String]` containing the decoded plaintext. Returns nothing (implicit `$null`) if the input string is empty.

---

## 10. Call Graph

```
Base64DecodeString
├── [validates InputString is non-empty]
│   └── Vbs ◄── external pslib (on error)
├── [validates Encoding parameter]
│   └── Vbs ◄── external pslib (on unknown encoding warning)
├── [computes OpsCode from Encoding + UrlDecode]
└── [executes decode branch based on OpsCode]
    ├── (OpsCode=0)  → UTF8 decode
    ├── (OpsCode=1)  → ASCII decode
    ├── (OpsCode=10) → UTF8 decode + UrlDecode
    └── (OpsCode=11) → ASCII decode + UrlDecode
```
