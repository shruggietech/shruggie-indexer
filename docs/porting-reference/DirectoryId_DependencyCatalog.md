# DirectoryId — Dependency Catalog

> **Source:** `main.ps1`, line 2819  
> **Purpose:** Generates hash-based unique identifiers for directories by combining hashes of the directory name and its parent directory name  
> **Audience:** AI-first, Human-second  

---

## 1. External PsLib Functions Called

| Function | Defined At | Called From | Purpose |
|---|---|---|---|
| `Vbs` | main.ps1:16412 | Top-level body and `DirectoryId-ResolvePath` | Verbose/logging output handler. Called with `-Caller`, `-Status` (i/e), `-Message`, `-Verbosity` |

This function has a minimal external dependency footprint. It only calls `Vbs` for informational logging and error reporting (missing directory, non-existent directory, empty input in path resolution).

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
| `Directory` | `[System.String]` | `d`, `dir`, `p`, `path` | `$null` | The full path to the target directory. Mandatory unless `-Here` is `$true` |
| `Here` | `[System.Boolean]` | *(none)* | `$false` | If `$true`, the current working directory (`$PWD`) is used instead of `-Directory` |
| `OutputObject` | `[Switch]` | `o` | `$false` | Return a `[PSCustomObject]` with all properties instead of a single hash string |
| `OutputJson` | `[Switch]` | `j` | `$false` | Return a JSON-formatted string of the full result object |
| `Verbosity` | `[System.Boolean]` | `v` | `$false` | Controls whether verbose/log messages are printed to the console |

---

## 5. Internal Sub-Functions (Defined Within DirectoryId)

| Function | Line | Purpose | Nesting |
|---|---|---|---|
| `DirectoryId-GetName` | main.ps1:2939 | Extracts the leaf name from a directory path using `[System.IO.Path]::GetFileName()`. Returns `$null` for root-level paths | Top-level internal |
| `DirectoryId-HashString` | main.ps1:2963 | Dispatcher function that routes hashing requests to the appropriate algorithm-specific sub-function based on a `-Type` parameter (`MD5`, `SHA1`, `SHA256`, `SHA512`) | Top-level internal |
| `DirectoryId-HashString-Md5` | main.ps1:2973 | Hashes a string using `[System.Security.Cryptography.MD5]::Create()`. Returns the null-hash constant `D41D8CD98F00B204E9800998ECF8427E` for empty/null inputs | Nested inside `DirectoryId-HashString` |
| `DirectoryId-HashString-Sha1` | main.ps1:2993 | Hashes a string using `[System.Security.Cryptography.SHA1]::Create()`. Returns the null-hash constant for empty/null inputs | Nested inside `DirectoryId-HashString` |
| `DirectoryId-HashString-Sha256` | main.ps1:3013 | Hashes a string using `[System.Security.Cryptography.SHA256]::Create()`. Returns the null-hash constant for empty/null inputs | Nested inside `DirectoryId-HashString` |
| `DirectoryId-HashString-Sha512` | main.ps1:3033 | Hashes a string using `[System.Security.Cryptography.SHA512]::Create()`. Returns the null-hash constant for empty/null inputs | Nested inside `DirectoryId-HashString` |
| `DirectoryId-ParentName` | main.ps1:3063 | Derives the parent directory's name by calling `Split-Path` then `DirectoryId-GetName`. Returns `$null` for root-level directories | Top-level internal |
| `DirectoryId-ResolvePath` | main.ps1:3086 | Resolves a path to its absolute form using `Resolve-Path` with a `[System.IO.Path]::GetFullPath()` fallback for hypothetical paths | Top-level internal |

---

## 6. Internal Logic Summary

**ID Generation Algorithm:**

The directory ID is computed by a two-layer hashing scheme:

1. Hash the directory's own name → `DirectoryNameHash`
2. Hash the parent directory's name → `ParentNameHash`
3. Concatenate both hash strings → `CombinedParts`
4. Hash the concatenated string → Final `Id`

This is performed independently for each of four hash algorithms (MD5, SHA1, SHA256, SHA512), producing four distinct IDs.

The final IDs are prefixed with `"x"` to distinguish directory IDs from file IDs (which use the `"y"` prefix in the companion function `FileId`).

**Null Hash Handling:**

When a directory is at the root of a filesystem (and thus has no parent name), the hash of an empty string is used for the parent component. The known null-hash constants for each algorithm are hardcoded in the sub-functions:

