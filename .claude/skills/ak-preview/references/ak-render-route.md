# AK Render Route (Opt-in)

The opt-in HTML route selected in `html-skill-composition.md`. The invoking skill
writes a short YAML **Page Spec**; the pinned AK Render compiler turns it into one
self-contained, offline HTML file. Do not hand-write HTML, CSS or JS on this route.

## Responsibility Boundaries

- **Invoking skill**: owns the facts, narrative, section choice, the Page Spec and
  the artifact path. It picks blocks and a theme; it never positions or styles.
- **AK Render** (`@bestagentkits/render@0.3.0`): owns the document shell, layout,
  typography, colour, motion, light/dark toggle, accessibility, CSP and offline
  assembly.
- **ak-diagram** (Engineer installs): owns typed diagram IR and its deterministic
  SVG, embedded through the `diagram-panel` block by its page wrapper.

## The Loop

Run from the project root (the directory that holds `.ak-render/`, else the repository root) and pass the spec and output as relative paths, e.g. `plans/x/plan.page.yaml --out plans/x/plan.html`; AK Render discovers project theme presets only under the working directory. Node 20.11+ is required.

```bash
npx -y @bestagentkits/render@0.3.0 catalog                          # once per task
npx -y @bestagentkits/render@0.3.0 describe <type> --json           # only block types you use
npx -y @bestagentkits/render@0.3.0 validate <name>.page.yaml --json # fix each diagnostic at its $.path
npx -y @bestagentkits/render@0.3.0 <name>.page.yaml --out <name>.html --json
```

- Exit 1 means fix the spec: edit only the field at the diagnostic `path`
  (`details.allowed` lists valid props) and validate again.
- Exit 2 means the input could not be read or the output could not be written.
  An exit with a stack trace instead of a diagnostic is an internal failure, not
  a spec problem.
- `-` reads the spec from stdin.
- Keep `<name>.page.yaml` beside `<name>.html`. Later edits change the spec and
  recompile; never patch the compiled HTML.
- Report the compile summary's `warnings`; an empty list is the success case.
- Local images (mockups, screenshots) are referenced by relative path and load
  from disk; keep them beside the HTML when moving or publishing it.

Minimal spec shape (check real props with `describe`; nested children go in
`blocks`, and text-bearing blocks such as `code` and `callout` use `text`;
quote any value containing a comma or colon inside `{ }` or `[ ]` (table rows),
or use block style):

```yaml
version: 1
meta:
  title: Gateway migration plan
  description: Move the public API to the new gateway without downtime.
theme:
  preset: editorial
blocks:
  - type: hero
    eyebrow: Plan
    title: Gateway migration plan
    description: Move the public API without downtime.
  - type: section
    title: Phases
    blocks:
      - type: steps
        items:
          - { title: Mirror traffic, text: Copy production requests to the new gateway. }
      - type: code
        language: bash
        text: curl -sS https://gateway.internal/health
```

## Choosing Blocks

Prefer semantic blocks; they carry the design. Carry the same depth of content
the default route would: every required section of the invoking skill, with its
evidence, not a summary of it.

| Content | Blocks |
|---|---|
| Title, summary, status | `hero`, `badge`, `key-value` |
| Metrics, progress | `kpi`, `stats`, `progress`, `chart` |
| Ordered work, phases | `steps`, `timeline`, `checklist` |
| Detail on demand | `accordion`, `tabs`, `dialog` + `button` |
| Options, trade-offs | `comparison`, `table`, `card-grid` |
| Risks | `risk-matrix`, `callout`, `alert` |
| Code, commands, files | `code`, `terminal`, `file-tree`, `diff-summary` |
| Review findings | `code-review` |
| UI mockups | `showcase`, `bento`, `before-after` with local images and `callout` annotations |
| Topology, flows | `diagram-panel` (see Diagrams) |

Use `section` to group blocks under a heading. Do not invent graph topology
for content that is not relational; use `steps` or `card-grid`.

