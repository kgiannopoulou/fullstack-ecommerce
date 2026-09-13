import bcrypt from "bcryptjs";
import { Request, Response } from "express";
import { z } from "zod";
import { pool } from "../../db/pool";
import { clearAuthCookie, issueAuthCookie } from "../../middleware/auth";
import { HttpError } from "../../middleware/errorHandler";

// Shared validation for both signup and login bodies. New users are always
// created with the default 'user' role (see the 0001_init.sql schema
// default) — there is no signup field for role, so a client can't self-
// promote to admin.
const credentialsSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8).max(72), // bcrypt silently truncates beyond 72 bytes
});

export async function signup(req: Request, res: Response) {
  const { email, password } = credentialsSchema.parse(req.body);

  const { rows: existing } = await pool.query("SELECT id FROM users WHERE email = $1", [email]);
  if (existing.length > 0) {
    throw new HttpError(409, "An account with this email already exists");
  }

  // Never store the plaintext password — only the bcrypt hash. Cost factor
  // 10 is bcrypt's default trade-off between brute-force resistance and
  // login latency.
  const passwordHash = await bcrypt.hash(password, 10);
  const { rows } = await pool.query(
    `INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id, email, role`,
    [email, passwordHash]
  );
  const user = rows[0];

  // Signing up logs the user in immediately, same as login below.
  issueAuthCookie(res, user);
  res.status(201).json({ user });
}

export async function login(req: Request, res: Response) {
  const { email, password } = credentialsSchema.parse(req.body);

  const { rows } = await pool.query(
    "SELECT id, email, role, password_hash FROM users WHERE email = $1",
    [email]
  );
  const record = rows[0];
  if (!record) {
    // Deliberately the same error message as a wrong password below —
    // don't reveal whether the email exists in the system.
    throw new HttpError(401, "Invalid email or password");
  }

  const valid = await bcrypt.compare(password, record.password_hash);
  if (!valid) {
    throw new HttpError(401, "Invalid email or password");
  }

  const user = { id: record.id, email: record.email, role: record.role };
  issueAuthCookie(res, user);
  res.json({ user });
}

export async function logout(_req: Request, res: Response) {
  clearAuthCookie(res);
  res.status(204).end();
}

// Polled by the frontend's AuthProvider on every page load to figure out
// who (if anyone) is currently signed in. req.user is populated by the
// attachUserIfPresent middleware, not by this handler.
export async function me(req: Request, res: Response) {
  res.json({ user: req.user ?? null });
}
