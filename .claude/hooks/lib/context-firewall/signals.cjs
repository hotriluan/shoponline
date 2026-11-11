'use strict';

/**
 * signals.cjs - Deterministic blast-radius signals for the context firewall.
 *
 * A signal is a fact about how much output a tool call can return, derived only
 * from the call itself plus `fs.statSync`. Nothing here guesses intent, and the
 * same inputs always produce the same signals, so a verdict is reproducible and
 * unit-testable.
 *
 * Three operation kinds carry blast radius:
 * - read   : whole-file reads with no offset/limit window
 * - search : pattern searches whose breadth and result bound are both loose
 * - shell  : commands that dump files, logs, or recursive trees
 */

const fs = require('fs');
const path = require('path');

const {
  SHELL_DIALECT_POWERSHELL,
  shellDialect,
  shellEscapeChar,
  normalizeShellCommand,
  stripCommandPrefix,
  unwrapShellExecutor,
  isAllowedCommand,
  detectBroadPatternIssue
} = require('../scout-checker.cjs');

// Commands that print a whole file with no built-in bound.
const WHOLE_FILE_DUMP_COMMANDS = new Set(['cat', 'bat', 'less', 'more', 'nl']);

// Log readers that stream everything unless explicitly bounded, mapped to the
// flag that bounds them.
const LOG_STREAM_COMMANDS = {
  journalctl: ['-n', '--lines'],
  dmesg: ['-n', '--lines'],
  'docker logs': ['--tail'],
  'kubectl logs': ['--tail'],
  'docker compose logs': ['--tail']
};

// Recursive walkers that traverse everything below their starting point.
const RECURSIVE_WALK_COMMANDS = new Set(['find', 'tree']);

// PowerShell spellings of the same operations. PowerShell resolves command and
// parameter names case-insensitively and accepts any unambiguous parameter
// prefix, so commands are keyed lower-cased and parameters are matched by
// isPowerShellParameter.
const POWERSHELL_FILE_DUMP_COMMANDS = new Set(['get-content', 'gc', 'type', 'cat']);
// Get-Content parameters (with their aliases) that bound how much is read.
const POWERSHELL_READ_BOUND_PARAMETERS = ['-TotalCount', '-Head', '-First', '-Tail', '-Last'];
const POWERSHELL_LOG_STREAM_COMMANDS = {
  'get-winevent': ['-MaxEvents'],
  'get-eventlog': ['-Newest']
};
// Get-ChildItem and its aliases walk the tree only with -Recurse; -Depth bounds it.
const POWERSHELL_WALK_COMMANDS = new Set(['get-childitem', 'gci', 'dir', 'ls']);
// Final pipeline stages that bound (or discard) whatever came before them.
const POWERSHELL_BOUNDING_STAGES = {
  'select-object': ['-First', '-Last', '-Index'],
  select: ['-First', '-Last', '-Index'],
  'measure-object': [],
  measure: [],
  'out-null': []
};
// Final pipeline stages that write the output to a file, like `tee` and `>`.
const POWERSHELL_FILE_SINK_STAGES = new Set([
  'out-file', 'set-content', 'sc', 'add-content', 'ac', 'tee-object', 'tee'
]);

/**
 * Whether a PowerShell token names one of `parameters`, in any case, by any
 * unambiguous prefix of at least two letters, and in the `-Name:value` form.
 *
 * @param {string} token
 * @param {string[]} parameters - parameter names with the leading dash
 * @returns {boolean}
 */
function isPowerShellParameter(token, parameters) {
  if (!/^-[A-Za-z]/.test(token)) return false;
  const name = token.toLowerCase().replace(/:.*$/, '');
  return name.length >= 3 && parameters.some(parameter => parameter.toLowerCase().startsWith(name));
}

/**
 * An operand as PowerShell would bind it: the value of `-Path:x`, without the
 * quotes the caller wrapped it in.
 *
 * @param {string} token
 * @returns {string}
 */
