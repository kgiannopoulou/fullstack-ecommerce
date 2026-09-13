import { Request, Response } from "express";
import { pool } from "../../db/pool";

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
