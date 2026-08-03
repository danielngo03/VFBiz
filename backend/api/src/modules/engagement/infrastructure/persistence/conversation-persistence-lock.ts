import { createHash } from 'node:crypto';
import { Prisma } from '../../../../generated/prisma/client';
export { conversationSubjectKeyHash } from '../../domain/conversation-subject-key';

export type ConversationPersistenceTransaction = Prisma.TransactionClient;

export async function lockConversationSession(
  transaction: ConversationPersistenceTransaction,
  sessionId: string,
): Promise<void> {
  await advisoryLock(transaction, `conversation-session:${sessionId}`);
}

export async function lockConversationSubject(
  transaction: ConversationPersistenceTransaction,
  subjectKeyHash: string,
): Promise<void> {
  await advisoryLock(transaction, `conversation-subject:${subjectKeyHash}`);
}

async function advisoryLock(
  transaction: ConversationPersistenceTransaction,
  value: string,
): Promise<void> {
  const digest = createHash('sha256').update(value, 'utf8').digest();
  const key = digest.readBigInt64BE(0);
  await transaction.$queryRaw(
    Prisma.sql`SELECT pg_advisory_xact_lock(${key}) IS NULL AS "acquired"`,
  );
}
