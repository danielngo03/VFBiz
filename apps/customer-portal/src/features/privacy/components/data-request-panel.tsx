"use client";

import { useActionState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import {
  initialDataRequestActionState,
  type PrivacyActionState,
} from "@/features/privacy/model/privacy-action-state";
import type { DataRequest } from "@/platform/api/customer-account/privacy-contracts";
import styles from "../styles/privacy.module.css";

const STATUS_LABEL: Record<DataRequest["status"], string> = {
  completed: "Hoàn tất",
  partially_completed: "Hoàn tất một phần",
  processing: "Đang xử lý",
  rejected: "Bị từ chối",
  requested: "Đã tiếp nhận",
};

function DataRequestList({
  requests,
}: {
  readonly requests: readonly DataRequest[];
}) {
  if (requests.length === 0) {
    return (
      <p className={styles.empty} role="status">
        Bạn chưa có yêu cầu dữ liệu nào.
      </p>
    );
  }
  return (
    <ol className={styles.requestList}>
      {requests.map((request) => (
        <li className={styles.request} key={request.id}>
          <div>
            <strong>
              {request.type === "export" ? "Xuất dữ liệu" : "Xóa dữ liệu"}
            </strong>
            <p>
              Yêu cầu lúc{" "}
              {new Intl.DateTimeFormat("vi-VN", {
                dateStyle: "medium",
                timeStyle: "short",
              }).format(new Date(request.requestedAt))}
            </p>
          </div>
          <span className={styles.requestStatus}>
            {STATUS_LABEL[request.status]}
          </span>
        </li>
      ))}
    </ol>
  );
}

export function DataRequestPanel({
  createAction,
  deleteIdempotencyKey,
  exportIdempotencyKey,
  requests,
}: {
  readonly createAction: (
    previous: PrivacyActionState,
    formData: FormData,
  ) => Promise<PrivacyActionState>;
  readonly deleteIdempotencyKey: string;
  readonly exportIdempotencyKey: string;
  readonly requests: readonly DataRequest[];
}) {
  const [state, formAction, pending] = useActionState(
    createAction,
    initialDataRequestActionState,
  );
  const [deletePending, startDeleteTransition] = useTransition();

  return (
    <div className={styles.dataRequestStack}>
      <section className={styles.card} aria-labelledby="create-request-title">
        <h2 id="create-request-title">Tạo yêu cầu mới</h2>
        <p>
          Yêu cầu được xử lý bất đồng bộ. Một số dữ liệu có thể phải giữ lại
          theo nghĩa vụ pháp lý; trạng thái sẽ phản ánh kết quả thực tế.
        </p>
        <form action={formAction}>
          <input
            name="idempotencyKey"
            type="hidden"
            value={exportIdempotencyKey}
          />
          <input name="type" type="hidden" value="export" />
          <Button disabled={pending} type="submit">
            {pending ? "Đang gửi…" : "Yêu cầu xuất dữ liệu"}
          </Button>
        </form>
        <ConfirmationDialog
          actionLabel="Gửi yêu cầu xóa"
          description="Yêu cầu xóa có thể ảnh hưởng tới khả năng sử dụng dịch vụ. Dữ liệu thuộc legal hold hoặc nghĩa vụ lưu trữ có thể chưa được xóa ngay."
          onConfirm={() => {
            const formData = new FormData();
            formData.set("idempotencyKey", deleteIdempotencyKey);
            formData.set("type", "delete");
            startDeleteTransition(async () => {
              await formAction(formData);
            });
          }}
          title="Yêu cầu xóa dữ liệu?"
        >
          <Button disabled={deletePending} variant="danger">
            {deletePending ? "Đang gửi…" : "Yêu cầu xóa dữ liệu"}
          </Button>
        </ConfirmationDialog>
        <div aria-live="polite">
          {state.message ? (
            <p
              className={state.ok ? styles.success : styles.error}
              role={state.ok ? "status" : "alert"}
            >
              {state.message}
              {state.correlationId
                ? ` Mã đối chiếu: ${state.correlationId}.`
                : ""}
            </p>
          ) : null}
        </div>
      </section>
      <section className={styles.card} aria-labelledby="request-history-title">
        <h2 id="request-history-title">Lịch sử yêu cầu</h2>
        <DataRequestList requests={requests} />
      </section>
    </div>
  );
}
