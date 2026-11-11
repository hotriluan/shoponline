// Tests for render-page.mjs: the AK Render page wrapper that registers the
// ak-diagram typed compiler as the diagram adapter.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, symlinkSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  PINNED_RENDER_VERSION,
  createDiagramAdapter,
  findThemeRoot,
  main,
  resolveRenderLibrary,
} from './render-page.mjs';

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const PAGE_FIXTURE = resolve(SCRIPT_DIR, '../fixtures/pages/diagram-workflow.page.yaml');

function captureIo(stdin = '') {
  const out = { stdout: '', stderr: '' };
  return {
    out,
    io: {
      stdout: (text) => { out.stdout += text; },
      stderr: (text) => { out.stderr += text; },
      readStdin: async () => stdin,
      cwd: SCRIPT_DIR,
    },
  };
}

function withTempDir(fn) {
  const dir = mkdtempSync(join(tmpdir(), 'ak-render-page-'));
  return Promise.resolve(fn(dir)).finally(() => rmSync(dir, { recursive: true, force: true }));
}

test('resolves the pinned AK Render library', async () => {
  const library = await resolveRenderLibrary({ pathDirs: [] });
  assert.equal(library.VERSION, PINNED_RENDER_VERSION);
  assert.equal(typeof library.compile, 'function');
});

test('refuses a library whose version differs from the pin', async () => {
  await withTempDir(async (dir) => {
    // Shape of an npx install: <prefix>/node_modules/.bin on PATH, package beside it.
    const binDir = join(dir, 'node_modules', '.bin');
    const pkgDir = join(dir, 'node_modules', '@bestagentkits', 'render');
    mkdirSync(binDir, { recursive: true });
    mkdirSync(join(pkgDir, 'dist'), { recursive: true });
    writeFileSync(join(pkgDir, 'package.json'), JSON.stringify({ name: '@bestagentkits/render', version: '9.9.9', type: 'module', exports: { '.': { import: './dist/index.js' } } }));
    writeFileSync(join(pkgDir, 'dist', 'index.js'), "export const VERSION = '9.9.9'; export function compile() {}\n");
    await assert.rejects(
      resolveRenderLibrary({ pathDirs: [binDir], allowBareImport: false }),
      (error) => error.message.includes('9.9.9') && error.message.includes(PINNED_RENDER_VERSION),
    );
  });
});

