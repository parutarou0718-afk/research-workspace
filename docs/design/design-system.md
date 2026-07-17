# Research Workspace Design System

Status: baseline for UI Phase 2  
Product posture: Research Workspace first, AI second

This document is the visual contract for Research Workspace UI work after
`v0.2-personal`. It is intentionally not a code file. UI commits must conform to
this system before adding or reshaping product pages.

## 1. Product Direction

Research Workspace is a structured research workbench, not an AI chat shell and
not a database admin tool. AI should appear as an enhancement inside research
workflows, especially on paper detail surfaces, rather than becoming the main
navigation or primary layout metaphor.

Preferred references:

- Linear
- Notion Desktop
- ChatGPT Desktop
- Raycast

Avoid:

- ERP dashboards
- default Qt utility layouts
- dense database tables as the primary experience
- Office-style back office screens
- fake graph or fake AI surfaces

## 2. Color

| Token | Value | Use |
| --- | --- | --- |
| Background | `#F6F8FC` | Main page background |
| Surface | `#FFFFFF` | Cards, panels, dialogs |
| Primary | `#4F7DFF` | Primary actions, selected navigation |
| Primary Hover | `#356AE6` | Primary hover / active text |
| Primary Soft | `#EEF4FF` | Selected navigation and subtle emphasis |
| Text Primary | `#172033` | Main text |
| Text Secondary | `#667085` | Descriptions and metadata |
| Text Muted | `#98A2B3` | Disabled/help text |
| Border | `#E4E7EC` | Card/input/table borders |
| Success | `#16A34A` | Accepted/success states |
| Warning | `#D97706` | Revision/warning states |
| Danger | `#DC2626` | Rejected/destructive states |

Do not introduce page-local accent colors without updating this document.

## 3. Typography

Primary runtime font:

```text
Microsoft YaHei UI
```

Design token stack:

```text
Segoe UI Variable, Microsoft YaHei UI
```

Qt stylesheet fallback is unreliable on some Windows/plugin combinations, so
runtime styles may explicitly choose `Microsoft YaHei UI` to keep Chinese text
readable.

| Role | Size | Weight |
| --- | ---: | ---: |
| Page title | 24 px | 600 |
| Section title | 16 px | 600 |
| Body | 14 px | 400 |
| Helper / metadata | 12 px | 400 |
| KPI number | 28 px | 600 |

## 4. Spacing, Radius, and Shadow

| Token | Value |
| --- | ---: |
| Page margin | 24 px |
| Section gap | 24 px |
| Card padding | 20 px |
| Dense card padding | 16 px |
| Control gap | 8 px |
| Large card radius | 16 px |
| Current card radius floor | 14 px |
| Control radius | 10 px |
| Current control radius floor | 8 px |
| Light shadow | `0 1px 3px rgba(16,24,40,0.06)` |

UI Phase 2 should converge shared components to the larger values above. Legacy
UI-01 cards at 14 px and controls at 8 px are acceptable only until the shared
component pass replaces them.

## 5. Components

### Button

Every visible button must map to one of four variants.

| Variant | Use | Visual |
| --- | --- | --- |
| Primary | Main page action | Primary fill, white text |
| Secondary | Standard action | Surface fill, border, primary/primary text |
| Ghost | Low-emphasis action | Transparent, no border unless focused |
| Danger | Destructive action | Danger color, never used for ordinary cancel |

Rules:

- Height: 40 px after shared component pass.
- Radius: 10 px after shared component pass.
- Hover must be visible but subtle.
- Disabled buttons are allowed only for a real unavailable existing operation.
- Do not show future features as disabled placeholders.

### Card

Cards are the default information container.

Rules:

- Surface background.
- 1 px border.
- Shared radius and padding.
- Light shadow only when separation is needed.
- No Qt `QGroupBox` default chrome.
- No page-specific card border/radius unless the design system changes.

### Input

Inputs must feel like search/workbench controls rather than raw Qt fields.

Rules:

- Height: 40 px after shared component pass.
- Radius: 10 px after shared component pass.
- Border: design-system border color.
- Focus: primary blue outline or border.
- Placeholder: specific and task-oriented.

### Badge

Badges are used for workflow state, not raw internal enum display.

Approved examples:

| Product state | Color family |
| --- | --- |
| Draft / Preparing | Gray |
| Ready | Blue |
| Submitted / Review | Blue or purple |
| Revision | Warning |
| Accepted | Success |
| Rejected | Danger |
| Archived | Gray |

