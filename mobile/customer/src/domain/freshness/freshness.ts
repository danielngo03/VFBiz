export type FreshnessState =
  | "fresh"
  | "stale"
  | "unknown"
  | "offline"
  | "restricted"
  | "pending"
  | "verified"
  | "unverified";

export interface FreshnessDescriptor {
  label: string;
  tone: "neutral" | "positive" | "warning" | "danger";
}

export const freshnessDescriptors: Record<
  FreshnessState,
  FreshnessDescriptor
> = {
  fresh: { label: "Mới cập nhật", tone: "positive" },
  stale: { label: "Có thể đã cũ", tone: "warning" },
  unknown: { label: "Chưa xác định", tone: "neutral" },
  offline: { label: "Đang ngoại tuyến", tone: "warning" },
  restricted: { label: "Chưa được cấp quyền", tone: "danger" },
  pending: { label: "Đang xử lý", tone: "neutral" },
  verified: { label: "Đã xác minh", tone: "positive" },
  unverified: { label: "Chưa xác minh", tone: "warning" },
};
