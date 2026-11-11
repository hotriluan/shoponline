# ak-diagram — Mermaid input notes

`.mmd` input renders with the vendored [Pele](https://github.com/obsidianmd/pele)
bundle (`assets/pele.mjs`, v1.6.0, MIT; see `references/vendoring-metadata.yaml`
for the one escaping change that keeps it intact through `ak` installs) through `scripts/render-mermaid.mjs`.
Pele targets Mermaid 12.1.0 syntax with its own layout and visual style, so a
diagram looks different from Mermaid's default rendering. It runs in Node
without a browser, so `render.py --no-png` writes the HTML and SVG without
starting Chromium.

## Supported diagram kinds

Pele supports every diagram type built into Mermaid 12.1.0: `flowchart`,
`sequenceDiagram`, `classDiagram`, `stateDiagram-v2`, `erDiagram`, `journey`,
`gantt`, `pie`, `mindmap`, `timeline`, `quadrantChart`, `requirementDiagram`,
`xychart-beta` and the rest.

## Fallback

When Pele rejects a diagram (a parse error or an unknown type) or `node` is not
on `PATH`, `render.py` prints a warning on stderr with the Pele error code and
line, then writes a page that loads Mermaid 11.4.1 from jsDelivr. The script
tag carries an SRI hash, and the source is HTML-escaped inside
`<pre class="mermaid">` (Mermaid decodes it before parsing). The fallback needs
network access. Each wait for the page is bounded (15 s for the CDN script,
15 s for network idle, 5 s for Mermaid to finish), so a capture takes at most
about 40 s; on a timeout the page is captured as is, showing the diagram source
as plain text. When the browser runs (PNG output, or SVG output Pele did not
produce), a Mermaid rejection is also printed on stderr. `--dry-run` and
`--no-png --no-svg` write the fallback page without checking it.

`doctor.py` lists `node` (20 or later) as required, because typed specs and
Pele both need it; `render.py` itself only falls back when `node` is missing.

## Editorial framing

The page maps Pele's `--pele-*` variables onto the token palette from
`assets/tokens.css` on `body.ak-diag`:

- `--ak-diag-paper` background, `--ak-diag-paper-soft` node surfaces
- `--ak-diag-ink` text and lines, `--ak-diag-ink-muted` secondary text
- `--ak-diag-rule` borders, `--ak-diag-accent` focal elements
- `--ak-diag-font` type family

The standalone `.svg` output keeps Pele's built-in fallback colours because the
mapping lives on the page, not on the `<svg>`.

Pass `--title` and `--caption` to `render.py` to add editorial headings above
the diagram.

## Animation

Mermaid syntax has no animation primitives. To animate connectors on a
rendered SVG:

1. Render once to HTML (`render.py --input diagram.mmd --no-png --no-svg`)
2. Post-process the emitted SVG: add `data-fx="<name>"` to the paths
   you want to animate (typically identifiable by their id/class).
3. Re-open the modified HTML and re-render or record.

For animation-heavy work, an editorial template from Tier 2 is usually
the better choice — templates ship with `data-fx` slots already wired.

## Deterministic rendering

- Pele renders synchronously and measures text without a browser, so the
  same source and Pele version produce the same SVG bytes. The exception is
  `gantt`: its today marker uses the render time (Pele's `now` option could
  pin it if reproducible builds ever need it). The pinned, vendored bundle
  prevents layout drift; upgrading Pele is a deliberate re-vendor.
- Pele sizes labels with its built-in width table, not the page font
  (`--ak-diag-font`), so a very long label can overflow its node in the
  HTML and PNG.
- PNG screenshots still depend on the system font stack.
- Use `<br/>` in labels for intentional line breaks.

## Golden hash coverage

Mermaid-syntax diagrams are not part of the golden snapshot suite —
their layout depends on label content and is expected to drift with
input changes. Templates (Tier 2) are the deterministic surface.

## Escape hatch: mmdc

If `mmdc` (mermaid-cli) is on PATH, `render.py` does not shortcut to it —
the Pele pipeline is used uniformly so editorial framing and token
overrides always apply. Use `mmdc` directly for Mermaid's own default
rendering.
