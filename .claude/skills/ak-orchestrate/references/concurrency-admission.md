# Concurrency Admission

Load before dispatching a stage with more than one runnable job, and again
when quota, cost or host pressure changes during a run.

Size parallelism from evidence, not a fixed worker count. The result becomes
the job spec's `concurrency:` before `prepare`; the engine enforces it as the
ceiling on active jobs. Lowering it for a running plan means preparing a new
run directory, or simply calling `advance` less often.

- Read provider-reported usage windows with `ak usage limits` (check its
  `--help` for the current flags). Keep headroom below the reported limits;
  runtimes that share an upstream account share one pool. Unknown quota or
  cost is not unlimited: admit serially or ask for a policy.
- Check host headroom (CPU, memory, disk) before admitting heavy jobs, and
  count the coordinator, running sessions and their builds and tests.
  Serialize heavy checks such as full preflights, browser suites and builds;
  parallelize cheap scouts.
- Under pressure, stop calling `advance` for new work. Every internal job
  `advance` already handed out must be started, or settled through `accept`
  with a failed outcome; never leave it dangling. Never stop processes the run
  did not start.
- Record why concurrency was reduced or a job was queued, so a slow run
  explains itself.
