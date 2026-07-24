"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { z } from "zod";
import type { SessionMutationResult } from "@/features/account-security/model/security-action-state";
import {
  CustomerAccountApiError,
  revokeAllCustomerSessions,
  revokeCustomerSession,
} from "@/platform/api/customer-account/security-gateway";
import { currentCustomerSession } from "@/platform/session/current-session";
import {
  deleteAllSessions,
  deleteSession,
} from "@/platform/session/redis-token-vault";

function failedSessionMutation(error: unknown): SessionMutationResult {
  if (error instanceof CustomerAccountApiError) {
    return {
      message:
        error.status === 401
          ? "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."
          : error.status === 404
            ? "Phiên này không còn tồn tại."
            : "Chưa thể thu hồi phiên. Không có trạng thái thành công nào được giả định.",
      ok: false,
    };
  }
  return {
    message:
      "Chưa thể thu hồi phiên. Không có trạng thái thành công nào được giả định.",
    ok: false,
  };
}

export async function revokeSessionAction(
  sessionId: string,
): Promise<SessionMutationResult> {
  if (!z.string().uuid().safeParse(sessionId).success) {
    return { message: "Mã phiên không hợp lệ.", ok: false };
  }
  let result: Awaited<ReturnType<typeof revokeCustomerSession>>;
  try {
    result = await revokeCustomerSession(sessionId);
    if (result.session.isCurrent) {
      const active = await currentCustomerSession();
      if (active !== null) {
        await deleteSession(
          active.record.session.id,
          active.record.session.subject,
          active.record.session.providerSessionId,
        );
        (await cookies()).delete(
          active.environment.CUSTOMER_SESSION_COOKIE_NAME,
        );
      }
    }
  } catch (error) {
    return failedSessionMutation(error);
  }
  if (result.session.isCurrent) {
    redirect(
      `/?sessionReconciliation=${encodeURIComponent(result.reconciliation)}`,
    );
  }
  try {
    revalidatePath("/account/security/sessions");
    return {
      message: "Phiên đã bị từ chối ở API Platform.",
      ok: true,
      reconciliation: result.reconciliation,
    };
  } catch (error) {
    return failedSessionMutation(error);
  }
}

export async function logoutAllSessionsAction(): Promise<SessionMutationResult> {
  let result: Awaited<ReturnType<typeof revokeAllCustomerSessions>>;
  try {
    const active = await currentCustomerSession();
    if (active === null) {
      return {
        message: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
        ok: false,
      };
    }
    result = await revokeAllCustomerSessions();
    await deleteAllSessions(active.record.session.subject);
    (await cookies()).delete(active.environment.CUSTOMER_SESSION_COOKIE_NAME);
  } catch (error) {
    return failedSessionMutation(error);
  }
  redirect(
    `/?sessionReconciliation=${encodeURIComponent(result.reconciliation)}`,
  );
}
