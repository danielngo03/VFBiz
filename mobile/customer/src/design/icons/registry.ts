export type CustomerIconName =
  | "home"
  | "garage"
  | "account"
  | "security"
  | "privacy"
  | "assistant";

// Brand icon artwork is intentionally absent until an approved asset pack exists.
export const customerIconLabels: Record<CustomerIconName, string> = {
  home: "Trang chủ",
  garage: "Garage",
  account: "Tài khoản",
  security: "Bảo mật",
  privacy: "Quyền riêng tư",
  assistant: "Trợ lý",
};
