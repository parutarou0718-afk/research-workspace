# Research Workspace v0.1 Foundation Design

**Date:** 2026-07-16
**Status:** Approved for v0.1-foundation implementation on 2026-07-16
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

### Locked repository structure

The following tree is the required `v0.1-foundation` repository layout. New long-lived production modules require a specification change; generated caches, virtual environments, build output, coverage output, and runtime user data are excluded from the repository.

```text
research_workspace_package/
├─ .gitignore
├─ .python-version                   # exactly 3.12
├─ app.py
├─ pyproject.toml
├─ uv.lock
├─ alembic.ini
├─ README.md
├─ THIRD_PARTY_NOTICES.md
├─ assets/
│  └─ ui_reference.png
├─ ui/                              # design inputs only; never loaded at runtime
│  ├─ design_tokens.json
│  └─ research_workspace_main.ui    # original overview prototype
├─ contracts/
│  ├─ domain_model.json
│  ├─ task_contract.schema.json
│  ├─ task_result.schema.json
│  ├─ event_contract.schema.json
│  ├─ parsed_document.schema.json
│  └─ provider_interfaces.md
├─ docs/
│  ├─ ARCHITECTURE.md
│  ├─ CODEX_INSTRUCTIONS.md
│  ├─ PRD.md
│  ├─ PRD.docx
│  ├─ UI_SPEC.md
│  └─ superpowers/
│     ├─ specs/
│     └─ plans/
├─ migrations/
│  ├─ env.py
│  ├─ script.py.mako
│  └─ versions/
│     └─ 0001_foundation_schema.py
├─ src/
│  └─ research_workspace/
│     ├─ __init__.py
│     ├─ bootstrap.py
│     ├─ presentation/
│     │  ├─ __init__.py
│     │  ├─ main_window.py
│     │  ├─ pages/
│     │  │  ├─ __init__.py
│     │  │  ├─ overview_page.py
│     │  │  ├─ papers_page.py
│     │  │  ├─ ideas_page.py
│     │  │  ├─ submissions_page.py
│     │  │  ├─ conferences_page.py
│     │  │  ├─ grants_page.py
│     │  │  ├─ settings_page.py
│     │  │  └─ startup_error_page.py
│     │  ├─ view_models/
│     │  │  ├─ __init__.py
│     │  │  └─ overview.py
│     │  └─ ui/
│     │     ├─ main_window.ui
│     │     ├─ overview_page.ui
│     │     ├─ papers_page.ui
│     │     ├─ ideas_page.ui
│     │     ├─ submissions_page.ui
│     │     ├─ conferences_page.ui
│     │     ├─ grants_page.ui
│     │     ├─ settings_page.ui
│     │     ├─ startup_error_page.ui
│     │     └─ design_tokens.json
│     ├─ application/
│     │  ├─ __init__.py
│     │  ├─ ports/
│     │  │  ├─ __init__.py
│     │  │  ├─ repositories.py
│     │  │  ├─ config_store.py
│     │  │  ├─ document_parser.py
│     │  │  ├─ event_bus.py
│     │  │  └─ task_executor.py
│     │  ├─ queries/
│     │  │  ├─ __init__.py
│     │  │  └─ get_overview.py
│     │  └─ services/
│     │     ├─ __init__.py
│     │     ├─ initialize_application.py
│     │     └─ change_data_directory.py
│     ├─ domain/
│     │  ├─ __init__.py
│     │  ├─ entities.py
│     │  ├─ enums.py
│     │  ├─ relations.py
│     │  ├─ tasks.py
│     │  └─ events.py
│     ├─ infrastructure/
│     │  ├─ __init__.py
│     │  ├─ config/
│     │  │  ├─ __init__.py
│     │  │  └─ json_config_store.py
│     │  ├─ db/
│     │  │  ├─ __init__.py
│     │  │  ├─ base.py
│     │  │  ├─ models.py
│     │  │  ├─ session.py
│     │  │  ├─ repositories.py
│     │  │  └─ seed.py
│     │  └─ logging/
│     │     ├─ __init__.py
│     │     └─ configure_logging.py
│     └─ shared/
│        ├─ __init__.py
│        ├─ errors.py
│        ├─ ids.py
│        ├─ result.py
│        └─ time.py
└─ tests/
   ├─ conftest.py
   ├─ unit/
   │  ├─ domain/
   │  └─ application/
   ├─ contracts/
   ├─ integration/
   ├─ ui/
   └─ acceptance/
```

`src/research_workspace/presentation/ui/` is the single runtime source of Qt layouts. The top-level `ui/` directory preserves the supplied design inputs and must not be imported or packaged as runtime UI. The locked tree is exact for root configuration files, migrations, `src/research_workspace/`, runtime UI, and contract files. Test modules named in §15 and future plan documents under `docs/superpowers/plans/` are required/allowed additions; caches, reports, build artifacts, and runtime data remain forbidden repository content.

## 5. UI Composition

The main window contains a stable navigation shell and one component per page:

```text
MainWindow
├─ OverviewPage
├─ PapersPage
├─ IdeasPage
├─ SubmissionsPage
├─ ConferencesPage
├─ GrantsPage
└─ SettingsPage
```

The existing visual direction, design tokens, and Chinese-first copy remain authoritative. Long-lived layouts stay in `.ui` files and are loaded through `QUiLoader`; Python controllers bind behavior without reproducing the layout imperatively. The existing overview prototype will be decomposed into a navigation shell and an overview page rather than converted into one large generated Python file.

The first release uses real query results backed by idempotent sample data. Hard-coded display data in the current prototype is replaced with view-model values.

### UI file and ownership rules

Every long-lived page has exactly one corresponding runtime `.ui` file and one Python controller. `main_window.ui` owns only the navigation shell and `QStackedWidget`; it must not contain page-specific cards, tables, or forms. Conference and Grant use separate `conferences_page.ui` and `grants_page.ui` files even while both display Coming Soon; shared colors and spacing come from design tokens rather than a shared page layout. `startup_error_page.ui` is loaded without opening the business-page stack.

Python controllers locate required child widgets by `objectName`, validate their presence during construction, connect signals explicitly, and receive application services through their constructors. `QMetaObject.connectSlotsByName` and implicit `on_<object>_<signal>` binding are not used.

### Qt `objectName` convention

All object names use lower camel case, contain a semantic purpose, and end with a type suffix. Designer defaults such as `pushButton`, `label_2`, or `verticalLayout_3` are forbidden.

| Qt object | Required pattern | Examples |
|---|---|---|
| Root page widget | `<pagePurpose>Page` | `overviewPage`, `settingsPage` |
| Main window | `mainWindow` | `mainWindow` |
| Button | `<action>Button` | `organizeNowButton`, `saveIdeaButton` |
| Navigation button | `nav<Page>Button` | `navOverviewButton`, `navPapersButton` |
| Label | `<contentPurpose>Label` | `pageTitleLabel`, `revisionCountLabel` |
| Line edit | `<fieldPurpose>LineEdit` | `ideaContentLineEdit`, `dataDirectoryLineEdit` |
| Combo box | `<fieldPurpose>ComboBox` | `logLevelComboBox` |
| Table | `<entityPurpose>Table` | `submissionOverviewTable` |
| List/tree view | `<entityPurpose>ListView` / `TreeView` | `paperListView` |
| Frame/card | `<contentPurpose>Card` | `aiSuggestionsCard` |
| Stacked widget | `<purpose>Stack` | `pageStack` |
| Scroll area | `<pagePurpose>ScrollArea` | `overviewScrollArea` |
| Layout | `<contentPurpose><Direction>Layout` | `statisticsHorizontalLayout` |
| Status/error widget | `<purpose>StatusLabel` / `ErrorLabel` | `dataDirectoryErrorLabel` |

