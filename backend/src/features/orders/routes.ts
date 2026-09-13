import { Router } from "express";
import { requireAuth } from "../../middleware/auth";
import { listMyOrders } from "./controller";

export const ordersRouter = Router();

ordersRouter.get("/", requireAuth, listMyOrders);
