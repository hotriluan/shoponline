// Contract for the Pele bridge that render.py calls for `.mmd` input: valid
// Mermaid becomes an SVG, Pele's own diagram errors become a structured
// result, and anything else (unreadable input) is an internal failure.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderMermaid } from './render-mermaid.mjs';

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(SCRIPT_DIR, 'render-mermaid.mjs');
const BUNDLE = join(SCRIPT_DIR, '..', 'assets', 'pele.mjs');

// Characters the kit emitter strips from every text file it installs (see
// apps/cli/internal/runtime/sanitize), after NFC normalization.
const EMIT_STRIPPED_RANGES = [
  [0x200b, 0x200f], [0x202a, 0x202e], [0x2060, 0x2064], [0x2066, 0x2069], [0xfeff, 0xfeff], [0xe0000, 0xe007f],
];
// Kept as numeric ranges so this file stays ASCII and is itself not scrubbed.
const hasStrippedChar = (text) => {
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (EMIT_STRIPPED_RANGES.some(([lo, hi]) => cp >= lo && cp <= hi)) return true;
  }
  return false;
};

test('vendored bundle survives the install scrub byte for byte', () => {
  const bundle = readFileSync(BUNDLE, 'utf8');
  assert.equal(hasStrippedChar(bundle), false, 'bundle contains characters the emitter strips');
  assert.equal(bundle === bundle.normalize('NFC'), true, 'bundle changes under NFC normalization');
});

test('keeps hyphens in link URLs', () => {
  const result = renderMermaid('flowchart LR\n  A --> B\n  click A href "https://my-site.example/a-b-c"');
  assert.equal(result.ok, true);
  assert.match(result.svg, /href="https:\/\/my-site\.example\/a-b-c"/);
});

test('labels cannot inject markup into the SVG', () => {
  const result = renderMermaid('flowchart LR\n  A["<img src=x onerror=alert(1)>"] --> B["<script>alert(2)</script>"]');
  assert.equal(result.ok, true);
  // Pele may strip or escape the tags; either way no real element may appear.
  assert.doesNotMatch(result.svg, /<(img|script)\b/i);
  assert.doesNotMatch(result.svg, /<[^>]*\sonerror=/i);
});

function runCli(args) {
  return spawnSync(process.execPath, [SCRIPT, ...args], { encoding: 'utf8' });
}

test('renders valid Mermaid to a Pele SVG', () => {
  const result = renderMermaid('flowchart LR\n  A[Mermaid text] --> B[SVG]');
  assert.equal(result.ok, true);
  assert.equal(result.type, 'flowchart');
  assert.match(result.svg, /^<svg [^>]*class="pele pele-flowchart"/);
});

test('reports a parse error with its location', () => {
  const result = renderMermaid('flowchart LR\n  A --> ');
  assert.equal(result.ok, false);
  assert.equal(typeof result.error.code, 'string');
  assert.match(result.error.message, /Parse error/);
  assert.ok(result.error.line > 0);
  assert.equal(typeof result.error.column, 'number');
});

test('reports an unknown diagram type with line 0', () => {
  const result = renderMermaid('notadiagram foo');
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'unsupported-diagram');
  assert.equal(result.error.line, 0);
});

test('CLI prints the JSON result and exits 0 for both outcomes', () => {
  const dir = mkdtempSync(join(tmpdir(), 'ak-render-mermaid-'));
  try {
    const good = join(dir, 'good.mmd');
    const bad = join(dir, 'bad.mmd');
    writeFileSync(good, 'sequenceDiagram\n  Alice->>Bob: hi\n');
    writeFileSync(bad, 'notadiagram foo\n');

    const ok = runCli([good]);
    assert.equal(ok.status, 0, ok.stderr);
    const okJson = JSON.parse(ok.stdout);
    assert.equal(okJson.ok, true);
    assert.match(okJson.svg, /^<svg /);

    const fail = runCli([bad]);
    assert.equal(fail.status, 0, fail.stderr);
    assert.equal(JSON.parse(fail.stdout).error.code, 'unsupported-diagram');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('CLI exits 2 when the input cannot be read', () => {
  const missing = runCli([join(tmpdir(), 'ak-render-mermaid-missing.mmd')]);
  assert.equal(missing.status, 2);
  assert.equal(missing.stdout, '');
  assert.match(missing.stderr, /render-mermaid/);

  const usage = runCli([]);
  assert.equal(usage.status, 2);
});

test('CLI exits 2 with a one-line message when the bundle is missing', () => {
  const dir = mkdtempSync(join(tmpdir(), 'ak-render-mermaid-nobundle-'));
  try {
    const script = join(dir, 'scripts', 'render-mermaid.mjs');
    mkdirSync(dirname(script));
    copyFileSync(SCRIPT, script);
    const input = join(dir, 'a.mmd');
    writeFileSync(input, 'flowchart LR\n  A --> B\n');
    const res = spawnSync(process.execPath, [script, input], { encoding: 'utf8' });
    assert.equal(res.status, 2);
    assert.equal(res.stdout, '');
    assert.match(res.stderr, /^render-mermaid: cannot load assets\/pele\.mjs: [^\n]*\n$/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
