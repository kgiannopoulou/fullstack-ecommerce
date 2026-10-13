import { Request, Response } from "express";
import { z } from "zod";
import { pool } from "../../db/pool";
import { HttpError } from "../../middleware/errorHandler";
import {
  ADMIN_TRANSITIONS,
  InvalidTransitionError,
  adminSetStatus,
} from "../checkout/orderLifecycle";

const statusSchema = z.object({
  status: z.enum(["pending", "paid", "shipped", "cancelled"]),
});

// Unlike listMyOrders, this returns every order across all users (with the
// owning user's email attached) — safe only because this whole router is
// gated behind requireAdmin. `next_statuses` tells the admin UI which manual
// changes the backend will accept for each order.
export async function listAdminOrders(_req: Request, res: Response) {
  const { rows } = await pool.query(
    `SELECT o.id, o.status, o.total_cents, o.created_at, u.email AS user_email
     FROM orders o JOIN users u ON u.id = o.user_id
     ORDER BY o.created_at DESC`
  );
  res.json({
    orders: rows.map((order) => ({ ...order, next_statuses: ADMIN_TRANSITIONS[order.status] ?? [] })),
  });
}

// Manual status changes an admin makes by hand (e.g. marking an order
// "shipped"). Only the moves in ADMIN_TRANSITIONS are allowed: an order can
// never be pushed back to 'pending' or forced to 'paid', and cancelling
// gives its stock back exactly once. See orderLifecycle.ts.
export async function updateOrderStatus(req: Request, res: Response) {
  const { status } = statusSchema.parse(req.body);
  const orderId = Number(req.params.id);
  if (!Number.isInteger(orderId) || orderId <= 0) {
    throw new HttpError(404, "Order not found");
  }

  let order;
  try {
    order = await adminSetStatus(orderId, status);
  } catch (err) {
    if (err instanceof InvalidTransitionError) {
      throw new HttpError(409, err.message);
    }
    throw err;
  }
  if (!order) {
    throw new HttpError(404, "Order not found");
  }
  res.json({ order });
}
