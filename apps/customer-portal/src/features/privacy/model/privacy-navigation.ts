import type { AccountSection } from "@/features/account-profile/model/account-navigation";

export const PRIVACY_ACCOUNT_SECTIONS: readonly AccountSection[] = Object.freeze(
  [
    { id: "privacy", label: "Quyền riêng tư", href: "/account/privacy" },
    {
      id: "data-requests",
      label: "Yêu cầu dữ liệu",
      href: "/account/data-requests",
    },
  ],
);
