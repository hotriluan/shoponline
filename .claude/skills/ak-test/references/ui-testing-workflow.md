# UI Testing Workflow

Use `ak-agent-browser` for live browser interaction when a fresh/tool-managed browser is enough. Use `ak-chrome-profile` only when the test needs the user's real Chrome profile, cookies, or already-logged-in state. Use `ak-web-testing` or project-native Playwright/Vitest/k6 commands for repeatable test runs.

## Purpose
Verify the requested UI contracts with bounded browser work and report the
observed scope. A focused change does not imply a whole-application audit.

## Arguments
- $1: URL - The URL of the website to test
- $2: OPTIONS - Optional test configuration (e.g., --headless, --mobile, --auth)

## Testing Protected Routes (Authentication)

### Step 1: Resolve test authentication
Prefer approved project test accounts and auth fixtures in an isolated environment.
Ask for manual login only when needed; do not request cookie/token exports or use
real customer data. Existing real-profile access must be necessary and authorized.

### Step 2: Persist Auth State Or Select The Chrome Profile
Prefer project-native auth helpers for repeatable tests. For ad-hoc browser driving with real user auth/cookies, invoke `ak-chrome-profile` and run:

```bash
chrome-profile doctor
chrome-profile setup
chrome-profile list
```

If real user Chrome state is not needed, use `agent-browser` state commands after manual login when available.

### Step 3: Run Tests
After auth is available, run tests normally. If real user Chrome state is not needed:
```bash
agent-browser open https://example.com/dashboard
agent-browser screenshot -o profile.png
```

If real user Chrome state is needed:

```bash
chrome-profile open --json work https://example.com/dashboard
```

Then select the MCP page whose URL contains the returned `bind_selector` such as `cdp-open=<token>`, verify it also contains `cdp-profile=work`, and capture screenshots or snapshots through the active bridge.

This restriction applies only when real user Chrome state is required. For profile-scoped testing, do not use raw Chrome MCP `new_page` or `navigate_page` as the opening path. Those tools use whichever profile/page the bridge currently targets.

## Workflow

1. State a narrow charter: accepted expectation, target journey/control, affected
   routes, account/data boundary and mandatory checks. Separate a goal that may
   use different paths from a claim that a specific button/path works.
2. Inspect only relevant pages and dependencies; broaden for discovered risk or
   policy. Use existing project browser tests first. No `e2e`, model, key or consent
   is required for this native route. Load `agentic-e2e-workflow.md` only when the
   project already uses that engine or the user requests its setup.
3. Set time/step/retry/model-call budgets appropriate to the charter. Run sequentially;
   delegate only independent targets with isolated resources and justified capacity.
4. Assert exact identities, permissions, counts and side effects deterministically.
   Use screenshots/vision only for claims requiring visual evidence, not every page.
5. Investigate findings: establish expected versus observed behavior, then reproduce
   a failure for the intended reason. Classify confirmed defect, semantic hypothesis,
   environment/tooling blocker or unknown; setup failures are not product defects.
6. Save each run's artifacts separately, check source/environment freshness, and
   report using `report-format.md`. Verify cleanup of owned browser/service/test data.

Exploration stopping without findings proves only what was observed within that
charter and budget. It cannot replace mandatory assertions. For a confirmed bug,
propose a durable regression test using `test-lifecycle.md`. An unfixed bug outside
this task remains visible and follows existing release policy, not silent quarantine.

## Output Requirements
- Clear, structured Markdown with headers, lists, code blocks
- Include test results summary, key findings, screenshot references
- Lead with the outcome. Keep reports short by being selective, not by compressing the writing into fragments or arrow chains; write complete sentences.

**Do not** start implementing fixes.

## Optional semantic regression experiment

Only for a requested shadow
experiment with an explicit user `ui-regression` consumer grant, use
`ak eval ui capture.json --mode shadow --json`. Default mode is `off`; ambient
credentials do not authorize inference. The command consumes reviewed compact
text from already-observed DOM, accessibility, computed layout, console/network,
viewport and journey evidence. Missing surfaces are `null`, observed empty
surfaces are `[]`. Never paste HTML, cookies, input values, raw console payloads,
URLs with credentials, screenshots or video. Use local opaque journey IDs.
An optional `vision_description` may reuse a description from the existing
native-vision/multimodal investigation; do not perform extra vision extraction
solely to feed the experiment. Review all text for private business/user data;
redaction is defense in depth, not permission to upload it.

Keep browser and accessibility outcomes in `deterministic` and preserve them in
the final report. A semantic probability never converts failures to passes or
cancels existing investigations. Save assertion results with `--output` to a new
local file; add an earlier report as `previous` only for the same journey/device
and observed surfaces. Comparable completed observations also require the same
assertion version, provider and model. Low probabilities and downward shifts
are signals, not confirmed regressions.

Example: `error-recovery` becomes an anomaly after a failed checkout request.
Follow the report's hypothetical handoff: reproduce the checkout with the
existing browser workflow, inspect visible retry controls and accessibility
announcements, then inspect an existing screenshot with native vision or the
installed multimodal capability when visual evidence is needed. Record whether
that investigation confirms or rejects the signal. The command never launches
these calls, skips screenshots, or changes the current UI test result.

Use `ak eval ui-benchmark corpus.json --json` for offline independently labeled
journeys. Synthetic protocol fixtures test integration, not model effectiveness.
Separate useful/false/missed signals and unknown coverage from recorded baseline
versus matched semantic measurements; unknown costs and missing call counts
remain unknown. Never call hypothetical investigation counts actual savings.
