import { Request, Response } from "express";
import { z } from "zod";
import { pool } from "../../db/pool";
import { HttpError } from "../../middleware/errorHandler";
import { orderHistory } from "../checkout/orderLifecycle";

export const idParamSchema = z.object({ id: z.coerce.number().int().positive() });

// Powers /account/orders — a user's own purchase history only (scoped to
// req.user.id below), never other users' orders. Admins get the unscoped
// view via admin/orders.controller.ts instead.
export async function listMyOrders(req: Request, res: Response) {
  const user = req.user!;

  const { rows: orders } = await pool.query(
    `SELECT id, status, total_cents, created_at FROM orders
     WHERE user_id = $1 ORDER BY created_at DESC`,
    [user.id]
  );

  // Two queries + an in-memory join, instead of one query with a JOIN,
  // because an order can have multiple items and joining would duplicate
  // the order row per item — this keeps the shape one row per order.
  const orderIds = orders.map((o) => o.id);
  const { rows: items } = orderIds.length
    ? await pool.query(
        `SELECT oi.order_id, oi.quantity, oi.price_cents, p.name, p.slug
         FROM order_items oi JOIN products p ON p.id = oi.product_id
         WHERE oi.order_id = ANY($1::int[])`,
        [orderIds]
      )
    : { rows: [] };

  const itemsByOrder = new Map<number, typeof items>();
  for (const item of items) {
    const list = itemsByOrder.get(item.order_id) ?? [];
    list.push(item);
    itemsByOrder.set(item.order_id, list);
  }

  res.json({
    orders: orders.map((order) => ({
      ...order,
      items: itemsByOrder.get(order.id) ?? [],
    })),
  });
}

// One of the user's own orders with its status history. Another user's
// order id answers 404, not 403, so ids can't be probed for existence.
export async function getMyOrder(req: Request, res: Response) {
  const { id } = idParamSchema.parse(req.params);
  const { rows } = await pool.query(
    `SELECT id, status, total_cents, created_at, paid_at FROM orders WHERE id = $1 AND user_id = $2`,
    [id, req.user!.id]
  );
  if (rows.length === 0) {
    throw new HttpError(404, "Order not found");
  }
  // Customers see what happened, not who did it internally.
  const history = (await orderHistory(id)).map(({ type, from_status, to_status, created_at }) => ({
    type,
    from_status,
    to_status,
    created_at,
  }));
  res.json({ order: rows[0], history });
}
