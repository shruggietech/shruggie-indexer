# Configuration

!!! note "Work in Progress"
    This page will be populated as the configuration system stabilizes. For the full configuration specification, see [§7 of the technical specification](https://github.com/shruggietech/shruggie-indexer/blob/main/shruggie-indexer-spec.md).

## Configuration File

`shruggie-indexer` reads configuration from a TOML file. The configuration file is optional — sensible defaults are built into the tool.

## Configuration Hierarchy

Configuration values are resolved in the following order (highest priority first):

1. CLI flags / API arguments
2. User configuration file
3. Built-in defaults

## Topics

Detailed configuration documentation will cover:

- File format and location
- Default values for all settings
- Metadata file parser patterns
- Exiftool exclusion lists
- Sidecar suffix patterns and type identification
- Override and merging behavior