### Window, DPI, and scrolling

- The design baseline is 1440 × 900 device-independent pixels.
- The main window minimum size is 1180 × 720 device-independent pixels.
- The `v0.1` sidebar is fixed at 220 device-independent pixels; the future collapsed 88-pixel state is out of scope.
- Qt 6 per-monitor DPI scaling remains enabled. The application must not disable high-DPI scaling or round scale factors to integers.
- Fonts use point sizes and layouts use size policies, minimum sizes, and stretch factors. Pixel-fixed text containers are forbidden.
- Each content page owns a `QScrollArea` with `widgetResizable=true`. Vertical scrolling appears when content exceeds available height. Horizontal page scrolling is forbidden at 1180 × 720; wide tables may scroll internally without forcing the whole page sideways.
- Changing scale factor or moving between monitors must not require restart and must not cause overlapping controls, clipped button text, inaccessible navigation, or off-screen confirmation controls.
- Acceptance covers Windows scaling at 100%, 125%, and 150%. Automated offscreen layout tests run with `QT_SCALE_FACTOR=1.0`, `1.25`, and `1.5`; a Windows visual smoke checklist verifies the same three factors on the packaged development build.

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

### User-facing data-directory switching

Changing the data directory follows a validate-then-switch flow:

1. Resolve the selected path without moving existing user files.
2. Verify directory creation and write access with a disposable probe.
3. Initialize or validate the target database.
4. Persist the new configuration only after validation succeeds.
5. Request an application restart to activate the new database connection.

The foundation release does not copy, move, merge, or migrate an existing database, logs, derived data, exports, or backups into a newly selected directory.

The Settings page must explain this before the chooser opens: **“切换后将使用新目录中的工作台数据；现有数据不会自动迁移或删除。”** After the user selects a directory, the page shows the resolved absolute path and whether it contains an existing Research Workspace database or will be initialized as a new workspace. The confirmation action is labelled **“验证并在重启后切换”**. On success, the application records the pending path, displays **“已验证。重启应用后切换；原目录保持不变。”**, and offers a Restart Now button plus a Later button. On validation failure, the active directory and persisted configuration remain unchanged. Cancelling the chooser or confirmation performs no write.

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

The configuration file is UTF-8 JSON at the `platformdirs.user_config_dir("ResearchWorkspace", "ResearchWorkspace")/config.json` location and has exactly these `v0.1` fields:

```json
{
  "schema_version": "1.0",
  "active_data_directory": "C:\\absolute\\workspace-data",
  "pending_data_directory": null,
  "log_level": "INFO"
}
```

When `config.json` does not exist, bootstrap chooses `platformdirs.user_data_dir("ResearchWorkspace", "ResearchWorkspace")` as the default active data directory, validates/creates it, and atomically writes the exact configuration above with that absolute path, null pending path, and `INFO`. No chooser interrupts a successful first launch. If the default cannot be created or written, bootstrap opens `startup_error_page.ui` before any database/business page and offers **“选择数据目录”**; a successfully validated choice becomes `active_data_directory` immediately because no prior workspace exists.

`active_data_directory` is the database used by the current process. A validated later switch writes only `pending_data_directory`. On the next startup, bootstrap validates and initializes the pending directory, atomically promotes it to `active_data_directory`, clears the pending field, and then opens its database. If that startup validation fails, bootstrap clears the invalid pending value, retains the prior active directory, and shows the recovery page with both paths and the failure reason. `log_level` is one of `DEBUG`, `INFO`, `WARNING`, or `ERROR`; production packaging defaults to `INFO`.

The first migration establishes tables corresponding to the approved domain contract: Paper, PaperVersion, Idea, Note, SourceDocument, Submission, Conference, Grant, EvidenceRef, EntityRelation, RelationObservation, Task, TaskAttempt, TaskEffect, AuditLog, and DomainEvent. `RelationObservation` is an append-only provenance record supporting repeated independent observations of one unique relation. TaskAttempt and TaskEffect are dormant operational records that preserve future retry and idempotency compatibility; `v0.1` does not run an executor. `ContextRecoverySnapshot` remains outside the foundation schema because its contract is not yet defined; it will be introduced by a later migration.

Only read/query paths needed by the foundation UI are exposed in `v0.1`. Later write behavior is not simulated through UI-only shortcuts.

Sample data has a stable seed identifier and is inserted transactionally. Repeated startup or migration execution must not duplicate it.

The seed manifest identifier is `research-workspace-foundation-seed-v1` with UUID namespace `4c8c9a20-06a5-5c0d-9d8c-41aeeab7ef10`. Every row ID is UUIDv5 of that namespace and `<EntityType>:<stable-key>`. All omitted nullable fields are null, all `created_at`/`updated_at` values are `2026-06-01T00:00:00Z`, and no seed uses the current clock.

| Entity | Stable key | Required seeded values |
|---|---|---|
| Paper | `multimodal-alignment` | title `多模态对齐方法研究`, status `revision` |
| Paper | `temporal-representation` | title `时序表示学习综述`, status `active` |
| Paper | `research-llm` | title `大模型在科研工作流中的应用`, status `active` |
| Idea | `causal-alignment` | title/content `跨模态因果对齐`, status `unused`, origin `manual` |
| Idea | `small-sample-eval` | title/content `小样本稳健性评估`, status `unused`, origin `manual` |
| Idea | `review-response-map` | title/content `审稿意见—证据映射`, status `unused`, origin `manual` |
| Idea | `cross-paper-memory` | title/content `跨论文研究记忆`, status `unused`, origin `manual` |
| Submission | `tpami-revision` | first Paper, venue `IEEE TPAMI`, status `revision`, submitted `2026-06-10T00:00:00Z`, deadline `2026-07-20T00:00:00Z` |
| Submission | `neurips-ready` | second Paper, venue `NeurIPS`, status `ready`, deadline `2026-07-31T00:00:00Z` |
| Submission | `acmmm-review` | third Paper, venue `ACM MM`, status `external_review`, submitted `2026-06-15T00:00:00Z` |
| Conference | `neurips-2026` | name `NeurIPS 2026`, starts `2026-07-25T00:00:00Z`, ends `2026-07-27T00:00:00Z`, location `Tokyo`, status `planned` |
| Conference | `research-workflow-forum` | name `科研工作流论坛`, starts/ends `2026-07-18T00:00:00Z`, location `Online`, status `planned` |
| Grant | `foundation-methods` | name `基础研究方法专项`, status `watching`, deadline `2026-07-30T00:00:00Z`, source URL `https://example.invalid/grants/foundation-methods` |