test('adapter returns the ak-diagram SVG and records compiler errors', () => {
  const errors = [];
  const adapter = createDiagramAdapter(errors);
  const spec = JSON.parse(readFileSync(resolve(SCRIPT_DIR, '../fixtures/workflow-sample.json'), 'utf8'));
  const svg = adapter.render({ spec, title: 'Release', nodeId: 'n1', contractVersion: 1 });
  assert.match(svg, /^<svg class="ak-diagram-svg"/);
  assert.doesNotMatch(svg, / style="/);
  assert.throws(() => adapter.render({ spec: { diagram_type: 'nope' }, title: 'Broken', nodeId: 'n2', contractVersion: 1 }));
  assert.equal(errors.length, 1);
  assert.equal(errors[0].title, 'Broken');
  assert.ok(errors[0].message.length > 0);
});

test('compiles a page with the diagram rendered by ak-diagram', async () => {
  await withTempDir(async (dir) => {
    const outFile = join(dir, 'page.html');
    const { io, out } = captureIo();
    const code = await main([PAGE_FIXTURE, '--out', outFile, '--json'], io);
    assert.equal(code, 0, out.stderr);
    const summary = JSON.parse(out.stdout);
    assert.equal(summary.out, outFile);
    assert.deepEqual(summary.diagramAdapter, { name: 'ak-diagram', renderVersion: PINNED_RENDER_VERSION });
    assert.deepEqual(summary.diagramErrors, []);
    assert.deepEqual(summary.warnings, []);
    const html = readFileSync(outFile, 'utf8');
    assert.match(html, /class="ak-diagram-svg"/);
    assert.doesNotMatch(html, /<script[^>]+src=/i);
    assert.equal(summary.bytes, Buffer.byteLength(html));
    // The page CSP only admits nonce'd styles: AK Render must give every
    // <style>, the diagram's included, the page nonce, and no inline style
    // attribute may remain in the diagram.
    const nonce = styleNonceOf(html);
    assert.ok(nonce, 'page CSP declares a style nonce');
    const styleTags = html.match(/<style[^>]*>/g);
    assert.ok(styleTags.length >= 2, 'page style plus diagram style');
    for (const tag of styleTags) assert.match(tag, new RegExp(`^<style nonce="${nonce}"[ >]`));
    assert.doesNotMatch(html, /style="--step:/);
  });
});

function styleNonceOf(html) {
  return /style-src (?:&#39;|')nonce-([A-Za-z0-9]+)(?:&#39;|')/.exec(html)?.[1];
}

test('invalid diagram IR falls back and reports the compiler message', async () => {
  const spec = [
    'version: 1',
    'meta: { title: Broken diagram }',
    'blocks:',
    '  - type: diagram-panel',
    '    title: Broken',
    '    spec: { schema_version: 1, diagram_type: workflow, meta: { title: Broken } }',
  ].join('\n');
  await withTempDir(async (dir) => {
    const { io, out } = captureIo(spec);
    const code = await main(['-', '--out', join(dir, 'page.html'), '--json'], io);
    assert.equal(code, 0, out.stderr);
    const summary = JSON.parse(out.stdout);
    assert.equal(summary.diagramErrors.length, 1);
    assert.equal(summary.diagramErrors[0].title, 'Broken');
    assert.equal(summary.warnings.length, 1);
    assert.match(out.stderr, /diagram "Broken"/);
  });
});

test('invalid spec exits 1 with a JSON-path diagnostic', async () => {
  const { io, out } = captureIo('version: 1\nmeta: { title: Bad }\nblocks:\n  - type: bogus\n');
  const code = await main(['-', '--json'], io);
  assert.equal(code, 1);
  assert.match(out.stderr, /\$\.blocks\[0\]\.type/);
});

test('unreadable input and unknown flags exit 2', async () => {
  const missing = captureIo();
  assert.equal(await main([join(SCRIPT_DIR, 'does-not-exist.page.yaml')], missing.io), 2);
  const badFlag = captureIo();
  assert.equal(await main([PAGE_FIXTURE, '--bogus'], badFlag.io), 2);
  const noSpec = captureIo();
  assert.equal(await main([], noSpec.io), 2);
});

test('runs as a CLI when invoked through a symlinked skill directory', async () => {
  await withTempDir((dir) => {
    const linkedScripts = join(dir, 'linked-scripts');
    symlinkSync(SCRIPT_DIR, linkedScripts, 'junction');
    const out = join(dir, 'page.html');
    execFileSync(process.execPath, [join(linkedScripts, 'render-page.mjs'), PAGE_FIXTURE, '--out', out], { stdio: 'pipe' });
    assert.ok(existsSync(out), 'the symlinked entry point must compile and write the page');
    assert.match(readFileSync(out, 'utf8'), /class="ak-diagram-svg"/);
  });
});

test('theme discovery uses the nearest ancestor of the spec that holds .ak-render', async () => {
  await withTempDir((dir) => {
    const project = join(dir, 'project');
    const specDir = join(project, 'plans', 'feature');
    mkdirSync(join(project, '.ak-render', 'themes'), { recursive: true });
    mkdirSync(specDir, { recursive: true });
    assert.equal(findThemeRoot(join(specDir, 'plan.page.yaml'), dir), project);
    const bare = join(dir, 'elsewhere');
    mkdirSync(bare);
    assert.equal(findThemeRoot(join(bare, 'plan.page.yaml'), bare), bare);
    assert.equal(findThemeRoot(undefined, bare), bare);
  });
});

test('theme discovery stops below the home directory', async () => {
  await withTempDir((dir) => {
    const home = join(dir, 'home');
    const specDir = join(home, 'work', 'plans');
    mkdirSync(join(home, '.ak-render', 'themes'), { recursive: true });
    mkdirSync(specDir, { recursive: true });
    assert.equal(findThemeRoot(join(specDir, 'plan.page.yaml'), specDir, home), specDir);
    // A bare .ak-render/ without themes/ is not a theme root.
    mkdirSync(join(home, 'work', 'plans', '.ak-render'));
    assert.equal(findThemeRoot(join(specDir, 'plan.page.yaml'), specDir, home), specDir);
    mkdirSync(join(home, 'work', '.config', 'ak-render', 'themes'), { recursive: true });
    assert.equal(findThemeRoot(join(specDir, 'plan.page.yaml'), specDir, home), join(home, 'work'));
  });
});

test('reports project theme preset problems before the compile error', async () => {
  await withTempDir(async (dir) => {
    mkdirSync(join(dir, '.ak-render', 'themes'), { recursive: true });
    writeFileSync(join(dir, '.ak-render', 'themes', 'team.yaml'), 'bogus: true\n');
    const spec = join(dir, 'page.page.yaml');
    writeFileSync(spec, 'version: 1\nmeta:\n  title: Team page\ntheme:\n  preset: team\nblocks:\n  - type: hero\n    title: Team page\n');
    const { io, out } = captureIo();
    const code = await main([spec, '--out', join(dir, 'page.html')], { ...io, cwd: dir });
    assert.equal(code, 1);
    assert.match(out.stderr, /warning: .*team\.yaml: /);
    assert.match(out.stderr, /render-page: .*team/);
    assert.ok(out.stderr.indexOf('warning:') < out.stderr.indexOf('render-page:'), 'preset warnings precede the compile error');
  });
});

test('a flag-looking --out value exits 2 and --out - writes to stdout', async () => {
  const flagValue = captureIo();
  assert.equal(await main([PAGE_FIXTURE, '--out', '--json'], flagValue.io), 2);
  assert.match(flagValue.out.stderr, /unknown or incomplete flag --out/);

  const toStdout = captureIo();
  assert.equal(await main([PAGE_FIXTURE, '--out', '-'], toStdout.io), 0);
  assert.match(toStdout.out.stdout, /^<!doctype html>/i);
});

test('ignores a package beside a PATH entry that is not node_modules/.bin', async () => {
  await withTempDir(async (dir) => {
    // A plain PATH dir whose parent holds a package must never be imported.
    const plainDir = join(dir, 'tools', 'bin');
    const pkgDir = join(dir, 'tools', '@bestagentkits', 'render');
    mkdirSync(plainDir, { recursive: true });
    mkdirSync(pkgDir, { recursive: true });
    writeFileSync(join(pkgDir, 'package.json'), JSON.stringify({ name: '@bestagentkits/render', type: 'module', main: 'index.js' }));
    writeFileSync(join(pkgDir, 'index.js'), "throw new Error('must not be imported');\n");
    await assert.rejects(
      resolveRenderLibrary({ pathDirs: [plainDir], allowBareImport: false }),
      (error) => error.message.includes('no install found'),
    );
  });
});

test('a broken candidate on PATH is reported and the search continues', async () => {
  await withTempDir(async (dir) => {
    const binDir = join(dir, 'node_modules', '.bin');
    const pkgDir = join(dir, 'node_modules', '@bestagentkits', 'render');
    mkdirSync(binDir, { recursive: true });
    mkdirSync(pkgDir, { recursive: true });
    writeFileSync(join(pkgDir, 'package.json'), '{ not json');
    const library = await resolveRenderLibrary({ pathDirs: [binDir] });
    assert.equal(library.VERSION, PINNED_RENDER_VERSION);
    await assert.rejects(
      resolveRenderLibrary({ pathDirs: [binDir], allowBareImport: false }),
      (error) => error.message.includes('import failed'),
    );
  });
});

test('reports the AK Render hash of the written page', async () => {
  const library = await resolveRenderLibrary({ pathDirs: [] });
  const plain = 'version: 1\nmeta:\n  title: Plain\nblocks:\n  - type: hero\n    title: Plain\n';
  const compiled = library.compile(plain);

  await withTempDir(async (dir) => {
    const { io, out } = captureIo(plain);
    assert.equal(await main(['-', '--out', join(dir, 'page.html'), '--json'], io), 0, out.stderr);
    const summary = JSON.parse(out.stdout);
    assert.match(summary.hash, /^[0-9a-z]{14}$/);
    assert.equal(summary.hash, compiled.hash);
    assert.equal(readFileSync(join(dir, 'page.html'), 'utf8'), compiled.html);
  });
});

test('refuses an --out path that is the input spec', async () => {
  await withTempDir(async (dir) => {
    const spec = join(dir, 'page.page.yaml');
    writeFileSync(spec, 'version: 1\nmeta:\n  title: Self\nblocks:\n  - type: hero\n    title: Self\n');
    const { io, out } = captureIo();
    assert.equal(await main([spec, '--out', spec], { ...io, cwd: dir }), 2);
    assert.match(out.stderr, /must not overwrite the input spec/);
    assert.match(readFileSync(spec, 'utf8'), /^version: 1/);
  });
});

test('lists theme problems in the JSON summary when the page still compiles', async () => {
  await withTempDir(async (dir) => {
    mkdirSync(join(dir, '.ak-render', 'themes'), { recursive: true });
    writeFileSync(join(dir, '.ak-render', 'themes', 'team.yaml'), 'bogus: true\n');
    const spec = join(dir, 'page.page.yaml');
    writeFileSync(spec, 'version: 1\nmeta:\n  title: Plain page\nblocks:\n  - type: hero\n    title: Plain page\n');
    const { io, out } = captureIo();
    const code = await main([spec, '--out', join(dir, 'page.html'), '--json'], { ...io, cwd: dir });
    assert.equal(code, 0);
    const summary = JSON.parse(out.stdout);
    assert.ok(summary.themeProblems.length > 0);
    assert.match(summary.themeProblems[0].path, /team\.yaml$/);
  });
});

test('a theme catalog that cannot be read exits 2, not 1', async () => {
  const library = await resolveRenderLibrary({ pathDirs: [] });
  const broken = { ...library, buildThemeCatalog: () => { throw new Error('EACCES: permission denied, scandir'); } };
  const { io, out } = captureIo();
  assert.equal(await main([PAGE_FIXTURE, '--out', '-'], { ...io, library: broken }), 2);
  assert.match(out.stderr, /cannot load theme presets: EACCES/);
});
