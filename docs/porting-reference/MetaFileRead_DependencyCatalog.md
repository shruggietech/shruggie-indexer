# MetaFileRead — Dependency Catalog

> **Source:** `main.ps1`, line 10233  
> **Purpose:** Reads and parses metadata sidecar files, determining their type, associated parent file, and internal data content  
> **Audience:** AI-first, Human-second  

---

## 1. External PsLib Functions Called

| Function | Defined At | Called From | Purpose |
|---|---|---|---|
| `Lnk2Path` | main.ps1:7283 | `MetaFileRead-Data-ReadLink` | Resolves a `.lnk` shortcut file to its target path |
| `UrlFile2Url` | main.ps1:15843 | `MetaFileRead-Data-ReadLink` | Extracts the URL from a `.url` internet shortcut file |
| `ValidateIsFile` | main.ps1:16098 | Top-level body | Validates that the input string references an existing file. Returns a boolean |
| `ValidateIsJson` | main.ps1:16189 | `MetaFileRead-Data` | Validates whether a file contains valid JSON. Returns a boolean |
| `Vbs` | main.ps1:16412 | Throughout (via `VbsFormatter` wrapper) | Verbose/logging output handler. Called indirectly through the internal `VbsFormatter` wrapper, which auto-formats messages with progress strings when available |

### Implicit External Dependency: `$global:MetadataFileParser`

This function receives the `$global:MetadataFileParser` configuration object as both a parameter default and a passed-through argument to multiple sub-functions. The `MetadataFileParser` object (defined at main.ps1:16977) governs all type-detection regex patterns, file-extension classification rules, and indexer include/exclude patterns. Without this object being populated at runtime, the function cannot detect meta file types or validate input files.

---

## 2. External Variables Loaded

| Variable | Defined At | Type | Description |
|---|---|---|---|
| `$global:MetadataFileParser` | main.ps1:16977 | `[ordered]@{}` (Hashtable) | Large configuration object governing metadata file parsing behavior. Consumed sub-properties include:<br>`.Indexer.IncludeString` — Regex string used to validate that the input file qualifies as a metadata file<br>`.Identify.<Key>` — Sub-objects mapping metadata file types (Description, GenericMetadata, Hash, JsonMetadata, Link, Screenshot, Subtitles, Thumbnail, Torrent) to their regex detection patterns |

---

## 3. External Binaries / Executables Invoked

| Binary | Called From (within MetaFileRead) | How Invoked | Purpose |
|---|---|---|---|
| `certutil` | `MetaFileRead-Data-Base64Encode` | `certutil -encode "$FilePath" "$TempFile" > $null` | Encodes binary file data to Base64 (used for Screenshot, Thumbnail, Torrent, and binary fallback data) |
| `jq` | `MetaFileRead-Data-ReadJson` | `jq -c '.' "$FilePath" 2> $null` | Reads and compacts JSON data from metadata files. Output is piped through `ConvertFrom-Json` |

### Note on Binary Resolution

Neither `certutil` nor `jq` are referenced via absolute paths. `certutil` is a Windows system utility and is expected to be available in the system PATH. `jq` must also be available in the system PATH. The `jq` dependency is shared with the `MakeIndex` function which also uses `jq` for JSON processing.

---

## 4. Parameters

| Parameter | Type | Alias(es) | Default | Description |
|---|---|---|---|---|
| `File` | `[System.String]` | `inputfile` | *(none)* | The absolute path to the metadata file to read |
| `Format` | `[System.String]` | *(none)* | `'json'` | Output format. ValidatePattern: `^(json|object|text)$` |
| `ProgressString` | `[System.String]` | *(none)* | *(none)* | Optional progress prefix string prepended to verbose messages by the `VbsFormatter` wrapper |
| `Verbosity` | `[System.Boolean]` | `v` | `$false` | Controls whether verbose/log messages are printed to the console |
| `$global:MetadataFileParser` | `[System.Object]` | *(none)* | `$global:MetadataFileParser` | Internal parameter: the metadata parser configuration object passed through from the global scope |

---

## 5. Internal Sub-Functions (Defined Within MetaFileRead)

### Top-Level Internal Functions

