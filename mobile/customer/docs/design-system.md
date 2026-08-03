# Design system Customer Mobile

Customer dùng semantic visual language premium, adaptive và native-feeling:
spacious layout, ít chrome, hierarchy rõ, icon-led nhưng không dựa riêng vào icon
hoặc màu. Light/dark cùng semantic role; không hard-code brand palette trong
feature screen.

Canonical primitive/semantic token nằm ở `packages/design-tokens`. Generator tạo
`native.ts`/`native.json`, chuyển `rem` sang React Native numeric unit tại build
time. App không parse CSS hay `rem` runtime. Brand token vẫn neutral cho tới khi
Brand/Legal duyệt asset/color pack.

Foundation components: Screen, Surface, Text, Button, IconButton, AppIcon,
Avatar, ListRow, ToggleRow, StatusPill, SectionHeader, QuickAction,
VehicleSilhouette, EmptyState, ProblemState và LoadingState. Component phải có
semantic prop nhỏ, không nhận arbitrary web class. Feature composition ở feature
layer; primitive không biết profile/garage/session.

Owner cockpit dùng ba tầng hierarchy: identity/context header, vehicle hero có
authority label, sau đó quick actions và trust/control content. Garage card luôn
phân biệt `self-reported` với verified ownership. Account nhóm identity,
security/session và privacy/consent thành các vùng riêng. Không dùng hero để giả
battery, lock, charging, location hoặc trạng thái xe live.

Material Symbols được bundle cục bộ qua Expo Font; không tải font runtime. Icon
trang trí bị ẩn khỏi accessibility tree, icon action luôn có text/label. Vehicle
silhouette hiện là neutral code-drawn placeholder, không phải VinFast artwork;
chỉ thay bằng asset có provenance sau Brand/Legal approval.

Touch target tối thiểu 44, body line-height 24, focus/error/loading/empty/offline
state bắt buộc. Motion dùng quick/standard/deliberate token và trở về 0 khi Reduce
Motion bật. Remote font, remote image và asset scrape bị cấm.
