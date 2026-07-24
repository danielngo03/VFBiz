import Link from "next/link";
import { Button } from "@/components/ui/button";
import type { CustomerIdentitySecurity } from "@/platform/api/customer-account/security-contracts";
import styles from "../styles/security.module.css";

function knownState(value: boolean | null, yes: string, no: string): string {
  if (value === null) return "Chưa xác nhận được từ CIAM";
  return value ? yes : no;
}

export function SessionSecuritySummary({
  security,
  session,
}:
  | {
      readonly security: CustomerIdentitySecurity;
      readonly session?: never;
    }
  | {
      readonly security?: never;
      readonly session: {
        readonly emailVerified: boolean;
        readonly mfaSatisfied: boolean;
      };
    }) {
  const resolved: CustomerIdentitySecurity =
    security ??
    ({
      currentSessionMfaSatisfied: session.mfaSatisfied,
      emailVerified: session.emailVerified,
      mfaConfigured: null,
      providerStatus: "unavailable",
    } satisfies CustomerIdentitySecurity);
  return (
    <section className={styles.card} aria-labelledby="security-summary-title">
      <div>
        <p className="eyebrow">Identity và phiên hiện tại</p>
        <h2 id="security-summary-title">Trạng thái bảo mật</h2>
      </div>
      <dl className={styles.definitionGrid}>
        <div>
          <dt>Email</dt>
          <dd>
            {knownState(
              resolved.emailVerified,
              "Đã xác minh",
              "Chưa xác minh",
            )}
          </dd>
        </div>
        <div>
          <dt>Cấu hình MFA</dt>
          <dd>
            {knownState(
              resolved.mfaConfigured,
              "Đã cấu hình",
              "Chưa cấu hình",
            )}
          </dd>
        </div>
        <div>
          <dt>MFA trong phiên hiện tại</dt>
          <dd>
            {resolved.currentSessionMfaSatisfied
              ? "Đã đáp ứng"
              : "Chưa đáp ứng"}
          </dd>
        </div>
      </dl>
      {resolved.providerStatus === "unavailable" ? (
        <p className={styles.warning} role="status">
          CIAM tạm thời không phản hồi. Hệ thống không suy đoán trạng thái email
          hoặc MFA; hãy thử lại trước khi thực hiện thao tác nhạy cảm.
        </p>
      ) : null}
      <div className="action-row">
        <Button asChild>
          <Link href="/api/auth/configure-mfa?returnTo=/account/security">
            Cấu hình MFA
          </Link>
        </Button>
        <Button asChild variant="secondary">
          <Link href="/account/security/sessions">Quản lý các phiên</Link>
        </Button>
      </div>
    </section>
  );
}
