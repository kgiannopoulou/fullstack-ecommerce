import { Pool } from "pg";
import { env } from "../config/env";

// Shared connection pool, imported by every module that needs the database.
// pg hands out and recycles individual client connections from this pool
// automatically for one-off pool.query() calls; code that needs a single
// connection across several statements (transactions) calls pool.connect()
// instead, e.g. in checkout/controller.ts.
export const pool = new Pool({ connectionString: env.databaseUrl });
