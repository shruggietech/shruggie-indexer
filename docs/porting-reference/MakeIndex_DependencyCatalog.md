# MakeIndex — Dependency Catalog

> **Source:** `main.ps1`, line 7531  
> **Purpose:** Generates JSON-formatted nested indexes of files and directories with metadata  
> **Audience:** AI-first, Human-second  

---

## 1. External PsLib Functions Called

These functions are defined at the top level of `main.ps1` (outside of MakeIndex) and are called from within MakeIndex or its nested sub-functions.

| Function | Defined At | Called From (within MakeIndex) | Purpose |
|---|---|---|---|
| `Base64DecodeString` | main.ps1:764 | `GetFileExif` → `GetFileExifArgsWrite` | Decodes Base64-encoded exiftool argument strings (with URL-decode and UTF8 encoding support) |
| `Date2UnixTime` | main.ps1:2517 | `MakeObject` | Converts formatted date strings to Unix timestamps |
| `DirectoryId` | main.ps1:2819 | `MakeObject` | Generates unique identifiers (MD5, SHA256) for directories based on directory name hashing. Returns an object with `.IdMD5`, `.IdSHA256`, `.DirectoryName`, `.DirectoryNameMD5`, `.DirectoryNameSHA256`, `.IsLink` properties |
| `FileId` | main.ps1:4941 | `MakeObject` | Generates unique identifiers (MD5, SHA256) for files based on content hashing. Returns an object with `.IdMD5`, `.IdSHA256`, `.ContentMD5`, `.ContentSHA256`, `.NameMD5`, `.NameSHA256`, `.IsLink` properties |
| `MetaFileRead` | main.ps1:10233 | `ReadMetaFile` | Reads and parses external metadata files (sidecar files). Accepts `-InputFile`, `-Format "object"`, `-ProgressString`, `-Verbosity`. Returns an object with `.Type`, `.Data`, `.Name` properties |
| `TempOpen` | main.ps1:15119 | `GetFileExif` | Creates a temporary file and returns its path. Called with `-Type 'txt'` |
| `TempClose` | main.ps1:15044 | `GetFileExif` | Deletes a temporary file. Called with `-Target <path>` |
| `Vbs` | main.ps1:16412 | Throughout (all sub-functions) | Verbose/logging output handler. Called with `-Caller`, `-Status` (i/d/w/e), `-Message`, `-Verbosity` |

### Listed but Not Directly Called

| Function | Notes |
|---|---|
| `ValidateIsLink` | Listed in the MakeIndex docstring under "Function Dependencies" but **never directly invoked** within MakeIndex code. The `.IsLink` property is obtained indirectly via the return objects of `DirectoryId` and `FileId`, which likely call `ValidateIsLink` internally. |

---

## 2. External Variables Loaded

These variables are defined at the script level of `main.ps1` (in the variable declarations section, lines ~17383–17441) and are accessed by MakeIndex through scope inheritance or the `$global:` prefix.

| Variable | Defined At | Type | Description |
|---|---|---|---|
| `$global:MetadataFileParser` | main.ps1:16977 | `[ordered]@{}` (Hashtable) | Large configuration object governing metadata file parsing behavior. MakeIndex consumes the following sub-properties:<br>`.Exiftool.Exclude` — Array of file extensions to skip for exiftool processing<br>`.Indexer.Include` — Array of regex patterns identifying metadata sidecar file suffixes<br>`.Indexer.IncludeString` — Joined regex string of the Include array<br>`.Indexer.Exclude` — Array of regex patterns for metadata files to exclude<br>`.Indexer.ExcludeString` — Joined regex string of the Exclude array<br>`.Identify.<Key>` — Sub-objects mapping metadata file types to their regex patterns (used by `MetaFileRead` downstream) |
| `$Sep` | main.ps1:17383 | `[System.Char]` | Directory separator character (`[System.IO.Path]::DirectorySeparatorChar`). Used when constructing renamed file paths in `MakeDirectoryIndexLogic`, `MakeDirectoryIndexRecursiveLogic`, and `MakeFileIndex` |

### Global Variables Created/Managed at Runtime

MakeIndex promotes several local parameter values to global scope for access by deeply nested sub-functions, then cleans them up at the end of execution:

| Variable | Lifecycle | Purpose |
|---|---|---|
| `$global:ExiftoolRejectList` | Created at start, removed at end | Copy of `$MetadataFileParser.Exiftool.Exclude` |
| `$global:MetaSuffixInclude` | Created at start, removed at end | Copy of `$MetadataFileParser.Indexer.Include` |
| `$global:MetaSuffixIncludeString` | Created at start, removed at end | Copy of `$MetadataFileParser.Indexer.IncludeString` |
| `$global:MetaSuffixExclude` | Created at start, removed at end | Copy of `$MetadataFileParser.Indexer.Exclude` |
| `$global:MetaSuffixExcludeString` | Created at start, removed at end | Copy of `$MetadataFileParser.Indexer.ExcludeString` |
| `$global:DeleteQueue` | Created at start (`@()`), removed at end | Accumulates file paths of metadata sidecar files to delete when `-MetaMergeDelete` is active |

