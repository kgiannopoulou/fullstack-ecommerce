import { Request, Response } from "express";
import { z } from "zod";
import { pool } from "../../db/pool";
import { HttpError } from "../../middleware/errorHandler";

const statusSchema = z.object({
  status: z.enum(["pending", "paid", "shipped", "cancelled"]),
});

// Unlike listMyOrders, this returns every order across all users (with the
// owning user's email attached) — safe only because this whole router is
// gated behind requireAdmin.
export async function listAdminOrders(_req: Request, res: Response) {
  const { rows } = await pool.query(
    `SELECT o.id, o.status, o.total_cents, o.created_at, u.email AS user_email
     FROM orders o JOIN users u ON u.id = o.user_id
     ORDER BY o.created_at DESC`
  );
  res.json({ orders: rows });
}

// Manual status transitions an admin makes by hand (e.g. marking an order
// "shipped"); 'paid' is normally set automatically by the Stripe webhook
// instead, but an admin could still force it here if needed.
export async function updateOrderStatus(req: Request, res: Response) {
  const { status } = statusSchema.parse(req.body);
  const { rows } = await pool.query(
    `UPDATE orders SET status = $1 WHERE id = $2 RETURNING *`,
    [status, req.params.id]
  );
  if (rows.length === 0) {
    throw new HttpError(404, "Order not found");
  }
  res.json({ order: rows[0] });
}
