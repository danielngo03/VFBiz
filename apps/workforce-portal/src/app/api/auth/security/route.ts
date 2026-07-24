import {cookies} from 'next/headers';
import {NextResponse} from 'next/server';
import {readWorkforcePortalEnvironment} from '@/platform/config/environment';
import type {OpaqueSessionId} from '@/platform/session/contracts';
import {readSession} from '@/platform/session/redis-token-vault';

export async function GET() {
  try {
    const environment = readWorkforcePortalEnvironment();
    const cookieStore = await cookies();
    const rawId = cookieStore.get(
      environment.WORKFORCE_SESSION_COOKIE_NAME,
    )?.value;
    if (rawId === undefined) {
      return NextResponse.json(
        {error: 'session_required'},
        {headers: {'Cache-Control': 'no-store'}, status: 401},
      );
    }
    const record = await readSession(rawId as OpaqueSessionId);
    if (record === null) {
      return NextResponse.json(
        {error: 'session_required'},
        {headers: {'Cache-Control': 'no-store'}, status: 401},
      );
    }
    return NextResponse.json(
      {
        emailVerified: record.session.emailVerified,
        // A successful MFA session proves that at least one authenticator was
        // configured. Absence of session evidence must remain unknown because
        // the BFF does not read the provider credential inventory.
        mfaConfigured: record.session.mfaSatisfied ? true : null,
        mfaSatisfied: record.session.mfaSatisfied,
      },
      {headers: {'Cache-Control': 'private, no-store'}},
    );
  } catch {
    return NextResponse.json(
      {error: 'session_service_unavailable'},
      {headers: {'Cache-Control': 'no-store'}, status: 503},
    );
  }
}
