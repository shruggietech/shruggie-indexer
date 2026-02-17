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

### 5.2. Reusable Type Definitions

#### 5.2.1. HashSet

#### 5.2.2. NameObject

#### 5.2.3. SizeObject

#### 5.2.4. TimestampPair

#### 5.2.5. TimestampsObject

#### 5.2.6. ParentObject

### 5.3. Top-Level IndexEntry Fields

### 5.4. Identity Fields

### 5.5. Naming and Content Fields

### 5.6. Filesystem Location and Hierarchy Fields

### 5.7. Timestamp Fields

### 5.8. Attribute Fields

### 5.9. Recursive Items Field

### 5.10. Metadata Array and MetadataEntry Fields

### 5.11. Dropped and Restructured Fields

### 5.12. Schema Validation and Enforcement

### 5.13. Backward Compatibility Considerations

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

## 10. GUI Application

### 10.1. GUI Framework and Architecture

### 10.2. Window Layout

### 10.3. Target Selection and Input

### 10.4. Configuration Panel

### 10.5. Indexing Execution and Progress

### 10.6. Output Display and Export

### 10.7. Keyboard Shortcuts and Accessibility

## 11. Logging and Diagnostics

### 11.1. Logging Architecture

### 11.2. Logger Naming Hierarchy

### 11.3. Log Levels and CLI Flag Mapping

### 11.4. Session Identifiers

### 11.5. Log Output Destinations

### 11.6. Progress Reporting

## 12. External Dependencies

### 12.1. Required External Binaries

### 12.2. Python Standard Library Modules

### 12.3. Third-Party Python Packages

### 12.4. Eliminated Original Dependencies

### 12.5. Dependency Verification at Runtime

## 13. Packaging and Distribution

### 13.1. Package Metadata

### 13.2. pyproject.toml Configuration

### 13.3. Entry Points and Console Scripts

### 13.4. Standalone Executable Builds

### 13.5. Release Artifact Inventory

### 13.6. Version Management

## 14. Testing

### 14.1. Testing Strategy

### 14.2. Unit Test Coverage

### 14.3. Integration Tests

### 14.4. Output Schema Conformance Tests

### 14.5. Cross-Platform Test Matrix

### 14.6. Backward Compatibility Validation

### 14.7. Performance Benchmarks

## 15. Platform Portability

### 15.1. Cross-Platform Design Principles

### 15.2. Windows-Specific Considerations

### 15.3. Linux and macOS Considerations

### 15.4. Filesystem Behavior Differences

### 15.5. Creation Time Portability

### 15.6. Symlink and Reparse Point Handling

## 16. Security and Safety

### 16.1. Symlink Traversal Safety

### 16.2. Path Validation and Sanitization

### 16.3. Temporary File Handling

### 16.4. Metadata Merge-Delete Safeguards

### 16.5. Large File and Deep Recursion Handling

## 17. Performance Considerations

### 17.1. Multi-Algorithm Hashing in a Single Pass

### 17.2. Chunked File Reading

### 17.3. Large Directory Tree Handling

### 17.4. JSON Serialization for Large Output Trees

### 17.5. Exiftool Invocation Strategy

## 18. Future Considerations

### 18.1. Potential Feature Additions

### 18.2. Schema Evolution

### 18.3. Plugin or Extension Architecture
