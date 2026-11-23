---
title: "Đại tu giao diện và trải nghiệm web"
description: "Design system tĩnh mới, sidebar nhóm theo quy trình, trang Việc hôm nay, thanh bước trên trang lô và làm lại cả 24 template."
status: completed
priority: P1
effort: 4d
branch: main
tags: [frontend, ui, ux]
blockedBy: []
blocks: []
created: 2026-11-23
---

# Đại tu giao diện và trải nghiệm web

## Overview

Design system tĩnh mới, sidebar nhóm theo quy trình, trang Việc hôm nay, thanh bước trên trang lô và làm lại cả 24 template. Đây là việc chỉ đổi phần trình bày: logic nghiệp vụ, route, form và schema giữ nguyên.

Hợp đồng đã chốt: [brainstorm-261123-1516-ui-ux-overhaul.md](../reports/brainstorm-261123-1516-ui-ux-overhaul.md). Quyết định của người dùng: phạm vi gồm cả trang Việc hôm nay, sidebar trái theo nhóm, phong cách gọn và sáng, không dark mode.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Design system và khung trang](./phase-01-start.md) | Completed |
| 2 | [Trang Việc hôm nay](./phase-02-today-dashboard.md) | Completed |
| 3 | [Trang việc hằng ngày và thanh bước của lô](./phase-03-daily-workflow-pages.md) | Completed |
| 4 | [Trang kế toán và dữ liệu gốc](./phase-04-accounting-and-master-data-pages.md) | Completed |
| 5 | [Trang hệ thống và đăng nhập](./phase-05-system-pages.md) | Completed |
| 6 | [Kiểm tra trực quan và tài liệu](./phase-06-verification-and-docs.md) | Completed |

Thứ tự: phase 1 chặn mọi phase khác. Phase 2–5 chỉ phụ thuộc phase 1, và mỗi phase sở hữu riêng các template của mình. Phase 6 chạy cuối.

## Constraints

- Giữ nguyên route, method, `action` và tên trường của form, mã trạng thái, và chữ nghiệp vụ mà `tests/web/` kiểm tra.
- Giữ hợp đồng JS: `data-autosave*`, `data-server`, [table_tools.html](../../src/shoponline/web/templates/table_tools.html).
- Không thêm bước build, framework JS, CDN hay font ngoài. CSS tĩnh phục vụ qua `StaticFiles` tại `/static`.
- Giữ phân quyền admin/viewer. Trang Việc hôm nay chỉ đọc.
- Đạt WCAG AA về tương phản, có `:focus-visible`, vùng bấm ≥ 32px trên desktop và ≥ 44px dưới 768px, có `prefers-reduced-motion`.

## Non-goals

Không đổi logic nghiệp vụ, schema, migration, route hiện có hay file xuất; không dark mode; không viết lại bằng SPA/Tailwind/HTMX.

## Success Criteria

- [x] `uv run pytest` xanh, không làm yếu test nào; có test mới cho `/` (admin, viewer, số liệu) và cho `aria-current` của sidebar.
- [x] Không còn `style="` trong `src/shoponline/web/templates/`; màu chỉ khai báo dưới dạng token trong `app.css`.
- [x] Cả 24 trang render đúng ở 1366px và 390px, không cuộn ngang ở cấp trang (16 trang đo trên trình duyệt, phần còn lại qua test; xem [visual-check.md](./reports/visual-check.md)).
- [x] Sidebar có 4 nhóm đúng mục, `aria-current="page"` ở trang đang mở, có chấm cảnh báo hệ thống.
- [x] [daily-operations.md](../../docs/daily-operations.md) nêu trang Việc hôm nay và vị trí menu mới.

## Validation Log

### Session 1 — 2026-11-23
**Trigger:** `/ak-plan validate`
**Questions asked:** 4

#### Verification Results
- **Tier:** Full (6 phases)
- **Claims checked:** ~40 (paths, symbols, line anchors, counts, tests, skill scripts)
- **Verified:** 37 | **Failed:** 3 | **Unverified:** 0

#### Failures (corrected in phase files)
1. [Fact Checker] `STATUS_LABELS` in `domain/states.py` — actual symbol is `states.LABELS`, exposed to templates as `STATUS_LABELS` at app.py:31.
2. [Fact Checker] `clock.today()` — actual function is `clock.today_vn()`.
3. [Flow Tracer] Phase 4 "script làm mới 10 giây" — it is a `<meta http-equiv="refresh">` in `{% block head %}`; `base.html` must keep that block.

Minor drift, not corrected: `render()` spans app.py:153-177 (plan cites 160-177); class counts differ by 1–15 from the plan's figures; the docs sentence is bold-formatted (`trang **Sao lưu** (mục trên cùng của menu)`). Style-attribute totals check out (30 = 4 accounting_run + 22 backup + 2 login + 2 sap_connection).

#### Questions & Answers

1. **[Scope]** Phase 2 card "File Shop Online": how to show the unexported DELIVERED count?
   - Options: One COUNT on sales_order | Link only | Use collect_rows
   - **Answer:** One COUNT on sales_order
   - **Rationale:** cheap, deterministic, removes the vague "if cheap" condition.
2. **[Architecture]** Post-login landing page?
   - Options: `/` Việc hôm nay | Keep `/batches`
   - **Answer:** `/`
   - **Rationale:** matches the new page's purpose; login.py:28 and any test expecting `/batches` change.
3. **[Tradeoffs]** Platform picker on the import form?
   - Options: Radio buttons with labels | Keep `<select>`, restyle
   - **Answer:** Radio buttons (same `name`/`value`)
   - **Rationale:** all platforms visible; form contract unchanged.
4. **[Risks]** Dev DB lacks states (OPEN run, robot error) during visual check?
   - Options: Record "not checkable" in report | Seed a copy of the DB
   - **Answer:** Record "not checkable" in report
   - **Rationale:** no fake data; automated tests cover those states.

#### Confirmed Decisions
- File Shop Online card: single COUNT query.
- Login redirects to `/`.
- Platform picker: radio.
- Unreachable states in visual check: documented, not seeded.

#### Impact on Phases
- Phase 1: keep `{% block head %}` in base.html (added step 7).
- Phase 2: symbol/function names fixed, COUNT decision, login redirect decision.
- Phase 3: no change (radio already planned).
- Phase 4: refresh-mechanism risk corrected.
- Phase 6: no change (already matches).

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01 through phase-06
- Decision deltas checked: 4
- Reconciled stale references: 3
- Unresolved contradictions: 0

<!-- slug: ui-ux-overhaul -->
