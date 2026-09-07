import bcrypt from "bcryptjs";
import { Request, Response } from "express";
import { z } from "zod";
import { pool } from "../../db/pool";
import { clearAuthCookie, issueAuthCookie } from "../../middleware/auth";
import { HttpError } from "../../middleware/errorHandler";

const credentialsSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8).max(72),
});

export async function signup(req: Request, res: Response) {
  const { email, password } = credentialsSchema.parse(req.body);

  const { rows: existing } = await pool.query("SELECT id FROM users WHERE email = $1", [email]);
  if (existing.length > 0) {
    throw new HttpError(409, "An account with this email already exists");
  }

  const passwordHash = await bcrypt.hash(password, 10);
  const { rows } = await pool.query(
    `INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id, email, role`,
    [email, passwordHash]
  );
  const user = rows[0];

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

export async function me(req: Request, res: Response) {
  res.json({ user: req.user ?? null });
}