The manifest intentionally contains no PaperVersion, SourceDocument, Note, EvidenceRef, EntityRelation, RelationObservation, Task, TaskAttempt, TaskEffect, AuditLog, or DomainEvent row. Bootstrap seed insertion is fixture initialization rather than a user domain write, so it is recorded in technical logs but excluded from AuditLog. Any later user or automated domain write is audited normally.

### Database conventions

- Table and column names are lower snake case; table names are plural.
- IDs are canonical lowercase UUID strings stored as `CHAR(36)`.
- Timestamps are UTC, timezone-aware application values stored as `TEXT` in RFC 3339 form ending in `Z`. `created_at` is immutable; `updated_at` changes on every persisted mutation.
- Enum columns are `VARCHAR(64)` lowercase strings checked by application validation and database `CHECK` constraints.
- Confidence decimals are `NUMERIC(6,5)` with inclusive bounds 0 and 1.
- JSON values are UTF-8 canonical JSON stored as `TEXT`, validated before persistence, and never contain Python object serialization.
- Boolean values are `BOOLEAN NOT NULL` with explicit defaults.
- Foreign keys are enabled for every SQLite connection. Destructive cascades are forbidden for research records; relations use `RESTRICT`, while optional current pointers use `SET NULL`.
- Mutable user records use `deleted_at` for soft deletion. Immutable evidence, audit, task, and event rows are never updated in place except for explicitly listed lifecycle columns.
- Constraints labelled **DB** are expressed by primary/foreign keys, unique indexes, `NOT NULL`, or `CHECK`. Constraints labelled **APP** are cross-row, cross-table, graph, URL, or state-machine invariants enforced in domain/application services and covered by the named unit/contract tests. AC12 distinguishes these two categories.

### Foundation table schemas

`papers`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `title` | `VARCHAR(500)` | required | trimmed, length 1–500 |
| `status` | enum | `active` | `active`, `paused`, `revision`, `submitted`, `completed`, `archived` |
| `current_version_id` | UUID | null | **DB:** FK `paper_versions.id`, `SET NULL`; **APP:** version belongs to this paper and is the same row whose `is_current=true` |
| `created_at` | timestamp | required | immutable |
| `updated_at` | timestamp | required | `updated_at >= created_at` |
| `deleted_at` | timestamp | null | soft deletion; must be `>= created_at` |

`paper_versions`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `paper_id` | UUID | required | FK `papers.id`, `RESTRICT` |
| `source_document_id` | UUID | required | FK `source_documents.id`, `RESTRICT` |
| `version_label` | `VARCHAR(128)` | required | unique with `paper_id` |
| `parent_version_id` | UUID | null | **DB:** self-FK, not self; **APP:** parent belongs to same paper |
| `is_current` | boolean | `false` | partial unique index permits at most one `true` row per paper |
| `created_at` | timestamp | required | immutable |

`ideas`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `title` | `VARCHAR(500)` | required | trimmed, length 1–500 |
| `content` | text | required | non-empty |
| `status` | enum | `unused` | `unused`, `used`, `parked`, `archived` |
| `origin_type` | enum | `manual` | `manual`, `document`, `note`, `meeting`, `chat`, `book`, `paper`, `ai_candidate` |
| `created_at` | timestamp | required | immutable |
| `updated_at` | timestamp | required | `updated_at >= created_at` |
| `deleted_at` | timestamp | null | soft deletion |

`notes`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `title` | `VARCHAR(500)` | required | trimmed, length 1–500 |
| `content` | text | required | may contain Markdown, non-empty |
| `source_document_id` | UUID | null | FK `source_documents.id`, `RESTRICT` |
| `created_at` | timestamp | required | immutable |
| `updated_at` | timestamp | required | `updated_at >= created_at` |
| `deleted_at` | timestamp | null | soft deletion |

`source_documents`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `path` | text | required | canonical absolute Windows path; unique with `NOCASE` collation |
| `sha256` | `CHAR(64)` | required | lowercase hexadecimal, indexed but not globally unique |
| `mime_type` | `VARCHAR(255)` | required | normalized MIME type |
| `size_bytes` | integer | required | `>= 0` |
| `modified_at` | timestamp | required | source filesystem time captured at fingerprinting |
| `imported_at` | timestamp | required | immutable |
| `read_only` | boolean | `true` | must be `true` for original research files |
| `missing_at` | timestamp | null | marks a path no longer observed; never deletes the record |

`submissions`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `paper_id` | UUID | required | FK `papers.id`, `RESTRICT` |
| `venue` | `VARCHAR(500)` | required | non-empty |
| `status` | enum | `preparing` | `preparing`, `ready`, `submitted`, `editorial_review`, `external_review`, `revision`, `accepted`, `rejected`, `withdrawn`, `no_response` |
| `submitted_at` | timestamp | null | **APP:** required for `submitted`, `editorial_review`, `external_review`, `revision`, `accepted`, `rejected`, and `no_response`; optional for `preparing`, `ready`, and `withdrawn` |
| `deadline_at` | timestamp | null | optional |
| `active_version_id` | UUID | null | **DB:** FK `paper_versions.id`; **APP:** version belongs to `paper_id` |
| `created_at` | timestamp | required | immutable |
| `updated_at` | timestamp | required | lifecycle updates are audited |
| `deleted_at` | timestamp | null | soft deletion |

`conferences`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `name` | `VARCHAR(500)` | required | non-empty |
| `starts_at` | timestamp | null | optional |
| `ends_at` | timestamp | null | `ends_at >= starts_at` when both exist |
| `location` | `VARCHAR(500)` | null | optional |
| `status` | enum | `planned` | `planned`, `registered`, `attending`, `completed`, `cancelled` |
| `created_at` | timestamp | required | immutable |
| `updated_at` | timestamp | required | audited |
| `deleted_at` | timestamp | null | soft deletion |

`grants`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `name` | `VARCHAR(500)` | required | non-empty |
| `status` | enum | `watching` | `watching`, `preparing`, `submitted`, `awarded`, `rejected`, `archived` |
| `deadline_at` | timestamp | null | optional |
| `source_url` | text | null | **APP:** absolute `http` or `https` URL |
| `created_at` | timestamp | required | immutable |
| `updated_at` | timestamp | required | audited |
| `deleted_at` | timestamp | null | soft deletion |

`evidence_refs`

`EvidenceTargetType` is the closed enum `Paper`, `PaperVersion`, `Idea`, `Note`, `SourceDocument`, `Submission`, `Conference`, `Grant`, and `EntityRelation`.

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `entity_type` | enum | required | `EvidenceTargetType` |
| `entity_id` | UUID | required | target entity identifier, validated by service |
| `document_id` | UUID | required | FK `source_documents.id`, `RESTRICT` |
| `version_id` | UUID | null | FK `paper_versions.id`, `RESTRICT` |
| `section` | `VARCHAR(1000)` | null | human-readable heading path joined with ` / ` |
| `page` | integer | null | 1-based, `>= 1` |
| `slide` | integer | null | 1-based, `>= 1` |
| `paragraph_id` | `CHAR(64)` | null | stable parser block ID |
| `char_start` | integer | null | 0-based inclusive offset within block text |
| `char_end` | integer | null | 0-based exclusive; `>= char_start` |
| `locator_json` | JSON text | required | complete `SourceLocator` contract; `{}` only for manually entered evidence |
| `quote_hash` | `CHAR(64)` | required | SHA-256 of normalized quoted text |
| `created_at` | timestamp | required | immutable |

