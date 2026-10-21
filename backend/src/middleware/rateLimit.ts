import { Request, Response } from "express";
import { rateLimit } from "express-rate-limit";
import { sendError } from "./errorHandler";

export type RateLimitOptions = {
  // Signup, login, password reset and email verification: per client IP.
  auth: { windowMs: number; limit: number };
  // Creating checkout sessions: per signed-in user (falls back to IP).
  checkout: { windowMs: number; limit: number };
};

export const DEFAULT_RATE_LIMITS: RateLimitOptions = {
  auth: { windowMs: 15 * 60 * 1000, limit: 20 },
  checkout: { windowMs: 60 * 1000, limit: 10 },
};

function onLimit(req: Request, res: Response) {
  sendError(req, res, 429, "RATE_LIMITED", "Too many requests, please try again later");
}

// Brute-forcing passwords, spamming reset emails and holding stock with
// endless checkout sessions are the abuse cases these limiters exist for.
// The store is in-memory, which is right for a single instance; behind a
// load balancer this would move to Redis (rate-limit-redis).
export function authLimiter(opts: RateLimitOptions["auth"]) {
  return rateLimit({
    ...opts,
    standardHeaders: "draft-8",
    legacyHeaders: false,
    handler: onLimit,
  });
}

export function checkoutLimiter(opts: RateLimitOptions["checkout"]) {
  return rateLimit({
    ...opts,
    standardHeaders: "draft-8",
    legacyHeaders: false,
    // Runs after requireAuth, so every request has a user.
    keyGenerator: (req) => `user:${req.user!.id}`,
    handler: onLimit,
  });
}
