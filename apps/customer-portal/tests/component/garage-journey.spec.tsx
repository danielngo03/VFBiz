import axe from "axe-core";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const garageActions = vi.hoisted(() => ({
  add: vi.fn(async () => ({
    code: "provider_unavailable",
    message: "Dịch vụ tạm thời không khả dụng.",
  })),
  primary: vi.fn(async () => ({
    code: "completed",
    message: "Xe chính đã được cập nhật.",
  })),
  remove: vi.fn(async () => ({
    code: "completed",
    message: "Xe đã được xóa.",
  })),
  rename: vi.fn(async () => ({
    code: "completed",
    message: "Tên đã được cập nhật.",
  })),
}));

vi.mock("@/features/garage/server/garage-actions", () => ({
  addGarageVehicleAction: garageActions.add,
  removeGarageVehicleAction: garageActions.remove,
  renameGarageVehicleAction: garageActions.rename,
  setPrimaryGarageVehicleAction: garageActions.primary,
}));

import { AddVehicleForm } from "@/features/garage/components/add-vehicle-form";
import { GarageVehicleCard } from "@/features/garage/components/garage-vehicle-card";
import { garageCreateIdempotencyKey } from "@/features/garage/model/garage-action-state";
import type { ApprovedVehicleModel } from "@/features/garage/model/garage-vehicle-view";

const catalog: readonly ApprovedVehicleModel[] = [
  {
    brandCode: "VINFAST",
    category: "suv",
    commercialStatus: "active",
    id: "11111111-1111-4111-8111-111111111111",
    market: "VN",
    modelCode: "VF_8",
    modelYear: 2026,
    name: "VF 8",
    releaseVersion: "catalog-v1",
    slug: "vf-8",
    source: {
      effectiveFrom: "2026-07-24T00:00:00.000Z",
      freshness: "fresh",
      revision: "r1",
      sourceId: "approved-catalog",
    },
    variants: [
      {
        commercialStatus: "active",
        connectorStandards: ["CCS2"],
        declaredRangeKm: 471,
        drivetrain: "AWD",
        grossBatteryCapacityKwh: 87.7,
        id: "22222222-2222-4222-8222-222222222222",
        maximumAcChargePowerKw: 11,
        maximumDcChargePowerKw: 150,
        name: "Plus",
        rangeTestStandard: "WLTP",
        seats: 5,
        usableBatteryCapacityKwh: 82,
        variantCode: "VF8_PLUS",
      },
    ],
  },
  {
    brandCode: "VINFAST",
    category: "suv",
    commercialStatus: "active",
    id: "33333333-3333-4333-8333-333333333333",
    market: "VN",
    modelCode: "VF_9",
    modelYear: 2026,
    name: "VF 9",
    releaseVersion: "catalog-v1",
    slug: "vf-9",
    source: {
      effectiveFrom: "2026-07-24T00:00:00.000Z",
      freshness: "fresh",
      revision: "r1",
      sourceId: "approved-catalog",
    },
    variants: [
      {
        commercialStatus: "active",
        connectorStandards: ["CCS2"],
        declaredRangeKm: 531,
        drivetrain: "AWD",
        grossBatteryCapacityKwh: 123,
        id: "44444444-4444-4444-8444-444444444444",
        maximumAcChargePowerKw: 11,
        maximumDcChargePowerKw: 250,
        name: "Eco",
        rangeTestStandard: "WLTP",
        seats: 7,
        usableBatteryCapacityKwh: 118,
        variantCode: "VF9_ECO",
      },
    ],
  },
];

describe("Customer Garage journey", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("selects variants only from the selected approved model and has no VIN input", async () => {
    const user = userEvent.setup();
    const requestId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const { container } = render(
      <AddVehicleForm initialRequestId={requestId} models={catalog} />,
    );

    expect(screen.getByLabelText("Phiên bản")).toHaveValue(
      "22222222-2222-4222-8222-222222222222",
    );
    await user.selectOptions(screen.getByLabelText("Mẫu xe"), catalog[1]!.id);
    expect(screen.getByLabelText("Phiên bản")).toHaveValue(
      "44444444-4444-4444-8444-444444444444",
    );
    expect(
      screen.queryByRole("textbox", { name: /vin/iu }),
    ).not.toBeInTheDocument();
    expect(container.querySelector('[name*="vin" i]')).toBeNull();
    expect(container.querySelector('[name="requestId"]')).toHaveValue(requestId);
    expect(garageCreateIdempotencyKey(requestId)).toBe(
      garageCreateIdempotencyKey(requestId),
    );

    const results = await axe.run(container);
    expect(
      results.violations.filter((violation) =>
        ["critical", "serious"].includes(violation.impact ?? ""),
      ),
    ).toEqual([]);
  });

  it("reuses the same request ID when a failed add submission is retried", async () => {
    const user = userEvent.setup();
    const requestId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    render(<AddVehicleForm initialRequestId={requestId} models={catalog} />);

    const submit = screen.getByRole("button", { name: "Thêm vào Garage" });
    await user.click(submit);
    await waitFor(() => expect(garageActions.add).toHaveBeenCalledTimes(1));
    await user.click(submit);
    await waitFor(() => expect(garageActions.add).toHaveBeenCalledTimes(2));

    const first = garageActions.add.mock.calls[0]?.[1] as FormData;
    const retry = garageActions.add.mock.calls[1]?.[1] as FormData;
    expect(first.get("requestId")).toBe(requestId);
    expect(retry.get("requestId")).toBe(requestId);
    expect(garageCreateIdempotencyKey(String(first.get("requestId")))).toBe(
      garageCreateIdempotencyKey(String(retry.get("requestId"))),
    );
  });

  it("explains unverified ownership and keeps destructive removal explicit", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <GarageVehicleCard
        vehicle={{
          displayName: "Xe gia đình",
          id: "55555555-5555-4555-8555-555555555555",
          isPrimary: false,
          modelName: "VF 8",
          nickname: "Xe gia đình",
          updatedAt: "2026-07-24T00:00:00.000Z",
          variantName: "Plus",
          verificationState: "unverified",
          version: 1,
        }}
      />,
    );

    expect(screen.getByText("Chưa xác minh")).toBeVisible();
    expect(screen.getByText(/chưa phải bằng chứng sở hữu/iu)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /xác minh/iu }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Xóa xe" }));
    expect(
      screen.getByRole("alertdialog", { name: "Xóa Xe gia đình?" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Xóa khỏi Garage" }),
    ).toBeVisible();

    const results = await axe.run(container);
    expect(
      results.violations.filter((violation) =>
        ["critical", "serious"].includes(violation.impact ?? ""),
      ),
    ).toEqual([]);
  });
});
