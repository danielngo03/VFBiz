"use server";

import { revalidatePath } from "next/cache";
import type { ProfileActionState } from "@/features/account-profile/model/profile-action-state";
import { profileFormSchema } from "@/features/account-profile/model/profile-form";
import {
  CustomerAccountApiError,
  updateCustomerProfile,
} from "@/platform/api/customer-account/profile-gateway";

function checked(formData: FormData, name: string): boolean {
  return formData.get(name) === "on";
}

export async function updateProfileAction(
  _previous: ProfileActionState,
  formData: FormData,
): Promise<ProfileActionState> {
  const parsed = profileFormSchema.safeParse({
    displayName: formData.get("displayName"),
    email: checked(formData, "email"),
    expectedEtag: formData.get("expectedEtag"),
    locale: formData.get("locale"),
    push: checked(formData, "push"),
    sms: checked(formData, "sms"),
    timezone: formData.get("timezone"),
  });
  if (!parsed.success) {
    return {
      fieldErrors: parsed.error.flatten().fieldErrors,
      message: "Vui lòng kiểm tra lại thông tin đã nhập.",
      status: "invalid",
    };
  }

  try {
    await updateCustomerProfile(
      {
        communicationPreferences: {
          email: parsed.data.email,
          push: parsed.data.push,
          sms: parsed.data.sms,
        },
        displayName: parsed.data.displayName || null,
        locale: parsed.data.locale,
        timezone: parsed.data.timezone,
      },
      parsed.data.expectedEtag,
    );
    revalidatePath("/account/profile");
    return {
      message: "Hồ sơ đã được cập nhật.",
      status: "success",
    };
  } catch (error) {
    if (error instanceof CustomerAccountApiError) {
      if (
        error.status === 409 &&
        error.code === "PROFILE_VERSION_CONFLICT"
      ) {
        return {
          correlationId: error.correlationId ?? undefined,
          message:
            "Hồ sơ đã thay đổi ở một phiên khác. Tải lại trước khi lưu tiếp.",
          status: "conflict",
        };
      }
      return {
        correlationId: error.correlationId ?? undefined,
        message:
          error.status === 401
            ? "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."
            : error.status === 403
              ? "Bạn không có quyền cập nhật hồ sơ."
              : "Chưa thể cập nhật hồ sơ. Vui lòng thử lại sau.",
        status: "error",
      };
    }
    return {
      message: "Chưa thể cập nhật hồ sơ. Vui lòng thử lại sau.",
      status: "error",
    };
  }
}
