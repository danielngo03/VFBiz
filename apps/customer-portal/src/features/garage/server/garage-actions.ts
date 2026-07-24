"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import {
  isApprovedVariant,
  loadApprovedVehicleCatalog,
} from "@/features/vehicle-catalog/server/approved-catalog";
import type {
  GarageActionCode,
  GarageActionState,
} from "@/features/garage/model/garage-action-state";
import { garageCreateIdempotencyKey } from "@/features/garage/model/garage-action-state";
import {
  archiveCustomerGarageEntry,
  createCustomerGarageEntry,
  updateCustomerGarageEntry,
  type GarageMutationResult,
} from "@/platform/api/garage-gateway";

const uuid = z.string().uuid();
const nickname = z
  .string()
  .trim()
  .max(80, "Tên gợi nhớ không được vượt quá 80 ký tự.");

const MESSAGES: Readonly<Record<GarageActionCode, string>> = Object.freeze({
  completed: "Thay đổi đã được lưu.",
  conflict:
    "Thông tin xe vừa được thay đổi ở nơi khác. Hãy tải lại trang trước khi thử lại.",
  forbidden: "Phiên hiện tại không có quyền thay đổi Garage.",
  invalid: "Dữ liệu gửi lên không hợp lệ. Hãy kiểm tra và thử lại.",
  invalid_variant:
    "Phiên bản xe không còn thuộc catalog được phê duyệt. Vui lòng chọn lại.",
  not_found: "Xe này không còn tồn tại trong Garage.",
  provider_unavailable:
    "Dịch vụ Garage đang tạm thời không khả dụng. Dữ liệu chưa được thay đổi.",
  session_required: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
  stale_catalog:
    "Catalog xe đang được đồng bộ. Bạn chưa thể thêm xe cho đến khi dữ liệu mới sẵn sàng.",
  unexpected: "Không thể hoàn tất thao tác. Vui lòng thử lại sau.",
});

function containsRawVinField(formData: FormData): boolean {
  return [...formData.keys()].some((key) => {
    const normalized = key.toLowerCase().replaceAll(/[^a-z0-9]/g, "");
    return (
      normalized === "vin" || normalized.includes("vehicleidentificationnumber")
    );
  });
}

function actionResult(
  result: GarageMutationResult,
  successMessage: string,
): GarageActionState {
  if (result.state === "completed") {
    revalidatePath("/account/garage");
    return { code: "completed", message: successMessage };
  }
  return {
    code: result.state,
    correlationId: result.correlationId,
    message: MESSAGES[result.state],
  };
}

export async function addGarageVehicleAction(
  _previous: GarageActionState,
  formData: FormData,
): Promise<GarageActionState> {
  if (containsRawVinField(formData)) {
    return { code: "invalid", message: MESSAGES.invalid };
  }
  const parsed = z
    .object({
      isPrimary: z.boolean(),
      nickname,
      requestId: uuid,
      variantId: uuid,
    })
    .safeParse({
      isPrimary: formData.get("isPrimary") === "on",
      nickname: String(formData.get("nickname") ?? ""),
      requestId: String(formData.get("requestId") ?? ""),
      variantId: String(formData.get("variantId") ?? ""),
    });
  if (!parsed.success) {
    return {
      code: "invalid",
      message: parsed.error.issues[0]?.message ?? MESSAGES.invalid,
    };
  }

  const catalog = await loadApprovedVehicleCatalog();
  if (catalog.state === "unavailable") {
    return {
      code: "provider_unavailable",
      message: MESSAGES.provider_unavailable,
    };
  }
  if (catalog.state === "stale") {
    return { code: "stale_catalog", message: MESSAGES.stale_catalog };
  }
  if (!isApprovedVariant(catalog.models, parsed.data.variantId)) {
    return { code: "invalid_variant", message: MESSAGES.invalid_variant };
  }

  const result = await createCustomerGarageEntry({
    idempotencyKey: garageCreateIdempotencyKey(parsed.data.requestId),
    isPrimary: parsed.data.isPrimary,
    nickname: parsed.data.nickname || null,
    variantId: parsed.data.variantId,
  });
  return actionResult(result, "Xe đã được thêm với trạng thái Chưa xác minh.");
}

export async function renameGarageVehicleAction(
  _previous: GarageActionState,
  formData: FormData,
): Promise<GarageActionState> {
  if (containsRawVinField(formData)) {
    return { code: "invalid", message: MESSAGES.invalid };
  }
  const parsed = z
    .object({
      entryId: uuid,
      nickname,
      version: z.coerce.number().int().positive(),
    })
    .safeParse({
      entryId: formData.get("entryId"),
      nickname: String(formData.get("nickname") ?? ""),
      version: formData.get("version"),
    });
  if (!parsed.success) {
    return {
      code: "invalid",
      message: parsed.error.issues[0]?.message ?? MESSAGES.invalid,
    };
  }
  return actionResult(
    await updateCustomerGarageEntry({
      entryId: parsed.data.entryId,
      nickname: parsed.data.nickname || null,
      version: parsed.data.version,
    }),
    "Tên gợi nhớ đã được cập nhật.",
  );
}

export async function setPrimaryGarageVehicleAction(
  _previous: GarageActionState,
  formData: FormData,
): Promise<GarageActionState> {
  if (containsRawVinField(formData)) {
    return { code: "invalid", message: MESSAGES.invalid };
  }
  const parsed = z
    .object({ entryId: uuid, version: z.coerce.number().int().positive() })
    .safeParse({
      entryId: formData.get("entryId"),
      version: formData.get("version"),
    });
  if (!parsed.success) {
    return { code: "invalid", message: MESSAGES.invalid };
  }
  return actionResult(
    await updateCustomerGarageEntry({
      entryId: parsed.data.entryId,
      isPrimary: true,
      version: parsed.data.version,
    }),
    "Xe chính đã được cập nhật.",
  );
}

export async function removeGarageVehicleAction(
  _previous: GarageActionState,
  formData: FormData,
): Promise<GarageActionState> {
  if (containsRawVinField(formData)) {
    return { code: "invalid", message: MESSAGES.invalid };
  }
  const parsed = z
    .object({ entryId: uuid, version: z.coerce.number().int().positive() })
    .safeParse({
      entryId: formData.get("entryId"),
      version: formData.get("version"),
    });
  if (!parsed.success) {
    return { code: "invalid", message: MESSAGES.invalid };
  }
  return actionResult(
    await archiveCustomerGarageEntry(parsed.data),
    "Xe đã được xóa khỏi Garage.",
  );
}
