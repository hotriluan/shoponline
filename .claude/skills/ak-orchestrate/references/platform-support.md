# Platform Support

Load before refusing a request on a non-Darwin host, or when `advance` or
`accept` reports error class `unsupported_platform`.

Orchestrate is not macOS-only. Only external process supervision is
Darwin-gated; check the host before refusing a request.

| Capability | Darwin | Linux, Windows, other |
| --- | --- | --- |
| `probe`, `prepare`, `advance`, `accept`, `plan-status` | Yes | Yes |
| `events`, `output`, `diagnose` | Yes | Yes, but only for runs recorded on a supervising host |
| `runtime: internal` jobs (current-runtime sessions) | Yes, when the live runtime qualifies | Yes, when the live runtime qualifies |
| CLI and Pi jobs supervised by `ak orchestrate` | Yes | No: `advance` settles the job `blocked` with error class `unsupported_platform` and exits 1 |
| Executable `verification:` checks in a job spec | Yes | No: `accept` settles the job `blocked` with error class `unsupported_platform` and exits 1 |
| `start`, `status`, `resume`, `stop` (supervisor runs) | Yes | No: unsupported-platform exit code in each command's `--help` |

On a non-Darwin host, route qualified jobs through `runtime: internal` and
keep jobs that need a supervised CLI or Pi process out of the prepared spec;
report them `blocked` with the platform reason. `advance` still lists
`internal[]` jobs in its `--json` payload when it blocks a CLI job; dispatch
them. A blocked job cannot be repaired in place, even on another host: report
it and prepare a new run directory that routes it internally without
executable `verification:`, or prepare it on a Darwin host. Never bypass the
supervision gate or launch an unsupervised process in its place. In a spec you
author, list check commands under `checks:`, run them in the harness and record
them as harness-attested per
[job-spec.md](job-spec.md). A `verification:` declared by the user
or a supplied spec is an acceptance constraint: block that job, never convert
it. When no session route qualifies either, block the run and say why.
