import * as SQLite from "expo-sqlite";

const DATABASE_NAME = "vfbiz-customer.db";
let databasePromise: Promise<SQLite.SQLiteDatabase> | undefined;

async function database(): Promise<SQLite.SQLiteDatabase> {
  databasePromise ??= SQLite.openDatabaseAsync(DATABASE_NAME);
  const db = await databasePromise;
  await db.execAsync(`
    PRAGMA journal_mode = WAL;
    PRAGMA foreign_keys = ON;
    CREATE TABLE IF NOT EXISTS cache_records (
      namespace TEXT NOT NULL,
      record_key TEXT NOT NULL,
      payload TEXT NOT NULL,
      etag TEXT,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (namespace, record_key)
    );
    CREATE TABLE IF NOT EXISTS mutation_outbox (
      namespace TEXT NOT NULL,
      mutation_id TEXT NOT NULL,
      idempotency_key TEXT NOT NULL,
      payload TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY (namespace, mutation_id)
    );
    CREATE TABLE IF NOT EXISTS pending_payloads (
      namespace TEXT NOT NULL,
      payload_key TEXT NOT NULL,
      payload TEXT NOT NULL,
      PRIMARY KEY (namespace, payload_key)
    );
  `);
  return db;
}

export async function wipeSubjectPartition(namespace: string): Promise<void> {
  const db = await database();
  await db.withTransactionAsync(async () => {
    await db.runAsync("DELETE FROM cache_records WHERE namespace = ?", namespace);
    await db.runAsync("DELETE FROM mutation_outbox WHERE namespace = ?", namespace);
    await db.runAsync("DELETE FROM pending_payloads WHERE namespace = ?", namespace);
  });
}

export async function putCacheRecord(
  namespace: string,
  key: string,
  payload: unknown,
  etag?: string,
): Promise<void> {
  const db = await database();
  await db.runAsync(
    `INSERT INTO cache_records(namespace, record_key, payload, etag, updated_at)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(namespace, record_key) DO UPDATE SET
       payload = excluded.payload,
       etag = excluded.etag,
       updated_at = excluded.updated_at`,
    namespace,
    key,
    JSON.stringify(payload),
    etag ?? null,
    new Date().toISOString(),
  );
}