function powerShellOperand(token) {
  const bound = token.match(/^-[A-Za-z][\w-]*:(.+)$/);
  const value = bound ? bound[1] : token;
  const quoted = value.match(/^(["'])(.*)\1$/);
  return quoted ? quoted[2] : value;
}

/**
 * Size a path on disk, returning null when it is missing or not a regular file.
 *
 * @param {string} target
 * @returns {number|null}
 */
function fileBytes(target) {
  try {
    const info = fs.statSync(target);
    return info.isFile() ? info.size : null;
  } catch {
    return null;
  }
}

/**
 * Resolve a possibly-relative path against the call's working directory.
 *
 * @param {string} target
 * @param {string} cwd
 * @returns {string}
 */
function resolveAgainst(target, cwd) {
  if (!target || typeof target !== 'string') return '';
  return path.isAbsolute(target) ? target : path.resolve(cwd || process.cwd(), target);
}

/**
 * Classify a tool call into the operation kind whose policy applies.
 *
 * Runtimes name their tools differently, so the name is only a hint; the shape
 * of `tool_input` decides when the name is unfamiliar.
 *
 * @param {string} toolName
 * @param {object} toolInput
 * @returns {'read'|'search'|'shell'|'other'}
 */
function classifyOperation(toolName, toolInput) {
  const name = String(toolName || '').toLowerCase();
  if (name.includes('bash') || name.includes('shell') || name.includes('terminal')) return 'shell';
  if (name.includes('grep') || name.includes('glob') || name.includes('search')) return 'search';
  if (name.includes('read')) return 'read';

  if (typeof toolInput?.command === 'string') return 'shell';
  if (typeof toolInput?.pattern === 'string') return 'search';
  if (typeof toolInput?.file_path === 'string') return 'read';
  return 'other';
}

/**
 * Signals for a whole-file read.
 *
 * A read that already carries an offset or limit is windowed by construction
 * and never flagged, however large the file is.
 */
function readSignals({ toolInput, cwd, thresholds }) {
  const filePath = toolInput?.file_path || toolInput?.path;
  if (typeof filePath !== 'string' || !filePath) return { signals: [], facts: {} };

  const hasWindow =
    Number.isFinite(Number(toolInput?.limit)) ||
    Number.isFinite(Number(toolInput?.offset)) ||
    typeof toolInput?.pages === 'string';

  const resolved = resolveAgainst(filePath, cwd);
  const bytes = fileBytes(resolved);
  const facts = { filePath, bytes, windowed: hasWindow };

  if (hasWindow || bytes === null) return { signals: [], facts };

  if (bytes >= thresholds.readBlockBytes) {
    return {
      signals: [{ id: 'read.unbounded', severity: 'block', bytes }],
      facts
    };
  }
  if (bytes >= thresholds.readWarnBytes) {
    return {
      signals: [{ id: 'read.unbounded', severity: 'warn', bytes }],
      facts
    };
  }
  return { signals: [], facts };
}

/**
 * Signals for a pattern search.
 *
 * Breadth reuses `scout-block`'s existing detector so the firewall and the
 * blocker agree on what "broad" means. Breadth alone is not a flood: it only
 * matters when the search also returns file *content* with no result bound.
 */
function searchSignals({ toolInput, thresholds }) {
  const pattern = toolInput?.pattern;
  if (typeof pattern !== 'string' || !pattern) return { signals: [], facts: {} };

  const outputMode = toolInput?.output_mode || 'files_with_matches';
  const headLimit = Number(toolInput?.head_limit);
  const bounded = Number.isFinite(headLimit) && headLimit > 0 && headLimit <= thresholds.searchHeadLimit;
  const searchPath = toolInput?.path || '.';

  let broad = false;
  try {
    broad = Boolean(detectBroadPatternIssue({ pattern, path: searchPath })?.blocked);
  } catch {
    broad = false;
  }

  const facts = { pattern, outputMode, headLimit: bounded ? headLimit : null, broad, searchPath };
  const returnsContent = outputMode === 'content';

  if (returnsContent && !bounded) {
    return {
      signals: [{ id: 'search.unbounded-content', severity: broad ? 'block' : 'warn', broad }],
      facts
    };
  }
  return { signals: [], facts };
}

/**
 * Read the token following a flag, supporting both `--tail 50` and `--tail=50`.
 *
 * @param {string[]} tokens
 * @param {string[]} flags
 * @returns {boolean} whether any of the flags is present with a value
 */
function hasBoundingFlag(tokens, flags) {
  return tokens.some((token, index) => {
    for (const flag of flags) {
      if (token === flag && tokens[index + 1] !== undefined) return true;
      if (token.startsWith(`${flag}=`) && token.length > flag.length + 1) return true;
    }
    return false;
  });
}

/**
 * Split a command into pipelines on `&&`, `||`, `;` and newlines, leaving each
 * pipeline's `|` stages intact.
 *
 * `scout-checker`'s `splitCompoundCommand` also splits on `|`, which loses the
 * distinction between `cat big.log | head` (bounded) and `cat big.log; head`
 * (not). That distinction is the whole point here, so this splitter keeps it.
 * Quotes are respected so a separator inside a string is not a separator.
 *
 * @param {string} command
 * @param {string} [dialect] - 'posix' (default) or 'powershell'; selects the escape character
 * @returns {string[]}
 */
function splitPipelines(command, dialect) {
  const escape = shellEscapeChar(dialect);
  const pipelines = [];
  let current = '';
  let quote = null;

  for (let index = 0; index < command.length; index += 1) {
    const char = command[index];

    if (quote) {
      current += char;
      if (char === quote && command[index - 1] !== escape) quote = null;
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      current += char;
      continue;
    }
    if (char === '\n' || char === ';') {
      pipelines.push(current);
      current = '';
      continue;
    }
    if ((char === '&' && command[index + 1] === '&') || (char === '|' && command[index + 1] === '|')) {
      pipelines.push(current);
      current = '';
      index += 1;
      continue;
    }
    current += char;
  }
  pipelines.push(current);

  return pipelines.map(entry => entry.trim()).filter(Boolean);
}

/**
 * Split one pipeline into its `|` stages, respecting quotes.
 *
 * @param {string} pipeline
 * @param {string} [dialect] - 'posix' (default) or 'powershell'; selects the escape character
 * @returns {string[]}
 */
function splitStages(pipeline, dialect) {
  const escape = shellEscapeChar(dialect);
  const stages = [];
  let current = '';
  let quote = null;

  for (let index = 0; index < pipeline.length; index += 1) {
    const char = pipeline[index];
    if (quote) {
      current += char;
      if (char === quote && pipeline[index - 1] !== escape) quote = null;
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      current += char;
      continue;
    }
    if (char === '|') {
      stages.push(current);
      current = '';
      continue;
    }
    current += char;
  }
  stages.push(current);

  return stages.map(entry => entry.trim()).filter(Boolean);
}

/**
 * Whether a pipeline sends its stdout to a file rather than back to the model.
 *
 * Output that never reaches context has no blast radius, so this is the single
 * strongest false-positive guard. `2>` and `&>` are stderr forms and do not
 * count as a stdout redirect on their own.
 *
 * PowerShell also writes a pipeline to a file by ending it in Out-File,
 * Set-Content, Add-Content, or Tee-Object.
 *
 * @param {string} pipeline
 * @param {string} [dialect] - 'posix' (default) or 'powershell'
 * @returns {boolean}
 */
function redirectsToFile(pipeline, dialect) {
  if (/(^|\s)\|\s*tee\b/.test(pipeline)) return true;
  if (dialect === SHELL_DIALECT_POWERSHELL) {
    const stages = splitStages(pipeline, dialect);
    const last = stages.length > 1 ? stages[stages.length - 1].split(/\s+/)[0].toLowerCase() : '';
    if (POWERSHELL_FILE_SINK_STAGES.has(last)) return true;
  }
  return /(^|[^0-9&>])>{1,2}\s*[^\s&|]+/.test(pipeline.replace(/2>\S+/g, ''));
}

/**
 * Whether any short-flag cluster (`-rn`, `-li`) carries one of `letters`,
 * independent of the order the letters appear in.
 *
 * @param {string[]} tokens
 * @param {string} letters
 * @returns {boolean}
 */
function hasShortFlag(tokens, letters) {
  return tokens.some(token =>
    /^-[a-zA-Z]+$/.test(token) && [...token.slice(1)].some(letter => letters.includes(letter)));
}

// Final pipeline stages that bound whatever came before them.
const BOUNDING_STAGE_VERBS = new Set(['head', 'tail', 'wc', 'sort', 'uniq', 'jq', 'column']);

/**
 * Whether a pipeline's last stage caps the volume that reaches the model.
 *
 * @param {string[]} stages
 * @param {string} [dialect] - 'posix' (default) or 'powershell'
 * @returns {boolean}
 */
function isTerminallyBounded(stages, dialect) {
  if (stages.length < 2) return false;
  const last = stripCommandPrefix(stages[stages.length - 1]);
  const tokens = last.split(/\s+/).filter(Boolean);
  const verb = tokens[0];

  if (dialect === SHELL_DIALECT_POWERSHELL) {
    const key = String(verb || '').toLowerCase();
    if (Object.prototype.hasOwnProperty.call(POWERSHELL_BOUNDING_STAGES, key)) {
      const bounds = POWERSHELL_BOUNDING_STAGES[key];
      // Select-Object only bounds with -First/-Last/-Index; Measure-Object and
      // Out-Null never pass the content on.
      if (bounds.length === 0) return true;
      if (tokens.slice(1).some(token => isPowerShellParameter(token, bounds))) return true;
    }
  }

  if (BOUNDING_STAGE_VERBS.has(verb)) {
    // `sort` and `uniq` reorder without bounding; they only count when the
    // pipeline ends in something that truly caps the output.
    if (verb === 'sort' || verb === 'uniq') return false;
    return true;
  }
  // `grep -c` and `grep -l` return counts and names, not content.
  if (/^(grep|egrep|rg)$/.test(verb) && hasShortFlag(tokens, 'cl')) return true;
  return false;
}

/**
 * Size each operand of a whole-file dump and flag the ones that flood context.
 *
 * @param {object} args
 * @param {string[]} args.operands
 * @param {string} args.verb
 * @param {string} args.cwd
 * @param {object} args.thresholds
 * @param {object} [args.extra] - fields copied onto every signal
 * @returns {object[]}
 */
function fileDumpSignals({ operands, verb, cwd, thresholds, extra = {} }) {
  const signals = [];
  for (const target of operands) {
    const bytes = fileBytes(resolveAgainst(target, cwd));
    if (bytes === null) continue;
    if (bytes >= thresholds.shellDumpBlockBytes) {
      signals.push({ id: 'shell.file-dump', severity: 'block', bytes, target, verb, ...extra });
    } else if (bytes >= thresholds.shellDumpWarnBytes) {
      signals.push({ id: 'shell.file-dump', severity: 'warn', bytes, target, verb, ...extra });
    }
  }
  return signals;
}

/**
 * Signals for a PowerShell leading stage whose verb is a PowerShell file
 * reader, event-log reader, or directory walker, or null when the verb is
 * none of those and the shared checks (git, docker, grep, find, ...) apply.
 *
 * @param {object} args
 * @param {string[]} args.tokens
 * @param {string} args.cwd
 * @param {object} args.thresholds
 * @returns {object[]|null}
 */
function powerShellSignals({ tokens, cwd, thresholds }) {
  const verb = tokens[0];
  const key = String(verb || '').toLowerCase();
  const args = tokens.slice(1);
  const extra = { dialect: SHELL_DIALECT_POWERSHELL };

  if (POWERSHELL_FILE_DUMP_COMMANDS.has(key)) {
    if (args.some(token => isPowerShellParameter(token, POWERSHELL_READ_BOUND_PARAMETERS))) return [];
    const operands = args
      .filter(token => !/^-[A-Za-z]/.test(token) || /^-[A-Za-z][\w-]*:./.test(token))
      .map(powerShellOperand);
    return fileDumpSignals({ operands, verb, cwd, thresholds, extra });
  }

  if (Object.prototype.hasOwnProperty.call(POWERSHELL_LOG_STREAM_COMMANDS, key)) {
    const bounds = POWERSHELL_LOG_STREAM_COMMANDS[key];
    if (args.some(token => isPowerShellParameter(token, bounds))) return [];
    return [{ id: 'shell.log-stream', severity: 'warn', verb, boundFlag: bounds[0], ...extra }];
  }

  if (POWERSHELL_WALK_COMMANDS.has(key)) {
    const recursive = args.some(token => /^-r(?:e(?:c(?:u(?:r(?:s(?:e)?)?)?)?)?)?(?::\$true)?$/i.test(token));
    if (!recursive || args.some(token => isPowerShellParameter(token, ['-Depth']))) return [];
    return [{ id: 'shell.recursive-walk', severity: 'warn', verb, ...extra }];
  }

  return null;
}

/**
 * Signals for the leading stage of one pipeline.
 */
function pipelineSignals({ pipeline, cwd, thresholds, dialect }) {
  // Output that lands in a file, or is capped by a final stage, cannot flood
  // the model's context whatever the leading command is.
  if (redirectsToFile(pipeline, dialect)) return [];

  const stages = splitStages(pipeline, dialect);
  if (isTerminallyBounded(stages, dialect)) return [];

  const command = stripCommandPrefix(unwrapShellExecutor(stages[0]) || stages[0]);
  if (!command) return [];

  const tokens = command.split(/\s+/).filter(Boolean);
  if (dialect === SHELL_DIALECT_POWERSHELL) {
    const powerShell = powerShellSignals({ tokens, cwd, thresholds });
    if (powerShell) return powerShell;
  }

  const verb = tokens[0];
  const twoWordVerb = tokens.length > 1 ? `${tokens[0]} ${tokens[1]}` : '';
  const logFlags = LOG_STREAM_COMMANDS[twoWordVerb] || LOG_STREAM_COMMANDS[verb];

  // Build and package-manager commands are the project's own tooling; their
  // output is the point of running them. Log subcommands are the exception:
  // `docker logs` and `kubectl logs` pass the tooling allowlist yet stream
  // without bound, which is exactly what this hook exists to catch.
  if (!logFlags) {
    try {
      if (isAllowedCommand(command)) return [];
    } catch { /* fall through to the signal checks */ }
  }

  const signals = [];

  // Whole-file dumps: size the operands and flag the ones that flood context.
  if (WHOLE_FILE_DUMP_COMMANDS.has(verb)) {
    const operands = tokens.slice(1).filter(token => !token.startsWith('-'));
    signals.push(...fileDumpSignals({ operands, verb, cwd, thresholds }));
  }

  // Log streams with no --tail/-n bound.
  if (logFlags && !hasBoundingFlag(tokens, logFlags)) {
    signals.push({
      id: 'shell.log-stream',
      severity: 'warn',
      verb: LOG_STREAM_COMMANDS[twoWordVerb] ? twoWordVerb : verb,
      boundFlag: logFlags[0]
    });
  }

  // Recursive walks with no depth bound. Breadth is not volume, so a walk is
  // never blocked outright — a small repository makes this harmless.
  if (RECURSIVE_WALK_COMMANDS.has(verb) && !hasBoundingFlag(tokens, ['-maxdepth', '-L'])) {
    signals.push({ id: 'shell.recursive-walk', severity: 'warn', verb });
  }

  // Recursive content search with no narrowing flag.
  if (/^(grep|egrep|rg|ag|ack)$/.test(verb)) {
    const recursive = verb !== 'grep' && verb !== 'egrep'
      ? !hasShortFlag(tokens, 'cl')
      : hasShortFlag(tokens, 'rR');
    const narrowed = hasShortFlag(tokens, 'clm') || tokens.some(token =>
      token.startsWith('--include') || token.startsWith('--exclude') ||
      token.startsWith('-m') || token.startsWith('--max-count'));
    if (recursive && !narrowed) {
      signals.push({ id: 'shell.recursive-search', severity: 'warn', verb });
    }
  }

  // History commands that print full diffs when given no bound.
  if (verb === 'git' && ['log', 'diff', 'show'].includes(tokens[1])) {
    const bounded = tokens.some(token =>
      /^-\d+$/.test(token) || token.startsWith('--stat') || token.startsWith('--name-only') ||
      token.startsWith('--oneline') || token.startsWith('-n') || token.startsWith('--max-count'));
    if (!bounded && tokens.length <= 2) {
      signals.push({ id: 'shell.verbose-history', severity: 'warn', verb: `git ${tokens[1]}` });
    }
  }

  return signals;
}

/**
 * Signals for a shell call, evaluated per pipeline so `a && b` is judged on
 * each command rather than on the concatenated string.
 */
function shellSignals({ toolInput, cwd, thresholds, dialect }) {
  const command = toolInput?.command;
  if (typeof command !== 'string' || !command.trim()) return { signals: [], facts: {} };

  const pipelines = splitPipelines(normalizeShellCommand(command, dialect), dialect);
  const signals = [];
  for (const pipeline of pipelines) {
    signals.push(...pipelineSignals({ pipeline, cwd, thresholds, dialect }));
  }
  return { signals, facts: { command, pipelines: pipelines.length } };
}

/**
 * Compute every blast-radius signal for one tool call.
 *
 * @param {object} args
 * @param {string} args.toolName
 * @param {object} args.toolInput
 * @param {string} args.cwd
 * @param {object} args.thresholds
 * @returns {{kind: string, signals: object[], facts: object}}
 */
function computeSignals({ toolName, toolInput, cwd, thresholds }) {
  const kind = classifyOperation(toolName, toolInput);
  if (kind === 'other' || !toolInput || typeof toolInput !== 'object') {
    return { kind, signals: [], facts: {} };
  }

  if (kind === 'read') return { kind, ...readSignals({ toolInput, cwd, thresholds }) };
  if (kind === 'search') return { kind, ...searchSignals({ toolInput, thresholds }) };
  return { kind, ...shellSignals({ toolInput, cwd, thresholds, dialect: shellDialect(toolName) }) };
}

module.exports = {
  computeSignals,
  classifyOperation,
  fileBytes,
  splitPipelines,
  splitStages,
  redirectsToFile,
  isTerminallyBounded,
  WHOLE_FILE_DUMP_COMMANDS,
  LOG_STREAM_COMMANDS,
  RECURSIVE_WALK_COMMANDS
};
