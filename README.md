# Research Workspace

**Turn research papers into structured ideas with a controlled AI workflow.**

Research Workspace is a local-first Windows desktop application for managing
research papers, notes, ideas, and follow-up work.

The Build Week demo focuses on one clear workflow:

```text
Create or import a paper
→ inspect the paper workspace
→ analyze the paper with an OpenAI-compatible model
→ review Summary, Key Claims, and Suggested Ideas
→ turn a suggested idea into a saved research idea

The project is built with Python 3.12, PySide6, SQLite, SQLAlchemy, Alembic,
PyInstaller, and a vendor-neutral AI provider interface.

Demo

Demo video: coming soon

Windows portable release:

Tag: v0.3-buildweek-en
Download: see the GitHub Releases page
Executable: app/ResearchWorkspace.exe
No local Python installation is required
Core Product Flow
Paper
→ Research Analysis
→ Suggested Ideas
→ Create Idea
→ Idea Detail

Research Workspace is not designed as a generic chatbot.

AI is embedded inside a structured research workflow and supports the user at a
specific point: turning a paper into reviewable research ideas.

Features
Research workspace
Local-first Windows desktop application
Persistent SQLite workspace
Paper list and Paper Detail workspace
Idea Library and Idea Detail
Research notes, relations, timeline, and next-step guidance
English Build Week interface
AI configuration
OpenAI-compatible provider
Configurable Base URL
Configurable API Key
Configurable model
Masked API key field
Save Settings
Test Connection
Structured paper analysis

The AI workflow returns:

Summary
Key Claims
Suggested Ideas

Each suggested idea contains:

title
content

Suggested ideas are not saved automatically. The user opens the existing Create
Idea dialog, reviews the generated content, and saves it through the normal
workflow.

UI states

Paper analysis supports:

not configured
ready
loading
success
failure

The UI does not display raw JSON, provider payloads, or chain-of-thought text.

Controlled AI Development Workflow

The main result of this project is not only the application itself, but also the
development process used to build it.

The project followed a checkpoint-driven workflow:

Discuss
→ Define
→ Freeze Scope
→ Implement
→ Test
→ Generate Screenshots
→ Review
→ Accept or Reject
→ Commit
→ Stop

Each feature was treated as a separate, verifiable checkpoint.

Codex was not asked to build the entire application in one prompt. Instead, each
task had:

a frozen scope
explicit exclusions
focused tests
UI screenshots
regression checks
a commit boundary
a mandatory stop for review

This prevented uncontrolled feature expansion and made every iteration
reversible.

How GPT-5.6 and Codex Were Used
GPT-5.6

GPT-5.6 was used for:

product definition
requirement refinement
scope control
architecture review
UX evaluation
screenshot acceptance
risk identification
prioritization of the next checkpoint

It helped convert high-level product intent into concrete, testable development
tasks.

For example:

The demo should be Paper → AI → Idea

was translated into:

a vendor-neutral AIProvider interface
an OpenAI-compatible implementation
an AI Settings surface
structured PaperAnalysis output
loading, success, and failure states
Suggested Idea handoff into the existing Create Idea workflow
Codex

Codex was used for:

implementation
test creation
focused regression checks
full test-suite execution
UI screenshot generation
packaging
Git commits
release preparation

The execution loop was:

frozen task
→ implementation
→ focused tests
→ screenshots
→ full regression
→ commit
→ stop for review

The project therefore used AI as a controlled product-engineering workflow,
rather than as one-shot code generation.

Example of the Review Process

The UI was not accepted simply because it worked.

Several iterations were rejected after screenshot review:

Paper Detail initially failed to guide the user toward Idea creation.
The first Paper workspace layout gave too much space to the list and too
little to the detail panel.
The English empty state contained stray square glyphs.
The empty Paper state incorrectly displayed Edit, Move to Trash, and Restore
controls.

Each issue was returned as a narrowly scoped task, fixed, retested, reviewed,
committed, and stopped.

This process kept the application visually coherent while preserving the
existing architecture.

Architecture

The AI slice follows this dependency direction:

Presentation
→ Application
→ AIProvider interface
→ OpenAI-compatible provider implementation

Presentation and Application code do not depend on OpenAI-specific SDK classes.

The structured result is:

PaperAnalysis
- summary
- key_claims
- suggested_ideas
  - title
  - content

The AI workflow does not modify:

Domain entities
repositories
ORM mappings
migrations
undo
recovery
submission logic
relation logic

Suggested Ideas are passed into the existing Create Idea dialog and are not
automatically persisted.

Technology Stack
Python 3.12
PySide6
SQLite
SQLAlchemy
Alembic
JSON Schema
PyInstaller
pytest
pytest-qt
Test Status

The current Build Week AI demo commit passed:

Focused AI tests: 11 passed
Focused UI / Gate3 UI regression: 34 passed
Full suite: 1168 passed

Additional checks included:

git diff --check
git status --short

Automated tests do not call a live AI API.

Running from Source

Requirements:

Python 3.12
uv

Install dependencies and start the application:

uv sync --locked
uv run python app.py

Run the full test suite:

uv run pytest -q
Building the Windows Portable Package

From the repository root:

powershell -ExecutionPolicy Bypass `
  -File packaging\windows\build_portable.ps1 `
  -OutputRoot ".\dist" `
  -IconPath "C:\path\to\app-icon.png"

The script creates a PyInstaller onedir package and a ZIP containing:

app/ResearchWorkspace.exe
Build Week Release

English Build Week version:

Branch: build/v0.2-personal-portable
Tag: v0.3-buildweek-en
Target: Devpost, judges, and demo video

Portable ZIP:

ResearchWorkspace-v0.3-buildweek-en-win64.zip

SHA-256:

db2178fc219d78c60d183c2b47cccdac9182d1a781edbd0bf0238049a115db6a
Included in the Build Week Demo
local Windows desktop application
persistent research workspace
Paper and Idea workflow
OpenAI-compatible paper analysis
Summary, Key Claims, and Suggested Ideas
Suggested Idea handoff
Windows portable EXE package
checkpoint-driven AI development workflow
Not Included

The Build Week demo intentionally excludes:

chat UI
streaming
RAG
embeddings
vector database
PDF analysis pipeline
batch analysis
multi-provider comparison
automatic idea saving
Submission workflow expansion
Relation graph expansion
cloud sync
installer
auto-update
digital signing
Version Plan
English Build Week version
Branch: build/v0.2-personal-portable
Tag: v0.3-buildweek-en
Target: Devpost and judges
Chinese friend-use version

Planned branch:

localization/zh-cn-friend

The Chinese version will change presentation text and packaging only. It will
not change the core business logic.

Release Note

This is a Build Week demo release, not a production-ready public release.

The application is intended to be tested as a Windows portable ZIP. Installer
support, signing, automatic updates, broader distribution hardening, and public
production support remain future work.
