import { Request, Response } from "express";
import { z } from "zod";
import { pool } from "../../db/pool";
import { HttpError } from "../../middleware/errorHandler";
import {
  ADMIN_TRANSITIONS,
  InvalidTransitionError,
  adminSetStatus,
  orderHistory,
} from "../checkout/orderLifecycle";
import { idParamSchema } from "../orders/controller";

const ORDER_STATUSES = ["pending", "paid", "shipped", "cancelled"] as const;

const statusSchema = z.object({
  status: z.enum(ORDER_STATUSES),
});

const listQuerySchema = z.object({
  status: z.enum(ORDER_STATUSES).optional(),
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(25),
});

// Unlike listMyOrders, this returns every order across all users (with the
// owning user's email attached) — safe only because this whole router is
// gated behind requireAdmin. `next_statuses` tells the admin UI which manual
// changes the backend will accept for each order.
export async function listAdminOrders(req: Request, res: Response) {
  const { status, page, pageSize } = listQuerySchema.parse(req.query);
  const params: unknown[] = status ? [status] : [];
  const whereSql = status ? "WHERE o.status = $1" : "";

  const { rows: countRows } = await pool.query<{ total: number }>(
    `SELECT count(*)::int AS total FROM orders o ${whereSql}`,
    params
  );
  const { rows } = await pool.query(
    `SELECT o.id, o.status, o.total_cents, o.created_at, u.email AS user_email
     FROM orders o JOIN users u ON u.id = o.user_id
     ${whereSql}
     ORDER BY o.created_at DESC, o.id DESC
     LIMIT $${params.length + 1} OFFSET $${params.length + 2}`,
    [...params, pageSize, (page - 1) * pageSize]
  );
  const total = countRows[0].total;
  res.json({
    orders: rows.map((order) => ({ ...order, next_statuses: ADMIN_TRANSITIONS[order.status] ?? [] })),
    pagination: { page, pageSize, total, totalPages: Math.max(1, Math.ceil(total / pageSize)) },
  });
}

// Full audit trail for one order: every status change and stock movement,
// who caused it (customer, Stripe, the sweeper, which admin) and when.
export async function getOrderHistory(req: Request, res: Response) {
  const { id } = idParamSchema.parse(req.params);
  const { rowCount } = await pool.query(`SELECT 1 FROM orders WHERE id = $1`, [id]);
  if (!rowCount) {
    throw new HttpError(404, "Order not found");
  }
  res.json({ history: await orderHistory(id) });
}

// Manual status changes an admin makes by hand (e.g. marking an order
// "shipped"). Only the moves in ADMIN_TRANSITIONS are allowed: an order can
// never be pushed back to 'pending' or forced to 'paid', and cancelling
// gives its stock back exactly once. See orderLifecycle.ts.
export async function updateOrderStatus(req: Request, res: Response) {
  const { status } = statusSchema.parse(req.body);
  const { id: orderId } = idParamSchema.parse(req.params);

  let order;
  try {
    order = await adminSetStatus(orderId, status, req.user!.id);
  } catch (err) {
    if (err instanceof InvalidTransitionError) {
      throw new HttpError(409, err.message, "INVALID_TRANSITION");
    }
    throw err;
  }
  if (!order) {
    throw new HttpError(404, "Order not found");
  }
  res.json({ order });
}
