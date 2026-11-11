#!/usr/bin/env node
/**
 * Update session state with new active plan
 *
 * Usage: node .claude/scripts/set-active-plan.cjs <plan-path>
 *        node .claude/scripts/set-active-plan.cjs --clear
 *
 * The runnable copy lives beside the emitted hook tree (`.claude/scripts/` for a
 * native project install, `~/.claude/scripts/` for a native global install, and
 * `<plugin>/scripts/` under an explicit plugin install) so the require below
 * resolves. The `.agentkit/scripts/` sidecar leaf is a forwarder to it.
 *
 * This script updates the session temp file with the new active plan path,
 * allowing subagents to receive the latest plan context via SubagentStart hook.
 *
 * The runtime-temporary session state is the source of truth for plan context
 * within a session. Environment variables are only the session-start snapshot.
 *
 * Exit 0 means the change was persisted and read back. Every outcome that
 * persists nothing exits non-zero, so a caller can never mistake a no-op for an
 * activation.
 *
 * This is session-scoped and distinct from `ak plan use`'s worktree-scoped
 * current-plan pointer — see docs/system-architecture.md, decision ledger,
 * "Session-scoped plan activation is retained; it is not the worktree plan
 * pointer", for why both mechanisms exist.
 */

const fs = require('fs');
const path = require('path');
const {
  describeSessionStateContext,
  readSessionState,
  updateSessionState,
  loadConfig,
  getReportsPath
} = require('../hooks/lib/ck-config-utils.cjs');
const { pathContains } = require('../hooks/lib/runtime-state-identity.cjs');

function usage() {
  console.log('Usage: node .claude/scripts/set-active-plan.cjs <plan-path>');
  console.log('       node .claude/scripts/set-active-plan.cjs --clear');
  console.log('Example: node .claude/scripts/set-active-plan.cjs plans/<timestamp>-feature-name');
}

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error('Error: Plan path required');
  usage();
  process.exit(1);
}
if (args.length > 1) {
  console.error(`Error: expected one argument, got ${args.length}`);
  usage();
  process.exit(1);
}

const clear = args[0] === '--clear';
if (!clear && args[0].startsWith('-')) {
  console.error(`Error: unknown option ${args[0]}`);
  usage();
  process.exit(1);
}

const { context: sessionContext, reason } = describeSessionStateContext({
  sessionId: process['env'].CK_SESSION_ID,
  cwd: process['env'].CK_PROJECT_ROOT || process.cwd(),
  requireBinding: true
});

if (!sessionContext) {
  fail(`no bound session state (${reason}); the active plan was not changed. ` +
    'Run this from a session started in the project, with CK_SESSION_ID set.');
}

// The session belongs to the project it was bound in. Invoking the script from
// another project still changes that session, never the invoking project, so
// say so instead of letting the caller assume otherwise.
let invokingDir = path.resolve(process.cwd());
try {
  invokingDir = fs.realpathSync.native(invokingDir);
} catch { /* compare the unresolved path */ }
if (!pathContains(sessionContext.canonicalProjectRoot, invokingDir)) {
  console.warn(`Warning: this session is bound to ${sessionContext.canonicalProjectRoot}, ` +
    'not the current directory; the change applies to that session.');
}

let absolutePlan = null;
if (!clear) {
  // Resolve relative paths from the immutable session launch directory, not the
  // caller's current directory after an in-session `cd`.
  absolutePlan = path.resolve(sessionContext.sessionLaunchRoot, args[0]);
  let isDirectory = false;
  try {
    isDirectory = fs.statSync(absolutePlan).isDirectory();
  } catch { /* reported below */ }
  if (!isDirectory) {
    fail(`plan directory does not exist: ${absolutePlan}` +
      (path.isAbsolute(args[0]) ? '' : ` (relative paths resolve from ${sessionContext.sessionLaunchRoot}; pass an absolute path otherwise)`));
  }
}

const success = updateSessionState(sessionContext, current => {
  const next = { ...current, timestamp: Date.now() };
  if (clear) delete next.activePlan;
  else next.activePlan = absolutePlan;
  return next;
});

const persisted = readSessionState(sessionContext);
const readBack = persisted ? (persisted.activePlan || null) : undefined;
if (!success || readBack !== absolutePlan) {
  fail('failed to persist the active plan to session state');
}

if (clear) {
  console.log('Active plan cleared');
  process.exit(0);
}

console.log(`Active plan set to: ${absolutePlan}`);

// Activation is the moment the plan-scoped reports directory starts being
// advertised to every subagent, so create it here. A subagent that trusts the
// injected Reports path otherwise writes into a directory nothing made.
// A failure here does not undo a successful activation.
try {
  const config = loadConfig({ includeProject: false, includeAssertions: false });
  const reportsPath = getReportsPath(absolutePlan, 'session', config.plan, config.paths);
  fs.mkdirSync(reportsPath, { recursive: true });
} catch (e) {
  console.warn(`Warning: could not create the plan reports directory: ${e.message}`);
}
