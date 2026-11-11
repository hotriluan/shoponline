# Suite Optimization Workflow (`optimize`)

Make the test suite and its CI cheaper and faster while keeping every safety
case covered. Optimize execution, never assertions: dropping real coverage to
save minutes is failure.

## Runtime impact selection

For a repository with a trusted test-impact manifest, use `ak test optimize
--base <ref> --json` to inspect ranked groups and selected/skipped reasons.
Add `--run` to execute them, or `--output <new-file>` to keep a local result.
Planning is read-only; execution runs repository-owned argv and is not a sandbox.
Do not infer a manifest from external scores or treat missing mappings as safe.
Use the [operating procedure](../../../../../docs/operations/test-impact.md)
for setup, evidence exchange, and comparative measurements.

Native changed-path and dependency evidence establishes the conservative floor.
External evidence can add or rank checks; uncertainty broadens to the declared
full suite. Mandatory groups and active policy checks remain required; unresolved
policy mappings block execution. A narrow failure stays a failure after broader
checks. These receipts never replace repository preflight or CI admission gates.
No semantic provider is contacted by this path.

## 1. Scope and baseline

Inspect the affected areas first. Delegate only independent large areas with
disjoint ownership and sufficient machine/model budget; sequential is the default:

- **CI/CD workflows** — every pipeline file (`.github/workflows/`, etc.): job
  graph, triggers, matrices, caches, artifact flows, wall-clock and billable
  minutes per job (use `gh run list`/`gh run view` timings when available).
- **Git history** — mine the git history for which paths change together, change frequency per area,
  confirmed regressions and test maintenance. Rare failures do not prove low value.
- **Codebase** — module boundaries and the dependency edges that map source
  paths to the tests that exercise them.
- **Docs** — documented workflows whose coverage must never be dropped, plus
  pure-docs surfaces eligible for test skips.

Merge into one evidence report: cost per job, slowest tests, path→test-group
mapping, and safety-critical groups that must always run.
Include per-test duration and shared setup cost when available. Use
`test-lifecycle.md` to assess expensive tests by contract value; sampled mutation
kills are supporting evidence, not a universal value/time score.

## 2. Choose measured opportunities

1. **Change-based test selection** — run only the test groups whose mapped
   source paths changed (derive the mapping from the dependency scout; keep a
   conservative fallback: unmapped changes run the full suite).
2. **Docs-only selection** — for docs-only changes, use the repository's existing
   classifier and policy. Executable skill instructions and generated inputs may
   require tests despite being Markdown. Do not add CI skips merely because files
   look like prose.
3. **Parallel lanes** — split slow suites into balanced parallel jobs/shards;
   keep shards deterministic and isolation-safe.
4. **Cache and setup cost** — cache dependency stores and build outputs;
   hoist repeated setup into fixtures or shared jobs.
5. **Tiering** — use existing fast/full-suite schedules and mandatory backstops.
   Moving a required PR check to nightly changes policy and needs that scope.
6. **Kill duplicate work** — deduplicate overlapping jobs, cancel superseded
   runs (concurrency groups), stop re-running unchanged matrices.

## 3. Safety gates (non-negotiable)

- Safety-critical groups (from the scout report) run on every code-touching
  diff regardless of change-based test selection.
- Selection/skip logic must fail open: classifier errors → run the full suite.
- Do not weaken assertions to save time. Audit can propose suite changes;
  authorized repairs must follow `test-lifecycle.md` and prove remaining protection.
- Merge-blocking gates keep their trigger conditions; only their internal
  parallelism and selection change.

## 4. Apply and prove

- With `--interview`: list every proposed change (per workflow file, per test
  group) with expected savings and risk; interview the user per group; apply
  only approved changes. Otherwise apply directly and report the list.
- Validate affected contracts and required broad gates on the final source. If
  tests were retired, replay the same valid sampled faults on the remaining suite;
  equal coverage totals alone do not demonstrate preserved safety.
- Compare before/after under matched environment and cache conditions. Include
  planning/generation/review effort, device CPU/memory and model tokens when
  observable, not just runner time. Label estimates separately from measurements.
- Report test count, CI minutes when actually measured, sampled defect detection,
  missed known regressions, false positives and cost gaps. Reduced time with lost
  required protection is a failed optimization. Unknown metrics stay unknown.

## Optional semantic evidence

Default `ak test optimize` stays offline. An explicitly granted `test-impact`
consumer may use `--semantic shadow` (effective baseline unchanged) or `advisory`
(additions/conservative broadening only). Off, missing key or denied consent
preserves deterministic behavior; attempted failures/uncertainty broaden advisory
selection. `ak test classify-e2e` uses a separate explicit grant and never changes
the class manifest or harness. Unknown effects prevent hermetic recommendations.
Use frozen `ak test benchmark --semantic-replay` records for offline regression
and holdout comparison. Keep independent labels outside input and report
prediction coverage/abstentions alongside oracle-confirmed misses. Synthetic
contract fixtures cannot prove live model quality or justify selective skipping.