`entity_relations`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `source_type` | enum | required | **APP:** allowed endpoint for relation type |
| `source_id` | UUID | required | application-validated entity reference |
| `relation_type` | enum | required | defined in §8 |
| `target_type` | enum | required | **APP:** allowed endpoint for relation type |
| `target_id` | UUID | required | application-validated entity reference; not same endpoint as source |
| `confidence` | decimal | null | cached maximum observation confidence, range 0–1 |
| `confirmation_state` | enum | `candidate` | `candidate`, `confirmed`, `rejected` |
| `created_by_actor_type` | enum | required | `user`, `system`, `task_executor`, `agent` |
| `created_by_actor_id` | `VARCHAR(255)` | null | concrete actor identity when available |
| `created_at` | timestamp | required | immutable |
| `updated_at` | timestamp | required | confirmation changes are audited |

`relation_observations`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `relation_id` | UUID | required | FK `entity_relations.id`, `RESTRICT` |
| `observed_by_actor_type` | enum | required | `user`, `system`, `task_executor`, `agent` |
| `observed_by_actor_id` | `VARCHAR(255)` | null | concrete actor identity when available |
| `provenance_type` | enum | required | `manual`, `rule`, `import`, `ai` |
| `confidence` | decimal | null | range 0–1; required for `import` and `ai` |
| `origin_task_id` | UUID | null | FK `tasks.id`, `RESTRICT`; required for task/agent observation |
| `evidence_ref_id` | UUID | null | FK `evidence_refs.id`, `RESTRICT`; required for `import` and `ai` |
| `provider_id` | `VARCHAR(255)` | null | required for `ai` |
| `model_id` | `VARCHAR(255)` | null | required for `ai` |
| `observed_at` | timestamp | required | append-only |
| `observation_key` | `VARCHAR(255)` | required | unique idempotency key for this observation |

`tasks`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key; equals contract `task_id` |
| `task_type` | enum | required | one of the locked TaskContract types |
| `status` | enum | `pending` | `pending`, `running`, `needs_confirmation`, `succeeded`, `failed`, `cancelled` |
| `idempotency_key` | `VARCHAR(255)` | required | unique |
| `request_fingerprint` | `CHAR(64)` | required | SHA-256 of the canonical semantic request defined in §12 |
| `payload_json` | JSON text | required | complete validated TaskContract |
| `result_json` | JSON text | null | complete validated TaskResult only after terminal/confirmation result |
| `attempt_count` | integer | `0` | `>= 0` |
| `max_attempts` | integer | `3` | range 1–10 |
| `next_attempt_at` | timestamp | null | present only for scheduled retry |
| `lease_owner` | `VARCHAR(255)` | null | executor instance ID while running |
| `lease_expires_at` | timestamp | null | required when `lease_owner` is set |
| `lease_generation` | integer | `0` | non-negative fencing token incremented on every lease/reclaim |
| `created_at` | timestamp | required | immutable |
| `started_at` | timestamp | null | first accepted execution time |
| `finished_at` | timestamp | null | terminal time |

`task_attempts`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `task_id` | UUID | required | FK `tasks.id`, `RESTRICT` |
| `attempt_number` | integer | required | `>=1`, unique with `task_id` |
| `lease_generation` | integer | required | must equal generation granted to this attempt |
| `lease_owner` | `VARCHAR(255)` | required | executor instance ID |
| `status` | enum | `running` | `running`, `retry_scheduled`, `succeeded`, `failed`, `cancelled`, `needs_confirmation` |
| `result_json` | JSON text | null | immutable validated TaskResult when attempt closes |
| `started_at` | timestamp | required | immutable |
| `finished_at` | timestamp | null | required when status is not `running` |

`task_effects`

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `operation_key` | `CHAR(64)` | required | unique lowercase SHA-256 defined in §12 |
| `task_id` | UUID | required | FK `tasks.id`, `RESTRICT` |
| `attempt_id` | UUID | required | FK `task_attempts.id`, `RESTRICT` |
| `effect_type` | `VARCHAR(255)` | required | stable executor-defined type |
| `output_type` | `VARCHAR(255)` | required | logical output entity/artifact type |
| `output_identity` | `VARCHAR(1000)` | required | stable logical identity, not a temporary path |
| `output_ref_json` | JSON text | required | persisted output reference |
| `status` | enum | required | `prepared`, `committed`, `manual_reconciliation` |
| `recovery_json` | JSON text | null | staging/final path and hash for filesystem effects; provider receipt for external effects |
| `created_at` | timestamp | required | append-only preparation time |
| `committed_at` | timestamp | null | only mutable lifecycle field; required for `committed` |

`audit_logs`

`AuditTargetType` is the closed enum `Paper`, `PaperVersion`, `Idea`, `Note`, `SourceDocument`, `Submission`, `Conference`, `Grant`, `EvidenceRef`, `EntityRelation`, `RelationObservation`, and `Task`.

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key |
| `actor_type` | enum | required | `user`, `system`, `task_executor`, `agent` |
| `actor_id` | `VARCHAR(255)` | null | user/executor/agent identity when available |
| `action` | `VARCHAR(255)` | required | stable dotted action name |
| `target_type` | enum | required | `AuditTargetType` |
| `target_id` | UUID | required | target identifier |
| `before_json` | JSON text | null | null only for create |
| `after_json` | JSON text | null | null only for delete tombstone |
| `task_id` | UUID | null | FK `tasks.id`, `RESTRICT` |
| `correlation_id` | UUID | null | workflow correlation |
| `undo_token` | `VARCHAR(255)` | null | unique when present; single-use |
| `undo_of_audit_id` | UUID | null | self-FK, unique; present only on the compensating undo row |
| `created_at` | timestamp | required | append-only |

`domain_events`

`EventAggregateType` is the closed enum `Paper`, `PaperVersion`, `Idea`, `SourceDocument`, `Submission`, `Conference`, `Grant`, `Task`, and `AuditLog`.

| Field | Type | Null/default | Constraint |
|---|---|---|---|
| `id` | UUID | required | primary key; equals contract `event_id` |
| `event_type` | enum | required | locked event type |
| `aggregate_type` | enum | required | `EventAggregateType` |
| `aggregate_id` | UUID | required | aggregate identifier |
| `payload_json` | JSON text | required | complete validated DomainEvent |
| `deduplication_key` | `VARCHAR(255)` | required | unique |
| `causation_id` | UUID | null | originating task/event ID |
| `correlation_id` | UUID | null | workflow correlation |
| `created_at` | timestamp | required | append-only |
| `processed_at` | timestamp | null | only mutable delivery field |

Circular foreign keys between `papers.current_version_id` and `paper_versions.paper_id` are created in migration-safe order. Cross-polymorphic references in `evidence_refs`, `entity_relations`, and `audit_logs` are validated by application services because SQLite cannot express their foreign keys directly.