---

## 3. External Binaries / Executables Invoked

| Binary | Called From (within MakeIndex) | How Invoked | Purpose |
|---|---|---|---|
| `exiftool` | `GetFileExif` → `GetFileExifRun` | `exiftool -@ "$ArgsFile" 2> $null` — Invoked via bare command name (must be in system PATH). Receives arguments from a temporary file written by `GetFileExifArgsWrite`. | Extracts EXIF/metadata from files. Arguments include: `-extractEmbedded3`, `-scanForXMP`, `-unknown2`, `-json`, `-G3:1`, `-struct`, `-ignoreMinorErrors`, `-charset filename=utf8`, `-api requestall=3`, `-api largefilesupport=1` (plus `-quiet` when verbosity is off) |
| `jq` | `GetFileExif` → `GetFileExifRun` | `$ExiftoolOutput \| jq -c '.[] \| .' 2> $null` and a second pass with `jq -c 'del(…)'` to strip unwanted keys | Parses and filters JSON output from exiftool. Removes system/exiftool metadata keys (ExifToolVersion, FileSequence, NewGUID, Directory, FileName, FilePath, BaseName, FilePermissions, etc.) |

### Note on Binary Resolution

Neither `exiftool` nor `jq` are referenced via absolute paths. Both must be available in the system `PATH` environment variable at runtime. The MakeIndex docstring explicitly states: *"exiftool must be installed and available in the system PATH. This function will not work without it."* The `jq` dependency is implicit (not mentioned in the docstring) but is equally required for metadata extraction to work.

---

## 4. Internal Sub-Functions (Defined Within MakeIndex)

For completeness and call-chain tracing, these are the functions defined *inside* the MakeIndex function body. They are not accessible outside of MakeIndex.

### Top-Level Internal Functions

| Function | Purpose | Calls (internal) | Calls (external PsLib) |
|---|---|---|---|
| `GetFileEncoding` | Detects file encoding via BOM byte inspection | — | — |
| `GetFileExif` | Orchestrates exiftool execution for a single file | `GetFileExifArgsWrite`, `GetFileExifRun`, `UpdateFunctionStack` | `Base64DecodeString`, `TempOpen`, `TempClose`, `Vbs` |
| `GetFileMetaSiblings` | Finds sibling metadata files matching a given file's basename | `GetParentPath`, `UpdateFunctionStack` | `Vbs` |
| `GetParentPath` | Extracts parent directory path from a full path string | — | — |
| `MakeDirectoryIndex` | Entry point for non-recursive directory indexing | `MakeDirectoryIndexLogic`, `UpdateFunctionStack` | `Vbs` |
| `MakeDirectoryIndexRecursive` | Entry point for recursive directory indexing | `MakeDirectoryIndexRecursiveLogic`, `UpdateFunctionStack` | `Vbs` |
| `MakeFileIndex` | Entry point for single-file indexing | `MakeObject`, `GetParentPath`, `UpdateFunctionStack` | `Vbs` |
| `MakeObject` | Core object builder — constructs the PSCustomObject for any file or directory | `GetFileEncoding`, `GetFileExif`, `GetFileMetaSiblings`, `GetParentPath`, `ReadMetaFile`, `VariableStringify`, `UpdateFunctionStack` | `Date2UnixTime`, `DirectoryId`, `FileId`, `Vbs` |
| `ReadMetaFile` | Reads a metadata sidecar file and wraps it in a standard object | `ReadMetaFile-GetNameHashMD5`, `ReadMetaFile-GetNameHashSHA256`, `UpdateFunctionStack` | `MetaFileRead`, `Vbs` |
| `ResolvePath` | Resolves real or hypothetical filesystem paths | `UpdateFunctionStack` | `Vbs` |
| `UpdateFunctionStack` | Maintains a colon-delimited call-stack string for logging | — | — |
| `VariableStringify` | Converts variables to string representations (handles null/empty) | — | — |

### Nested Internal Functions (defined inside other internal functions)

| Function | Parent Function | Purpose |
|---|---|---|
| `GetFileExifArgsWrite` | `GetFileExif` | Writes decoded exiftool argument strings to a temp file |
| `GetFileExifRun` | `GetFileExif` | Executes `exiftool` and pipes output through `jq` |
| `MakeDirectoryIndexLogic` | `MakeDirectoryIndex` | Core non-recursive directory traversal and object assembly |
| `MakeDirectoryIndexRecursiveLogic` | `MakeDirectoryIndexRecursive` | Core recursive directory traversal and object assembly (calls itself recursively for child directories) |
| `ReadMetaFile-GetNameHashMD5` | `ReadMetaFile` | Computes MD5 hash of a filename string |
| `ReadMetaFile-GetNameHashSHA256` | `ReadMetaFile` | Computes SHA256 hash of a filename string |

---

## 5. PowerShell Built-in Cmdlets and .NET Types Used

For porting reference, MakeIndex relies on these PowerShell cmdlets and .NET framework types.

### Cmdlets

