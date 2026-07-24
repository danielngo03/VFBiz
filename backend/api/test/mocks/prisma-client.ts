/**
 * Jest-only Prisma client seam. Database behavior is covered by the disposable
 * PostGIS migration suite; application tests override repositories explicitly.
 */
export class PrismaClient {
  async $connect(): Promise<void> {}

  async $disconnect(): Promise<void> {}
}