Per-skill section mappings:

| Skill | Sections → blocks |
|---|---|
| `ak-plan` | `hero` + `key-value` (status, priority, issue, branch); roadmap `steps`/`timeline`; one `accordion` item per phase (bullets, files, `checklist` criteria, `code` commands); workflow `diagram-panel`; `risk-matrix`; open questions `list`; citations `table` |
| `ak-explain` | `hero` + `badge`s; mental model `diagram-panel`; walkthrough `steps`/`tabs`; trace `code`/`terminal`; warnings `callout`/`alert`; glossary `key-value`/`accordion` (required for `--eli5`) |
| `ak-brainstorm` | contract fields `key-value`/`card`; approaches `comparison` (two) or `table`/`card-grid`; scoring `kpi`/`chart`; recommendation `callout` (`success`); implementation flow `diagram-panel`; risks `risk-matrix` + `list` |
| `ak-preview --diff` | `hero` + `kpi`; `diff-summary`; module map `diagram-panel`/`file-tree`; before/after `comparison`; `code-review`; decisions `timeline`; re-entry `checklist` |
| `ak-preview --plan-review` | `hero` + impact `kpi`; current vs planned `comparison`; changes `table`; dependencies `file-tree`; `risk-matrix`; `code-review`; gaps `callout` |
| `ak-preview --recap` | `hero` + `key-value`; architecture `diagram-panel`; activity `timeline`; state `kpi`; decisions `table`; debt `risk-matrix`; next steps `checklist` |

## Themes

Pick one preset per artifact from `blueprint`, `editorial`, `paper-ink`,
`swiss-clean`, `terminal-mono` and `warm-signal`, or a project preset in
`.ak-render/themes/` (list with `npx -y @bestagentkits/render@0.3.0 themes`).
A project preset that encodes `docs/design-guidelines.md` wins over a built-in.

## Diagrams

A `diagram-panel` holds a typed diagram spec (`title`, `spec`, `caption`).

- **ak-diagram installed** (it appears in the live skill catalog): author the
  ak-diagram typed JSON IR as the panel `spec`, activate ak-diagram, and compile
  the page with its page wrapper instead of the bare CLI. The wrapper is
  `scripts/render-page.mjs` in the ak-diagram skill directory:

  ```bash
  npx -y -p @bestagentkits/render@0.3.0 node <ak-diagram-dir>/scripts/render-page.mjs <name>.page.yaml --out <name>.html --json
  ```

  It accepts the same `validate`-clean spec (exit 1 = fix the spec), embeds the real SVG,
  and lists `diagramErrors`. Repair the IR for each error; if repair fails, the
  panel keeps its labelled structured fallback. Never fall back to raw HTML or
  Mermaid. Keep each diagram small (about 8 nodes or fewer). The ak-diagram SVG
  declares `width="100%"`, so the panel always scales it to the panel width
  rather than scrolling: a wide diagram shrinks until its labels are unreadable,
  most visibly at 375 px. Split a large topology into several narrow panels
  (prefer top-to-bottom flows) instead of relying on sideways scroll.
- **ak-diagram absent** (Core-only, Marketing): use the bare CLI. The panel
  renders a structured text fallback, so also show the flow with `steps` or
  `timeline`, and state the reduced interaction in the page `meta.description`.

## Fallback

| State | Behaviour |
|---|---|
| Node < 20.11, no `npx`, or the package cannot be fetched | Use the default route in `html-skill-composition.md` and state the reason in the report. |
| Spec still invalid after three repairs by `path` | Same: default route, reason in the report. |
| Content needs a block the catalog lacks | Compose from primitives (`card`, `table`, `list`); use the default route only if no composition carries the facts. |

The compiled page's CSP is `default-src 'none'`; it opens over `file://` with
zero network requests. The compile step is different: the first `npx` run
downloads the pinned package from the npm registry (cached afterwards). Do not add remote `src`/`href` assets to the spec unless
`policy.network` explicitly opts in.
