# Accessibility acceptance

Mục tiêu là hành trình chính dùng được với Dynamic Type, VoiceOver, TalkBack,
Switch/keyboard trên tablet, reduced motion và light/dark high contrast.

Mọi control có role, label, state và hit target >= 44. Icon decorative bị ẩn khỏi
accessibility tree; icon-only control có label. StatusPill có text semantic, không
dựa riêng màu. Reading order theo visual order; modal/focus phải trở về trigger.

Text cho phép scale tới 200% mà không mất action hoặc truncate thông tin quan
trọng. Layout dùng wrap/scroll thay fixed height. Motion duration về 0 khi Reduce
Motion. Error được announce và gắn với field; loading có progress label.

Test matrix tối thiểu: iOS VoiceOver + Largest Accessibility Size, Android
TalkBack + font 200%, reduced motion, dark/light contrast, portrait/tablet và
keyboard navigation cho form. Screenshot test chỉ dùng synthetic data.
