import 'server-only';
import {randomUUID} from 'node:crypto';
import {cache} from 'react';
import {cookies} from 'next/headers';
import {redirect} from 'next/navigation';
import {
  hasAllCapabilities,
  type WorkforceEntitlements,
} from '@/platform/api/entitlements';
import {
  WorkforceApiClient,
  WorkforceApiError,
  type WorkforceApiRequest,
} from '@/platform/api/workforce-api';
import {readWorkforcePortalEnvironment} from '@/platform/config/environment';
import type {OpaqueSessionId} from './contracts';
import {deleteSession} from './redis-token-vault';
import {ensureFreshWorkforceSession} from './workforce-session';

export interface CurrentWorkforceContext {
  readonly entitlements: WorkforceEntitlements;
  readonly mfaSatisfied: boolean;
  readonly subject: string;
}

interface CurrentWorkforceSession {
  readonly accessToken: string;
  readonly sessionId: OpaqueSessionId;
  readonly mfaSatisfied: boolean;
  readonly subject: string;
}

export type WorkforceDataState<T> =
  | {readonly status: 'ready'; readonly data: T}
  | {readonly status: 'forbidden'}
  | {
      readonly status: 'unavailable';
      readonly correlationId?: string;
    };

const requireCurrentWorkforceSession = cache(async (): Promise<
  CurrentWorkforceSession
> => {
  const environment = readWorkforcePortalEnvironment();
  const cookieStore = await cookies();
  const rawSessionId = cookieStore.get(
    environment.WORKFORCE_SESSION_COOKIE_NAME,
  )?.value;
  if (rawSessionId === undefined) redirect('/sign-in');
  const sessionId = rawSessionId as OpaqueSessionId;
  const stored = await ensureFreshWorkforceSession(sessionId);
  if (stored === null) {
    redirect('/sign-in?reason=session_expired');
  }
  if (!stored.session.mfaSatisfied) {
    await deleteSession(sessionId);
    redirect('/sign-in?reason=mfa_required');
  }
  return {
    accessToken: stored.tokenSet.accessToken,
    sessionId,
    mfaSatisfied: stored.session.mfaSatisfied,
    subject: stored.session.subject,
  };
});

export const requireCurrentWorkforceContext = cache(
  async (): Promise<CurrentWorkforceContext> => {
    const session = await requireCurrentWorkforceSession();
    try {
      const entitlements = await workforceApi().getEntitlements(
        apiRequest(session),
      );
      return {
        entitlements,
        mfaSatisfied: session.mfaSatisfied,
        subject: session.subject,
      };
    } catch (error) {
      if (error instanceof WorkforceApiError && error.status === 401) {
        await deleteSession(session.sessionId);
      }
      redirect('/sign-in?reason=authorization_unavailable');
    }
  },
);

export async function loadCurrentWorkforceData<T>(
  requiredCapabilities: readonly string[],
  loader: (
    client: WorkforceApiClient,
    request: WorkforceApiRequest,
  ) => Promise<T>,
): Promise<WorkforceDataState<T>> {
  const [context, session] = await Promise.all([
    requireCurrentWorkforceContext(),
    requireCurrentWorkforceSession(),
  ]);
  if (!hasAllCapabilities(context.entitlements, requiredCapabilities)) {
    return {status: 'forbidden'};
  }
  try {
    return {
      status: 'ready',
      data: await loader(workforceApi(), apiRequest(session)),
    };
  } catch (error) {
    if (error instanceof WorkforceApiError && error.status === 401) {
      await deleteSession(session.sessionId);
      redirect('/sign-in?reason=session_expired');
    }
    return {
      status: 'unavailable',
      correlationId:
        error instanceof WorkforceApiError ? error.correlationId : undefined,
    };
  }
}

function workforceApi(): WorkforceApiClient {
  return new WorkforceApiClient(
    new URL(readWorkforcePortalEnvironment().WORKFORCE_API_BASE_URL),
  );
}

function apiRequest(session: CurrentWorkforceSession): WorkforceApiRequest {
  return {
    accessToken: session.accessToken,
    correlationId: randomUUID(),
  };
}