| Cmdlet | Usage Context |
|---|---|
| `Add-Content` | Appending filename to exiftool args file |
| `ConvertFrom-Json` | Parsing exiftool JSON output (`-AsHashtable`) |
| `ConvertTo-Json` | Serializing output objects (`-Depth 100`) |
| `Get-ChildItem` | Directory listing (with `-Force`, `-File`, `-Recurse`, `-LiteralPath`) |
| `Get-Help` | (not directly, but pattern exists in other functions) |
| `Get-Item` | File/directory info retrieval (`-Force`, `-LiteralPath`) |
| `Measure-Object` | Directory size calculation (`-Property Length -Sum`) |
| `Move-Item` | File renaming (`-LiteralPath`, `-Destination`, `-Force`) |
| `Out-File` | Writing final JSON output (`-Encoding UTF8`) |
| `Out-Null` | Suppressing output from `Remove-Item` |
| `Remove-Item` | Deleting metadata files from DeleteQueue (`-LiteralPath`, `-Force`) |
| `Remove-Variable` | Cleaning up global variables at end of execution |
| `Resolve-Path` | Path resolution (`-LiteralPath`) |
| `Select-Object` | Property selection and exclusion |
| `Set-Content` | Writing in-place metadata JSON files (`-LiteralPath`, `-Force`) |
| `Set-Location` | Changing working directory for exiftool and directory traversal |
| `Split-Path` | Extracting parent path |
| `Test-Path` | Validating file/directory existence (`-LiteralPath`, `-PathType Leaf/Container`) |
| `Where-Object` | Filtering child items (excluding `$RECYCLE.BIN`, `System Volume Information`; separating files from directories) |

### .NET Types and Methods

| Type / Method | Usage |
|---|---|
| `[math]::Round()` | Progress percentage calculation |
| `[System.Collections.ArrayList]` | Combining file and directory child item arrays |
| `[System.IO.FileStream]` | BOM-based encoding detection |
| `[System.IO.Path]::GetFileName()` | Extracting filename from full path |
| `[System.IO.Path]::GetFileNameWithoutExtension()` | Extracting basename |
| `[System.IO.Path]::GetFullPath()` | Resolving hypothetical paths |
| `[System.IO.Path]::GetDirectoryName()` | Extracting directory from file path |
| `[System.Security.Cryptography.MD5]::Create()` | MD5 hashing (in ReadMetaFile sub-functions) |
| `[System.Security.Cryptography.SHA256]::Create()` | SHA256 hashing (in ReadMetaFile sub-functions) |
| `[System.Text.Encoding]::UTF8` | Encoding for hash computation |
| `[System.Text.RegularExpressions.Regex]::Escape()` | Escaping basename for regex matching |
| `[BitConverter]::ToString()` | Converting hash bytes to hex string |
| `[DateTimeOffset]::Now.ToUnixTimeMilliseconds()` | Session ID generation |
| `[PSCustomObject]@{}` | All output object construction |
| `[Text.Encoding]::ASCII/UTF7/Unicode/BigEndianUnicode/UTF32/UTF8` | Encoding type constants for BOM detection |

---

## 6. Summary Call Graph

```
MakeIndex
├── [validates inputs, resolves paths, sets up globals]
├── ResolvePath → Vbs
├── GetParentPath
│
├── (TargetTyp=0) MakeDirectoryIndexRecursive → Vbs
│   └── MakeDirectoryIndexRecursiveLogic (recursive)
│       ├── MakeObject ──────────────────────────────┐
│       │   ├── VariableStringify                    │
│       │   ├── GetParentPath                        │
│       │   ├── DirectoryId ◄────── external pslib   │
│       │   ├── FileId ◄────────── external pslib    │
│       │   ├── Date2UnixTime ◄──── external pslib   │
│       │   ├── GetFileEncoding                      │
│       │   ├── GetFileExif                          │
│       │   │   ├── Base64DecodeString ◄── ext pslib │
│       │   │   ├── TempOpen ◄──────────── ext pslib │
│       │   │   ├── TempClose ◄─────────── ext pslib │
│       │   │   ├── [exiftool] ◄────────── BINARY    │
│       │   │   └── [jq] ◄─────────────── BINARY     │
│       │   ├── GetFileMetaSiblings                  │
│       │   ├── ReadMetaFile                         │
│       │   │   ├── MetaFileRead ◄──── external pslib│
│       │   │   ├── ReadMetaFile-GetNameHashMD5      │
│       │   │   └── ReadMetaFile-GetNameHashSHA256   │
│       │   └── Vbs ◄──────────── external pslib     │
│       └── MakeDirectoryIndexRecursiveLogic (self)  │
│                                                    │
├── (TargetTyp=1) MakeFileIndex → Vbs                │
│   └── MakeObject ──────────────────────────────────┘
│
├── (TargetTyp=2) MakeDirectoryIndex → Vbs
│   └── MakeDirectoryIndexLogic
│       └── MakeObject (same as above)
│
├── [DeleteQueue processing]
├── [Global variable cleanup via Remove-Variable]
├── [OutFile via ConvertTo-Json | Out-File]
└── [StandardOutput via ConvertTo-Json]
```
