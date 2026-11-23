---
title: "Backup schedule moved to 16:30"
date: 2026-11-23
summary: "Automatic db and full backups now default to 16:30 instead of midnight"
---

# Backup schedule moved to 16:30

## What happened
Owner moved the automatic backup time in plan 261123-0312-backup-restore-server-migration from midnight (db 23:00, full Sunday 23:15) to 16:30.

## Decision
Both kinds default to 16:30. When db and full are due together on Sunday, the runner makes db first, then full, in the same run. Backups do not stop web or robot, and the manifest stays consistent through the pg_dump snapshot. The time can still be changed on the web.

## Next steps
Implement with /ak-cook, starting at phase 1.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
