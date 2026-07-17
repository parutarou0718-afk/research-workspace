# UX-01 Research Flow Validation

## Executive Summary

The current Build Week demo flow is usable and coherent enough for an internal walkthrough: a user can launch the app, recognize the main workspace shell, navigate to Papers, create a paper, inspect its detail panel, navigate to Ideas, create an idea, inspect Idea Library, open Idea Detail, and exit without touching backend or technical screens.

The strongest parts of the flow are the new product shell, the Papers workspace, Idea Library, and Idea Detail. These pages now feel like a research workspace rather than a database admin tool. The selected-card pattern, right-side detail panels, empty states, and explicit AI placeholders make the product direction understandable.

The main weakness is that the flow is not yet fully self-guiding. Paper Detail does not strongly tell the user that the next meaningful action is to capture an idea from the paper. A judge can still complete the flow, but only if they already know to switch from Papers to Idea Library manually. This is the most important improvement before AI work begins.

The second weakness is a presentation mismatch between the redesigned pages and the legacy editor dialogs. The pages feel like Product Mode; the Paper and Idea creation dialogs still feel like basic forms with internal status choices. This does not block the demo, but it breaks the illusion a little.

Overall demo readiness is promising. The product value can be explained in 30 seconds, and the Paper -> Idea path can be demonstrated in under two minutes with light narration. It is not yet fully "no narration required."

## Flow Review

### 1. Launch

- Current behavior
  - The app opens into the Research Workspace shell with a persistent left sidebar and Dashboard as the default page.
  - Navigation is stable and always visible.

- Positive observations
  - The product frame is clear: this is a workspace, not a file converter or isolated CRUD app.
  - Sidebar persistence helps the user know where they are.
  - The product name is visible immediately.

- Issues
  - Some navigation/page labels remain mixed between Chinese and English across the current UI surface.
  - The first screen communicates "research management," but the fastest path to the demo flow is not explicitly called out.

- Severity
  - Medium

- Suggested improvement
  - Add a first-run or dashboard-level "Start here" prompt that points to Papers: "Create or import your first paper."
  - Keep language consistent for the Build Week demo surface.

### 2. Dashboard

- Current behavior
  - Dashboard shows high-level status cards, AI suggestions, quick record, and submission overview.
  - The sidebar can take the user to Papers or Ideas.

- Positive observations
  - The dashboard gives a credible research OS first impression.
  - KPI cards and the quick-record area make the page feel alive even before AI is implemented.
  - Empty AI suggestions are handled rather than leaving a blank white area.

- Issues
  - The most demo-relevant next action is not obvious. A first-time user may wonder whether to use quick record, organize now, import data, or Papers.
  - Submission appears on the dashboard even though Submission is not part of the Build Week core story.

- Severity
  - Medium

- Suggested improvement
  - Add a compact "Next step" card for the demo path: "Create your first paper" or "Open Papers."
  - Reduce visual priority of Submission during the Build Week story unless it has demo data.

### 3. Create Paper

- Current behavior
  - User navigates to Papers and clicks "+ New Paper."
  - A Paper editor dialog appears.
  - After saving, the page refreshes and the paper list/detail area can show the new paper.

- Positive observations
  - The Papers page has a clear top-level action.
  - Empty state also provides a Create Paper action.
  - The action is easy to discover from the Papers page.

- Issues
  - The editor dialog still feels like an internal form rather than part of the new design system.
  - Status choices expose implementation-like states rather than a guided authoring flow.
  - The dialog does not explain what happens after saving.

- Severity
  - Medium

- Suggested improvement
  - Redesign the Paper editor dialog later using the shared Design System.
  - Prefer a minimal first-paper form for the demo: title first, optional status hidden or defaulted.
  - Add helper text: "After saving, this paper will appear in your Paper workspace."

### 4. Open Paper Detail

- Current behavior
  - Selecting a paper shows a right-side Paper Detail panel with metadata, abstract, notes, timeline, AI Summary placeholder, related ideas, related papers, and relations.

- Positive observations
  - The split list/detail layout is strong.
  - The AI Summary placeholder clearly reserves the future AI insertion point.
  - Related Ideas and Relations sections prepare the user for the later AI workflow.

- Issues
  - The page does not explicitly guide the user from Paper Detail to creating an Idea.
  - "AI Summary" is present, but there is no actionable "Analyze with AI" placeholder on Paper Detail yet.
  - Empty/detail text is useful but somewhat passive.

- Severity
  - High

- Suggested improvement
  - Add a Paper Detail "Next Step" section: "Capture an idea from this paper" with a "Create Idea" action.
  - Add a Paper AI placeholder matching the Idea Detail pattern:
    - "No analysis yet."
    - "Analyze this paper to generate summary, key claims, and suggested ideas."
    - "Analyze with AI"
    - "Available in the next milestone."

### 5. Create Idea

- Current behavior
  - User navigates to Idea Library and clicks "+ New Idea."
  - Idea editor dialog collects title, status, and Markdown content.
  - After saving, Idea Library refreshes.

- Positive observations
  - Idea Library has a clear create button and a helpful empty state.
  - The page communicates "capture research fragments" rather than "manage database rows."
  - Search is visible and understandable.

- Issues
  - There is no direct Create Idea handoff from Paper Detail.
  - The editor dialog still exposes status and Markdown in a technical way.
  - For the demo story, the user may not understand that the idea should be derived from the paper they just viewed.