Internal enum values such as `external_review`, `revision`, or `ready` must not
appear directly in the UI.

### Empty State

Empty states are product copy, not placeholders.

Pattern:

```text
Icon
Title
One-sentence explanation
Primary or secondary action when a real operation exists
```

Avoid:

```text
暂无数据
No data
blank white panels
fake disabled actions
```

Example for Papers:

```text
No papers yet.
Import your first paper to start building your research workspace.
[Import Paper]
```

For Chinese UI, use similarly specific copy instead of generic `暂无数据`.

### Dialog

Dialogs must stay task-focused.

Rules:

- Use the same Button/Input/Card primitives.
- No business rules inside dialog controller code.
- Dialog layout remains Designer-owned (`.ui`).

### Toast / Inline Feedback

Toast behavior is not implemented yet. Until it exists, use inline status areas
already present in the relevant page/dialog. Do not invent a new notification
system inside a page.

### Loading / Skeleton

Loading states should be explicit and non-alarming.

Allowed patterns:

- short inline text;
- subtle skeleton card placeholder;
- progress label for long operations.

Do not block the main UI thread for visual loading states.

### Icons

Use one line-icon family: Lucide-style SVG assets.

Required semantic set:

```text
Dashboard
Paper
Idea
Relation
Submission
Calendar
Import
Monitor
Candidate
Bot
Settings
Search
Filter
Plus
Archive
Alert
Check
X
```

Rules:

- Do not mix emoji, Windows shell icons, and text-character pseudo-icons.
- Do not use filled icons beside line icons unless the system is updated.
- If an icon asset is missing, add the asset before using the concept.

## 6. Page Direction

### Dashboard

UI-01 establishes the first dashboard baseline. Do not keep refining dashboard
until the shared system and core pages catch up.

### Paper

Paper is the most important Build Week surface.

The page should support:

- search;
- status/year/tag filters;
- new paper action;
- paper cards or list rows, not a full-screen raw table;
- detail surface with:
  - Metadata
  - Abstract
  - Research Notes
  - Timeline
  - AI Summary
  - Related Ideas
  - Related Papers
  - Relations

`AI Summary` may initially be an honest placeholder. It should reserve the
future slot without adding AI behavior.

### Idea

Idea should feel closer to a knowledge workspace than a database table.

Preferred groups:

- Resultative / Theory
- Supporting
- Questions
- Evidence

Cards should show title, type, excerpt, linked papers, tags, and update time.

### Submission

Submission should use a lightweight Kanban layout.

Columns:

- Draft
- Ready
- Submitted
- Review
- Revision

Accepted and Rejected should be archive/history surfaces, not primary daily
workflow columns.

### Relation

Do not draw a fake graph.

Use:

- honest `Relation Graph` coming-soon panel;
- relation cards/list beneath it;
- source, target, relation type, evidence, status, and decision entry when a
  real existing operation supports it.

## 7. Responsive and DPI Rules

Every page-level UI task must provide screenshots or automated geometry evidence
for:

```text
1366×768 at 100%
1920×1080 at 100%
1920×1080 at 150%
```

Required checks:

- no control clipping;
- no text overlap;
- no page-level horizontal scrollbar;
- navigation selected state remains visible;
- Chinese and English copy do not overflow obvious containers.

## 8. Implementation Rules

Allowed UI Phase 2 changes:

- Qt `.ui` files;
- QSS/style resources;
- icon/static resources;
- presentation controllers for view binding only;
- read projections only when required for display and already backed by
  approved facts.

Forbidden:

- Domain changes;
- Application command behavior changes;
- Repository, ORM, Session, Migration, or Schema changes;
- Audit, Undo, Recovery behavior changes;
- Gate 2 or Gate 3 semantic changes;
- fake disabled controls for future features;
- page-local custom components that duplicate shared Button/Card/Input/Badge.

## 9. Checkpoint Order

UI Phase 2 should proceed in this order:

1. Checkpoint A: Design tokens, shared components, sidebar, Button, Card, Input,
   Badge, Empty State.
2. Checkpoint A.5: Responsive and DPI verification for shared components.
3. Checkpoint B: Paper.
4. Checkpoint C: Idea.
5. Checkpoint D: Submission.
6. Checkpoint E: Relation.

Paper, Idea, Submission, and Relation must consume shared components instead of
defining page-local button/card/input/badge styles.
