# FileId — Dependency Catalog

> **Source:** `main.ps1`, line 4941  
> **Purpose:** Generates hash-based unique identifiers for files based on file content hashing (or name hashing for symbolic links)  
> **Audience:** AI-first, Human-second  

---

## 1. External PsLib Functions Called

| Function | Defined At | Called From | Purpose |
|---|---|---|---|
| `Vbs` | main.ps1:16412 | Top-level body and `FileId-ResolvePath` | Verbose/logging output handler. Called with `-Caller`, `-Status` (e/w), `-Message`, `-Verbosity` |

This function has a minimal external dependency footprint. It only calls `Vbs` for error/warning logging (missing input, invalid file, invalid hash types, empty path in resolution).

---

## 2. External Variables Loaded

| Variable | Defined At | Type | Description |
|---|---|---|---|
| *(none)* | — | — | This function does not reference any script-level or global variables. All state is derived from its own parameters and the filesystem. |

---

## 3. External Binaries / Executables Invoked

| Binary | Notes |
|---|---|
| *(none)* | This function is entirely .NET-based and does not invoke any external executables. |

---

## 4. Parameters

| Parameter | Type | Alias(es) | Default | Description |
|---|---|---|---|---|
| `FileIdPendingFile` | `[System.String]` | *(none)* | `$null` | The file path to generate an identifier for |
| `OutputObject` | `[Switch]` | `o` | `$false` | Return a `[PSCustomObject]` with all properties |
| `OutputJson` | `[Switch]` | `j` | `$false` | Return a JSON-formatted string of the full result object |
| `IncludeHashTypes` | `[System.Array]` | *(none)* | `@('md5','sha256')` | Array of hash algorithms to use. Valid values: `md5`, `sha1`, `sha256`, `sha512`, `all`. Case-insensitive. Specifying `all` expands to all four types |
| `Verbosity` | `[System.Boolean]` | `v` | `$true` | Controls whether verbose/log messages are printed to the console |

---

## 5. Internal Sub-Functions (Defined Within FileId)

| Function | Line | Purpose | Nesting |
|---|---|---|---|
| `FileId-GetName` | main.ps1:5041 | Extracts the simple file name from a path using `[System.IO.Path]::GetFileName()`. Returns `$null` for empty paths | Top-level internal |
| `FileId-HashMd5` | main.ps1:5063 | Computes MD5 hash of **file contents** via `[System.IO.File]::OpenRead()` and `[System.Security.Cryptography.MD5]::Create()` | Top-level internal |
| `FileId-HashMd5-String` | main.ps1:5076 | Computes MD5 hash of a **string** value. Returns null-hash constant for empty/null inputs | Top-level internal |
| `FileId-HashSha1` | main.ps1:5094 | Computes SHA1 hash of **file contents** | Top-level internal |
| `FileId-HashSha1-String` | main.ps1:5107 | Computes SHA1 hash of a **string** value. Returns null-hash constant for empty/null inputs | Top-level internal |
| `FileId-HashSha256` | main.ps1:5125 | Computes SHA256 hash of **file contents** | Top-level internal |
| `FileId-HashSha256-String` | main.ps1:5138 | Computes SHA256 hash of a **string** value. Returns null-hash constant for empty/null inputs | Top-level internal |
| `FileId-HashSha512` | main.ps1:5156 | Computes SHA512 hash of **file contents** | Top-level internal |
| `FileId-HashSha512-String` | main.ps1:5169 | Computes SHA512 hash of a **string** value. Returns null-hash constant for empty/null inputs | Top-level internal |
| `FileId-ResolvePath` | main.ps1:5187 | Resolves a file path to its absolute form using `Resolve-Path` with a `[System.IO.Path]::GetFullPath()` fallback | Top-level internal |

---

## 6. Internal Logic Summary

**ID Generation Algorithm:**

Unlike `DirectoryId` (which hashes directory + parent name), `FileId` hashes file **contents** directly:

1. Resolve the file path to absolute form
2. Detect if the file is a symbolic link (via `ReparsePoint` attribute check)
3. For each requested hash type:
   - If the file **is** a symbolic link → hash the **file name string** instead of contents
   - If the file **is not** a symbolic link → hash the **file contents** via file stream
4. Prepend `"y"` to each content hash to form the final ID

The `"y"` prefix distinguishes file IDs from directory IDs (which use the `"x"` prefix in `DirectoryId`).

**Symlink Handling:**

Symbolic links are detected via: `(Get-Item -LiteralPath $FilePath -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint`

When a file is a symlink, the content hash is replaced with the name hash, ensuring the ID remains deterministic without requiring the link target to be accessible.

**Name Hashes:**

Name hashes (MD5, SHA1, SHA256, SHA512 of the file name string) are always computed regardless of the `IncludeHashTypes` parameter, as they are low-overhead and are needed for the symlink fallback path.

---

## 7. Output Object Properties

