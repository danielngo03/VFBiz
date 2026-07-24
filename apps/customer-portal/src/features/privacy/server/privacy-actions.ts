"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import {
  type PrivacyActionState,
} from "@/features/privacy/model/privacy-action-state";
import {
  createCustomerDataRequest,
  CustomerAccountApiError,
  listCustomerConsents,
  updateCustomerConsents,
} from "@/platform/api/customer-account/privacy-gateway";

const idempotencyKeySchema = z
  .string()
  .min(16)
  .max(128)
  .regex(/^[A-Za-z0-9._~:+\-/]+$/u);

function privacyFailure(
  error: unknown,
  fallback: string,
): PrivacyActionState {
  if (error instanceof CustomerAccountApiError) {
    return {
      correlationId: error.correlationId ?? undefined,
      message:
        error.status === 401
          ? "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."
          : error.code === "CONSENT_POLICY_UNAVAILABLE"
            ? "Policy đã thay đổi. Tải lại trang trước khi lưu lựa chọn mới."
            : error.code === "IDEMPOTENCY_KEY_REUSED"
              ? "Yêu cầu đã được dùng cho một nội dung khác. Vui lòng tải lại trang."
              : fallback,
      ok: false,
    };
  }
  return { message: fallback, ok: false };
}

export async function updateConsentsAction(
  _previous: PrivacyActionState,
  formData: FormData,
): Promise<PrivacyActionState> {
  const key = idempotencyKeySchema.safeParse(formData.get("idempotencyKey"));
  if (!key.success) {
    return {
      message: "Phiên biểu mẫu không hợp lệ. Vui lòng tải lại trang.",
      ok: false,
    };
  }
  try {
    const current = await listCustomerConsents();
    if (current.length === 0) {
      return {
        message: "Không có consent purpose đang hoạt động để cập nhật.",
        ok: false,
      };
    }
    await updateCustomerConsents(
      current.map((consent) => ({
        policyVersion: consent.policyVersion,
        purpose: consent.purpose,
        state:
          formData.get(`consent:${consent.purpose}`) === "on"
            ? "granted"
            : "withdrawn",
      })),
      key.data,
    );
    revalidatePath("/account/privacy");
    return { message: "Lựa chọn quyền riêng tư đã được ghi nhận.", ok: true };
  } catch (error) {
    return privacyFailure(
      error,
      "Chưa thể cập nhật consent. Không có thay đổi nào được giả định.",
    );
  }
}

export async function createDataRequestAction(
  _previous: PrivacyActionState,
  formData: FormData,
): Promise<PrivacyActionState> {
  const parsed = z
    .object({
      idempotencyKey: idempotencyKeySchema,
      type: z.enum(["export", "delete"]),
    })
    .safeParse({
      idempotencyKey: formData.get("idempotencyKey"),
      type: formData.get("type"),
    });
  if (!parsed.success) {
    return {
      message: "Yêu cầu không hợp lệ. Vui lòng tải lại trang.",
      ok: false,
    };
  }
  try {
    await createCustomerDataRequest(
      { type: parsed.data.type },
      parsed.data.idempotencyKey,
    );
    revalidatePath("/account/data-requests");
    return {
      message:
        parsed.data.type === "export"
          ? "Yêu cầu xuất dữ liệu đã được tiếp nhận."
          : "Yêu cầu xóa dữ liệu đã được tiếp nhận.",
      ok: true,
    };
  } catch (error) {
    return privacyFailure(
      error,
      "Chưa thể tạo yêu cầu dữ liệu. Không có trạng thái thành công nào được giả định.",
    );
  }
}
