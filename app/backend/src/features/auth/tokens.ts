import { createHash, randomBytes } from "node:crypto";
import { PoolClient } from "pg";
import { pool } from "../../db/pool";

// Single-use, expiring tokens for links sent by email. The raw token only
// ever exists in the email; the database keeps its SHA-256 hash.
export type TokenPurpose = "verify_email" | "reset_password";

export const TOKEN_TTL_MINUTES: Record<TokenPurpose, number> = {
  verify_email: 24 * 60,
  reset_password: 30,
};

export function hashToken(token: string) {
  return createHash("sha256").update(token).digest("hex");
}

// Issues a new token and invalidates any older unused token for the same
// purpose, so only the most recent email's link works.
export async function createToken(userId: number, purpose: TokenPurpose) {
  const token = randomBytes(32).toString("base64url");
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query(
      `UPDATE auth_tokens SET used_at = now() WHERE user_id = $1 AND purpose = $2 AND used_at IS NULL`,
      [userId, purpose]
    );
    await client.query(
      `INSERT INTO auth_tokens (user_id, purpose, token_hash, expires_at)
       VALUES ($1, $2, $3, now() + make_interval(mins => $4))`,
      [userId, purpose, hashToken(token), TOKEN_TTL_MINUTES[purpose]]
    );
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
  return token;
}

// Marks a token used and returns its user id, or null if the token is
// unknown, expired or already used. The UPDATE ... WHERE used_at IS NULL
// makes this atomic: two concurrent requests with the same token can't
// both succeed.
export async function consumeToken(client: PoolClient, token: string, purpose: TokenPurpose) {
  const { rows } = await client.query<{ user_id: number }>(
    `UPDATE auth_tokens SET used_at = now()
     WHERE token_hash = $1 AND purpose = $2 AND used_at IS NULL AND expires_at > now()
     RETURNING user_id`,
    [hashToken(token), purpose]
  );
  return rows[0]?.user_id ?? null;
}
