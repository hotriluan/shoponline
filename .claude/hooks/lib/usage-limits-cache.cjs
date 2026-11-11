#!/usr/bin/env node
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execSync } = require('child_process');

const DEFAULT_CACHE_TTL_MS = 60_000;
const DEFAULT_FETCH_TIMEOUT_MS = 5_000;
const DEFAULT_USER_AGENT = 'claudekit-engineer/1.0';
const DEFAULT_ELIGIBILITY_CACHE_TTL_MS = 60_000;

// claudeConfigDir is the Claude Code config directory a profile launcher such
// as CCS selects through CLAUDE_CONFIG_DIR, or null for the default ~/.claude.
function claudeConfigDir(envObj = process.env) {
  const dir = typeof envObj?.CLAUDE_CONFIG_DIR === 'string' ? envObj.CLAUDE_CONFIG_DIR.trim() : '';
  return dir || null;
}

function sha256Hex(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

// Each Claude config directory signs in its own account, so its quota cache
// gets its own file and profiles never read each other's quota. The default
// directory keeps the original file name. The core context builder and the
// marketing statusline derive the same path.
function getUsageCachePath(envObj = process.env) {
  if (envObj?.CK_USAGE_CACHE_PATH) return envObj.CK_USAGE_CACHE_PATH;
  const dir = claudeConfigDir(envObj);
  const name = dir
    ? `ck-usage-limits-cache-${sha256Hex(path.resolve(dir)).slice(0, 12)}.json`
    : 'ck-usage-limits-cache.json';
  return path.join(os.tmpdir(), name);
}

function getQuotaEligibilityCachePath(envObj = process.env) {
  return envObj?.CK_USAGE_ELIGIBILITY_CACHE_PATH || `${getUsageCachePath(envObj)}.eligibility`;
}

function readUsageCache(cachePath = getUsageCachePath()) {
  try {
    if (!fs.existsSync(cachePath)) return null;
    const parsed = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function getCacheAgeMs(cache, now = Date.now()) {
  if (!cache || typeof cache.timestamp !== 'number') return Number.POSITIVE_INFINITY;
  return Math.max(0, now - cache.timestamp);
}

function isUsageCacheFresh(cache, maxAgeMs, now = Date.now()) {
  return getCacheAgeMs(cache, now) <= maxAgeMs;
}

function normalizeUtilization(utilization) {
  if (typeof utilization !== 'number' || !Number.isFinite(utilization)) return null;
  if (utilization > 0 && utilization < 1) return Math.round(utilization * 100);
  return Math.max(0, Math.round(utilization));
}

function buildUsageSnapshot(data = null, now = Date.now()) {
  if (!data || typeof data !== 'object') return null;

  return {
    sourceVersion: 1,
    fetchedAt: new Date(now).toISOString(),
    fiveHourPercent: normalizeUtilization(data.five_hour?.utilization),
    weekPercent: normalizeUtilization(data.seven_day?.utilization)
  };
}

function writeUsageCache(status, data = null, { cachePath = getUsageCachePath(), now = Date.now() } = {}) {
  const tmpFile = `${cachePath}.${process.pid}.${now}.${Math.random().toString(16).slice(2)}.tmp`;
  const snapshot = status === 'available' ? buildUsageSnapshot(data, now) : null;

  try {
    fs.writeFileSync(
      tmpFile,
      JSON.stringify({
        timestamp: now,
        status,
        data,
        snapshot
      })
    );
    fs.renameSync(tmpFile, cachePath);
  } catch {
    try { fs.unlinkSync(tmpFile); } catch {}
  }
}

function readQuotaEligibilityCache(cachePath = getQuotaEligibilityCachePath()) {
  try {
    if (!fs.existsSync(cachePath)) return null;
    const parsed = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
    if (parsed && typeof parsed === 'object' && typeof parsed.eligible === 'boolean') {
      return parsed;
    }
  } catch {}
  return null;
}

function writeQuotaEligibilityCache(result, { cachePath = getQuotaEligibilityCachePath(), now = Date.now() } = {}) {
  if (!result || typeof result.eligible !== 'boolean') return;

  const tmpFile = `${cachePath}.${process.pid}.${now}.${Math.random().toString(16).slice(2)}.tmp`;
  try {
    fs.writeFileSync(
      tmpFile,
      JSON.stringify({
        timestamp: now,
        eligible: result.eligible,
        note: result.note || null
      })
    );
    fs.renameSync(tmpFile, cachePath);
  } catch {
    try { fs.unlinkSync(tmpFile); } catch {}
  }
}

function hasAnthropicRuntimeOverride(envObj = process.env) {
  return ['ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY']
    .some((key) => typeof envObj?.[key] === 'string' && envObj[key].trim() !== '');
}

// readClaudeCredentials reads the credentials of the Claude config directory
// in use: CLAUDE_CONFIG_DIR when set, otherwise ~/.claude. A profile's own
// directory never falls back to the default account's credentials. On macOS
// Claude Code keeps them in the keychain, under a service name suffixed with
// a hash of a non-default config directory.
function readClaudeCredentials({
  platform = os.platform(),
  homedir = os.homedir(),
  env: envObj = process.env,
  execSyncImpl = execSync
} = {}) {
  const configDir = claudeConfigDir(envObj);
  if (platform === 'darwin') {
    const service = configDir
      ? `Claude Code-credentials-${sha256Hex(configDir).slice(0, 8)}`
      : 'Claude Code-credentials';
    try {
      const raw = execSyncImpl(`security find-generic-password -s "${service}" -w`, {
        timeout: 5_000,
        encoding: 'utf8',
        stdio: ['pipe', 'pipe', 'ignore']
      }).trim();
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') return parsed;
    } catch {}
  }

  try {
    const dir = configDir ? path.resolve(configDir) : path.join(homedir, '.claude');
    const credentialsPath = path.join(dir, '.credentials.json');
    const parsed = JSON.parse(fs.readFileSync(credentialsPath, 'utf8'));
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function getClaudeAccessTokenFromCredentials(credentials) {
  return credentials?.claudeAiOauth?.accessToken || null;
}

function hasSupportedClaudeSubscription(credentials) {
  const subscriptionType = String(credentials?.claudeAiOauth?.subscriptionType || '').trim().toLowerCase();
  if (subscriptionType && subscriptionType !== 'free' && subscriptionType !== 'none') return true;

  const rateLimitTier = String(credentials?.claudeAiOauth?.rateLimitTier || '').trim().toLowerCase();
  return /claude|max|pro|team|enterprise/.test(rateLimitTier);
}

function resolveQuotaDisplayEligibility(options = {}) {
  if (hasAnthropicRuntimeOverride(options.env)) {
    return { eligible: false, note: 'runtime-override', accessToken: null };
  }

  const explicitAccessToken = typeof options.accessToken === 'string' && options.accessToken.trim() !== '';
  const explicitCredentials = Object.prototype.hasOwnProperty.call(options, 'credentials');

  if (options.useCache && !explicitAccessToken && !explicitCredentials) {
    const cached = readQuotaEligibilityCache(options.eligibilityCachePath);
    if (isUsageCacheFresh(cached, options.eligibilityCacheTtlMs || DEFAULT_ELIGIBILITY_CACHE_TTL_MS, options.now)) {
      return { eligible: cached.eligible, note: cached.note || 'cached', accessToken: null };
    }
  }

  const credentials = explicitCredentials ? options.credentials : readClaudeCredentials(options);

  let result;
  if (explicitAccessToken) {
    result = credentials && !hasSupportedClaudeSubscription(credentials)
      ? { eligible: false, note: 'non-subscription-auth', accessToken: null }
      : { eligible: true, note: 'eligible', accessToken: options.accessToken.trim() };
  } else {
    const accessToken = getClaudeAccessTokenFromCredentials(credentials);
    if (!accessToken) {
      result = { eligible: false, note: 'missing-credentials', accessToken: null };
    } else if (!hasSupportedClaudeSubscription(credentials)) {
      result = { eligible: false, note: 'non-subscription-auth', accessToken: null };
    } else {
      result = { eligible: true, note: 'eligible', accessToken };
    }
  }

  if (options.useCache && !explicitAccessToken && !explicitCredentials) {
    writeQuotaEligibilityCache(result, {
      cachePath: options.eligibilityCachePath,
      now: options.now
    });
  }

  return result;
}

function getClaudeAccessToken(options = {}) {
  return resolveQuotaDisplayEligibility(options).accessToken;
}

async function fetchUsageLimits(options = {}) {
  const {
  fetchImpl = fetch,
  fetchTimeoutMs = DEFAULT_FETCH_TIMEOUT_MS,
  userAgent = DEFAULT_USER_AGENT,
  accessToken
  } = options;
  const eligibility = resolveQuotaDisplayEligibility({ ...options, accessToken });
  const token = eligibility.accessToken;
  if (!eligibility.eligible || !token) {
    return {
      ok: false,
      cacheStatus: 'unavailable',
      note: eligibility.note || 'missing-credentials',
      data: null
    };
  }

  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  const timeoutId = controller
    ? setTimeout(() => controller.abort(), fetchTimeoutMs)
    : null;

  try {
    const response = await fetchImpl('https://api.anthropic.com/api/oauth/usage', {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        'anthropic-beta': 'oauth-2025-04-20',
        'User-Agent': userAgent
      },
      signal: controller?.signal
    });

    if (!response.ok) {
      return { ok: false, cacheStatus: 'unavailable', note: `http-${response.status}`, data: null };
    }

    const data = await response.json();
    if (!data || typeof data !== 'object') {
      return { ok: false, cacheStatus: 'unavailable', note: 'invalid-body', data: null };
    }

    return { ok: true, cacheStatus: 'available', note: 'fetched', data };
  } catch (error) {
    const note = error?.name === 'AbortError' ? 'timeout' : 'fetch-failed';
    return { ok: false, cacheStatus: 'unavailable', note, data: null };
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

async function refreshUsageCache(options = {}) {
  const result = await fetchUsageLimits(options);
  writeUsageCache(result.cacheStatus, result.data, options);

  return {
    ...result,
    cache: readUsageCache(options.cachePath)
  };
}

module.exports = {
  DEFAULT_CACHE_TTL_MS,
  DEFAULT_FETCH_TIMEOUT_MS,
  DEFAULT_ELIGIBILITY_CACHE_TTL_MS,
  claudeConfigDir,
  getUsageCachePath,
  getQuotaEligibilityCachePath,
  readUsageCache,
  readQuotaEligibilityCache,
  getCacheAgeMs,
  isUsageCacheFresh,
  buildUsageSnapshot,
  writeUsageCache,
  writeQuotaEligibilityCache,
  hasAnthropicRuntimeOverride,
  readClaudeCredentials,
  hasSupportedClaudeSubscription,
  resolveQuotaDisplayEligibility,
  getClaudeAccessToken,
  fetchUsageLimits,
  refreshUsageCache,
  normalizeUtilization
};
