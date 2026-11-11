---
name: ak-docx
description: "Create, edit and analyze .docx Word files: tracked changes, comments, preserved formatting, text extraction, templates."
when_to_use: "Invoke when the file is a Word document."
category: multimedia
keywords: [docx, word, document, office]
license: Proprietary. LICENSE.txt has complete terms
argument-hint: "[path] [create|edit|extract]"
metadata:
  author: agentkit
  version: "1.0.2"
---

# Word documents

Preserve the original template, runs, formatting, comments and tracked changes. Mark only
changed text; retain unchanged run identity. Validate OOXML and inspect rendered output for
layout-sensitive changes. The full guide reads remain required by their routes until
consumer evidence establishes that shorter guidance preserves all content.

| Intent | Load |
|---|---|
| Extract/analyze | `references/extract.md` |
| Create | `references/create.md` then full `docx-js.md` |
| Edit own document | `references/edit.md` then full `ooxml.md` |
| Redline another/legal/business document | `references/redline.md` then full `ooxml.md` |
| Render or missing dependencies | `references/render-and-dependencies.md` |

Validate the packed artifact, expected content and tracked-change granularity; report any
unavailable renderer instead of claiming visual verification.
