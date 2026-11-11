/**
 * Compile an AK Render Page Spec with ak-diagram registered as the diagram adapter.
 *
 * The published `ak-render` CLI has no adapter flag, so through the CLI every
 * `diagram-panel` block renders only its semantic fallback. This wrapper calls
 * the library `compile()` with an adapter backed by this skill's typed compiler,
 * so diagram panels embed the real deterministic SVG. Everything else (spec
 * parsing, validation, theme discovery, offline document assembly, adapter
 * markup checks) stays inside AK Render.
 *
 * Usage, from any directory (npx supplies the pinned library):
 *   npx -y -p @bestagentkits/render@0.3.0 node <ak-diagram>/scripts/render-page.mjs \
 *     page.yaml --out page.html [--theme <preset>] [--json]
 *
 * Exit codes mirror `ak-render`: 0 compiled, 1 fix the spec, 2 environment
 * problem or internal failure (unreadable input, unwritable output, bad flags, wrong or missing
 * library version).
 */

import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, delimiter, dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { compile as compileDiagram } from './compiler/compile.mjs';

/** The AK Render version every AgentKit skill pins; keep kit prose in step. */
export const PINNED_RENDER_VERSION = '0.3.0';
const PACKAGE_NAME = '@bestagentkits/render';
const SCRIPT_PATH = fileURLToPath(import.meta.url);
const NPX_HINT = `npx -y -p ${PACKAGE_NAME}@${PINNED_RENDER_VERSION} node "${SCRIPT_PATH}" <spec> --out <file.html>`;

class EnvironmentError extends Error {}

/**
 * Package directories implied by PATH entries that are `node_modules/.bin`
 * folders (npx puts its temporary install there). Walking from the bin folder
 * instead of resolving the bin symlink keeps this working with Windows shims.
 */
function packageDirsFromPath(pathDirs) {
  // Only real `node_modules/.bin` entries: importing runs package code, so an
  // arbitrary PATH entry (or a relative `.`) must never pick a sibling package.
  return pathDirs
    .filter((dir) => dir && basename(dir) === '.bin' && basename(dirname(dir)) === 'node_modules')
    .map((dir) => join(dir, '..', '@bestagentkits', 'render'))
    .filter((dir) => existsSync(join(dir, 'package.json')));
}

/** Import a package directory through its declared ESM entry point. */
async function importPackageDir(dir) {
  const manifest = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8'));
  const rootExport = manifest.exports?.['.'];
  const entry = (typeof rootExport === 'string' ? rootExport : rootExport?.import) ?? manifest.main ?? 'index.js';
  return import(pathToFileURL(join(dir, entry)).href);
}

/**
 * Load the pinned AK Render library. Candidates on PATH (an explicit
 * `npx -p` install) win over a package resolvable from this script's own
 * location (the repository devDependency in CI); the first candidate at the
 * pinned version is used. Any other version is refused rather than risking
 * output that differs from what the skills document.
 */
export async function resolveRenderLibrary({
  pathDirs = (process.env.PATH || '').split(delimiter),
  allowBareImport = true,
} = {}) {
  const found = [];
  for (const dir of packageDirsFromPath(pathDirs)) {
    let library;
    try {
      library = await importPackageDir(dir);
    } catch (error) {
      found.push(`${dir}: import failed (${error instanceof Error ? error.message : String(error)})`);
      continue;
    }
    if (library.VERSION === PINNED_RENDER_VERSION) return library;
    found.push(`${library.VERSION} at ${dir}`);
  }
  if (allowBareImport) {
    try {
      const library = await import(PACKAGE_NAME);
      if (library.VERSION === PINNED_RENDER_VERSION) return library;
      found.push(`${library.VERSION} (resolved from the script location)`);
    } catch (error) {
      // Only "the package itself is absent" means keep looking; a present
      // package with a broken dependency must surface its own error.
      if (error?.code !== 'ERR_MODULE_NOT_FOUND' || !String(error.message).includes(`'${PACKAGE_NAME}'`)) throw error;
    }
  }
  const seen = found.length > 0 ? `found ${found.join(', ')}` : 'no install found';
  throw new EnvironmentError(
    `${PACKAGE_NAME}@${PINNED_RENDER_VERSION} is required (${seen}); run: ${NPX_HINT}`,
  );
}

