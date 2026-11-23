---
title: "Backup, restore and migration plan hardened by red-team"
date: 2026-11-23
summary: "Seven-phase backup plan; red-team forced ops schema, exit code 3 and legacy restore path"
---

# Backup, restore and migration plan hardened by red-team

## What happened
Planned backup, restore and server migration as seven phases in `plans/261123-0312-backup-restore-server-migration/`, built on the existing PowerShell backup. Four red-team reviewers raised 40 findings, merged into 15, all accepted. The serious ones: restoring an older dump with `pg_restore --clean` always fails at `migrate`; a backup that loses the advisory lock exited 0, so deploy migrated with no backup; `-Bundle drive:latest` ran its steps in an impossible order; restore rolled back `app_user`, so sessions could resolve to another user.

## Decision
- A new schema `ops` holds `app_user` and the backup ledgers. A same-machine restore drops and rebuilds `public` only. Every migration that touches `ops` must be idempotent.
- Lock busy gives exit code 3. Deploy and restore exclude each other through a maintenance marker file.
- `restore-db.ps1` stays as it is. Old backups without a manifest can still be drilled and restored.
- Keep 15 `db`, 15 `app` and 4 `full` backups. Logs are not included. Pre-deploy backups stay on the server only.
- Ship phase by phase to `main`.

## Next steps
Implement phase 1 with `/ak-cook`. Check on the production machine that `schtasks /Run` works from the web process.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
