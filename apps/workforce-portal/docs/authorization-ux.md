---
id: workforce-portal-authorization-ux
title: Authorization UX của Workforce Portal
status: active
owner_role: design-lead
scope: workforce-portal
when_to_read:
  - workforce-admin
  - authorization
  - accessibility
context_anchors:
  workforce-admin: "## Nguyên tắc"
  authorization: "## Role editor"
  accessibility: "## Accessibility"
tags:
  - authorization
  - workforce
  - accessibility
revision: 1
review_date: 2026-08-24
supersedes: []
---

# Authorization UX

## Nguyên tắc

Giao diện phản ánh entitlement do NestJS trả về nhưng không cấp hoặc xác nhận
quyền. Người dùng sửa DOM, URL hoặc request trực tiếp vẫn phải bị backend từ
chối nếu thiếu capability, scope hoặc object policy.

Capability là action nguyên tử. UI có thể nhóm chúng theo domain và hành vi
Read/Create/Update/Disable/Approve để dễ hiểu, nhưng không chuyển nhóm UI thành
wildcard hoặc quyền `manage-all`.

## Trạng thái hiển thị

- Không có capability đọc: không hiển thị module trong navigation.
- Có read nhưng thiếu mutation: hiển thị dữ liệu và lý do read-only; ẩn action
  không liên quan hoặc disable khi việc giải thích giúp người dùng.
- Assignment hết hạn hoặc revision đổi: tải lại entitlement từ server trước
  mutation.
- Capability đặc quyền: hiển thị phạm vi, expiry, lý do, người đề xuất và yêu
  cầu phê duyệt độc lập.
- API trả `401`: kết thúc hoặc phục hồi session qua BFF.
- API trả `403`: không retry; hiển thị thông báo không đủ quyền và correlation
  ID an toàn.
- API trả `409`/`412`: hiển thị diff/version conflict; không tự ghi đè.

## Role editor

- Capability catalog là read-only và được nhóm theo resource.
- Trước khi lưu phải hiển thị capability thêm/bớt và số assignment bị ảnh
  hưởng.
- Không cho tạo permission string hoặc wildcard.
- Không dùng hard-delete; role được disable có reason và version.
- Cảnh báo role phạm vi rộng, capability sensitive/privileged và expiry thiếu.

Các màn hình hiện tại chỉ đọc role, assignment, approval và audit từ API. Không
hiển thị nút mutation giả hoặc dữ liệu fixture như dữ liệu live. Editor và
approval action chỉ được mở sau khi Server Action/Route Handler đáp ứng đầy đủ
session, CSRF/origin, idempotency, expected version và API authorization.

## Assignment và maker-checker

- Scope chỉ chọn từ global, market, showroom hoặc department do API cung cấp.
- Người dùng không viết condition DSL.
- Privileged assignment bắt buộc reason, expiry và approval.
- Người đề xuất không được tự phê duyệt.
- Portal phải giải thích last-admin protection và self-elevation denial; không
  cung cấp nút bypass.

## Accessibility

- Permission matrix dùng tên hàng/cột có thể đọc bởi screen reader.
- Không truyền đạt risk hoặc trạng thái chỉ bằng màu.
- Dialog giữ focus, hỗ trợ Escape và trả focus đúng vị trí.
- Mọi action dùng được bằng bàn phím; focus visible đạt tương phản WCAG AA.
- Error đặt gần field, có summary cho form dài và không xóa dữ liệu người dùng
  khi validation thất bại.
