/**
 * Render Mermaid source to SVG with the vendored Pele bundle.
 *
 * render.py calls this for `.mmd` input. Pele renders synchronously in Node
 * without a DOM, so no browser is needed to produce the SVG.
 *
 * Usage:
 *   node scripts/render-mermaid.mjs diagram.mmd
 *
 * Prints one JSON object on stdout and exits 0:
 *   {"ok": true, "type": "flowchart", "svg": "<svg ..."}
 *   {"ok": false, "error": {"code", "message", "line", "column"}}
 * A diagram Pele rejects is a normal result (the caller falls back to Mermaid).
 * Exit 2 means an environment problem or internal failure (bad arguments,
 * unreadable input, an unexpected exception).
 */

import { readFileSync, realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// `.mjs` keeps the bundle an ES module wherever the skill is installed, since
// the install location has no `"type": "module"` package scope. A missing or
// unloadable bundle is reported by main() as exit 2, not as a stack trace.
let pele;
let loadError;
try {
  pele = await import(new URL('../assets/pele.mjs', import.meta.url));
} catch (err) {
  loadError = err;
}

const SCRIPT_PATH = fileURLToPath(import.meta.url);

/**
 * Render one Mermaid diagram. Pele's diagram errors become `ok: false`; the
 * class name is minified in the bundle, so match it with `instanceof`.
 */
export function renderMermaid(source) {
  if (!pele) throw new Error(`cannot load assets/pele.mjs: ${loadError?.message ?? 'unknown error'}`);
  const { render, PeleError } = pele;
  try {
    const { type, svg } = render(source);
    return { ok: true, type, svg };
  } catch (err) {
    if (!(err instanceof PeleError)) throw err;
    return {
      ok: false,
      error: { code: err.code, message: err.message, line: err.line, column: err.column },
    };
  }
}

export function main(argv) {
  if (argv.length !== 1) {
    process.stderr.write('usage: node render-mermaid.mjs <diagram.mmd>\n');
    return 2;
  }
  try {
    const result = renderMermaid(readFileSync(argv[0], 'utf8'));
    process.stdout.write(`${JSON.stringify(result)}\n`);
    return 0;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    process.stderr.write(`render-mermaid: ${message.split('\n')[0]}\n`);
    return 2;
  }
}

function invokedDirectly() {
  if (!process.argv[1]) return false;
  try {
    return realpathSync(process.argv[1]) === realpathSync(SCRIPT_PATH);
  } catch {
    return false;
  }
}

if (invokedDirectly()) {
  process.exitCode = main(process.argv.slice(2));
}
