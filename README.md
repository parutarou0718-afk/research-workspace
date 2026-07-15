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
