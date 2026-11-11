#!/usr/bin/env python3
"""ak-diagram render — freeze animations, screenshot to PNG, extract SVG.

HTML pipeline with Playwright for screenshots. Accepts:
    - a raw HTML file (already rendered)
    - a mermaid source (.mmd) — rendered to SVG by the vendored Pele bundle
      (assets/pele.mjs, via scripts/render-mermaid.mjs) and wrapped in the
      editorial frame. If Pele rejects the diagram or node is missing, the page
      loads Mermaid 11.4.1 from jsDelivr (SRI-pinned) instead.
    - a JSON spec matching a per-type schema — fills the corresponding template

Outputs:
    <basename>.html   (self-contained except a Mermaid fallback page, which
                       loads Mermaid from jsDelivr; animated, mobile-safe)
    <basename>.png    (frozen final-frame screenshot, deterministic)
    <basename>.svg    (Pele SVG, or extracted from the page DOM, if present)

The browser starts only when a PNG is wanted, or an SVG is wanted that Pele
did not produce.

Usage:
    python3 scripts/render.py --input diagram.mmd --out ./build/
    python3 scripts/render.py --input spec.json --type loop --out ./build/
    python3 scripts/render.py --input page.html --out ./build/ --no-png --no-svg
    python3 scripts/render.py --input diagram.mmd --dry-run   # skip screenshot
"""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import sys
import subprocess
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS = SKILL_ROOT / "assets"
TOKENS_CSS = ASSETS / "tokens.css"
EFFECTS_CSS = ASSETS / "connector-effects.css"
TEMPLATES_DIR = ASSETS / "templates"
COMPILER_MJS = SKILL_ROOT / "scripts" / "compiler" / "compile.mjs"
PELE_BRIDGE_MJS = SKILL_ROOT / "scripts" / "render-mermaid.mjs"

# Fallback for diagrams Pele rejects: the Mermaid release this skill used to
# vendor, fetched only when needed. The SRI hash pins the exact bytes.
MERMAID_FALLBACK_VERSION = "11.4.1"
MERMAID_FALLBACK_URL = (
    f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_FALLBACK_VERSION}/dist/mermaid.min.js"
)
MERMAID_FALLBACK_SRI = "sha384-rbtjAdnIQE/aQJGEgXrVUlMibdfTSa4PQju4HDhN3sR2PmaKFzhEafuePsl9H/9I"
# Pele renders a 1,500-edge graph in well under a second; this only stops a hang.
PELE_TIMEOUT_S = 60
# Budget for the fallback page's CDN script before capturing the page as is.
FALLBACK_NETWORK_TIMEOUT_MS = 15000

# Pele reads its colours and font from --pele-* variables; point them at the
# editorial tokens so the diagram follows tokens.css (light and dark).
PELE_TOKEN_MAP = """
    .ak-diag {
      --pele-bg: var(--ak-diag-paper);
      --pele-fg: var(--ak-diag-ink);
      --pele-muted: var(--ak-diag-ink-muted);
      --pele-line: var(--ak-diag-ink);
      --pele-surface: var(--ak-diag-paper-soft);
      --pele-surface-alt: var(--ak-diag-accent-soft);
      --pele-border: var(--ak-diag-rule);
      --pele-accent: var(--ak-diag-accent);
      --pele-font: var(--ak-diag-font);
      --pele-radius: var(--ak-diag-radius-sm);
    }
    .ak-diag__figure { margin: 0; }"""