## 8. Entity Relations

Relation direction is semantic, not merely storage order. The source is the subject of the relation phrase and the target is its object.

`RelationEntityType` is the closed enum `Paper`, `PaperVersion`, `Idea`, `Note`, `SourceDocument`, `Submission`, `Conference`, `Grant`, and `EvidenceRef`. Task, AuditLog, DomainEvent, and RelationObservation are operational records and cannot be relation endpoints.

| Relation | Direction | Allowed source → target | Meaning |
|---|---|---|---|
| `belongs_to` | directed | Note/SourceDocument → Paper; Submission → Paper | source is owned by the target project |
| `derived_from` | directed | Idea/Note/PaperVersion → SourceDocument/Idea/Note | source was derived from target |
| `version_of` | directed | PaperVersion → Paper | version is a version of paper |
| `used_in` | directed | Idea → Paper/PaperVersion | idea is intentionally used in target |
| `deleted_from` | directed | Idea → PaperVersion | idea captures content removed from target version |
| `supports` | directed | Idea/Note/SourceDocument/EvidenceRef → Paper/Idea/Note/Submission | source provides support for target |
| `contradicts` | symmetric | any pair from Idea, Note, SourceDocument | endpoints materially conflict |
| `extends` | directed | Paper → Paper; Idea → Idea; Note → Note | source extends target of exactly the same type |
| `related_to` | symmetric | any two distinct `RelationEntityType` endpoints | non-specific relationship |
| `presented_at` | directed | Paper/PaperVersion → Conference | source was presented at target |
| `submitted_as` | directed | PaperVersion → Submission | exact version used for submission |
| `reviewed_by` | directed | Submission → SourceDocument | target contains review material for submission |
| `suggested_for` | directed | Idea → Paper | idea is a candidate for paper |
| `split_from` | directed | Paper → Paper | source paper split from target paper |
| `merged_from` | directed | Paper → Paper | source paper incorporates target paper |

For symmetric relations, endpoints are canonicalized before persistence by lexicographically sorting `(entity_type, entity_id)`. Directed relations retain semantic order. A unique constraint applies to the canonical tuple `(relation_type, source_type, source_id, target_type, target_id)`. Re-observing the same relation appends a unique RelationObservation and may update only the cached maximum `confidence`; it never changes a confirmed/rejected state or overwrites earlier provenance. A rejected relation remains stored to suppress repeated suggestions. Only an explicit user action labelled “重新考虑此关系” may transition it back to `candidate`, and that transition is audited.

Confirmation rules:

- `candidate` is the only initial state permitted when the first observation has `provenance_type` of `rule`, `import`, or `ai`, or when the creating actor is `task_executor` or `agent`.
- Only a user action may transition `candidate` to `confirmed` or `rejected`.
- A user may create a relation directly as `confirmed`.
- AI/import observations require `confidence`, `origin_task_id`, and `evidence_ref_id`; AI additionally requires `provider_id` and `model_id`.
- User-created manual observations may omit confidence and evidence, but creator actor and provenance remain explicit.
- No relation is physically deleted. Retraction uses `rejected`, with before/after snapshots in `audit_logs`.
- A relation cannot target itself. The union graph of `split_from` plus `merged_from` must be acyclic across Paper endpoints. Each same-type `extends` graph is checked independently for cycles. Application validation rejects a write that would create a cycle.

## 9. Error Handling and Privacy

Application and infrastructure services return a structured `Result` containing success state, error code, user-safe message, retryability, and optional diagnostic details.

- Database migrations and sample-data insertion run transactionally.
- A failed configuration, directory, database, or migration step prevents business pages from opening and shows a recoverable startup page.
- Routine errors appear inline. Destructive actions are the only foundation interactions that may use blocking confirmation dialogs.
- Logs record error categories, stack traces, and technical context, but exclude paper bodies, extracted text, model inputs, and secrets by default.
- No foundation workflow overwrites, moves, parses, or modifies a user research document.

## 10. Testing Strategy

Development follows test-driven development: a behavior test is written and observed failing before the smallest production change is added.

### Domain tests

Verify entity construction, enum values, relation confirmation states, and agreed invariants without Qt or SQLite.

### Application tests

Verify overview queries, initialization, data-directory validation, configuration persistence, and idempotent seed behavior using explicit test doubles only at infrastructure boundaries.

### Infrastructure integration tests

Run Alembic against temporary SQLite databases, verify the expected schema, transaction rollback, repeatable migration execution, repository reads, and single-instance sample data.

### Qt smoke tests

Run with the Qt offscreen platform and verify application construction, page loading, every navigation destination, overview data binding, settings validation, and the startup recovery page.

## 11. Task and Event JSON Contracts

The repository contract files are normative. The schemas below define their required shape; implementation copies them verbatim into the corresponding files and contract tests reject drift between files and domain types. All contracts use JSON Schema Draft 2020-12, `schema_version="1.0"`, UUIDs, UTC RFC 3339 timestamps ending in `Z`, and `additionalProperties=false`. Deliberately open extension objects are limited to `TaskContract.options.extensions`, `TaskResult.result`, `TaskResult.error.details`, `DomainEvent.payload`, and the ParsedDocument metadata maps. Contract validation uses `jsonschema.Draft202012Validator` with `FormatChecker`, so `uuid` and `date-time` formats are enforced in addition to the UTC pattern.