| Algorithm | Null Hash |
|---|---|
| MD5 | `D41D8CD98F00B204E9800998ECF8427E` |
| SHA1 | `DA39A3EE5E6B4B0D3255BFEF95601890AFD80709` |
| SHA256 | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| SHA512 | `CF83E1357EEFB8BDF1542850D66D8007D620E4050B5715DC83F4A921D36CE9CE47D0D13C5D85F2B0FF8318D2877EEC2F63B931BD47417A81A538327AF927DA3E` |

---

## 7. Output Object Properties

The full `[PSCustomObject]` (returned when `-OutputObject` is used) contains:

| Property | Type | Description |
|---|---|---|
| `IsDirectory` | `[Boolean]` | Always `$true` for valid directory inputs |
| `IsFile` | `[Boolean]` | Always `$false` (inverse of `IsDirectory`) |
| `IsLink` | `[Boolean]` | Always hardcoded to `$false` (symlink detection is not performed in this function) |
| `DirectoryName` | `[String]` | The leaf name of the directory |
| `DirectoryNameMD5` | `[String]` | MD5 hash of the directory name |
| `DirectoryNameSHA1` | `[String]` | SHA1 hash of the directory name |
| `DirectoryNameSHA256` | `[String]` | SHA256 hash of the directory name |
| `DirectoryNameSHA512` | `[String]` | SHA512 hash of the directory name |
| `ParentName` | `[String]` | The leaf name of the parent directory |
| `ParentNameMD5` | `[String]` | MD5 hash of the parent name |
| `ParentNameSHA1` | `[String]` | SHA1 hash of the parent name |
| `ParentNameSHA256` | `[String]` | SHA256 hash of the parent name |
| `ParentNameSHA512` | `[String]` | SHA512 hash of the parent name |
| `IdMD5` | `[String]` | Final directory ID (MD5), prefixed with `"x"` |
| `IdSHA1` | `[String]` | Final directory ID (SHA1), prefixed with `"x"` |
| `IdSHA256` | `[String]` | Final directory ID (SHA256), prefixed with `"x"` |
| `IdSHA512` | `[String]` | Final directory ID (SHA512), prefixed with `"x"` |

---

## 8. .NET Types and Methods Used

| Type / Method | Usage |
|---|---|
| `[System.IO.Path]::GetFileName()` | Extracting directory leaf name |
| `[System.IO.Path]::GetFullPath()` | Resolving hypothetical paths |
| `[System.Security.Cryptography.MD5]::Create()` | MD5 hash computation |
| `[System.Security.Cryptography.SHA1]::Create()` | SHA1 hash computation |
| `[System.Security.Cryptography.SHA256]::Create()` | SHA256 hash computation |
| `[System.Security.Cryptography.SHA512]::Create()` | SHA512 hash computation |
| `[System.Text.Encoding]::UTF8.GetBytes()` | String → byte-array conversion for hashing |
| `[BitConverter]::ToString()` | Byte-array → hex-string conversion |
| `[PSCustomObject]@{}` | Output object construction |

---

## 9. PowerShell Built-in Cmdlets Used

| Cmdlet | Usage Context |
|---|---|
| `ConvertTo-Json` | Serializing output object when `-OutputJson` is specified (`-Depth 100`) |
| `Resolve-Path` | Resolving directory paths to absolute form (`-LiteralPath`) |
| `Select-Object` | Extracting `$PWD` path (`-Expand Path`) |
| `Split-Path` | Extracting parent directory path (`-LiteralPath`) |
| `Test-Path` | Validating directory existence (`-LiteralPath`, `-PathType Container`) |

---

## 10. Return Value

Default (no output switches): Returns a `[System.String]` containing the SHA256-based directory ID (prefixed with `"x"`).

With `-OutputObject`: Returns the full `[PSCustomObject]` described in Section 7.

With `-OutputJson`: Returns a JSON-formatted string of the full result object.

Returns `$null` if the input directory is missing or does not exist.

---

## 11. Call Graph

```
DirectoryId
├── [resolves -Here or -Directory input]
│   └── Vbs ◄── external pslib (on missing/invalid directory)
├── DirectoryId-ResolvePath
│   └── Vbs ◄── external pslib (on empty input)
├── DirectoryId-GetName (directory name)
├── DirectoryId-HashString (×4 algorithms, directory name)
│   ├── DirectoryId-HashString-Md5
│   ├── DirectoryId-HashString-Sha1
│   ├── DirectoryId-HashString-Sha256
│   └── DirectoryId-HashString-Sha512
├── DirectoryId-ParentName
│   ├── Split-Path
│   └── DirectoryId-GetName (parent name)
├── DirectoryId-HashString (×4 algorithms, parent name)
├── [concatenate directory + parent hashes]
├── DirectoryId-HashString (×4 algorithms, concatenated parts → final IDs)
└── [format output based on switches]
```