DEFAULT_VIEWPORT = {"width": 1400, "height": 900}
SNAPSHOT_CHROMIUM_VERSION = "151.0.7922.34"
SNAPSHOT_FONT_PROBE = "AgentKit snapshot Wm0@/ 12345 — glyph probe"
SNAPSHOT_FONT_WIDTHS = {
    "sans-serif": 349.7734375,
    "serif": 323.1484375,
    "monospace": 412.8671875,
    "system-ui": 353.1484375,
    "ui-monospace": 323.1484375,
    '"Geist", system-ui, sans-serif': 353.1484375,
    '"Geist Mono", ui-monospace, monospace': 412.8671875,
    '"Instrument Serif", serif': 323.1484375,
    '"Instrument Serif", "Times New Roman", serif': 323.1484375,
    '"Geist Mono", ui-monospace, Menlo, monospace': 414.2109375,
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _render_with_pele(input_path: Path) -> tuple[str | None, str | None]:
    """Return (svg, None) from Pele, or (None, reason) when the fallback is needed."""
    # Resolve like doctor.py does, so a Windows node.cmd shim is found too.
    node = shutil.which("node")
    if node is None:
        return None, "node not found on PATH"
    try:
        res = subprocess.run(
            [node, str(PELE_BRIDGE_MJS), str(input_path)],
            capture_output=True,
            encoding="utf-8",
            timeout=PELE_TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError:
        return None, "node not found on PATH"
    except subprocess.TimeoutExpired:
        return None, f"Pele bridge timed out after {PELE_TIMEOUT_S}s"
    if res.returncode != 0:
        first_line = next(iter(res.stderr.strip().splitlines()), f"exit {res.returncode}")
        return None, f"Pele bridge failed: {first_line}"
    try:
        result = json.loads(res.stdout)
    except json.JSONDecodeError:
        return None, "Pele bridge printed invalid JSON"
    if result.get("ok"):
        return result["svg"], None
    err = result.get("error") or {}
    message = " ".join(str(err.get("message", "")).split())
    where = f" at line {err['line']}" if err.get("line") is not None else ""
    return None, f"{err.get('code', 'pele-error')}{where}: {message}"


def _editorial_page(title: str, caption: str, extra_css: str, body: str) -> str:
    tokens = _read(TOKENS_CSS)
    effects = _read(EFFECTS_CSS)
    safe_title = html.escape(title) if title else "ak-diagram"
    title_html = f'<h1 class="ak-diag__title">{html.escape(title)}</h1>' if title else ""
    caption_html = f'<p class="ak-diag__caption">{html.escape(caption)}</p>' if caption else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{safe_title}</title>
  <style>{tokens}</style>
  <style>{effects}</style>
  <style>
    body {{ margin: 0; background: var(--ak-diag-paper); }}{extra_css}
  </style>
</head>
<body class="ak-diag">
  {title_html}
  {caption_html}
{body}
</body>
</html>
"""


def _mermaid_fallback_body(mermaid_source: str) -> str:
    # Escaping keeps the source inside the <pre>; Mermaid's run() decodes the
    # entities back before parsing.
    return f"""  <pre class="mermaid">
{html.escape(mermaid_source)}
  </pre>
  <script src="{MERMAID_FALLBACK_URL}" integrity="{MERMAID_FALLBACK_SRI}" crossorigin="anonymous"></script>
  <script>
    (async () => {{
      if (!window.mermaid) throw new Error('Mermaid fallback did not load');
      mermaid.initialize({{ startOnLoad: false, theme: 'base', fontFamily: 'inherit' }});
      await mermaid.run({{ querySelector: '.mermaid' }});
      window.__ak_diag_mermaid_done = true;
    }})().catch(err => {{
      // Mermaid parse errors are plain objects with `str`/`message`, not Errors.
      window.__ak_diag_mermaid_err = String((err && (err.message || err.str)) || err);
    }});
  </script>"""


def _mermaid_editorial_frame(input_path: Path, title: str = "",
                             caption: str = "") -> tuple[str, str | None]:
    """Return the editorial page and the Pele SVG (None when falling back)."""
    svg, reason = _render_with_pele(input_path)
    if svg is not None:
        body = f'  <figure class="ak-diag__figure">\n{svg}\n  </figure>'
        return _editorial_page(title, caption, PELE_TOKEN_MAP, body), svg
    print(
        f"ak-diagram: Pele could not render {input_path} ({reason}); "
        f"falling back to Mermaid {MERMAID_FALLBACK_VERSION} from jsDelivr (needs network).",
        file=sys.stderr,
    )
    extra_css = "\n    .mermaid { font-family: var(--ak-diag-font); }"
    body = _mermaid_fallback_body(_read(input_path))
    return _editorial_page(title, caption, extra_css, body), None


def _load_template(dtype: str, variant: str) -> str:
    candidate = TEMPLATES_DIR / dtype / f"{variant}.html"
    if not candidate.exists():
        raise SystemExit(f"template not found: {candidate}")
    return _read(candidate)


def _fill_template(template_html: str, spec: dict) -> str:
    """Small slot filler — replaces {{key}} tokens with HTML-escaped str(spec[key]).

    Values are HTML-escaped before insertion. If a template deliberately needs
    raw HTML in a slot (rare), name the key with a `_html` suffix — those keys
    are passed through unescaped and the responsibility for safety shifts to
    the caller.
    """
    out = template_html
    for key, value in spec.items():
        token = f"{{{{{key}}}}}"
        if key.endswith("_html"):
            replacement = str(value)
        else:
            replacement = html.escape(str(value), quote=True)
        out = out.replace(token, replacement)
    return out


def _compose_html(input_path: Path, dtype: str | None, spec: dict | None,
                  title: str, caption: str) -> tuple[str, str | None]:
    """Return the page HTML and, for Pele-rendered Mermaid, the ready SVG."""
    suffix = input_path.suffix.lower()
    if suffix == ".html":
        return _read(input_path), None
    if suffix == ".mmd":
        return _mermaid_editorial_frame(input_path, title, caption)
    if suffix == ".json":
        # Typed IR detection
        if spec and ("schema_version" in spec or "schemaVersion" in spec or "diagram_type" in spec):
            res = subprocess.run(
                ["node", str(COMPILER_MJS), "--input", str(input_path), "--format", "html"],
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode != 0:
                raise SystemExit(f"Typed IR compile error: {res.stderr.strip()}")
            return res.stdout, None
        if not dtype:
            raise SystemExit("--type is required when --input is a legacy JSON spec")
        template = _load_template(dtype, spec.get("variant", "light") if spec else "light")
        return _fill_template(template, spec or {}), None
    raise SystemExit(f"unsupported input: {input_path}")


def _verify_snapshot_profile(browser, page) -> None:
    """Refuse a golden comparison outside the renderer profile that seeded it."""
    if browser.version != SNAPSHOT_CHROMIUM_VERSION:
        raise RuntimeError(
            f"snapshot renderer requires Chromium {SNAPSHOT_CHROMIUM_VERSION}, got {browser.version}"
        )
    widths = page.evaluate(
        """({sample, fonts}) => {
            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d');
            return Object.fromEntries(fonts.map(font => {
                context.font = `16px ${font}`;
                return [font, context.measureText(sample).width];
            }));
        }""",
        {"sample": SNAPSHOT_FONT_PROBE, "fonts": list(SNAPSHOT_FONT_WIDTHS)},
    )
    mismatches = [
        font for font, expected in SNAPSHOT_FONT_WIDTHS.items()
        if widths.get(font) != expected
    ]
    if mismatches:
        raise RuntimeError(
            "snapshot renderer font profile differs for: " + ", ".join(mismatches)
        )


def _load_fallback_page(page, url: str, timeout_error: type[Exception]) -> None:
    """Load the Mermaid fallback page without failing on a slow or hanging CDN.

    Its parser-blocking CDN script holds back DOMContentLoaded and load, so both
    waits are bounded; on timeout the page is captured as is (the diagram
    source shows as plain text) and Mermaid's own errors are reported.
    """
    for wait in (lambda: page.goto(url, timeout=FALLBACK_NETWORK_TIMEOUT_MS),
                 lambda: page.wait_for_load_state("networkidle", timeout=FALLBACK_NETWORK_TIMEOUT_MS)):
        try:
            wait()
        except timeout_error:
            print(f"ak-diagram: Mermaid fallback still loading after "
                  f"{FALLBACK_NETWORK_TIMEOUT_MS // 1000}s; capturing the page as is",
                  file=sys.stderr)
            return
    try:
        page.wait_for_function(
            "() => window.__ak_diag_mermaid_done || window.__ak_diag_mermaid_err",
            timeout=5000,
        )
    except timeout_error:
        print("ak-diagram: Mermaid fallback did not finish rendering within 5s; "
              "capturing the page as is", file=sys.stderr)
        return
    mermaid_err = page.evaluate("() => window.__ak_diag_mermaid_err || null")
    if mermaid_err:
        print(f"ak-diagram: Mermaid fallback could not render the diagram either: {mermaid_err}",
              file=sys.stderr)


def _freeze_and_screenshot(html_path: Path, out_dir: Path, basename: str,
                           want_png: bool, want_svg: bool,
                           snapshot_profile: bool, mermaid_fallback: bool = False) -> dict:
    """Launch Playwright headless Chromium, freeze animations, capture PNG + SVG."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # type: ignore
    from playwright.sync_api import sync_playwright  # type: ignore

    result = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--font-render-hinting=none",
            "--disable-lcd-text",
        ])
        page = browser.new_page(viewport=DEFAULT_VIEWPORT, device_scale_factor=2)
        url = html_path.resolve().as_uri()
        if mermaid_fallback:
            _load_fallback_page(page, url, PlaywrightTimeoutError)
        else:
            page.goto(url)
            page.wait_for_load_state("networkidle", timeout=15000)
        if snapshot_profile:
            _verify_snapshot_profile(browser, page)
        # Give Mermaid a chance to finish async render. `.mermaid` <pre> becomes
        # a rendered <svg> inside the same element; wait for it or skip after a
        # short budget for non-Mermaid inputs.
        try:
            page.wait_for_selector("svg", timeout=5000)
        except Exception:
            pass  # no SVG expected (raw HTML input with no diagram markup)
        # Freeze all animations to their final frame for byte-hash determinism
        page.evaluate("""
            () => {
                document.querySelectorAll('svg').forEach(s => s.classList.add('ak-fx-frozen'));
                document.body?.classList.add('ak-fx-frozen');
                const anims = document.getAnimations();
                anims.forEach(a => {
                    const dur = a.effect?.getComputedTiming?.().duration || 0;
                    if (typeof dur === 'number' && dur > 0) a.currentTime = dur;
                    a.pause();
                });
            }
        """)

        if want_png:
            png_path = out_dir / f"{basename}.png"
            page.screenshot(path=str(png_path), full_page=True, omit_background=False)
            result["png"] = str(png_path)

        if want_svg:
            svg_source = page.evaluate("""
                () => {
                    const svg = document.querySelector('svg');
                    return svg ? new XMLSerializer().serializeToString(svg) : null;
                }
            """)
            if svg_source:
                svg_path = out_dir / f"{basename}.svg"
                svg_path.write_text(svg_source, encoding="utf-8")
                result["svg"] = str(svg_path)
        browser.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an ak-diagram to HTML/PNG/SVG")
    parser.add_argument("--input", type=Path, required=True, help="Input path (.html/.mmd/.json)")
    parser.add_argument("--out", type=Path, default=Path("./build"), help="Output directory")
    parser.add_argument("--type", type=str, default=None, help="Editorial type slug (json input only)")
    parser.add_argument("--title", type=str, default="", help="Editorial frame title")
    parser.add_argument("--caption", type=str, default="", help="Editorial frame caption")
    parser.add_argument("--no-png", action="store_true", help="Skip PNG screenshot")
    parser.add_argument("--no-svg", action="store_true", help="Skip SVG extraction")
    parser.add_argument("--dry-run", action="store_true", help="Write HTML only, skip browser")
    parser.add_argument("--snapshot-profile", action="store_true", help="Require the pinned golden renderer profile")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"input not found: {args.input}")

    spec = None
    if args.input.suffix.lower() == ".json":
        spec = json.loads(_read(args.input))

    html, pele_svg = _compose_html(args.input, args.type, spec, args.title, args.caption)
    basename = args.input.stem

    args.out.mkdir(parents=True, exist_ok=True)
    html_path = args.out / f"{basename}.html"
    html_path.write_text(html, encoding="utf-8")
    if args.dry_run:
        print(f"dry-run: wrote {html_path}")
        return 0

    result = {"html": str(html_path)}
    want_png = not args.no_png
    want_svg = not args.no_svg
    if want_svg and pele_svg is not None:
        svg_path = args.out / f"{basename}.svg"
        svg_path.write_text(pele_svg, encoding="utf-8")
        result["svg"] = str(svg_path)
        want_svg = False  # already written; the browser is not needed for it
    if want_png or want_svg:
        result.update(_freeze_and_screenshot(
            html_path,
            args.out,
            basename,
            want_png=want_png,
            want_svg=want_svg,
            snapshot_profile=args.snapshot_profile,
            mermaid_fallback=args.input.suffix.lower() == ".mmd" and pele_svg is None,
        ))
    for kind in ("html", "png", "svg"):
        if kind in result:
            print(f"{kind}: {result[kind]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