### TaskContract — `contracts/task_contract.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://research-workspace.local/schemas/task-contract-1.0.json",
  "title": "TaskContract",
  "type": "object",
  "required": ["schema_version", "task_id", "task_type", "created_at", "requested_by", "idempotency_key", "input_refs", "options"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "task_id": {"type": "string", "format": "uuid"},
    "task_type": {"enum": ["import_document", "compare_versions", "extract_idea_candidates", "recover_paper_context", "refresh_submission_overview", "scheduled_incremental_organize", "export_data"]},
    "created_at": {"$ref": "#/$defs/utcDateTime"},
    "requested_by": {"$ref": "#/$defs/actor"},
    "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 255},
    "correlation_id": {"type": ["string", "null"], "format": "uuid"},
    "target": {
      "type": ["object", "null"],
      "required": ["entity_type", "entity_id"],
      "properties": {"entity_type": {"type": "string", "minLength": 1}, "entity_id": {"type": "string", "format": "uuid"}},
      "additionalProperties": false
    },
    "input_refs": {"type": "array", "items": {"$ref": "#/$defs/ref"}},
    "options": {
      "type": "object",
      "required": ["local_only", "dry_run", "requires_confirmation", "max_attempts", "extensions"],
      "properties": {
        "local_only": {"type": "boolean", "default": true},
        "provider_id": {"type": ["string", "null"]},
        "dry_run": {"type": "boolean", "default": false},
        "requires_confirmation": {"type": "boolean", "default": true},
        "max_attempts": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
        "extensions": {"type": "object"}
      },
      "additionalProperties": false
    }
  },
  "$defs": {
    "utcDateTime": {"type": "string", "format": "date-time", "pattern": "Z$"},
    "actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {"actor_type": {"enum": ["user", "system", "task_executor", "agent"]}, "actor_id": {"type": ["string", "null"], "maxLength": 255}},
      "additionalProperties": false
    },
    "ref": {
      "type": "object",
      "required": ["ref_type", "ref_id"],
      "properties": {"ref_type": {"type": "string", "minLength": 1}, "ref_id": {"type": "string", "minLength": 1}},
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### TaskResult — `contracts/task_result.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://research-workspace.local/schemas/task-result-1.0.json",
  "title": "TaskResult",
  "type": "object",
  "required": ["schema_version", "task_id", "status", "attempt", "started_at", "finished_at", "output_refs", "result", "error", "retry", "event_ids", "audit_log_ids"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "task_id": {"type": "string", "format": "uuid"},
    "status": {"enum": ["retry_scheduled", "needs_confirmation", "succeeded", "failed", "cancelled"]},
    "attempt": {"type": "integer", "minimum": 1},
    "started_at": {"$ref": "#/$defs/utcDateTime"},
    "finished_at": {"$ref": "#/$defs/utcDateTime"},
    "output_refs": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["ref_type", "ref_id"],
        "properties": {"ref_type": {"type": "string", "minLength": 1}, "ref_id": {"type": "string", "minLength": 1}},
        "additionalProperties": false
      }
    },
    "result": {"type": ["object", "null"]},
    "error": {
      "type": ["object", "null"],
      "required": ["code", "message", "retryable", "details"],
      "properties": {"code": {"type": "string", "minLength": 1}, "message": {"type": "string", "minLength": 1}, "retryable": {"type": "boolean"}, "details": {"type": "object"}},
      "additionalProperties": false
    },
    "retry": {
      "type": ["object", "null"],
      "required": ["next_attempt_at"],
      "properties": {"next_attempt_at": {"$ref": "#/$defs/utcDateTime"}},
      "additionalProperties": false
    },
    "event_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}, "uniqueItems": true},
    "audit_log_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}, "uniqueItems": true}
  },
  "$defs": {"utcDateTime": {"type": "string", "format": "date-time", "pattern": "Z$"}},
  "allOf": [
    {"if": {"properties": {"status": {"const": "retry_scheduled"}}}, "then": {"properties": {"result": {"type": "null"}, "error": {"type": "object", "properties": {"retryable": {"const": true}}}, "retry": {"type": "object"}}}},
    {"if": {"properties": {"status": {"const": "failed"}}}, "then": {"properties": {"result": {"type": "null"}, "error": {"type": "object", "properties": {"retryable": {"const": false}}}, "retry": {"type": "null"}}}},
    {"if": {"properties": {"status": {"enum": ["succeeded", "needs_confirmation"]}}}, "then": {"properties": {"result": {"type": "object"}, "error": {"type": "null"}, "retry": {"type": "null"}}}},
    {"if": {"properties": {"status": {"const": "cancelled"}}}, "then": {"properties": {"result": {"type": "null"}, "error": {"type": "object", "properties": {"code": {"const": "TASK_CANCELLED"}, "retryable": {"const": false}}}, "retry": {"type": "null"}}}}
  ],
  "additionalProperties": false
}
```

### DomainEvent — `contracts/event_contract.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://research-workspace.local/schemas/domain-event-1.0.json",
  "title": "DomainEvent",
  "type": "object",
  "required": ["schema_version", "event_id", "event_type", "occurred_at", "actor", "aggregate", "payload", "deduplication_key"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "event_id": {"type": "string", "format": "uuid"},
    "event_type": {"enum": ["document.imported", "paper.created", "paper.version_added", "paper.version_relation_corrected", "idea.created", "idea.candidate_extracted", "idea.linked", "submission.created", "submission.status_changed", "context.recovered", "task.failed", "audit.undo_applied"]},
    "occurred_at": {"$ref": "#/$defs/utcDateTime"},
    "actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {"actor_type": {"enum": ["user", "system", "task_executor", "agent"]}, "actor_id": {"type": ["string", "null"], "maxLength": 255}},
      "additionalProperties": false
    },
    "aggregate": {
      "type": "object",
      "required": ["type", "id"],
      "properties": {"type": {"enum": ["Paper", "PaperVersion", "Idea", "SourceDocument", "Submission", "Conference", "Grant", "Task", "AuditLog"]}, "id": {"type": "string", "format": "uuid"}},
      "additionalProperties": false
    },
    "payload": {"type": "object"},
    "deduplication_key": {"type": "string", "minLength": 1, "maxLength": 255},
    "causation_id": {"type": ["string", "null"], "format": "uuid"},
    "correlation_id": {"type": ["string", "null"], "format": "uuid"}
  },
  "$defs": {"utcDateTime": {"type": "string", "format": "date-time", "pattern": "Z$"}},
  "additionalProperties": false
}
```

## 12. Future Executor and Agent Rules

These rules are contracts only in `v0.1`; no executor or Agent is run.

### Idempotency

- Every task has a caller-supplied `idempotency_key`, unique across the task table. Before hashing, `input_refs` are sorted lexicographically by `(ref_type, ref_id)`. The semantic request fingerprint is lowercase SHA-256 of RFC 8785 JSON Canonicalization Scheme bytes after removing `task_id`, `created_at`, `correlation_id`, and `idempotency_key`; actor, task type, target, normalized input refs, and options remain included. Submitting the same key with the same fingerprint returns the existing task and result even when transport IDs/timestamps or input-ref order differ. Reusing a key with a different fingerprint returns `TASK_IDEMPOTENCY_CONFLICT` and performs no write. The fingerprint is stored in `tasks.request_fingerprint`.
- Each side effect operation key is lowercase SHA-256 of RFC 8785 JCS bytes for `{ "task_id": task_id, "executor_id": stable_executor_id, "effect_type": effect_type, "output_type": output_type, "output_identity": stable_output_identity }`. A replay that finds a `committed` operation key returns `output_ref_json` and performs no second effect.
- Database effects and their committed TaskEffect row share one SQLite transaction. Filesystem effects use a recoverable two-phase protocol: write and fsync a deterministic staging file under the selected data directory; insert a `prepared` TaskEffect containing staging path, final path, and SHA-256; atomically `os.replace` staging to final on the same volume; then mark the row `committed`. Replay of `prepared` verifies the final hash and commits the row, or completes the staged rename; if neither verified file exists it returns a retryable recovery error. It never overwrites a user research source file.
- External connector/provider effects receive `operation_key` as their idempotency token. If the provider cannot honor idempotency, that effect is limited to one attempt; an ambiguous transport outcome marks TaskEffect `manual_reconciliation` and returns `needs_confirmation` rather than blindly retrying.
- Every emitted event has a unique `deduplication_key`. Event publication is outbox-style: task state, audit rows, and event rows commit in one database transaction; delivery may repeat but consumption deduplicates.
- `dry_run=true` forbids persistent domain changes, audit undo tokens, and external writes; it may create the Task and TaskResult records needed to report the preview.

### Retry and leasing

- Lease acquisition is one atomic compare-and-update for `(status=pending AND (next_attempt_at IS NULL OR next_attempt_at<=now) AND attempt_count<max_attempts)`. Expired-running cleanup is a separate atomic transition for `(status=running AND lease_expires_at<=now)` so it remains reachable even after the final allowed attempt.
- Acquisition sets `status=running`, owner/expiry, increments `attempt_count` and `lease_generation`, and inserts one running TaskAttempt with that attempt number and generation. Every executor write includes both task ID and lease generation; a stale generation is rejected with `TASK_LEASE_LOST` before side effects.
- A live lease cannot be stolen. Expired-running cleanup first closes the prior TaskAttempt. If `attempt_count<max_attempts`, it records `retry_scheduled` with retryable `EXECUTOR_LEASE_EXPIRED`, changes the task to due `pending`, and a later lease acquisition starts the next attempt. If `attempt_count>=max_attempts`, it records terminal non-retryable `failed` with `TASK_LEASE_EXHAUSTED`, writes `tasks.result_json`, clears lease fields, and sets `finished_at`.
- On a retryable execution error, the executor checks remaining attempts in the same fenced transaction. If `attempt_count<max_attempts`, it closes the TaskAttempt with `TaskResult.status=retry_scheduled`, sets the Task back to `pending`, clears lease fields, and stores the jittered actual `next_attempt_at`; `tasks.result_json` remains null. If `attempt_count>=max_attempts`, it closes both attempt and task as non-retryable terminal `failed`, preserving the original error code/details and adding `details.retries_exhausted=true`. Validation, permission, unsupported format, idempotency conflict, and confirmation-required errors are non-retryable.
- Default maximum attempts are 3. Base retry delays are 5 seconds, 30 seconds, then 5 minutes for any explicitly configured higher attempt. The scheduler adds 0–20% jitter and stores the resulting actual execution timestamp in both `TaskResult.retry.next_attempt_at` and `tasks.next_attempt_at`.
- Every closed attempt keeps its immutable TaskResult in `task_attempts.result_json`. Only `succeeded`, final `failed`, `cancelled`, or `needs_confirmation` is copied to `tasks.result_json`; those task-level states are immutable. `needs_confirmation` resumes only through a new user-authorized task linked by `correlation_id`, not by mutating and rerunning the old result.

### Audit

- Every domain write after bootstrap seeding creates an append-only AuditLog row with actor, action, target, before/after JSON, task/correlation IDs, and timestamp. The exact fixed seed manifest is explicitly exempt as specified in §7.
- Automated writes that are reversible receive a unique `undo_token`. Undo creates a compensating audit row whose unique `undo_of_audit_id` references the original row, plus an `audit.undo_applied` event. The unique reference makes the token single-use without mutating or deleting prior history.
- Reads are not audited in `v0.1`. Future reads of model-bound source excerpts must be logged as privacy telemetry without storing the excerpt itself.
- TaskResult lists every created audit and event ID so a future orchestrator can prove completion.

### Permissions

- Executors and Agents never receive a SQLAlchemy session or filesystem-wide access. They call application ports with an explicit capability set.
- `document_parser`: read one declared source path and write only derived output under the selected data directory.
- `knowledge`: create candidate Idea/EntityRelation records; cannot confirm, reject, overwrite, or delete user-confirmed data.
- `context_recovery`: read approved aggregates and write a candidate snapshot plus evidence; cannot modify source entities.
- `submission`: propose or apply a status transition only when the task was user-requested; every transition is audited.
- `export`: read the selected entities and write only to the user-approved export target.
- `grant`: recommendation output only; no external submission or state mutation.
- Original research files are read-only for every capability. Network access is denied unless the task declares `local_only=false`, a configured connector/provider is selected, and the UI has captured user consent for the disclosed data range.

## 13. DocumentParser Output Contract

`v0.1` defines and validates this contract but does not parse documents. `DocumentParser.parse(source: Path) -> ParsedDocument` must return a value satisfying `contracts/parsed_document.schema.json`:

```json
{
  "schema_version": "1.0",
  "source": {
    "path": "C:\\research\\paper.docx",
    "sha256": "64 lowercase hex characters",
    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "size_bytes": 12345,
    "modified_at": "2026-07-16T00:00:00Z"
  },
  "parser": {"parser_id": "markitdown", "parser_version": "0.1.6"},
  "title": "Optional title",
  "metadata": {},
  "blocks": [
    {
      "block_id": "64 lowercase hex characters",
      "kind": "paragraph",
      "text": "Extracted text",
      "locator": {
        "page": null,
        "slide": null,
        "paragraph_index": 0,
        "paragraph_id": "64 lowercase hex characters",
        "heading_path": ["Introduction", "Background"],
        "char_start": 0,
        "char_end": 14,
        "source_offset_start": null,
        "source_offset_end": null,
        "bbox": null
      },
      "metadata": {}
    }
  ],
  "warnings": []
}
```

Every top-level key shown is required. `title` is `string|null`; `metadata` is an open object; `blocks` and `warnings` are arrays and may be empty. `source` is closed and requires `path`, a 64-character lowercase hexadecimal `sha256`, non-empty `mime_type`, non-negative integer `size_bytes`, and UTC `modified_at`. `parser` is closed and requires non-empty `parser_id` and `parser_version`.

Every block is closed except its `metadata` extension object and requires `block_id`, `kind`, `text`, `locator`, and `metadata`. `block_id` is 64-character lowercase hexadecimal; `text` has minimum length 1. Every locator is closed and requires all ten keys shown: `page`, `slide`, `paragraph_index`, `paragraph_id`, `heading_path`, `char_start`, `char_end`, `source_offset_start`, `source_offset_end`, and `bbox`. Page/slide are `integer>=1|null`; paragraph index is `integer>=0`; paragraph ID is 64-character lowercase hexadecimal or null; heading path is an array of non-empty strings; character offsets are non-negative integers; source offsets are non-negative integers or null; bounding box is a closed object or null.

A non-null bounding box requires `left`, `top`, `right`, `bottom`, `unit`, and `page`; coordinates are numbers `>=0`, unit is `pt`, `px`, or `normalized`, and page is `integer>=1|null`. Every warning is closed and requires non-empty `code`, non-empty `message`, `locator` (the same locator schema or null), and boolean `retryable`.

Contract rules:

- `kind` is one of `title`, `heading`, `paragraph`, `list_item`, `table`, `caption`, `footnote`, `header`, `footer`, `code`, `equation`, `image_alt`, or `other`.
- `page` and `slide` are 1-based when known. They are null when the source format does not provide a stable rendered page or slide.
- `paragraph_index` is a unique contiguous 0-based sequence across all blocks in parser reading order: the block at array position `i` has `paragraph_index=i`. The exact paragraph-like set is `paragraph`, `list_item`, `caption`, `footnote`, `code`, `equation`, and `image_alt`; for those kinds `paragraph_id` equals `block_id`. For `title`, `heading`, `table`, `header`, `footer`, and `other`, `paragraph_id` is null.
- `heading_path` is the ordered hierarchy from outermost to innermost heading and is an empty array when unknown.
- `char_start` is inclusive and `char_end` exclusive within the block's normalized `text`. For a full block they are `0` and `len(text)`.
- `source_offset_start` and `source_offset_end` are optional 0-based half-open offsets into the parser-accessible source text stream; both are null or both are integers with end `>=` start. They are null for binary formats without stable offsets.
- `bbox`, when available, is `{ "left": number, "top": number, "right": number, "bottom": number, "unit": "pt"|"px"|"normalized", "page": integer|null }` and has non-negative ordered coordinates.
- A block ID is deterministic: lowercase SHA-256 of UTF-8 bytes for `source.sha256 + NUL + kind + NUL + JCS(locator without paragraph_id) + NUL + NFC(text with CRLF normalized to LF)`, where JCS is RFC 8785 JSON Canonicalization Scheme. It is stable for identical parser output and changes when the located content changes.
- Blocks are in ascending parser reading order and contain non-empty text. When two blocks have non-null source offsets in the same source stream, their half-open ranges may touch but must not overlap. Parsers must emit one block representation rather than overlapping structural and textual duplicates.
- Parser warnings have `{code, message, locator|null, retryable}` and never replace valid blocks.
- Parser implementations do not write domain entities. The application layer validates the contract, persists derived data, and creates EvidenceRef records.

The full JSON Schema file must express these required fields, enums, nullability, bounds, and `additionalProperties=false` for `source`, `parser`, block, locator, bounding box, and warning objects; only the top-level `metadata` and block `metadata` extension objects are open.

## 14. Foundation Acceptance Criteria

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
11. The locked repository structure exists, contains no undeclared production modules, and every long-lived page has its own runtime `.ui` file with compliant object names.
12. The first migration matches every field, nullability rule, default, index, uniqueness rule, foreign key, and check constraint in §7.
13. TaskContract, TaskResult, DomainEvent, and ParsedDocument fixtures validate against their repository JSON Schemas; invalid, extra, or incompatible fields are rejected.
14. EntityRelation validation enforces endpoint types, semantic/canonical direction, uniqueness, confirmation provenance, self-link rejection, and acyclic same-type lineage.
15. At 100%, 125%, and 150% Qt scale factors, the 1180 × 720 window retains accessible navigation and controls, has no overlapping/clipped text, and uses only page-vertical or table-internal scrolling.
16. Pure contract/policy tests validate task request fingerprints, side-effect operation keys, retry/lease state transitions, immutable attempt recording, audit undo uniqueness, and the capability permission matrix without running an executor or Agent.

## 15. Acceptance-to-Test Implementation Checklist

The implementation plan must create the named automated checks. A criterion is not complete until its listed tests have been observed failing before implementation and passing afterward.

| Criterion | Automated test or command | Required assertion |
|---|---|---|
| AC1 | `tests/acceptance/test_environment.py::test_runtime_requires_python_3_12`; `uv sync --locked` | metadata requires `>=3.12,<3.13`; locked environment installs without resolution changes |
| AC2 | `tests/acceptance/test_offline_startup.py::test_application_starts_with_network_disabled` | startup reaches main window with socket creation blocked |
| AC3 | `tests/ui/test_navigation.py::test_every_navigation_destination_is_reachable`; `::test_active_navigation_state_follows_page` | all seven destinations load and exactly one nav button is active |
| AC4 | `tests/unit/application/test_get_overview.py`; `tests/ui/test_overview_binding.py::test_overview_renders_view_model_values` | query owns values; controller contains no sample literals and renders injected view model |
| AC5 | `tests/ui/test_coming_soon.py::test_conference_and_grant_are_noninteractive_coming_soon_pages` | both titles render, no unfinished action control is enabled |
| AC6 | `tests/integration/test_fresh_database.py::test_fresh_directory_gets_schema_and_one_seed_dataset`; `::test_seed_is_idempotent` | head migration applied; stable seed IDs occur once after repeated initialization |
| AC7 | `tests/unit/application/test_change_data_directory.py`; `tests/acceptance/test_data_directory_restart.py` | failure/cancel preserves active path; success persists pending path, activates only after restart, and leaves old directory untouched |
| AC8 | `tests/integration/test_migrations.py::test_upgrade_head_is_repeatable`; `::test_failed_seed_rolls_back` | repeated upgrade is a no-op; failure leaves no partial seed/schema mutation |
| AC9 | `uv run pytest -q` | complete unit, contract, integration, UI, and acceptance suite exits 0 without warnings promoted to errors |
| AC10 | `tests/acceptance/test_license_policy.py::test_locked_dependencies_have_reviewed_commercial_licenses`; license inventory command in README | inventory includes every locked distribution dependency and denies GPL/AGPL/unknown entries |
| AC11 | `tests/acceptance/test_repository_structure.py`; `tests/ui/test_ui_object_names.py` | tree matches §4; one `.ui` per page; no forbidden Designer defaults or duplicate runtime UI sources |
| AC12 | `tests/integration/test_schema_contract.py`; `tests/unit/domain/test_entity_invariants.py` | SQLAlchemy metadata plus inspected SQLite constraints exactly match every §7 **DB** rule; domain tests cover every §7 **APP** cross-table/state invariant |
| AC13 | `tests/contracts/test_task_contract.py`; `test_task_result.py`; `test_domain_event.py`; `test_parsed_document.py`; `test_parsed_document_semantics.py` | valid fixtures pass; missing required, wrong enum/type/range, non-UTC time, bad UUID, extra-property, deterministic block-ID, paragraph-ID, ordering, normalization, and overlap violations fail |
| AC14 | `tests/unit/domain/test_relations.py`; `tests/integration/test_relation_observations.py` | exact endpoint enum, directed/symmetric normalization, unique assertion key, append-only idempotent observations, cached confidence, user-only state transitions, self-link rejection, and the specified lineage/extends cycle rules pass |
| AC15 | `tests/ui/test_dpi_scaling.py` parametrized with `1.0`, `1.25`, `1.5`; `tests/ui/test_scrolling.py` | subprocess reports expected scale, visible required controls, non-overlapping widget rectangles, no page horizontal scrollbar, and correct vertical/table scroll policy |
| AC16 | `tests/unit/domain/test_task_idempotency.py`; `tests/unit/domain/test_task_retry_policy.py`; `tests/unit/domain/test_task_permissions.py`; `tests/integration/test_task_attempt_schema.py`; `tests/integration/test_task_effect_recovery.py`; `tests/integration/test_audit_undo_uniqueness.py` | RFC 8785 fingerprints/operation keys are deterministic; final-attempt and expired-lease paths terminate; staged file-effect recovery and external manual-reconciliation policy match §12; attempts/effects are unique; permission denials and single-use undo are enforced without executor/Agent execution |

In addition to automated AC15 coverage, a separate release gate records a manual Windows visual smoke at 100%, 125%, and 150%, including a live move 100%→125%→150%→100% across differently scaled monitors without restart and a screenshot at each state. This is required because offscreen Qt geometry cannot prove native font rasterization or monitor-transition behavior. Manual evidence supplements but never replaces the automated tests and is not counted as an automated acceptance criterion.

## 16. Explicit Non-Goals

The foundation release does not implement document parsing, file monitoring, paper creation forms, Idea editing, submission CRUD, version comparison, AI providers, context recovery, semantic search, real Agent execution, email/calendar integration, OCR, cloud sync, or an installer for public distribution.

These exclusions prevent visual scaffolding from becoming untested pseudo-functionality and keep the first implementation plan independently reviewable.
