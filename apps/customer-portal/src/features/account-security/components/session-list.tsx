"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import type { SessionMutationResult } from "@/features/account-security/model/security-action-state";
import type { CustomerSession } from "@/platform/api/customer-account/security-contracts";
import styles from "../styles/security.module.css";

const RECONCILIATION_LABEL = {
  confirmed: "Nhà cung cấp đã xác nhận.",
  manual_review_required: "Cần nhân sự kiểm tra việc thu hồi tại CIAM.",
  pending: "Đang chờ CIAM xác nhận.",
  retry_required: "Hệ thống sẽ cần thử lại với CIAM.",
} as const;

function dateTime(value: string): string {
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

interface SessionActions {
  readonly logoutAllAction: () => Promise<SessionMutationResult>;
  readonly revokeAction: (sessionId: string) => Promise<SessionMutationResult>;
}

function SessionRow({
  revokeAction,
  session,
}: {
  readonly revokeAction: SessionActions["revokeAction"];
  readonly session: CustomerSession;
}) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<SessionMutationResult | null>(null);

  return (
    <li className={styles.session}>
      <div className={styles.sessionHeader}>
        <div>
          <h3>
            {session.deviceLabel ?? "Thiết bị chưa đặt tên"}
            {session.isCurrent ? (
              <span className={styles.currentBadge}>Phiên hiện tại</span>
            ) : null}
          </h3>
          <p>
            {session.userAgentSummary ?? "Trình duyệt không xác định"} ·{" "}
            {session.networkHint ?? "Mạng không xác định"}
          </p>
        </div>
        <span className={styles.status}>{session.status}</span>
      </div>
      <dl className={styles.sessionDetails}>
        <div>
          <dt>Đăng nhập</dt>
          <dd>{dateTime(session.authenticatedAt)}</dd>
        </div>
        <div>
          <dt>Gần nhất</dt>
          <dd>{dateTime(session.lastSeenAt)}</dd>
        </div>
        <div>
          <dt>MFA</dt>
          <dd>{session.mfaSatisfied ? "Có trong phiên" : "Không có"}</dd>
        </div>
      </dl>
      <p className={styles.auditNote}>
        Tên thiết bị, trình duyệt và mạng chỉ là metadata hỗ trợ nhận biết; không
        phải bằng chứng định danh hoặc yếu tố cấp quyền.
      </p>
      {result?.message ? (
        <p
          className={result.ok ? styles.success : styles.error}
          role={result.ok ? "status" : "alert"}
        >
          {result.message}
          {result.reconciliation
            ? ` ${RECONCILIATION_LABEL[result.reconciliation]}`
            : ""}
        </p>
      ) : null}
      {session.status === "active" ? (
        <ConfirmationDialog
          actionLabel={session.isCurrent ? "Đăng xuất phiên này" : "Thu hồi"}
          description={
            session.isCurrent
              ? "Bạn sẽ được đăng xuất ngay sau khi phiên hiện tại bị thu hồi."
              : "Phiên này sẽ không thể tiếp tục gọi API. Việc thu hồi tại CIAM có thể cần thời gian đối soát."
          }
          onConfirm={() => {
            startTransition(async () => {
              setResult(await revokeAction(session.id));
            });
          }}
          title={
            session.isCurrent
              ? "Đăng xuất phiên hiện tại?"
              : "Thu hồi phiên đăng nhập?"
          }
        >
          <Button disabled={pending} variant="danger">
            {pending
              ? "Đang xử lý…"
              : session.isCurrent
                ? "Đăng xuất phiên này"
                : "Thu hồi phiên"}
          </Button>
        </ConfirmationDialog>
      ) : null}
    </li>
  );
}

export function SessionList({
  logoutAllAction,
  revokeAction,
  sessions,
}: SessionActions & {
  readonly sessions: readonly CustomerSession[];
}) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<SessionMutationResult | null>(null);

  if (sessions.length === 0) {
    return (
      <p className={styles.empty} role="status">
        Không có phiên hoạt động nào để hiển thị.
      </p>
    );
  }

  return (
    <>
      <ul className={styles.sessionList}>
        {sessions.map((session) => (
          <SessionRow
            key={session.id}
            revokeAction={revokeAction}
            session={session}
          />
        ))}
      </ul>
      <section className={styles.dangerZone} aria-labelledby="logout-all-title">
        <h2 id="logout-all-title">Đăng xuất khỏi tất cả thiết bị</h2>
        <p>
          Tất cả phiên local sẽ bị từ chối ngay. Trạng thái thu hồi tại CIAM
          được hiển thị riêng và không được coi là đã hoàn tất khi còn pending.
        </p>
        {result?.message ? (
          <p
            className={result.ok ? styles.success : styles.error}
            role={result.ok ? "status" : "alert"}
          >
            {result.message}
          </p>
        ) : null}
        <ConfirmationDialog
          actionLabel="Đăng xuất tất cả"
          description="Bạn sẽ bị đăng xuất trên trình duyệt này và mọi phiên khác. Dữ liệu hồ sơ không bị xóa."
          onConfirm={() => {
            startTransition(async () => {
              setResult(await logoutAllAction());
            });
          }}
          title="Đăng xuất khỏi tất cả thiết bị?"
        >
          <Button disabled={pending} variant="danger">
            {pending ? "Đang xử lý…" : "Đăng xuất tất cả"}
          </Button>
        </ConfirmationDialog>
      </section>
    </>
  );
}
