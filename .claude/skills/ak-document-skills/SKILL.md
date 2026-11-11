---
name: ak-document-skills
description: "Read, create and edit Word (docx), PDF, PowerPoint (pptx) and Excel (xlsx) files: tables, forms, slide decks, spreadsheets, workbook formulas."
when_to_use: "Invoke for any Office file; it routes to the nested skill."
category: media
keywords: [docx, pdf, pptx, xlsx, office, word, powerpoint, excel]
argument-hint: "<docx|pdf|pptx|xlsx> [path] [action]"
metadata:
  author: agentkit
  version: "1.0.1"
---

# Document skills

Choose the requested output format and read its workflow:

- Word: [ak-docx](ak-docx/SKILL.md)
- PDF: [ak-pdf](ak-pdf/SKILL.md)
- PowerPoint: [ak-pptx](ak-pptx/SKILL.md)
- Spreadsheet: [ak-xlsx](ak-xlsx/SKILL.md)

Preserve supplied templates and existing content. For multiple formats, use each format's
workflow and validate each artifact; do not stop at routing. Distinguish extraction from
editing and render/inspect layout when relevant to the requested result.
