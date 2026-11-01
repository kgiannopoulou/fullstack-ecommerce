// A minimal hand-rolled migration runner (no framework, matches the
// "raw pg, no ORM" choice for this project). Each .sql file under
// ./migrations is applied at most once, in filename order (hence the
// 0001_, 0002_, ... prefixes), and recorded in schema_migrations so
// re-running `npm run migrate` is a safe no-op for anything already applied.
import fs from "node:fs";
import path from "node:path";
import { Pool } from "pg";
import { pool } from "./pool";

const MIGRATIONS_DIR = path.join(__dirname, "migrations");

export async function runMigrations(db: Pool, log: (line: string) => void = console.log) {
  // The tracking table itself is created on first run, so a brand-new
  // database needs no manual setup before `npm run migrate`.
  await db.query(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      name TEXT PRIMARY KEY,
      applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
  `);

  const { rows: applied } = await db.query<{ name: string }>(
    "SELECT name FROM schema_migrations"
  );
  const appliedNames = new Set(applied.map((row) => row.name));

  const files = fs
    .readdirSync(MIGRATIONS_DIR)
    .filter((file) => file.endsWith(".sql"))
    .sort();

  for (const file of files) {
    if (appliedNames.has(file)) {
      log(`skip  ${file} (already applied)`);
      continue;
    }

    // Each migration file runs in its own transaction: either the whole
    // file's SQL applies and gets recorded, or none of it does.
    const sql = fs.readFileSync(path.join(MIGRATIONS_DIR, file), "utf8");
    const client = await db.connect();
    try {
      await client.query("BEGIN");
      await client.query(sql);
      await client.query("INSERT INTO schema_migrations (name) VALUES ($1)", [file]);
      await client.query("COMMIT");
      log(`apply ${file}`);
    } catch (err) {
      await client.query("ROLLBACK");
      throw err;
    } finally {
      client.release();
    }
  }

  log("Migrations complete.");
}

// `npm run migrate` runs this file directly; the tests import runMigrations.
if (require.main === module) {
  runMigrations(pool)
    .then(() => pool.end())
    .catch((err) => {
      console.error(err);
      process.exit(1);
    });
}
