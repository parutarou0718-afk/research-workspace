# Research Workspace

Research Workspace is a local-first Windows desktop app for turning research
papers into structured notes, ideas, and follow-up work. The Build Week demo
focuses on one clear story:

```text
Create or import a paper
→ inspect the paper workspace
→ analyze the paper with an OpenAI-compatible model
→ turn a suggested idea into a saved research idea
```

The project is built with Python 3.12, PySide6, SQLite, SQLAlchemy, Alembic,
PyInstaller, and an OpenAI-compatible AI provider interface.

## Build Week demo status

The English Build Week branch is:

```text
build/v0.2-personal-portable
```

The English demo tag is:

```text
v0.3-buildweek-en
```

The Windows portable package is built as a ZIP containing:

```text
app/ResearchWorkspace.exe
```

The app does not require a local Python installation after packaging.

Current local English portable build:

```text
E:\research assistant\portable-output-ai01\ResearchWorkspace-v0.2-personal-win64.zip
```

SHA-256:

```text
db2178fc219d78c60d183c2b47cccdac9182d1a781edbd0bf0238049a115db6a
```

Smoke result:

```text
ResearchWorkspace.exe started: true
CloseMainWindow: true
Exit code: 0
```

## Features in the demo

- Local SQLite workspace initialization
- Paper workspace with card/list layout and detail panel
- Idea Library and Idea Detail views
- Settings page with OpenAI-compatible AI configuration
- AI Settings:
  - provider label
  - configurable base URL
  - masked API key
  - configurable model
  - Save Settings
  - Test Connection
- Paper Detail research analysis states:
  - not configured
  - ready
  - loading
  - success
  - failure
- Structured AI analysis:
  - Summary
  - Key Claims
  - Suggested Ideas
- Suggested idea handoff into the existing Create Idea dialog
- No automatic idea saving; the user reviews and saves normally

Compatibility note for the v0.2 lineage: Overview and Imports are backed by application queries. Importing documents creates local immutable snapshots.
Papers, Ideas, and Submissions are foundation placeholders. They were expanded
into the current protected editing workflow.

## How I collaborated with Codex

This project was built through an iterative collaboration with Codex and
GPT-5.6. Codex was not used as a one-shot code generator. Instead, I treated it
as a product-engineering partner that could help me move between architecture,
implementation, UI iteration, packaging, and release preparation while I made
the key product decisions.

### My role in the collaboration

I directed the product vision and the decision-making. The main product
direction was:

- build a real research workspace, not a generic chatbot;
- keep AI as an enhancement layer inside the research workflow;
- make the demo story understandable in under three minutes;
- prioritize Paper → AI → Idea over adding many unrelated pages;
- keep English Build Week and Chinese friend-use builds as separate versions;
- ship a Windows portable EXE instead of asking judges to run from source.

I also made the major scope decisions throughout the project:

- Gate 1 focused on deterministic import and parsing.
- Gate 2 focused on monitoring and version candidates.
- Gate 3 focused on protected CRUD, audit, undo, relations, and UI.
- Build Week work shifted into Product Mode, where each page or interaction was
  reviewed visually and committed in small reversible steps.
- The AI slice was intentionally kept small: no chat UI, no streaming, no RAG,
  no embeddings, no multi-provider UI, and no automatic idea creation.

### Where Codex accelerated the workflow

Codex accelerated the project in several concrete ways:

1. **Architecture and boundary control**

   Codex helped maintain strict boundaries between Presentation, Application,
   Infrastructure, Domain, Repository, Migration, Undo, Recovery, and Worker
   code. When a task risked crossing those boundaries, the workflow paused for a
   specification stop instead of silently changing the architecture.

2. **Test-driven implementation**

   Most major backend and UI changes were implemented by writing or identifying
   failing tests first, observing the real RED state, then making the smallest
   useful GREEN change. This kept the project from turning into uncontrolled
   “vibe coding.”

