import bcrypt from "bcryptjs";
import { Request, Response } from "express";
import { z } from "zod";
import { env } from "../../config/env";
import { pool } from "../../db/pool";
import { sendMail } from "../../lib/mailer";
import { clearAuthCookie, issueAuthCookie } from "../../middleware/auth";
import { HttpError } from "../../middleware/errorHandler";
import { consumeToken, createToken } from "./tokens";

// bcrypt silently truncates beyond 72 bytes, hence the max.
const passwordSchema = z.string().min(8).max(72);

// Shared validation for both signup and login bodies. New users are always
// created with the default 'user' role (see the 0001_init.sql schema
// default) — there is no signup field for role, so a client can't self-
// promote to admin.
const credentialsSchema = z.object({
  email: z.string().trim().toLowerCase().email(),
  password: passwordSchema,
});

const emailSchema = z.object({ email: z.string().trim().toLowerCase().email() });
const tokenSchema = z.object({ token: z.string().min(1).max(200) });
const resetSchema = z.object({ token: z.string().min(1).max(200), password: passwordSchema });

// Cost factor 10 is bcrypt's default trade-off between brute-force
// resistance and login latency.
const BCRYPT_COST = 10;

async function sendVerificationEmail(userId: number, email: string) {
  const token = await createToken(userId, "verify_email");
  await sendMail({
    to: email,
    subject: "Confirm your email address",
    text: `Confirm your email address to start placing orders:\n\n${env.clientUrl}/verify-email?token=${token}\n\nThe link is valid for 24 hours.`,
  });
}

export async function signup(req: Request, res: Response) {
  const { email, password } = credentialsSchema.parse(req.body);

  const { rows: existing } = await pool.query("SELECT id FROM users WHERE lower(email) = $1", [email]);
  if (existing.length > 0) {
    throw new HttpError(409, "An account with this email already exists", "EMAIL_TAKEN");
  }

  // Never store the plaintext password — only the bcrypt hash.
  const passwordHash = await bcrypt.hash(password, BCRYPT_COST);
  const { rows } = await pool.query(
    `INSERT INTO users (email, password_hash) VALUES ($1, $2)
     RETURNING id, email, role, session_version`,
    [email, passwordHash]
  );
  const user = rows[0];

  await sendVerificationEmail(user.id, user.email);

  // Signing up logs the user in immediately, same as login below. They can
  // browse and fill a cart; checkout waits for the email to be verified.
  issueAuthCookie(res, user.id, user.session_version);
  res.status(201).json({ user: { id: user.id, email: user.email, role: user.role, emailVerified: false } });
}

export async function login(req: Request, res: Response) {
  const { email, password } = credentialsSchema.parse(req.body);

  const { rows } = await pool.query(
    `SELECT id, email, role, password_hash, email_verified_at, session_version
     FROM users WHERE lower(email) = $1`,
    [email]
  );
  const record = rows[0];
  if (!record) {
    // Deliberately the same error message as a wrong password below —
    // don't reveal whether the email exists in the system.
    throw new HttpError(401, "Invalid email or password", "INVALID_CREDENTIALS");
  }

  const valid = await bcrypt.compare(password, record.password_hash);
  if (!valid) {
    throw new HttpError(401, "Invalid email or password", "INVALID_CREDENTIALS");
  }

  issueAuthCookie(res, record.id, record.session_version);
  res.json({
    user: {
      id: record.id,
      email: record.email,
      role: record.role,
      emailVerified: record.email_verified_at !== null,
    },
  });
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

// --- Email verification ---------------------------------------------------

// "Resend the verification email" for the signed-in user.
export async function requestEmailVerification(req: Request, res: Response) {
  const user = req.user!;
  if (!user.emailVerified) {
    await sendVerificationEmail(user.id, user.email);
  }
  res.status(202).json({ sent: !user.emailVerified });
}

export async function verifyEmail(req: Request, res: Response) {
  const { token } = tokenSchema.parse(req.body);
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const userId = await consumeToken(client, token, "verify_email");
    if (!userId) {
      throw new HttpError(400, "This verification link is invalid or has expired", "INVALID_TOKEN");
    }
    await client.query(
      `UPDATE users SET email_verified_at = COALESCE(email_verified_at, now()) WHERE id = $1`,
      [userId]
    );
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
  res.json({ verified: true });
}

// --- Password reset -------------------------------------------------------

// Always answers 202 with the same body whether or not the email exists, so
// this endpoint can't be used to find out who has an account.
export async function forgotPassword(req: Request, res: Response) {
  const { email } = emailSchema.parse(req.body);
  const { rows } = await pool.query(`SELECT id, email FROM users WHERE lower(email) = $1`, [email]);
  const user = rows[0];
  if (user) {
    const token = await createToken(user.id, "reset_password");
    await sendMail({
      to: user.email,
      subject: "Reset your password",
      text: `Someone asked to reset the password for this account. If it was you, choose a new password here:\n\n${env.clientUrl}/reset-password?token=${token}\n\nThe link is valid for 30 minutes. If you didn't ask for this, you can ignore this email.`,
    });
  }
  res.status(202).json({ message: "If that email has an account, a reset link is on its way." });
}

// Sets the new password, logs out every existing session (session_version
// bump) and signs the user in with a fresh one. Following a reset link also
// proves the user controls the address, so it verifies the email too.
export async function resetPassword(req: Request, res: Response) {
  const { token, password } = resetSchema.parse(req.body);
  const passwordHash = await bcrypt.hash(password, BCRYPT_COST);

  const client = await pool.connect();
  let user;
  try {
    await client.query("BEGIN");
    const userId = await consumeToken(client, token, "reset_password");
    if (!userId) {
      throw new HttpError(400, "This reset link is invalid or has expired", "INVALID_TOKEN");
    }
    const { rows } = await client.query(
      `UPDATE users SET password_hash = $1, session_version = session_version + 1,
         email_verified_at = COALESCE(email_verified_at, now())
       WHERE id = $2 RETURNING id, email, role, session_version`,
      [passwordHash, userId]
    );
    user = rows[0];
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }

  issueAuthCookie(res, user.id, user.session_version);
  res.json({ user: { id: user.id, email: user.email, role: user.role, emailVerified: true } });
}
