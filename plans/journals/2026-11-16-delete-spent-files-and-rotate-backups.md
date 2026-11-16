---
title: Delete spent files and rotate backups
date: 2026-11-16
summary: Stored files are deleted when spent under one keep-rule set; nightly sweep always runs; backups keep one per day for 14 days
---

# Delete spent files and rotate backups

## What happened

Implemented plan `plans/261116-1520-delete-spent-files` (phases 01-05). Files under `SHOPONLINE_DATA_DIR` used to sit for 90 days, and the nightly `shoponline retention` task ran in list mode, so nothing was ever deleted. Backups piled up (17 in 4 days) because every deploy takes one and old ones went only after 30 days.

## Key changes

- `maintenance/retention.py`: one keep-rule set (`kept_files`) for uploads and exports, `discard_unused` for immediate deletion after a commit, and `sweep_files` for the nightly sweep (1-hour grace, robot-work by job status, evidence via `evidence.prune`). It only ever deletes inside `uploads/` and `exports/`.
- Immediate deletion points: platform, SKU-mapping and zrsd001 imports; rejected uploads (only when this request wrote the file, via `store_file` returning `(record, created)`); robot `_finish` on DONE (work folder plus a spent stored report); accounting finalize and cancel; Shop Online confirm; order file after the response (`BackgroundTask`).
- `runs.waiting_uploads` was split out of `available_uploads` so retention reuses the same query.
- CLI: `retention` always sweeps files, and `--apply` now covers customer data only. It logs through `RotatingFileHandler`.
- `scripts/windows/backup-rotation.ps1`: keeps every backup of today plus the newest of each of 14 earlier days, dating by file name.

## Problems hit

- `dict(session.execute(...))` treats a Result as a mapping (it has `.keys()`). Use `.all()` first.
- `ruff format tests/web` reformatted an unrelated file. I reverted it.

## Verification

379 tests pass and ruff is clean. The rotation was tested on a fake 21-day folder. The `-WhatIf` run on `C:\shoponline-backup` matched the plan. No real backups were deleted by hand.

## Next steps

- Deploy. The first sweep removes the existing backlog. Next morning, read `retention.log` and check `C:\shoponline-backup`.
- Check whether the production `.env` pins `SHOPONLINE_BACKUP_KEEP_DAYS=30`.
- Open question: does `SHOPONLINE_BACKUP_DIRS` include an off-machine location?

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
