import { Request, Response } from "express";
import { z } from "zod";
import { pool } from "../../db/pool";
import { HttpError } from "../../middleware/errorHandler";

// Public catalog endpoints — no auth required, used by the storefront.

const SORTS = {
  newest: "created_at DESC, id DESC",
  price_asc: "price_cents ASC, id ASC",
  price_desc: "price_cents DESC, id DESC",
  name: "name ASC, id ASC",
} as const;

// Query strings arrive as strings, hence z.coerce for the numbers.
const listQuerySchema = z
  .object({
    q: z.string().trim().max(100).optional(),
    minPrice: z.coerce.number().int().nonnegative().optional(), // cents
    maxPrice: z.coerce.number().int().nonnegative().optional(), // cents
    inStock: z.enum(["true", "false"]).optional(),
    sort: z.enum(Object.keys(SORTS) as [keyof typeof SORTS]).default("newest"),
    page: z.coerce.number().int().min(1).default(1),
    pageSize: z.coerce.number().int().min(1).max(50).default(12),
  })
  .refine((v) => v.minPrice === undefined || v.maxPrice === undefined || v.minPrice <= v.maxPrice, {
    message: "minPrice must not be greater than maxPrice",
    path: ["minPrice"],
  });

// Powers both the homepage grid and the search/filter controls. Every
// filter is optional; the response carries the paging metadata the
// frontend needs to render page links.
//
//   GET /api/products?q=mug&minPrice=500&maxPrice=5000&inStock=true&sort=price_asc&page=2&pageSize=12
export async function listProducts(req: Request, res: Response) {
  const query = listQuerySchema.parse(req.query);

  // Each filter appends a parameterised condition; user input never ends up
  // in the SQL text itself. `sort` is safe to interpolate because it was
  // validated against the SORTS keys above.
  const where: string[] = [];
  const params: unknown[] = [];
  if (query.q) {
    params.push(`%${query.q}%`);
    where.push(`(name ILIKE $${params.length} OR description ILIKE $${params.length})`);
  }
  if (query.minPrice !== undefined) {
    params.push(query.minPrice);
    where.push(`price_cents >= $${params.length}`);
  }
  if (query.maxPrice !== undefined) {
    params.push(query.maxPrice);
    where.push(`price_cents <= $${params.length}`);
  }
  if (query.inStock === "true") where.push(`stock > 0`);
  if (query.inStock === "false") where.push(`stock = 0`);
  const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";

  const { rows: countRows } = await pool.query<{ total: number }>(
    `SELECT count(*)::int AS total FROM products ${whereSql}`,
    params
  );
  const total = countRows[0].total;

  const offset = (query.page - 1) * query.pageSize;
  const { rows } = await pool.query(
    `SELECT id, name, slug, description, price_cents, image_url, stock
     FROM products ${whereSql}
     ORDER BY ${SORTS[query.sort]}
     LIMIT $${params.length + 1} OFFSET $${params.length + 2}`,
    [...params, query.pageSize, offset]
  );

  res.json({
    products: rows,
    pagination: {
      page: query.page,
      pageSize: query.pageSize,
      total,
      totalPages: Math.max(1, Math.ceil(total / query.pageSize)),
    },
  });
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
