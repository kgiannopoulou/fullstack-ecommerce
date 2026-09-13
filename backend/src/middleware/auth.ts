import { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";
import { env } from "../config/env";
import { AuthUser } from "../types/express";

// Session strategy: a JWT containing { id, email, role } is stored in an
// httpOnly cookie (not localStorage/a client-readable header), so client-side
// JS can never read or tamper with it directly — only the browser sends it
// back automatically on same-site requests. The frontend calls every API
// with `credentials: "include"` (see frontend/src/lib/api.ts) for this
// cookie to be attached cross-port (localhost:3000 -> localhost:4000).
//
// IMPORTANT CAVEAT: the token's payload (including `role`) is fixed at the
// moment it's issued (signup/login) and is NOT re-checked against the
// database on every request. If an admin promotes a user's role directly in
// Postgres, that user's *existing* cookie still carries the old role until
// they log out and back in and get a freshly signed token. See the "Becoming
// an admin" section in the root README.
const COOKIE_NAME = "token";

export function issueAuthCookie(res: Response, user: AuthUser) {
  const token = jwt.sign(user, env.jwtSecret, { expiresIn: "7d" });
  res.cookie(COOKIE_NAME, token, {
    httpOnly: true, // inaccessible to client-side JS (mitigates XSS token theft)
    sameSite: "lax", // not sent on cross-site requests (mitigates CSRF)
    secure: process.env.NODE_ENV === "production", // HTTPS-only outside local dev
    maxAge: 7 * 24 * 60 * 60 * 1000,
  });
}

export function clearAuthCookie(res: Response) {
  res.clearCookie(COOKIE_NAME);
}

// Route guard for endpoints that require a signed-in user (checkout, order
// history, admin routes). Rejects with 401 if there's no valid token.
export function requireAuth(req: Request, res: Response, next: NextFunction) {
  const token = req.cookies?.[COOKIE_NAME];
  if (!token) {
    return res.status(401).json({ error: "Not authenticated" });
  }

  try {
    const payload = jwt.verify(token, env.jwtSecret) as AuthUser;
    req.user = payload;
    next();
  } catch {
    return res.status(401).json({ error: "Invalid or expired session" });
  }
}

// Softer variant used only by GET /api/auth/me: populates req.user when a
// valid cookie is present, but never rejects the request. This lets the
// frontend ask "am I logged in?" on every page load without that check
// itself requiring you to already be logged in.
export function attachUserIfPresent(req: Request, _res: Response, next: NextFunction) {
  const token = req.cookies?.[COOKIE_NAME];
  if (token) {
    try {
      req.user = jwt.verify(token, env.jwtSecret) as AuthUser;
    } catch {
      // ignore invalid token, treat as unauthenticated
    }
  }
  next();
}
