# Research Workspace v0.1 Foundation Design

**Date:** 2026-07-15  
**Status:** Approved design, pending written-spec review  
**Target:** Windows 10/11 local desktop application with a future closed-source commercial distribution path

## 1. Objective

Build the first independently runnable foundation of Research Workspace. Version `v0.1-foundation` establishes the desktop shell, architectural boundaries, database and migration baseline, local configuration, logging, sample data, and page navigation. It intentionally does not implement real document ingestion, version comparison, or AI context recovery.

This release must make later deterministic and AI features additive rather than forcing a rewrite of the UI, persistence layer, or application boundaries.

## 2. Delivery Sequence

The product is split into three independently testable releases.

### v0.1-foundation

- Install and pin Python 3.12 in a project-owned virtual environment.
- Initialize project metadata, tests, dependency lock, and third-party license inventory.
- Establish Presentation, Application, Domain, Infrastructure, and Shared boundaries.
- Implement the main window and Overview, Papers, Ideas, Submissions, Settings, Conference, and Grant navigation destinations.
- Display Conference and Grant as Coming Soon pages.
- Initialize SQLite through SQLAlchemy and Alembic.
- Add idempotent sample data, unified logging, and configurable data-directory selection.

### v0.2-deterministic

- Add document parsing through a MarkItDown adapter.
- Add read-only import, fingerprints, duplicate detection, version candidates, and incremental file monitoring.
- Add Paper, Idea, and Submission write use cases, version summaries, auditing, undo, export, and backup.

### v0.3-context-recovery

- Add MockProvider and structured LLM provider contracts.
- Add evidence bundles, fixed-schema recovery cards, candidate confirmation, and scheduled organization.
- Add optional real model providers.
- Offer Docling and sqlite-vec as optional enhanced parsing and retrieval packages.

Each release must launch independently, pass its own acceptance suite, and document startup steps and known limitations.

## 3. Open-Source Reuse and Commercial Boundary

The implementation uses composition rather than forking an existing research manager.

Approved reuse direction:

- PySide6 for the native desktop UI.
- SQLAlchemy and Alembic for persistence and schema migrations.
- MarkItDown as the future default lightweight document-conversion adapter.
- watchdog as the future Windows file-event adapter.
- Docling as a future optional enhanced parser, isolated behind `DocumentParser`.
- sqlite-vec as a future optional search implementation, isolated behind `SearchProvider`.

GPL and AGPL projects, including Paperlib, Open Paper, Zotero application code, and PyQt-Fluent-Widgets, may inform product research but must not be copied, linked, bundled, or adapted into the commercial codebase. Dependencies intended for distribution must use a commercial-compatible permissive license or an explicitly reviewed dynamic-linking arrangement. The repository will generate and retain a third-party license inventory.

Qt/PySide distribution obligations and all installer dependencies must receive a release-time compliance review. This design is an engineering boundary, not a substitute for legal advice.

## 4. Architecture

The application follows the boundaries already established by `docs/ARCHITECTURE.md`.

```text
app.py
  -> composition root and startup error boundary
  -> application services
      -> domain objects and rules
      -> infrastructure implementations
  -> presentation controllers and pages
```

### Presentation

Owns Qt widgets, UI loading, navigation, view models, and translation of user actions into application calls. It must not issue SQL, open model SDKs, or contain domain transitions.

### Application

Owns use-case orchestration. The foundation release includes overview queries, application initialization, settings changes, and sample-data initialization.

### Domain

Owns entity definitions, enums, relation rules, and state invariants. It has no dependency on Qt, SQLAlchemy, filesystem APIs, or provider SDKs.

### Infrastructure

Owns SQLite sessions and repositories, Alembic migration integration, JSON configuration, filesystem path validation, and logging configuration.

### Shared

Owns the generic `Result` type, application error codes, ID/time helpers, and cross-layer value types that have no UI or persistence dependency.

`app.py` remains a composition root. Business behavior must not accumulate in the entry point.

## 5. UI Composition

The main window contains a stable navigation shell and one component per page:

```text
MainWindow
├─ OverviewPage
├─ PapersPage
├─ IdeasPage
├─ SubmissionsPage
├─ ComingSoonPage("会议")
├─ ComingSoonPage("基金")
└─ SettingsPage
```

