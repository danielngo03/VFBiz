import { createHash } from 'node:crypto';

export function conversationSubjectKeyHash(
  issuer: string,
  subject: string,
): string {
  const framed = `${Buffer.byteLength(issuer, 'utf8')}:${issuer}${Buffer.byteLength(subject, 'utf8')}:${subject}`;
  return createHash('sha256').update(framed, 'utf8').digest('hex');
}
