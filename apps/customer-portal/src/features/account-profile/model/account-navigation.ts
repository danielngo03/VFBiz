import { PRIVACY_ACCOUNT_SECTIONS } from "@/features/privacy/model/privacy-navigation";

export interface AccountSection {
  readonly id: "profile" | "privacy" | "sessions" | "data-requests" | "garage";
  readonly label: string;
  readonly href: string;
}

export const ACCOUNT_SECTIONS: readonly AccountSection[] = Object.freeze([
  { id: "profile", label: "Hồ sơ", href: "/account/profile" },
  { id: "sessions", label: "Bảo mật và phiên", href: "/account/security" },
  ...PRIVACY_ACCOUNT_SECTIONS,
  { id: "garage", label: "Garage của tôi", href: "/account/garage" },
]);
