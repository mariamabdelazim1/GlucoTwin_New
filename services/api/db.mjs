import pg from 'pg';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const { Pool } = pg;
const rootEnvironment = fileURLToPath(new URL('../../.env', import.meta.url));
if (existsSync(rootEnvironment) && typeof process.loadEnvFile === 'function') process.loadEnvFile(rootEnvironment);

export function databaseUrl({ test = false } = {}) {
  const value = test ? process.env.TEST_DATABASE_URL : process.env.DATABASE_URL;
  const name = test ? 'TEST_DATABASE_URL' : 'DATABASE_URL';
  if (!value) throw new Error(`${name} is required; PostgreSQL persistence has no JSON fallback`);
  if (test && !new URL(value).pathname.includes('_test')) throw new Error('TEST_DATABASE_URL must name a dedicated database containing `_test`');
  return value;
}

export function createPool({ test = false, connectionString = databaseUrl({ test }) } = {}) {
  const pool = new Pool({ connectionString, max: Number(process.env.DB_POOL_SIZE || 10) });
  pool.on('error', (error) => console.error('Unexpected PostgreSQL pool error:', error.message));
  return pool;
}

export async function withTransaction(pool, callback) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await callback(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

export async function assertDatabaseReady(pool) {
  await pool.query('SELECT 1');
  const result = await pool.query("SELECT to_regclass('users') AS users_table");
  if (!result.rows[0].users_table) {
    throw new Error('Database is reachable but migrations are missing; run npm run db:migrate');
  }
}

