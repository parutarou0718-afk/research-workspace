# 科研工作台 / Research Workspace

Research Workspace v0.1 is a local-first Windows desktop foundation for
recovering research context. It uses Python 3.12, PySide6, SQLite, SQLAlchemy,
and Alembic. The application starts and initializes its workspace without
network access.

## Requirements and startup

Install Python 3.12 and `uv`, then create the exact locked environment and start
the desktop application:

```powershell
uv sync --locked
uv run python app.py
```

The project metadata intentionally requires Python `>=3.12,<3.13`.

## Database migrations

The application applies the Alembic migration automatically when it initializes
a new workspace. To apply the locked migration explicitly from the repository
root, run:

```powershell
uv run alembic upgrade head
```

The migration is repeatable. The local data directory can be changed in
Settings; a successful change becomes active only after restart, while the old
directory remains untouched.

## Tests

Qt tests run headlessly on Windows with the offscreen platform:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
uv run pytest -q
```

Run the commercial-license release check separately when reviewing dependency
changes:

```powershell
uv run pytest tests/acceptance/test_license_policy.py -v
```

The check compares the installed inventory with every third-party distribution
in `uv.lock`, excludes only the first-party `research-workspace` distribution,
and fails closed for empty, unknown, GPL, AGPL, or unreviewed licenses. LGPL is
allowed only for the four Qt runtime distributions recorded in
`THIRD_PARTY_NOTICES.md`.

## Third-party inventory

Regenerate the inventory from the locked Python 3.12 environment with this exact
command:

```powershell
uv run pip-licenses --format=markdown --with-urls --with-license-file
```

On a Windows console that is not UTF-8, set `PYTHONUTF8=1` or use the tool's
UTF-8 `--output-file` option. `pip-licenses` omits itself, `prettytable`, and
`wcwidth`; their locked name, version, license, and URL must remain in the
supplementary table in `THIRD_PARTY_NOTICES.md`.

## v0.1 verification record

The foundation milestone was re-verified on 2026-07-16 with Python 3.12.10,
pytest 9.1.1, PySide6 6.11.1, and Qt 6.11.1. These commands and results were
observed from the locked environment:

```powershell
uv lock --check
# PASS: exit 0; 31 locked packages resolved without changing uv.lock

uv run pytest tests/acceptance/test_environment.py tests/acceptance/test_repository_structure.py tests/contracts -v
# PASS: 77 passed

uv run pytest tests/unit tests/integration -v
# PASS: 415 passed

$env:QT_QPA_PLATFORM='offscreen'
uv run pytest tests/ui tests/acceptance -v --disable-socket
# PASS: 52 passed, including the license-policy check

$env:QT_QPA_PLATFORM='offscreen'
uv run pytest -q
# PASS: 542 passed

uv run python -m compileall -q app.py src tests migrations
git diff --check
# PASS: both commands exited 0 with no output
```

The Task 1 SHA-256 capture matched all eight immutable research, design, and UI
assets. The six Task 2 contract files matched the approved normative content.
No new reproducible defect was found during this verification.

## Release blocker and scope ledger

- **REL-GATE-001 — Windows mixed-DPI manual release verification**
  - Type: manual release verification
  - Status: `BLOCKED_BY_ENVIRONMENT`
  - Blocks: public packaged release only
  - Does not block: v0.2 internal development

  Native Windows mixed-monitor visual smoke and
  screenshots for a live 100%→125%→150%→100% move remain unverified. No
  packaged development executable or verified multi-scale monitor set was
  available. Automated offscreen geometry tests passed at 100%, 125%, and
  150%, but they do not prove native font rasterization or monitor transitions.
- **Explicit v0.1 non-goals are not bugs:** the capabilities listed below were
  deliberately excluded from the foundation milestone and must not be logged
  as reproduced defects.
- **Technical risks:** no additional evidence-based technical risk was
  reproduced during this verification.

Complete release readiness is not claimed while the manual mixed-DPI gate is
unresolved.

## Current v0.1 functions

- Seven reachable desktop destinations: Overview, Papers, Ideas, Submissions,
  Conferences, Grants, and Settings.
- Only Overview is backed by the application query and seeded local data.
- Papers, Ideas, and Submissions are foundation placeholders.
- Conference and Grant pages shown as noninteractive coming-soon views.
- Workspace initialization, repeatable migrations, idempotent seed data, and a
  restart-safe data-directory preference.
- Offline startup, schema/contract validation, task policy contracts, and
  responsive offscreen Qt coverage at 100%, 125%, and 150% scale factors.

## Explicit non-goals

This foundation release does not implement document parsing, file monitoring,
paper creation forms, Idea editing, submission CRUD, version comparison, AI
providers, context recovery, semantic search, real Agent execution,
email/calendar integration, OCR, cloud sync, or a public installer. Conference
and Grant workflows are placeholders, not interactive product functions.

Original research and design files are never overwritten by application or AI
workflows.
