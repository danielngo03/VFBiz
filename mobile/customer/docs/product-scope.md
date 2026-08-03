# Phạm vi sản phẩm Customer Mobile

## Người dùng và lời hứa

App phục vụ customer đã có tài khoản VFBiz và muốn quản lý owner relationship
nhanh, rõ và có thể tin cậy trên điện thoại. App mở vào owner shell sau khi khôi
phục phiên, không có marketing landing page trong authenticated experience.

## Phase 1

- Home: account/freshness summary, primary self-reported garage entry và quick
  actions có authority thật.
- Garage: danh sách xe tự khai báo, unverified ownership label, thêm/sửa/archive
  bằng idempotency + optimistic concurrency khi catalog khả dụng.
- Account: profile, identity security, sessions, privacy request, consents và
  local logout wipe.
- Support/Assistant chỉ là guarded entrypoint; không hứa SLA hay AI capability
  chưa được API authority trả về.

## Không thuộc phase 1

Battery, lock/unlock, climate, charging, live location, trip, notification,
camera/document, Bluetooth/vehicle control, commerce và service booking đều
đóng. UI không suy diễn trạng thái xe từ self-reported garage data.

## Ownership và quyền quyết định

`mobile-experience`/Engineering Lead sở hữu implementation và engineering
evidence. Product Owner/Product Manager chấp thuận journey, copy và outcome
measure. API/domain teams giữ server capability authority; Customer app không
tự mở một hành vi chỉ vì có thể dựng UI.

Material product ambiguity được ghi vào VFBIZ-0203 với decision owner và exact
next action, không được “đồng thuận” qua agent chat. Design Lead duyệt experience/
accessibility; Legal/Brand chỉ tham gia khi copy/asset/claim cần quyền tương ứng.

## Chỉ số acceptance

Auth callback/logout wipe thành công trên iOS/Android development build; route
không lộ khi anonymous; cache không giao thoa subject/environment; mọi trạng thái
fresh/stale/unknown/offline/restricted có copy; Dynamic Type và screen reader
không chặn hành trình chính. Product outcome metric chỉ được đặt khi có staging
telemetry và baseline, không bịa target trong foundation.
