import type { components } from "@vfbiz/api-client";

export type CustomerGarageEntry = components["schemas"]["CustomerGarageEntry"];
export type ApprovedVehicleModel =
  components["schemas"]["VehicleModelProjection"];

export type VehicleVerificationState =
  "unverified" | "verification_pending" | "verified" | "rejected";

export interface GarageVehicleView {
  readonly id: string;
  readonly displayName: string;
  readonly isPrimary: boolean;
  readonly modelName: string | null;
  readonly nickname: string | null;
  readonly updatedAt: string;
  readonly variantName: string | null;
  readonly verificationState: VehicleVerificationState;
  readonly version: number;
}

const VERIFICATION_LABELS: Readonly<Record<VehicleVerificationState, string>> =
  Object.freeze({
    unverified: "Chưa xác minh",
    verification_pending: "Đang chờ xác minh",
    verified: "Đã xác minh",
    rejected: "Không thể xác minh",
  });

const VERIFICATION_DESCRIPTIONS: Readonly<
  Record<VehicleVerificationState, string>
> = Object.freeze({
  unverified:
    "Xe do bạn tự khai báo và chưa phải bằng chứng sở hữu đã được VinFast xác minh.",
  verification_pending:
    "Yêu cầu đang được nguồn dữ liệu tin cậy kiểm tra. Bạn không cần gửi lại.",
  verified: "Thông tin sở hữu đã được nguồn dữ liệu tin cậy xác minh.",
  rejected:
    "Thông tin chưa thể xác minh. Dữ liệu đã lưu không tự động trở thành bằng chứng sở hữu.",
});

export function vehicleVerificationLabel(
  state: VehicleVerificationState,
): string {
  return VERIFICATION_LABELS[state];
}

export function vehicleVerificationDescription(
  state: VehicleVerificationState,
): string {
  return VERIFICATION_DESCRIPTIONS[state];
}

function recognizedVerificationState(value: unknown): VehicleVerificationState {
  if (
    value === "unverified" ||
    value === "verification_pending" ||
    value === "verified" ||
    value === "rejected"
  ) {
    return value;
  }
  return "unverified";
}

export function buildGarageVehicleView(
  entry: CustomerGarageEntry,
  catalog: readonly ApprovedVehicleModel[],
): GarageVehicleView {
  for (const model of catalog) {
    const variant = model.variants.find(
      (candidate) => candidate.id === entry.claimedVehicleVariantId,
    );
    if (variant !== undefined) {
      return {
        id: entry.id,
        displayName: entry.nickname?.trim() || `${model.name} ${variant.name}`,
        isPrimary: entry.isPrimary,
        modelName: model.name,
        nickname: entry.nickname,
        updatedAt: entry.updatedAt,
        variantName: variant.name,
        verificationState: recognizedVerificationState(entry.ownershipStatus),
        version: entry.version,
      };
    }
  }

  return {
    id: entry.id,
    displayName: entry.nickname?.trim() || "Xe đã lưu",
    isPrimary: entry.isPrimary,
    modelName: null,
    nickname: entry.nickname,
    updatedAt: entry.updatedAt,
    variantName: null,
    verificationState: recognizedVerificationState(entry.ownershipStatus),
    version: entry.version,
  };
}