The full `[PSCustomObject]` (returned when `-OutputObject` is used) contains:

| Property | Type | Description |
|---|---|---|
| `IsDirectory` | `[Boolean]` | Always `$false` for valid file inputs |
| `IsFile` | `[Boolean]` | `$true` if the file exists |
| `IsLink` | `[Boolean]` | `$true` if the file is a symbolic link (ReparsePoint) |
| `Name` | `[String]` | The simple file name (with extension, no path) |
| `Path` | `[String]` | The resolved absolute file path |
| `NameMD5` | `[String]` | MD5 hash of the file name string |
| `NameSHA1` | `[String]` | SHA1 hash of the file name string |
| `NameSHA256` | `[String]` | SHA256 hash of the file name string |
| `NameSHA512` | `[String]` | SHA512 hash of the file name string |
| `ContentMD5` | `[String]` or `$null` | MD5 hash of file contents (or name hash if symlink). `$null` if not in `IncludeHashTypes` |
| `ContentSHA1` | `[String]` or `$null` | SHA1 hash of file contents (or name hash if symlink). `$null` if not requested |
| `ContentSHA256` | `[String]` or `$null` | SHA256 hash of file contents (or name hash if symlink). `$null` if not requested |
| `ContentSHA512` | `[String]` or `$null` | SHA512 hash of file contents (or name hash if symlink). `$null` if not requested |
| `IdMD5` | `[String]` or `$null` | `"y"` + ContentMD5. `$null` if not requested |
| `IdSHA1` | `[String]` or `$null` | `"y"` + ContentSHA1. `$null` if not requested |
| `IdSHA256` | `[String]` or `$null` | `"y"` + ContentSHA256. `$null` if not requested |
| `IdSHA512` | `[String]` or `$null` | `"y"` + ContentSHA512. `$null` if not requested |
| `ContentHashTypes` | `[Array]` | Array of hash type strings that were actually processed |

---

## 8. .NET Types and Methods Used

| Type / Method | Usage |
|---|---|
| `[System.IO.File]::OpenRead()` | Opening file stream for content hashing |
| `[System.IO.FileAttributes]::ReparsePoint` | Symbolic link detection via bitwise AND |
| `[System.IO.Path]::GetFileName()` | Extracting file name from path |
| `[System.IO.Path]::GetFullPath()` | Resolving hypothetical paths |
| `[System.Security.Cryptography.MD5]::Create()` | MD5 hash computation |
| `[System.Security.Cryptography.SHA1]::Create()` | SHA1 hash computation |
| `[System.Security.Cryptography.SHA256]::Create()` | SHA256 hash computation |
| `[System.Security.Cryptography.SHA512]::Create()` | SHA512 hash computation |
| `[System.Text.Encoding]::UTF8.GetBytes()` | String → byte-array conversion for name hashing |
| `[BitConverter]::ToString()` | Byte-array → hex-string conversion |
| `[PSCustomObject]@{}` | Output object construction |

---

## 9. PowerShell Built-in Cmdlets Used

| Cmdlet | Usage Context |
|---|---|
| `ConvertTo-Json` | Serializing output when `-OutputJson` is specified (`-Depth 100`) |
| `Get-Item` | Checking file attributes for symlink detection (`-Force`, `-LiteralPath`) |
| `Resolve-Path` | Resolving file paths to absolute form (`-LiteralPath`) |
| `Test-Path` | Validating file existence (`-LiteralPath`, `-PathType Leaf/Container`) |

---

## 10. Return Value

Default (no output switches): Returns a `[System.String]` containing the **last** content hash ID processed (corresponds to the last element in the `IncludeHashTypes` array; with defaults this is the SHA256-based ID prefixed with `"y"`).

With `-OutputObject`: Returns the full `[PSCustomObject]` described in Section 7.

With `-OutputJson`: Returns a JSON-formatted string of the full result object.

Returns `$null` if the input file is missing, does not exist, or no valid hash types were processed.

---

## 11. Call Graph

```
FileId
├── [validates FileIdPendingFile is non-empty and exists]
│   └── Vbs ◄── external pslib (on error)
├── FileId-ResolvePath
│   └── Vbs ◄── external pslib (on empty input)
├── FileId-GetName
├── [compute name hashes — always performed]
│   ├── FileId-HashMd5-String
│   ├── FileId-HashSha1-String
│   ├── FileId-HashSha256-String
│   └── FileId-HashSha512-String
├── [detect symbolic link via ReparsePoint]
├── [expand "all" keyword in IncludeHashTypes]
├── [for each requested hash type]
│   ├── (is symlink) → use name hash as content hash
│   └── (not symlink) → compute content hash via:
│       ├── FileId-HashMd5 (file stream)
│       ├── FileId-HashSha1 (file stream)
│       ├── FileId-HashSha256 (file stream)
│       └── FileId-HashSha512 (file stream)
│   └── prepend "y" to form final ID
└── [format output based on switches]
```
