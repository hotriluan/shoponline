// Compatibility contract between the pinned AK Render compiler and the HTML
// producers: every producer-shaped page fixture compiles deterministically,
// keeps a no-network CSP, and references nothing outside the document.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { main } from './render-page.mjs';

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const PAGES_DIR = resolve(SCRIPT_DIR, '../fixtures/pages');
const FIXTURES = readdirSync(PAGES_DIR).filter((name) => name.endsWith('.page.yaml')).sort();

// Resource-loading attributes or CSS that would reach outside the document.
const OFF_DOCUMENT_PATTERNS = [
  /\s(?:src|href|poster|action|data)\s*=\s*["']?(?:https?:)?\/\//i,
  /\ssrcset\s*=\s*["'][^"']*(?:https?:)?\/\//i,
  /url\(\s*["']?(?:https?:)?\/\//i,
  /@import\b/i,
];

async function compileFixture(name, dir, run) {
  const out = join(dir, `${name}.${run}.html`);
  const io = { stdout: () => {}, stderr: () => {}, readStdin: async () => '', cwd: PAGES_DIR };
  const code = await main([join(PAGES_DIR, name), '--out', out, '--json'], io);
  assert.equal(code, 0, `${name} should compile`);
  return readFileSync(out, 'utf8');
}

test('covers one page fixture per first-wave producer', () => {
  for (const name of ['plan', 'explain', 'brainstorm', 'preview-diff']) {
    assert.ok(FIXTURES.includes(`${name}.page.yaml`), `missing fixture ${name}.page.yaml`);
  }
});

for (const name of FIXTURES) {
  test(`${name} compiles to identical, self-contained HTML`, async () => {
    const dir = mkdtempSync(join(tmpdir(), 'ak-render-compat-'));
    try {
      const first = await compileFixture(name, dir, 1);
      const second = await compileFixture(name, dir, 2);
      assert.equal(first, second, 'compiling the same spec twice must give identical bytes');

      const csp = first.match(/http-equiv=["']Content-Security-Policy["'][^>]*content=["']([^"']+)["']/i)
        ?? first.match(/content=["']([^"']+)["'][^>]*http-equiv=["']Content-Security-Policy["']/i);
      assert.ok(csp, 'page must declare a Content-Security-Policy');
      const policy = csp[1].replaceAll('&#39;', "'");
      assert.match(policy, /default-src 'none'/);
      assert.match(policy, /connect-src 'none'/);

      for (const pattern of OFF_DOCUMENT_PATTERNS) {
        assert.doesNotMatch(first, pattern, `off-document reference matched ${pattern}`);
      }
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
}
