import { readdir, readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createPool, databaseUrl } from '../db.mjs';

const directory = join(dirname(fileURLToPath(import.meta.url)), '..', 'migrations');
const useTest = process.argv.includes('--test');
const through = process.argv.find((argument) => argument.startsWith('--through='))?.slice('--through='.length);
const pool = createPool({ connectionString: databaseUrl({ test: useTest }) });

try {
  await pool.query(`CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
  )`);
  const applied = new Set((await pool.query('SELECT version FROM schema_migrations')).rows.map((row) => row.version));
  let files = (await readdir(directory)).filter((name) => /^\d+.*\.sql$/.test(name)).sort();
  if (through) {
    const index = files.indexOf(through);
    if (index < 0) throw new Error(`Unknown migration requested by --through: ${through}`);
    files = files.slice(0, index + 1);
  }
  for (const file of files) {
    if (applied.has(file)) continue;
    const sql = await readFile(join(directory, file), 'utf8');
    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      await client.query(sql);
      await client.query('INSERT INTO schema_migrations(version) VALUES ($1) ON CONFLICT DO NOTHING', [file]);
      await client.query('COMMIT');
      console.log(`Applied migration ${file}`);
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  }
  console.log('Database migrations are current');
} finally {
  await pool.end();
}

