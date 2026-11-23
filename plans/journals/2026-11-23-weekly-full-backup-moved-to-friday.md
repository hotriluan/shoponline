---
title: Weekly full backup moved to Friday
date: 2026-11-23
summary: "Weekly full backup default changed from Sunday to Friday 16:30"
---

# Weekly full backup moved to Friday

## What happened
The owner moved the weekly full backup in plan 261123-0312-backup-restore-server-migration from Sunday to Friday.

## Decision
full_weekday is now 4 (Friday, Python weekday with Monday = 0). It runs at 16:30, right after the daily db backup. It can still be changed on the web.

## Next steps
Implement with /ak-cook, starting at phase 1.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