| Function | Purpose | Calls (internal) | Calls (external) |
|---|---|---|---|
| `MetaFileRead-Data` | Dispatcher: reads the internal data of a meta file based on its detected type. Routes to type-specific reader sub-functions | `MetaFileRead-Data-Base64Encode`, `MetaFileRead-Data-IsText`, `MetaFileRead-Data-ReadBinary`, `MetaFileRead-Data-ReadJson`, `MetaFileRead-Data-ReadLink`, `MetaFileRead-Data-ReadText`, `MetaFileRead-Data-ReadText-Hash`, `MetaFileRead-Data-ReadText-Subtitles` | `ValidateIsJson`, `VbsFormatter` |
| `MetaFileRead-Detect` | Iterates through `$MetadataFileParser.Identify` keys and matches the input file name against regex patterns to determine the meta file type | — | — |
| `MetaFileRead-Parent` | Determines the parent file/directory associated with a given meta file by analyzing sibling files in the same directory | `MetaFileRead-Parent-Base`, `MetaFileRead-Parent-Keys-Orphan`, `MetaFileRead-Parent-Keys-Directory`, `MetaFileRead-Parent-Keys-File`, `MetaFileRead-Parent-List-Audio`, `MetaFileRead-Parent-List-Image`, `MetaFileRead-Parent-List-Other`, `MetaFileRead-Parent-List-Video` | `VbsFormatter` |
| `MetaFileRead-Sha256-File` | Computes SHA256 hash of a file's contents (used for the `_id` field) | — | `VbsFormatter` |
| `MetaFileRead-Sha256-String` | Computes SHA256 hash of a string (used for `NameHash` fields) | — | `VbsFormatter` |
| `MetaFileRead-Temp-Close` | Deletes a temporary file by path | — | `VbsFormatter` |
| `MetaFileRead-Temp-Open` | Creates a temporary file in `$D_PSLIB_TEMP` and returns its path. Uses UUID+timestamp naming | — | — |
| `VbsFormatter` | Internal wrapper around the external `Vbs` function. Auto-prepends the `$ProgressString` to log messages when present | — | `Vbs` |

### Nested Internal Functions (defined inside other internal functions)

| Function | Parent Function | Purpose |
|---|---|---|
| `MetaFileRead-Data-Base64Encode` | `MetaFileRead-Data` | Encodes file data to Base64 using `certutil`. Creates and cleans up a temp file |
| `MetaFileRead-Data-IsText` | `MetaFileRead-Data` | Tests whether a file contains valid text by attempting `Get-Content -Raw` in a try/catch |
| `MetaFileRead-Data-ReadBinary` | `MetaFileRead-Data` | Reads binary file data by delegating to `MetaFileRead-Data-Base64Encode` |
| `MetaFileRead-Data-ReadJson` | `MetaFileRead-Data` | Reads JSON file data using `jq -c '.'` piped through `ConvertFrom-Json` |
| `MetaFileRead-Data-ReadLink` | `MetaFileRead-Data` | Reads `.url` files via `UrlFile2Url` or `.lnk` files via `Lnk2Path` |
| `MetaFileRead-Data-ReadText` | `MetaFileRead-Data` | Reads file as UTF8 text via `[System.IO.File]::ReadAllText()` |
| `MetaFileRead-Data-ReadText-Hash` | `MetaFileRead-Data` | Reads hash files as text lines via `Get-Content`, filtering out empty lines |
| `MetaFileRead-Data-ReadText-Subtitles` | `MetaFileRead-Data` | Reads subtitle files as text lines via `Get-Content`, filtering out empty lines |
| `MetaFileRead-Parent-Base` | `MetaFileRead-Parent` | Strips the metadata suffix from the meta file name to derive the base parent file name. Uses single-pass or multi-pass regex replacement depending on the meta type |
| `MetaFileRead-Parent-Keys-Orphan` | `MetaFileRead-Parent` | Returns a PSCustomObject with orphan parent properties (Name=null, Type="orphan", Exists=$false) |
| `MetaFileRead-Parent-Keys-Directory` | `MetaFileRead-Parent` | Returns a PSCustomObject with directory parent properties |
| `MetaFileRead-Parent-Keys-File` | `MetaFileRead-Parent` | Returns a PSCustomObject with file parent properties |
| `MetaFileRead-Parent-List-Audio` | `MetaFileRead-Parent` | Filters directory matches to audio file extensions |
| `MetaFileRead-Parent-List-Image` | `MetaFileRead-Parent` | Filters directory matches to image file extensions |
| `MetaFileRead-Parent-List-Other` | `MetaFileRead-Parent` | Filters directory matches to other file extensions |
| `MetaFileRead-Parent-List-Video` | `MetaFileRead-Parent` | Filters directory matches to video file extensions |

