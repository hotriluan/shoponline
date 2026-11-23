---
title: "Backup, restore and server migration implemented on dev"
date: 2026-11-23
summary: "All seven phases are coded, tested and documented on the dev machine; nothing is pushed or run on the production machine yet"
---

# Backup, restore and server migration implemented on dev

## What happened
Phases 1 to 7 of plan 261123-0312-backup-restore-server-migration were built in one session as seven local commits on `main`, not pushed. 610 tests pass (460 before). The live drill on the production machine (phase 7) is the only part not done; see plans/reports/live-check-261123-1210-backup-restore.md.

## Decisions and surprises
- Row counts are compared right after the business schema is restored and before `migrate`, not after it. They check that the restore was faithful, and a migration may legitimately add rows.
- Revision checks use the migrations of the running code, not the backed-up repo, and the set of known revisions is cached; tests must patch `restore.known_revisions`, not the private finder, or the cache keeps the patched value for the whole run.
- The test harness wraps every web request in a savepoint that is rolled back, which undoes anything another session of the same request commits. Production uses separate connections, so only the tests needed workarounds (the Drive client in web tests uses real connections; delete and upload routes commit explicitly, as the app's convention says).
- The Drive list is cached for five minutes in the web process; tests that upload to the fake Drive must invalidate the cache.
- The review of the 23 criteria found one gap, criterion 14: after the Drive is disconnected the banner stayed silent. It now warns when the latest scheduled backup wanted Drive and found it not connected.
- The role `shoponline_app` cannot create databases, so there is no scratch database for restore drills on dev; the drill test restores into the test database itself while settings name another one as the running database.
- The dev machine has every `shoponline-*` scheduled task Disabled, so no script that stops or starts services was run for real.
- A `git stash` was run by mistake mid-session and popped at once; nothing was lost.

## Next steps
Push when ready (deploy runs on the production machine). Then follow the six-step list in the live-check report: deploy, OAuth client and Drive connection, scratch database and drills, a real restore outside working hours, `server-export.ps1 -Prepare` with a test machine, and the 16:30 schedule after 24 hours.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