3. **Large-scale verification**

   Codex repeatedly ran focused tests, UI regression tests, Gate acceptance
   tests, full pytest suites, `git diff --check`, and clean `git status`
   checks. The current AI demo commit passed:

   ```text
   Focused AI tests: 11 passed
   Focused UI / Gate3 UI regression: 34 passed
   Full suite: 1168 passed
   ```

4. **UI and product iteration**

   Codex helped rapidly iterate from a traditional Qt-looking app into a more
   polished Research Workspace interface. I reviewed screenshots, rejected
   layouts that felt too database-like, and redirected the work toward a design
   system, Paper workspace, Idea Library, and clear “Next Step” guidance.

5. **Packaging and release preparation**

   Codex helped create and validate the PyInstaller portable build path,
   inspect package contents, produce a ZIP artifact, smoke-test the EXE startup,
   and push the English Build Week branch and tags to GitHub.

### How GPT-5.6 and Codex contributed to the final result

GPT-5.6 was most useful as the reasoning layer behind Codex. It helped connect
product intent to concrete engineering steps: for example, translating “the
demo should be Paper → AI → Idea” into a vendor-neutral AI provider interface,
settings UI, Paper Detail state machine, structured response validation, and
existing Idea dialog handoff.

Codex contributed the execution loop:

```text
product direction
→ implementation plan
→ focused tests
→ code changes
→ UI screenshots
→ full regression
→ commit
→ stop for review
```

That loop made it possible to move quickly without losing control of the code
base. The final Build Week result is not just an AI prompt wrapped in a UI; it
is a runnable desktop research workspace with persistent local data, a
structured paper-to-idea workflow, and a minimal AI layer that fits naturally
into that workflow.

## Architecture overview

The Build Week AI slice follows this boundary:

```text
Presentation
→ Application
→ AIProvider interface
→ OpenAI-compatible provider implementation
```

Presentation and Application code do not import OpenAI-specific SDK classes.
The current implementation uses a small OpenAI-compatible HTTP provider and a
strict structured response model:

```text
PaperAnalysis
- summary
- key_claims
- suggested_ideas
  - title
  - content
```

The AI flow does not modify Domain entities, repositories, migrations, undo,
recovery, submission logic, or relation logic. Suggested ideas are passed into
the existing Create Idea dialog and are not saved automatically.

## Running from source

Install Python 3.12 and `uv`, then run:

```powershell
uv sync --locked
uv run python app.py
```

Run the full test suite:

```powershell
uv run pytest -q
```

## Building the Windows portable ZIP

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_portable.ps1 `
  -OutputRoot "E:\research assistant\portable-output-ai01" `
  -IconPath "C:\path\to\app-icon.png"
```

The script creates a PyInstaller `onedir` package and a ZIP containing
`app/ResearchWorkspace.exe`.

## Project scope and non-goals

Included in the Build Week demo:

- local desktop app;
- persistent workspace data;
- Paper and Idea demo flow;
- OpenAI-compatible paper analysis;
- suggested idea handoff;
- Windows portable EXE packaging.

Not included in the Build Week demo:

- chat UI;
- streaming;
- RAG;
- embeddings;
- multi-provider UI;
- automatic idea saving;
- Submission workflow expansion;
- Relation graph expansion;
- cloud sync;
- installer;
- auto-update;
- digital signing.

## Version plan

Two versions are planned:

1. **English Build Week version**
   - branch: `build/v0.2-personal-portable`
   - tag: `v0.3-buildweek-en`
   - target: Devpost / judges / demo video

2. **Chinese friend-use version**
   - planned branch: `localization/zh-cn-friend`
   - target: a separate Chinese portable ZIP
   - scope: UI text and packaging only, not business logic changes

Keeping these as separate versions avoids mixing Build Week English submission
requirements with the friend-facing Chinese build.

## Release note

This is a Build Week demo build, not a public production release. The app is
intended to be tested as a Windows portable ZIP. Public release readiness,
installer work, signing, automatic updates, and broader distribution hardening
remain future work.
