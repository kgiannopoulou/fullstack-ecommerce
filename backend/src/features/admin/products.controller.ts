import { Request, Response } from "express";
import { z } from "zod";
import { pool } from "../../db/pool";
import { HttpError } from "../../middleware/errorHandler";

// All handlers in this file sit behind requireAuth + requireAdmin, applied
// once for the whole router in admin/routes.ts, rather than repeated here
// per handler.
const productSchema = z.object({
  name: z.string().min(1),
  slug: z
    .string()
    .min(1)
    .regex(/^[a-z0-9-]+$/, "slug must be lowercase letters, numbers, and hyphens"),
  description: z.string().default(""),
  price_cents: z.number().int().nonnegative(),
  image_url: z.string().url().optional().nullable(),
  stock: z.number().int().nonnegative(),
});

export async function listAdminProducts(_req: Request, res: Response) {
  const { rows } = await pool.query(
    `SELECT id, name, slug, description, price_cents, image_url, stock, created_at
     FROM products ORDER BY created_at DESC`
  );
  res.json({ products: rows });
}

export async function getAdminProduct(req: Request, res: Response) {
  const { rows } = await pool.query(
    `SELECT id, name, slug, description, price_cents, image_url, stock, created_at
     FROM products WHERE id = $1`,
    [req.params.id]
  );
  if (rows.length === 0) {
    throw new HttpError(404, "Product not found");
  }
  res.json({ product: rows[0] });
}

export async function createProduct(req: Request, res: Response) {
  const data = productSchema.parse(req.body);
  const { rows } = await pool.query(
    `INSERT INTO products (name, slug, description, price_cents, image_url, stock)
     VALUES ($1, $2, $3, $4, $5, $6) RETURNING *`,
    [data.name, data.slug, data.description, data.price_cents, data.image_url ?? null, data.stock]
  );
  res.status(201).json({ product: rows[0] });
}

export async function updateProduct(req: Request, res: Response) {
  const data = productSchema.parse(req.body);
  const { rows } = await pool.query(
    `UPDATE products SET name = $1, slug = $2, description = $3, price_cents = $4,
     image_url = $5, stock = $6 WHERE id = $7 RETURNING *`,
    [
      data.name,
      data.slug,
      data.description,
      data.price_cents,
      data.image_url ?? null,
      data.stock,
      req.params.id,
    ]
  );
  if (rows.length === 0) {
    throw new HttpError(404, "Product not found");
  }
  res.json({ product: rows[0] });
}

export async function deleteProduct(req: Request, res: Response) {
  const { rowCount } = await pool.query(`DELETE FROM products WHERE id = $1`, [req.params.id]);
  if (rowCount === 0) {
    throw new HttpError(404, "Product not found");
  }
  res.status(204).end();
}