---

## 6. Internal Logic Summary

**Processing Pipeline:**

1. **Input Validation:** The input file path is checked for non-empty string and existence via `ValidateIsFile`. The file is then matched against `$global:MetadataFileParser.Indexer.IncludeString` to confirm it qualifies as a metadata file.

2. **Type Detection:** The `MetaFileRead-Detect` function iterates through all keys in `$MetadataFileParser.Identify` and matches the file name against each type's regex pattern array. A single match is expected; zero or multiple matches produce an error and an empty output.

3. **Parent Resolution:** The `MetaFileRead-Parent` function determines which file or directory the metadata file is associated with. It strips the metadata suffix from the file name to produce a "base" string, then scans sibling entries in the same directory for matches. Matches are classified by media type (audio, image, video, other) and the parent is assigned based on the meta file type's prioritization rules (e.g., Description files prioritize video parents; Subtitles prioritize video then audio). Unmatched meta files are classified as orphans.

4. **Data Reading:** The `MetaFileRead-Data` function dispatches to a type-specific reader based on the detected meta type. Text-based types are tested with both JSON and text validation; binary types (Screenshot, Thumbnail, Torrent) are Base64-encoded via `certutil`. Link types are resolved to their target paths.

5. **Output Assembly:** The final output object is constructed with `_id` (SHA256 of file contents), `Name`, `NameHash`, `Path`, `Type`, `Parent` (sub-object), and `Data` fields. Output is formatted as JSON, object, or text based on the `-Format` parameter.

**Recognized Meta File Types:**

| Type | Data Handling |
|---|---|
| `Description` | JSON → text → binary fallback chain |
| `GenericMetadata` | JSON → text → binary fallback chain |
| `Hash` | Read as text lines (single-line expected) |
| `JsonMetadata` | Read directly as JSON via `jq` |
| `Link` | Resolve `.url` via `UrlFile2Url` or `.lnk` via `Lnk2Path` |
| `Screenshot` | Base64-encode binary data |
| `Subtitles` | JSON → text → binary fallback chain |
| `Thumbnail` | Base64-encode binary data |
| `Torrent` | Base64-encode binary data |

---

## 7. Output Object Properties

The full `[PSCustomObject]` (returned when `-Format "object"` is specified) contains:

| Property | Type | Description |
|---|---|---|
| `_id` | `[String]` | SHA256 hash of the meta file's contents |
| `Name` | `[String]` | The file name of the meta file |
| `NameHash` | `[String]` | SHA256 hash of the file name string |
| `Path` | `[String]` | Absolute path to the meta file |
| `Type` | `[String]` | The detected meta file type (e.g., `Description`, `JsonMetadata`) |
| `Parent` | `[PSCustomObject]` | Sub-object describing the associated parent. Properties: `Base`, `Name`, `NameHash`, `Path`, `Type` ("file"/"orphan"/"directory"), `Extension`, `Exists`, `PossibleMatches` |
| `Data` | `[Object]` | The parsed internal data of the meta file. Type varies: string, PSCustomObject (from JSON), array of lines, Base64 string, or `$null` |

---

## 8. .NET Types and Methods Used

| Type / Method | Usage |
|---|---|
| `[System.IO.File]::OpenRead()` | File content hashing for `_id` generation |
| `[System.IO.File]::ReadAllText()` | Reading text-based meta file contents (UTF8) |
| `[System.IO.Path]::GetDirectoryName()` | Extracting parent directory path from meta file path |
| `[System.IO.Path]::GetFileName()` | Extracting file name from path |
| `[System.Security.Cryptography.SHA256]::Create()` | SHA256 hash computation (for `_id` and `NameHash`) |
| `[System.Text.Encoding]::UTF8` | Encoding constant for string-to-bytes conversion and file reading |
| `[BitConverter]::ToString()` | Byte-array → hex-string conversion |
| `[System.GUID]::NewGuid()` | UUID generation for temp file names |
| `[DateTimeOffset]::Now.ToUnixTimeMilliseconds()` | Timestamp component in temp file names |
| `[Regex]::Escape()` | Escaping base name strings for regex matching |
| `[PSCustomObject]@{}` | Output object and parent object construction |