The existing visual direction, design tokens, and Chinese-first copy remain authoritative. Long-lived layouts stay in `.ui` files and are loaded through `QUiLoader`; Python controllers bind behavior without reproducing the layout imperatively. The existing overview prototype will be decomposed into a navigation shell and an overview page rather than converted into one large generated Python file.

The first release uses real query results backed by idempotent sample data. Hard-coded display data in the current prototype is replaced with view-model values.

## 6. Startup and Data Flow

Startup proceeds in this order:

```text
read local application configuration
→ resolve or create the selected data directory
→ initialize privacy-safe logging
→ open SQLite
→ apply Alembic migrations
→ insert idempotent sample data on first run
→ create repositories and application services
→ load pages and show the main window
```

Changing the data directory follows a validate-then-switch flow:

1. Resolve the selected path without moving existing user files.
2. Verify directory creation and write access with a disposable probe.
3. Initialize or validate the target database.
4. Persist the new configuration only after validation succeeds.
5. Request an application restart to activate the new database connection.

The foundation release does not silently migrate an existing database or derived data to a newly selected directory.

## 7. Local Data Layout

The selected data directory contains:

```text
<data-directory>/
├─ research_workspace.db
├─ logs/
├─ derived/
├─ exports/
└─ backups/
```

Application configuration is stored separately in the Windows per-user application configuration location. It stores the selected data directory, UI preferences, and logging level. It does not store paper text, model prompts, or extracted research content.

The first migration establishes tables corresponding to the approved domain contract: Paper, PaperVersion, Idea, Note, SourceDocument, Submission, Conference, Grant, EvidenceRef, EntityRelation, Task, AuditLog, and DomainEvent. `ContextRecoverySnapshot` remains outside the foundation schema because its contract is not yet defined; it will be introduced by a later migration.

Only read/query paths needed by the foundation UI are exposed in `v0.1`. Later write behavior is not simulated through UI-only shortcuts.

Sample data has a stable seed identifier and is inserted transactionally. Repeated startup or migration execution must not duplicate it.

## 8. Error Handling and Privacy

Application and infrastructure services return a structured `Result` containing success state, error code, user-safe message, retryability, and optional diagnostic details.

- Database migrations and sample-data insertion run transactionally.
- A failed configuration, directory, database, or migration step prevents business pages from opening and shows a recoverable startup page.
- Routine errors appear inline. Destructive actions are the only foundation interactions that may use blocking confirmation dialogs.
- Logs record error categories, stack traces, and technical context, but exclude paper bodies, extracted text, model inputs, and secrets by default.
- No foundation workflow overwrites, moves, parses, or modifies a user research document.

## 9. Testing Strategy

Development follows test-driven development: a behavior test is written and observed failing before the smallest production change is added.

### Domain tests

Verify entity construction, enum values, relation confirmation states, and agreed invariants without Qt or SQLite.

### Application tests

Verify overview queries, initialization, data-directory validation, configuration persistence, and idempotent seed behavior using explicit test doubles only at infrastructure boundaries.

### Infrastructure integration tests

Run Alembic against temporary SQLite databases, verify the expected schema, transaction rollback, repeatable migration execution, repository reads, and single-instance sample data.

### Qt smoke tests

Run with the Qt offscreen platform and verify application construction, page loading, every navigation destination, overview data binding, settings validation, and the startup recovery page.

## 10. Foundation Acceptance Criteria

`v0.1-foundation` is accepted only when all of the following are true:

1. A documented Python 3.12 environment can install the locked dependencies.
2. The application launches on Windows 10/11 without requiring network access.
3. Every navigation destination loads and the active navigation state updates correctly.
4. Overview content is read through application queries rather than embedded in controllers.
5. Conference and Grant pages clearly show Coming Soon without exposing unfinished controls.
6. A fresh data directory receives the current schema and exactly one sample dataset.
7. The selected data directory persists across restart and is activated only after successful validation.
8. Migration commands are repeatable and do not duplicate or corrupt data.
9. Unit, integration, and offscreen Qt smoke tests pass.
10. A third-party dependency and license inventory can be generated from the locked environment.

## 11. Explicit Non-Goals

The foundation release does not implement document parsing, file monitoring, paper creation forms, Idea editing, submission CRUD, version comparison, AI providers, context recovery, semantic search, real Agent execution, email/calendar integration, OCR, cloud sync, or an installer for public distribution.

These exclusions prevent visual scaffolding from becoming untested pseudo-functionality and keep the first implementation plan independently reviewable.
