import { beforeEach, describe, expect, it } from "vitest";
import { createProduct, createUser, startServer } from "./helpers";

const api = startServer();

describe("product catalog", () => {
  beforeEach(async () => {
    await createProduct({ name: "Blue Mug", priceCents: 1200, stock: 5 });
    await createProduct({ name: "Red Mug", priceCents: 900, stock: 0 });
    await createProduct({ name: "Desk Lamp", priceCents: 4500, stock: 3 });
    await createProduct({ name: "Green Mug", priceCents: 1500, stock: 8 });
    await createProduct({ name: "Notebook", priceCents: 300, stock: 40 });
  });

  const names = (res: { body: { products: { name: string }[] } }) => res.body.products.map((p) => p.name);

  it("paginates with metadata", async () => {
    const page1 = await api().get("/api/products?pageSize=2&sort=name");
    const page3 = await api().get("/api/products?pageSize=2&sort=name&page=3");

    expect(names(page1)).toEqual(["Blue Mug", "Desk Lamp"]);
    expect(page1.body.pagination).toEqual({ page: 1, pageSize: 2, total: 5, totalPages: 3 });
    expect(names(page3)).toEqual(["Red Mug"]);
  });

  it("searches, filters by price and stock, and sorts", async () => {
    const res = await api().get("/api/products?q=mug&minPrice=1000&inStock=true&sort=price_desc");
    expect(names(res)).toEqual(["Green Mug", "Blue Mug"]);
    expect(res.body.pagination.total).toBe(2);

    const soldOut = await api().get("/api/products?inStock=false");
    expect(names(soldOut)).toEqual(["Red Mug"]);
  });

  it("treats search input as data, not SQL", async () => {
    const res = await api().get(`/api/products?q=${encodeURIComponent("%' OR 1=1 --")}`);
    expect(res.status).toBe(200);
    expect(res.body.products).toEqual([]);
  });

  it("validates query parameters", async () => {
    const res = await api().get("/api/products?pageSize=500&sort=random&minPrice=50&maxPrice=10");
    expect(res.status).toBe(400);
    const paths = res.body.error.details.map((d: { path: string }) => d.path).sort();
    expect(paths).toEqual(["pageSize", "sort"]);
  });

  it("rejects an inverted price range", async () => {
    const res = await api().get("/api/products?minPrice=500&maxPrice=10");
    expect(res.status).toBe(400);
    expect(res.body.error.details[0].path).toBe("minPrice");
  });
});

describe("error format", () => {
  it("has a code, message and request id on every error", async () => {
    const res = await api().get("/api/products/does-not-exist").set("X-Request-Id", "req-123");
    expect(res.status).toBe(404);
    expect(res.body).toEqual({ error: { code: "NOT_FOUND", message: "Product not found", requestId: "req-123" } });
    expect(res.headers["x-request-id"]).toBe("req-123");
  });

  it("answers unknown API routes with a JSON 404", async () => {
    const res = await api().get("/api/nope");
    expect(res.status).toBe(404);
    expect(res.body.error.code).toBe("NOT_FOUND");
  });

  it("reports malformed JSON as INVALID_JSON", async () => {
    const res = await api().post("/api/auth/login").set("Content-Type", "application/json").send("{bad json");
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe("INVALID_JSON");
  });

  it("lists every validation problem with its field path", async () => {
    const user = await createUser();
    const res = await api()
      .post("/api/checkout/create-session")
      .set("Cookie", user.cookie)
      .send({ items: [{ productId: -1, quantity: 1000 }] });
    expect(res.status).toBe(400);
    expect(res.body.error.details.map((d: { path: string }) => d.path).sort()).toEqual([
      "items.0.productId",
      "items.0.quantity",
    ]);
  });

  it("maps a duplicate slug to 409 instead of a 500", async () => {
    const admin = await createUser(undefined, { role: "admin" });
    const product = { name: "Thing", slug: "thing", price_cents: 100, stock: 1 };
    await api().post("/api/admin/products").set("Cookie", admin.cookie).send(product);
    const dup = await api().post("/api/admin/products").set("Cookie", admin.cookie).send(product);
    expect(dup.status).toBe(409);
    expect(dup.body.error.code).toBe("CONFLICT");
  });

  it("validates id parameters", async () => {
    const admin = await createUser(undefined, { role: "admin" });
    const res = await api().get("/api/admin/products/abc").set("Cookie", admin.cookie);
    expect(res.status).toBe(400);
  });

  it("doesn't advertise the framework", async () => {
    const res = await api().get("/api/health");
    expect(res.headers["x-powered-by"]).toBeUndefined();
  });
});
