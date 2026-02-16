# Shruggie-Indexer — Technical Specification

## 1. Document Information

### 1.1. Purpose and Audience

### 1.2. Scope

### 1.3. Versioning and Revision History

### 1.4. Conventions Used in This Document

### 1.5. Reference Documents

## 2. Project Overview

### 2.1. Project Identity

### 2.2. Relationship to the Original Implementation

### 2.3. Design Goals and Non-Goals

### 2.4. Platform and Runtime Requirements

### 2.5. Python Version Requirements

### 2.6. Intentional Deviations from the Original

## 3. Repository Structure

### 3.1. Top-Level Layout

### 3.2. Source Package Layout

### 3.3. Configuration File Locations

### 3.4. Test Directory Layout

### 3.5. Scripts and Build Tooling

### 3.6. Documentation Artifacts

## 4. Architecture

### 4.1. High-Level Processing Pipeline

### 4.2. Module Decomposition

### 4.3. Data Flow

### 4.4. State Management

### 4.5. Error Handling Strategy

### 4.6. Entry Point Routing

## 5. Output Schema

### 5.1. Schema Overview

### 5.2. Top-Level IndexEntry Fields

### 5.3. Identity Fields

### 5.4. Filesystem Metadata Fields

### 5.5. Relationship Fields

### 5.6. Timestamp Fields

### 5.7. Recursive Items Field

### 5.8. Metadata Array and MetadataEntry Fields

### 5.9. Dropped Fields

### 5.10. Schema Validation and Enforcement

### 5.11. Backward Compatibility Considerations

## 6. Core Operations

### 6.1. Filesystem Traversal and Discovery

### 6.2. Path Resolution and Manipulation

### 6.3. Hashing and Identity Generation

### 6.4. Symlink Detection

### 6.5. Filesystem Timestamps and Date Conversion

### 6.6. EXIF and Embedded Metadata Extraction

### 6.7. Sidecar Metadata File Handling

### 6.8. Index Entry Construction

### 6.9. JSON Serialization and Output Routing

### 6.10. File Rename and In-Place Write Operations

## 7. Configuration

### 7.1. Configuration Architecture

### 7.2. Default Configuration

### 7.3. Metadata File Parser Configuration

### 7.4. Exiftool Exclusion Lists

### 7.5. Sidecar Suffix Patterns and Type Identification

### 7.6. Configuration File Format

### 7.7. Configuration Override and Merging Behavior

## 8. CLI Interface

### 8.1. Command Structure

### 8.2. Target Input Options

### 8.3. Output Mode Options

### 8.4. Metadata Processing Options

### 8.5. Rename Option

### 8.6. ID Type Selection

### 8.7. Verbosity and Logging Options

### 8.8. Mutual Exclusion Rules and Validation

### 8.9. Output Scenarios

### 8.10. Exit Codes

## 9. Python API

### 9.1. Public API Surface

### 9.2. Core Functions

### 9.3. Configuration API

### 9.4. Data Classes and Type Definitions

### 9.5. Programmatic Usage Examples

## 10. Logging and Diagnostics

### 10.1. Logging Architecture

### 10.2. Logger Naming Hierarchy

### 10.3. Log Levels and CLI Flag Mapping

### 10.4. Session Identifiers

### 10.5. Log Output Destinations

### 10.6. Progress Reporting

## 11. External Dependencies

### 11.1. Required External Binaries

### 11.2. Python Standard Library Modules

### 11.3. Third-Party Python Packages

### 11.4. Eliminated Original Dependencies

### 11.5. Dependency Verification at Runtime

## 12. Packaging and Distribution

### 12.1. Package Metadata

### 12.2. pyproject.toml Configuration

### 12.3. Entry Points and Console Scripts

### 12.4. Standalone Executable Builds

### 12.5. Release Artifact Inventory

### 12.6. Version Management

## 13. Testing

### 13.1. Testing Strategy

### 13.2. Unit Test Coverage

### 13.3. Integration Tests

### 13.4. Output Schema Conformance Tests

### 13.5. Cross-Platform Test Matrix

### 13.6. Backward Compatibility Validation

### 13.7. Performance Benchmarks

## 14. Platform Portability

### 14.1. Cross-Platform Design Principles

### 14.2. Windows-Specific Considerations

### 14.3. Linux and macOS Considerations

### 14.4. Filesystem Behavior Differences

### 14.5. Creation Time Portability

### 14.6. Symlink and Reparse Point Handling

## 15. Security and Safety

### 15.1. Symlink Traversal Safety

### 15.2. Path Validation and Sanitization

### 15.3. Temporary File Handling

### 15.4. Metadata Merge-Delete Safeguards

### 15.5. Large File and Deep Recursion Handling

## 16. Performance Considerations

### 16.1. Multi-Algorithm Hashing in a Single Pass

### 16.2. Chunked File Reading

### 16.3. Large Directory Tree Handling

### 16.4. JSON Serialization for Large Output Trees

### 16.5. Exiftool Invocation Strategy

## 17. Future Considerations

### 17.1. Potential Feature Additions

### 17.2. Schema Evolution

### 17.3. Plugin or Extension Architecture