/**
 * Diagram adapter backed by the ak-diagram compiler. A compiler error is
 * recorded (AK Render's own warning does not carry the reason) and rethrown so
 * AK Render emits the structured semantic fallback for that panel.
 *
 * The page CSP refuses inline style attributes and AK Render strips them with
 * a warning, so the per-element `style="--step:N"` animation delays are
 * dropped here; the stylesheet falls back to `var(--step, 0)`.
 */
export function createDiagramAdapter(errors) {
  return {
    name: 'ak-diagram',
    version: '1.0.0',
    render({ spec, title }) {
      try {
        return compileDiagram(spec, { format: 'svg' }).replace(/ style="--step:[^"]*"/g, '');
      } catch (error) {
        errors.push({ title, message: error instanceof Error ? error.message : String(error) });
        throw error;
      }
    },
  };
}

function parseArgs(argv) {
  const flags = { spec: undefined, out: undefined, theme: undefined, json: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--json') flags.json = true;
    else if (arg === '--out' && argv[i + 1] === '-') { i += 1; } // `-` means stdout, like no --out
    else if ((arg === '--out' || arg === '--theme') && i + 1 < argv.length && !argv[i + 1].startsWith('--')) flags[arg.slice(2)] = argv[++i];
    else if (arg === '-' || !arg.startsWith('-')) {
      if (flags.spec !== undefined) throw new EnvironmentError(`unexpected argument ${arg}`);
      flags.spec = arg;
    } else throw new EnvironmentError(`unknown or incomplete flag ${arg}`);
  }
  if (flags.spec === undefined) throw new EnvironmentError('a spec path (or - for stdin) is required');
  return flags;
}

function readStdinDefault() {
  return new Promise((resolveText, reject) => {
    let text = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { text += chunk; });
    process.stdin.on('end', () => resolveText(text));
    process.stdin.on('error', reject);
  });
}

/** Project theme folders AK Render searches under its working directory (its THEME_DIRECTORIES). */
const PROJECT_THEME_MARKERS = [join('.ak-render', 'themes'), join('.config', 'ak-render', 'themes')];

/** Path identity for the home-boundary check: realpath when it exists, case-folded on Windows. */
function samePath(a, b) {
  const canonical = (path) => {
    let real = resolve(path);
    try { real = realpathSync.native(real); } catch { /* keep the resolved path */ }
    return process.platform === 'win32' ? real.toLowerCase() : real;
  };
  return canonical(a) === canonical(b);
}

/**
 * AK Render discovers project theme presets only under its working directory.
 * Specs usually live deep in `plans/`, so use the nearest directory, from the
 * spec's own folder up, that holds a project theme folder; otherwise the
 * working dir. The walk stops below the home directory, whose theme folders
 * AK Render already reads as user presets.
 */
export function findThemeRoot(specPath, cwd, home = homedir()) {
  if (specPath !== undefined) {
    for (let dir = dirname(specPath); !samePath(dir, home); dir = dirname(dir)) {
      if (PROJECT_THEME_MARKERS.some((marker) => existsSync(join(dir, marker)))) return dir;
      if (dirname(dir) === dir) break;
    }
  }
  return cwd;
}

