import { Router } from "express";
import { requireAuth } from "../../middleware/auth";
import { createCheckoutSession } from "./controller";

export const checkoutRouter = Router();

checkoutRouter.post("/create-session", requireAuth, createCheckoutSession);
