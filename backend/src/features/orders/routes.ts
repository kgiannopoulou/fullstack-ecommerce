import { Router } from "express";
import { requireAuth } from "../../middleware/auth";
import { getMyOrder, listMyOrders } from "./controller";

export const ordersRouter = Router();

ordersRouter.get("/", requireAuth, listMyOrders);
ordersRouter.get("/:id", requireAuth, getMyOrder);
