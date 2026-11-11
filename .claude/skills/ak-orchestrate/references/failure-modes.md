# Failure Modes

Classify every failed or stuck attempt before acting. A fallback is a policy
decision, not a synonym for retry.

## Failure Classes

The coordinator classes below describe why an attempt failed. The plan engine
has its own, smaller vocabulary: report the mapped `error_class` in the
`accept` receipt so the engine sees the same outcome, and keep the coordinator
class in `status.json` and the report.

| Coordinator class | Examples | Receipt `error_class` |
| --- | --- | --- |
| `transient` | Short network loss, timeout with a confirmed stopped writer | `transient`, or `timeout` when the bound expired |
| `rate_limited` | Retryable provider rate limit; honour its retry delay | `rate-limit` |
| `quota_exhausted`, `budget_exhausted` | Usage window spent, run cost ceiling reached | the supervisor's class when it reported one, otherwise a non-retryable class |
| `runtime_missing`, `auth_unavailable`, `model_unavailable`, `unsupported_capability` | Missing or unauthenticated runtime, model not in the live set, session operation unsupported | non-retryable |
| `host_resource_pressure` | Low memory or disk, heavy checks already running | non-retryable |
| `process_crash`, `lost_handle`, `message_unavailable` | Worker died, session handle cannot be resolved, follow-up not delivered | non-retryable until the old writer is proven stopped |
| `verification_failure`, `merge_conflict`, `task_spec_error` | Checks fail, worktrees conflict, the job itself is wrong | non-retryable |
| `permission_denied`, `security_risk`, `external_effect_requires_approval` | Runtime refused an action, unsafe input, R3 effect without approval | non-retryable |

The engine retries automatically only for `transient`, `rate-limit` and
`timeout`, and only when the job's `retry:` policy lists that class. Check the
installed receipt type and `accept --help` for the exact field. Unknown state
stays explicit (`unknown`, `orphaned`); it never counts as success,
cancellation or a free ownership boundary.

## Fallback Ladder

Climb only as far as needed, within the run's time and cost limits. A prepared
run fixes each job's runtime, model and invocation; a failed job does not
re-route inside the same run.

1. **Reattach** to the original attempt or session when its handle, ownership
   and input/base fingerprints are proven. `advance` reconciles supervisor
   attempts; session handles need native inspection.
2. **Retry on the same route** only through the job's `retry:` policy, after
   the previous writer is settled or cancelled, for an engine-retryable class
   or a diagnosed, fixed cause. Do not rerun identical failing checks expecting
   a different result.
3. **Adapt within the current runtime**: for jobs not yet dispatched, lower
   `concurrency:` or wait for a usage window; for a failed job, prepare a new
   run directory with another live model or effort. Allowed only when user
   pins permit it, capability and risk floors still hold, and quota and budget
   admit it.
4. **Cross-runtime** only when the run is opted in (`--cross-runtime`, a spec
   `fallback_runtime` chain, or a runtime the user named), by preparing a new
   run directory that routes the job to a freshly probed candidate. Never
   carry a model identifier or flag from one runtime to another.
5. **Pause, replan or block**: queue until a quota reset, split the work into
   smaller independent jobs, or report an actionable blocker or approval
   request.

No step may raise permissions, skip checks, ignore a user pin, or leave the
authorized project roots. Stop climbing after the run's recovery budget; an
impossible task is reported, not retried indefinitely.

The only subagent route is the permission fallback in
[session-routing.md](session-routing.md#permission-fallback). `quota_exhausted`,
`runtime_missing`, `unsupported_capability`, `host_resource_pressure`,
`process_crash` and every other class never fall back to a subagent.

## Specific Cases

- **Missing or unauthenticated runtime:** evaluate opted-in fallbacks through
  the same live policy in a new run directory; otherwise block.
- **Session surface unavailable:** route to a qualified CLI of the current
  runtime, then opted-in cross-runtime candidates; otherwise block with the
  probe evidence.
- **Unknown flag or model:** fail the attempt, return to live probe, and never
  guess a replacement.
- **Permission prompt:** stop the job and report the exact approval boundary.
  A user declining a prompt is a decision, not a reason to fall back.
- **Quota or budget exhausted:** stop calling `advance` for new work, settle
  jobs already handed out, and resume after the reported reset or report the
  blocker. Unknown quota is not unlimited.
- **Timeout:** preserve bounded partial output, fail the job, and block
  dependents.
- **Interrupted run:** reload the prepared plan and call `advance`; it
  reconciles existing supervisor attempts, validates accepted inputs/artifacts,
  and blocks uncertain ownership. For raw graphs, `resume <run-id> <graph>`
  reconnects to the same digest without relaunch. Session handles require
  equivalent native inspection. Do not redispatch merely because a client died.
- **Ambiguous ownership:** sequence the jobs or assign separate worktrees and
  an explicit integration step.
- **Reference disagreement:** stop and report the contract mismatch instead of
  choosing whichever copied route looks newer.

Record each attempt's coordinator class, mapped `error_class`, the ladder step
taken and its reason in the receipt, `status.json` and the report.