/** Run the wrapper; returns the exit code instead of exiting so tests can drive it. */
export async function main(argv, io = {}) {
  const stdout = io.stdout ?? ((text) => process.stdout.write(text));
  const stderr = io.stderr ?? ((text) => process.stderr.write(text));
  const cwd = io.cwd ?? process.cwd();
  let flags;
  let library;
  let text;
  try {
    flags = parseArgs(argv);
    library = io.library ?? await resolveRenderLibrary(io.resolveOptions);
    text = flags.spec === '-'
      ? await (io.readStdin ?? readStdinDefault)()
      : readFileSync(resolve(cwd, flags.spec), 'utf8');
    if (flags.out !== undefined && flags.spec !== '-' && samePath(resolve(cwd, flags.out), resolve(cwd, flags.spec))) {
      throw new EnvironmentError('--out must not overwrite the input spec');
    }
  } catch (error) {
    stderr(`render-page: ${error instanceof Error ? error.message : String(error)}\n`);
    return 2;
  }

  // Preset load problems are warnings, as in the `ak-render` CLI; without them
  // an "unknown theme preset" error gives the agent nothing to repair.
  // An unreadable theme folder is an environment problem (exit 2), not a spec fix.
  let themeCatalog;
  try {
    themeCatalog = library.buildThemeCatalog({
      cwd: findThemeRoot(flags.spec === '-' ? undefined : resolve(cwd, flags.spec), cwd),
    });
  } catch (error) {
    stderr(`render-page: cannot load theme presets: ${error instanceof Error ? error.message : String(error)}\n`);
    return 2;
  }
  for (const problem of themeCatalog.problems ?? []) {
    stderr(`warning: ${problem.path}: ${problem.message}\n`);
  }

  const diagramErrors = [];
  let result;
  try {
    result = library.compile(text, {
      source: flags.spec === '-' ? '<stdin>' : flags.spec,
      themeCatalog,
      diagramAdapter: createDiagramAdapter(diagramErrors),
      ...(flags.theme === undefined ? {} : { theme: flags.theme }),
    });
  } catch (error) {
    if (!library.isRenderError(error)) {
      stderr(`render-page: internal compile failure: ${error instanceof Error ? error.message : String(error)}\n`);
      return 2;
    }
    stderr(`render-page: ${error.message} (${error.path ?? '$'})\n`);
    for (const diagnostic of error.details?.diagnostics ?? []) {
      stderr(`${diagnostic.severity}: ${diagnostic.path}: ${diagnostic.message} [${diagnostic.code}]\n`);
    }
    return 1;
  }

  const { html, hash } = result;
  const bytes = Buffer.byteLength(html);

  if (flags.out !== undefined) {
    try {
      const outFile = resolve(cwd, flags.out);
      mkdirSync(dirname(outFile), { recursive: true });
      writeFileSync(outFile, html, 'utf8');
    } catch (error) {
      stderr(`render-page: cannot write ${flags.out}: ${error instanceof Error ? error.message : String(error)}\n`);
      return 2;
    }
  } else {
    stdout(html);
  }

  if (flags.json) {
    stdout(`${JSON.stringify({
      source: flags.spec === '-' ? '<stdin>' : flags.spec,
      out: flags.out ?? null,
      bytes,
      hash,
      title: result.ir.meta.title,
      theme: result.theme.name,
      features: result.features,
      nodes: result.ir.nodes.length,
      diagramAdapter: { name: 'ak-diagram', renderVersion: library.VERSION },
      diagramErrors,
      themeProblems: themeCatalog.problems ?? [],
      warnings: result.warnings,
    }, null, 2)}\n`);
  } else if (flags.out !== undefined) {
    stdout(`wrote ${bytes} bytes to ${flags.out} (hash ${hash})\n`);
  }
  for (const failure of diagramErrors) {
    stderr(`warning: diagram "${failure.title}": ${failure.message}; semantic fallback used\n`);
  }
  for (const warning of result.warnings) {
    stderr(`warning: ${warning.path}: ${warning.message}\n`);
  }
  return 0;
}

/** True when this file is the process entry point, also through symlinks, `/tmp` aliases or junctions. */
function isEntryPoint() {
  if (!process.argv[1]) return false;
  try {
    return realpathSync(process.argv[1]) === realpathSync(SCRIPT_PATH);
  } catch {
    return false;
  }
}

if (isEntryPoint()) {
  process.exitCode = await main(process.argv.slice(2));
}
