import { RequestHandler, Router } from "express";
import { requireAuth, requireVerifiedEmail } from "../../middleware/auth";
import { createCheckoutSession } from "./controller";

// `limiter` caps how many checkout sessions one user can open per minute,
// so nobody can hold the whole catalog's stock with throwaway reservations.
export function checkoutRouter(limiter: RequestHandler) {
  const router = Router();
  router.post("/create-session", requireAuth, requireVerifiedEmail, limiter, createCheckoutSession);
  return router;
}
