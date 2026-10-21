import { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";
import { env } from "../config/env";
import { pool } from "../db/pool";
import { AuthUser } from "../types/express";
import { HttpError } from "./errorHandler";

// Session strategy: a JWT is stored in an httpOnly cookie (not
// localStorage/a client-readable header), so client-side JS can never read
// or tamper with it directly — only the browser sends it back automatically
// on same-site requests. The frontend calls every API with
// `credentials: "include"` (see frontend/src/lib/api.ts) for this cookie to
// be attached cross-port (localhost:3000 -> localhost:4000).
//
// The token only carries the user's id and their `session_version`. The
// user's current email, role and verification status are loaded from the
// database on every request, so promoting someone to admin takes effect
// immediately, and bumping session_version (done on password reset) logs
// out every existing session for that user.
export const COOKIE_NAME = "token";

type TokenPayload = { id: number; ver: number };

export function signSessionToken(userId: number, sessionVersion: number) {
  const payload: TokenPayload = { id: userId, ver: sessionVersion };
  return jwt.sign(payload, env.jwtSecret, { expiresIn: "7d" });
}

export function issueAuthCookie(res: Response, userId: number, sessionVersion: number) {
  res.cookie(COOKIE_NAME, signSessionToken(userId, sessionVersion), {
    httpOnly: true, // inaccessible to client-side JS (mitigates XSS token theft)
    sameSite: "lax", // not sent on cross-site requests (mitigates CSRF)
    secure: process.env.NODE_ENV === "production", // HTTPS-only outside local dev
    maxAge: 7 * 24 * 60 * 60 * 1000,
  });
}

export function clearAuthCookie(res: Response) {
  res.clearCookie(COOKIE_NAME);
}

// Returns the user a session cookie belongs to, or null if the cookie is
// missing, invalid, expired, or was issued before the last session reset.
async function userFromCookie(req: Request): Promise<AuthUser | null> {
  const token = req.cookies?.[COOKIE_NAME];
  if (!token) return null;

  let payload: TokenPayload;
  try {
    payload = jwt.verify(token, env.jwtSecret) as TokenPayload;
  } catch {
    return null;
  }

  const { rows } = await pool.query(
    `SELECT id, email, role, email_verified_at, session_version FROM users WHERE id = $1`,
    [payload.id]
  );
  const row = rows[0];
  if (!row || row.session_version !== payload.ver) return null;
  return { id: row.id, email: row.email, role: row.role, emailVerified: row.email_verified_at !== null };
}

// Route guard for endpoints that require a signed-in user (checkout, order
// history, admin routes). Rejects with 401 if there's no valid session.
export async function requireAuth(req: Request, _res: Response, next: NextFunction) {
  const user = await userFromCookie(req);
  if (!user) {
    throw new HttpError(401, "Not signed in, or your session has expired");
  }
  req.user = user;
  next();
}

// For actions that need a confirmed email address (placing an order). Must
// run after requireAuth.
export function requireVerifiedEmail(req: Request, _res: Response, next: NextFunction) {
  if (!req.user?.emailVerified) {
    throw new HttpError(403, "Please verify your email address first", "EMAIL_NOT_VERIFIED");
  }
  next();
}

// Softer variant used only by GET /api/auth/me: populates req.user when a
// valid cookie is present, but never rejects the request. This lets the
// frontend ask "am I logged in?" on every page load without that check
// itself requiring you to already be logged in.
export async function attachUserIfPresent(req: Request, _res: Response, next: NextFunction) {
  req.user = (await userFromCookie(req)) ?? undefined;
  next();
}
