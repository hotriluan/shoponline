# Bounded consumer regression

`evals.json` contains one composite case with five train/regression assertions and
one inert E2E receipt case per variant. They are synthetic examples, not independent holdout or
production cost evidence. `fixtures/WORK.md` is the consumer brief; consumers
must not see `evals.json` or another variant.

Copy `fixtures/` into separate clean workspaces. Assign each fresh consumer the
same brief and tools plus one frozen skill snapshot. Allow test edits and
report artifacts only; preserve `model.py`. Save actual commands and outputs.
Do not install dependencies or run remote/browser services.

Replay a completed consumer with Python standard library:

```sh
python verify-consumer.py /path/to/workspace --output /path/to/replay.json
```

The replay independently checks source preservation and executes the resulting
suite against current code, two authorization mutants, a corrected JSON path,
and the old quota contract. Review individual failures, not just aggregate exit
codes: the intentional JSON regression should fail current code while passing
the corrected implementation; auth mutants should add their own assertion
failures. The old quota mutant demonstrates accepted-spec sensitivity, not a
current quota defect. Temporary mutation copies are cleaned automatically.

Use the installed skill-creator `eval_skill.py` to validate/grade these cases.
Rubric verdicts require reading reports and execution artifacts; missing output
or a setup error never establishes behavioral detection. Preserve raw records
before adding reviewer verdicts. One composite run is one observation, even
though its five groups are graded separately.

The fixture contains an intentional product defect; do not add its consumer suite
to generic repository test discovery. The verifier exits nonzero for failed
mechanical checks and records a 10-second child timeout as inconclusive.

For an archived input whose line endings differ from the current LF fixture,
supply `--expected-source-sha256` from its original input manifest. This preserves
byte-exact checking without rewriting old consumer evidence.