- Severity
  - High

- Suggested improvement
  - Provide a Paper Detail -> Create Idea entry point that pre-frames the action as "Capture an idea from this paper."
  - Later, simplify the Idea editor copy for non-technical users: "Idea content" instead of "Markdown content."

### 6. Idea Library

- Current behavior
  - Ideas appear as cards with title, type, preview, related-paper count, relation count, tags, and update marker.
  - Selecting an item highlights the card and updates Idea Detail.

- Positive observations
  - The page now reads as a library of research thoughts, not a table.
  - Selection state is visually clear.
  - Empty state is product-like: "No ideas yet. Capture your first research idea."
  - The search/filter toolbar gives a scalable structure for more data.

- Issues
  - Related paper and relation counts currently read like fixed/demo values rather than live contextual truth.
  - Type and Tags controls appear as filters, but their exact interaction is not obvious yet.

- Severity
  - Low

- Suggested improvement
  - Use neutral placeholder wording if live counts are not yet backed by real data.
  - If filters are not interactive yet, make them visually less primary or add a small "coming later" affordance.

### 7. Idea Detail

- Current behavior
  - Selecting an idea shows Content, Research Notes, Related Papers, Relations, Timeline, AI Suggestions, and Next Step.
  - AI Suggestions is informational only.

- Positive observations
  - This is currently the clearest "what happens next" page in the demo flow.
  - The AI placeholder is well scoped and does not pretend AI is implemented.
  - The "Next Step" section explicitly guides the user toward AI without creating fake behavior.
  - The empty detail state tells the user to select an idea.

- Issues
  - The content hierarchy is good, but the lower cards can become vertically long on smaller screens.
  - Related Papers, Relations, and Timeline are placeholder-heavy; this is acceptable now but should not dominate the demo.

- Severity
  - Low

- Suggested improvement
  - Keep Idea Detail as the reference pattern for Paper AI placeholder work.
  - When AI is implemented, preserve this structure rather than introducing chat as the primary surface.

### 8. Exit

- Current behavior
  - Closing the window triggers service close handling.
  - Created data should persist through the existing command/database path.

- Positive observations
  - The flow does not require special shutdown behavior.
  - Existing persistence architecture is not exposed to the user.

- Issues
  - The UI does not explicitly reassure users that changes are saved.

- Severity
  - Low

- Suggested improvement
  - Add subtle save/completion feedback after Paper and Idea creation, such as a status toast or inline "Saved" message.

## Cross-page Findings

### Navigation

- The sidebar is stable and effective.
- The main gap is not navigation availability, but flow guidance: Paper Detail should guide the user toward Idea creation.
- The demo path currently relies on the presenter knowing to click Ideas after viewing a Paper.

### Visual hierarchy

- Dashboard, Papers, Idea Library, and Idea Detail now have a coherent card-based hierarchy.
- Editor dialogs remain visually older than the pages.
- Paper Detail lacks the same strong "Next Step" affordance that Idea Detail has.

### Terminology consistency

- Product language is strongest on the newly redesigned pages.
- Some labels still mix languages or expose technical terms such as status enum-like values and Markdown.
- Build Week should prioritize consistent user-facing copy on the main demo path.

### Next Step guidance

- Idea Detail passes this requirement.
- Dashboard partially passes; it shows possible areas but not the recommended first path.
- Paper Detail is the main gap.
- Editor dialogs do not explain what happens after saving.

### Empty states

- Idea Library and Idea Detail have helpful empty states.
- Papers has a useful create action in the empty state.
- Dashboard has non-blank empty suggestions.
- Empty states are good enough for Build Week, but the wording should be aligned into one voice.

## Demo Readiness

- Can a judge understand the product in 30 seconds?
  - Yes, with light narration. The shell, Dashboard, Papers, and Ideas communicate "research workspace." Without narration, the exact Paper -> Idea story is not fully obvious yet.

- Can the complete Paper -> Idea workflow be demonstrated in under 2 minutes?
  - Yes. The workflow is short enough: Dashboard -> Papers -> New Paper -> Save -> Ideas -> New Idea -> Save -> Idea Detail. The number of clicks is acceptable, but the transition from Paper to Idea is not self-guiding.

- Is the AI insertion point obvious?
  - Partially. Idea Detail makes the AI insertion point obvious. Paper Detail has an AI Summary placeholder, but it should be upgraded to match the Idea Detail AI placeholder before AI work begins.

- Is there any blocker for Build Week?
  - No hard blocker. The main risk is demo coherence rather than functionality. A judge can complete the flow, but the presenter currently has to narrate why the user moves from Paper Detail to Idea Library.

## Recommendations

1. High - Add a Paper Detail "Next Step" section guiding the user to capture an idea from the selected paper.

2. High - Add a Paper AI placeholder matching the Idea Detail pattern before implementing AI behavior.

3. Medium - Add a Dashboard start-here affordance for the Build Week story: "Create your first paper" or "Open Papers."

4. Medium - Redesign Paper and Idea editor dialogs later so they match the Design System and reduce technical wording.

5. Medium - Avoid showing Submission as a primary Dashboard concern during the Build Week demo unless it is intentionally part of the story.

6. Low - Add subtle saved/completed feedback after create actions.

7. Low - Align empty-state copy across Dashboard, Papers, and Ideas into one product voice.

8. Low - Keep Idea Detail as the model for future AI surfaces: structured panel first, chat later only if it serves the workflow.