---

## 9. PowerShell Built-in Cmdlets Used

| Cmdlet | Usage Context |
|---|---|
| `Add-Content` | (Not directly used, but `certutil` writes to the temp file) |
| `ConvertFrom-Json` | Parsing `jq` output into PowerShell objects |
| `ConvertTo-Json` | Serializing final output when `-Format "json"` (`-Depth 100`) |
| `Get-ChildItem` | Listing directory contents to find sibling files for parent resolution (`-LiteralPath`, `-Force`) |
| `Get-Content` | Reading text-based meta file data (`-LiteralPath`, `-Encoding "UTF8"`, `-Raw`) |
| `Get-Item` | Retrieving file/directory properties (Name, Extension, FullName, PSIsContainer) (`-LiteralPath`, `-Force`) |
| `New-Item` | Creating temporary files (`-ItemType File`, `-Force`) |
| `Remove-Item` | Deleting temporary files (`-LiteralPath`, `-Force`) |
| `Resolve-Path` | Resolving file paths to absolute form (`-LiteralPath`) |
| `Select-Object` | Skipping certutil header/footer lines (`-Skip 1`, `-SkipLast 1`) |
| `Set-Content` | (Not used directly in MetaFileRead but available in the broader pipeline) |
| `Test-Path` | Validating file/directory existence (`-LiteralPath`, `-PathType Leaf/Container`) |
| `Where-Object` | Filtering empty lines from file contents; filtering directory matches by name |

---

## 10. Return Value

With `-Format "json"` (default): Returns a JSON-formatted string of the full output object.

With `-Format "object"`: Returns the `[PSCustomObject]` described in Section 7.

With `-Format "text"`: Returns only the `Type` property as a string.

Returns `$null` if the input file is empty, does not exist, or does not validate as a meta file.

Returns an empty object (`'{}'` for JSON, `[PSCustomObject]@{}` for object, `'null'` for text) if type detection fails (zero or multiple type matches).

---

## 11. Call Graph

```
MetaFileRead
├── [validates File parameter is non-empty]
│   └── VbsFormatter → Vbs ◄── external pslib
├── ValidateIsFile ◄── external pslib
├── [matches against MetadataFileParser.Indexer.IncludeString]
├── MetaFileRead-Detect (type detection via MetadataFileParser.Identify)
├── MetaFileRead-Parent (parent resolution)
│   ├── MetaFileRead-Parent-Base (strip suffix)
│   ├── Get-ChildItem (list siblings)
│   ├── MetaFileRead-Parent-List-Audio/Image/Other/Video (classify matches)
│   └── MetaFileRead-Parent-Keys-File / -Directory / -Orphan (build parent object)
│       └── MetaFileRead-Sha256-String (hash parent name)
├── MetaFileRead-Data (data reading)
│   ├── ValidateIsJson ◄── external pslib
│   ├── MetaFileRead-Data-IsText
│   ├── MetaFileRead-Data-ReadJson → jq ◄── BINARY
│   ├── MetaFileRead-Data-ReadText
│   ├── MetaFileRead-Data-ReadText-Hash
│   ├── MetaFileRead-Data-ReadText-Subtitles
│   ├── MetaFileRead-Data-ReadBinary
│   │   └── MetaFileRead-Data-Base64Encode → certutil ◄── BINARY
│   │       ├── MetaFileRead-Temp-Open
│   │       └── MetaFileRead-Temp-Close
│   └── MetaFileRead-Data-ReadLink
│       ├── UrlFile2Url ◄── external pslib
│       └── Lnk2Path ◄── external pslib
├── MetaFileRead-Sha256-String (hash file name → NameHash)
├── MetaFileRead-Sha256-File (hash file contents → _id)
└── [format output based on -Format parameter]
```
