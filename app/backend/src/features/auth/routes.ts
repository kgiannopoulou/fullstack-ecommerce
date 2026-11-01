import { RequestHandler, Router } from "express";
import { attachUserIfPresent, requireAuth } from "../../middleware/auth";
import {
  forgotPassword,
  login,
  logout,
  me,
  requestEmailVerification,
  resetPassword,
  signup,
  verifyEmail,
} from "./controller";

// `limiter` guards everything an attacker could brute-force or use to spam
// email: signup, login, password reset and verification.
export function authRouter(limiter: RequestHandler) {
  const router = Router();

  router.post("/signup", limiter, signup);
  router.post("/login", limiter, login);
  router.post("/logout", logout);
  // Only /me needs to read the cookie if present; signup/login/logout don't
  // care about an existing session.
  router.get("/me", attachUserIfPresent, me);

  router.post("/verify-email", limiter, verifyEmail);
  router.post("/verify-email/resend", limiter, requireAuth, requestEmailVerification);
  router.post("/password/forgot", limiter, forgotPassword);
  router.post("/password/reset", limiter, resetPassword);

  return router;
}
