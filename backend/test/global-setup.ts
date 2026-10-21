import { Pool } from "pg";
import { TEST_DATABASE_URL } from "./env";

// Runs once before all test files: rebuilds the test database schema from
// the real migrations, so the tests exercise exactly what production runs.
export default async function setup() {
  const { runMigrations } = await import("../src/db/migrate");
  const db = new Pool({ connectionString: TEST_DATABASE_URL });
  try {
    await db.query("DROP SCHEMA public CASCADE; CREATE SCHEMA public;");
    await runMigrations(db, () => undefined);
  } finally {
    await db.end();
  }
  // The migrate module's own pool connected to the same database.
  const { pool } = await import("../src/db/pool");
  await pool.end();
}
