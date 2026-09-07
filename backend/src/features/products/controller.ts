import { Request, Response } from "express";
import { pool } from "../../db/pool";
import { HttpError } from "../../middleware/errorHandler";

export async function listProducts(req: Request, res: Response) {
  const search = typeof req.query.q === "string" ? req.query.q.trim() : "";

  const { rows } = search
    ? await pool.query(
        `SELECT id, name, slug, description, price_cents, image_url, stock
         FROM products WHERE name ILIKE $1 ORDER BY created_at DESC`,
        [`%${search}%`]
      )
    : await pool.query(
        `SELECT id, name, slug, description, price_cents, image_url, stock
         FROM products ORDER BY created_at DESC`
      );

  res.json({ products: rows });
}

export async function getProductBySlug(req: Request, res: Response) {
  const { rows } = await pool.query(
    `SELECT id, name, slug, description, price_cents, image_url, stock
     FROM products WHERE slug = $1`,
    [req.params.slug]
  );

  if (rows.length === 0) {
    throw new HttpError(404, "Product not found");
  }

  res.json({ product: rows[0] });
}
