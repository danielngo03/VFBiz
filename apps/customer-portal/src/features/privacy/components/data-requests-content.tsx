import { randomUUID } from "node:crypto";
import { StatusPanel } from "@/components/feedback/status-panel";
import {
  CustomerAccountApiError,
  listCustomerDataRequests,
} from "@/platform/api/customer-account/privacy-gateway";
import { createDataRequestAction } from "../server/privacy-actions";
import { DataRequestPanel } from "./data-request-panel";

export async function DataRequestsContent() {
  const state = await listCustomerDataRequests()
    .then((requests) => ({ kind: "ready" as const, requests }))
    .catch((error: unknown) => ({
      correlationId:
        error instanceof CustomerAccountApiError
          ? error.correlationId
          : null,
      kind: "unavailable" as const,
    }));

  if (state.kind === "ready") {
    return (
      <DataRequestPanel
        createAction={createDataRequestAction}
        deleteIdempotencyKey={randomUUID()}
        exportIdempotencyKey={randomUUID()}
        requests={state.requests}
      />
    );
  }

  return (
    <StatusPanel
      title="Chưa thể tải yêu cầu dữ liệu"
      description={`Không có yêu cầu mới nào được tự tạo. Vui lòng thử lại sau.${
        state.correlationId ? ` Mã đối chiếu: ${state.correlationId}.` : ""
      }`}
      tone="warning"
    />
  );
}
