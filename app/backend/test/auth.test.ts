import { describe, expect, it } from "vitest";
import { pool } from "../src/db/pool";
import { PASSWORD, createUser, startServer } from "./helpers";
import { lastTokenSentTo, outbox } from "./fakes";

const api = startServer();

function cookieFrom(res: { headers: Record<string, unknown> }) {
  const header = res.headers["set-cookie"] as string[] | undefined;
  return header?.[0]?.split(";")[0] ?? "";
}

describe("signup and login", () => {
  it("signs up, sends a verification email, and starts a session", async () => {
    const res = await api().post("/api/auth/signup").send({ email: "New@Example.com", password: PASSWORD });

    expect(res.status).toBe(201);
    expect(res.body.user).toMatchObject({ email: "new@example.com", role: "user", emailVerified: false });
    expect(outbox.map((m) => m.to)).toEqual(["new@example.com"]);

    const me = await api().get("/api/auth/me").set("Cookie", cookieFrom(res));
    expect(me.body.user.email).toBe("new@example.com");
  });

  it("rejects a duplicate email regardless of case", async () => {
    await createUser("taken@example.com");
    const res = await api().post("/api/auth/signup").send({ email: "TAKEN@example.com", password: PASSWORD });
    expect(res.status).toBe(409);
    expect(res.body.error.code).toBe("EMAIL_TAKEN");
  });

  it("gives the same answer for an unknown email and a wrong password", async () => {
    await createUser("real@example.com");
    const unknown = await api().post("/api/auth/login").send({ email: "nobody@example.com", password: PASSWORD });
    const wrong = await api().post("/api/auth/login").send({ email: "real@example.com", password: "wrong-password" });

    expect(unknown.status).toBe(401);
    expect(wrong.status).toBe(401);
    expect(unknown.body.error.message).toBe(wrong.body.error.message);
    expect(unknown.body.error.code).toBe("INVALID_CREDENTIALS");
  });

  it("can't self-assign a role at signup", async () => {
    const res = await api().post("/api/auth/signup").send({ email: "sneaky@example.com", password: PASSWORD, role: "admin" });
    expect(res.body.user.role).toBe("user");
  });

  it("applies a role change on the next request, without logging in again", async () => {
    const user = await createUser();
    expect((await api().get("/api/admin/orders").set("Cookie", user.cookie)).status).toBe(403);

    await pool.query(`UPDATE users SET role = 'admin' WHERE id = $1`, [user.id]);

    expect((await api().get("/api/admin/orders").set("Cookie", user.cookie)).status).toBe(200);
  });
});

describe("email verification", () => {
  it("verifies with the emailed token, which then can't be reused", async () => {
    const signup = await api().post("/api/auth/signup").send({ email: "v@example.com", password: PASSWORD });
    const token = lastTokenSentTo("v@example.com", "verify-email");

    const first = await api().post("/api/auth/verify-email").send({ token });
    const again = await api().post("/api/auth/verify-email").send({ token });

    expect(first.status).toBe(200);
    expect(again.status).toBe(400);
    expect(again.body.error.code).toBe("INVALID_TOKEN");
    const me = await api().get("/api/auth/me").set("Cookie", cookieFrom(signup));
    expect(me.body.user.emailVerified).toBe(true);
  });

  it("stores only a hash of the token", async () => {
    await api().post("/api/auth/signup").send({ email: "h@example.com", password: PASSWORD });
    const token = lastTokenSentTo("h@example.com", "verify-email");
    const { rows } = await pool.query(`SELECT token_hash FROM auth_tokens`);
    expect(rows[0].token_hash).not.toContain(token);
    expect(rows[0].token_hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it("rejects an expired token", async () => {
    await api().post("/api/auth/signup").send({ email: "e@example.com", password: PASSWORD });
    const token = lastTokenSentTo("e@example.com", "verify-email");
    await pool.query(`UPDATE auth_tokens SET expires_at = now() - interval '1 second'`);

    const res = await api().post("/api/auth/verify-email").send({ token });
    expect(res.status).toBe(400);
  });

  it("resending invalidates the previous link", async () => {
    const signup = await api().post("/api/auth/signup").send({ email: "r@example.com", password: PASSWORD });
    const oldToken = lastTokenSentTo("r@example.com", "verify-email");

    await api().post("/api/auth/verify-email/resend").set("Cookie", cookieFrom(signup));
    const newToken = lastTokenSentTo("r@example.com", "verify-email");

    expect((await api().post("/api/auth/verify-email").send({ token: oldToken })).status).toBe(400);
    expect((await api().post("/api/auth/verify-email").send({ token: newToken })).status).toBe(200);
  });
});

describe("password reset", () => {
  it("doesn't reveal whether an account exists", async () => {
    await createUser("exists@example.com");
    const known = await api().post("/api/auth/password/forgot").send({ email: "exists@example.com" });
    const unknown = await api().post("/api/auth/password/forgot").send({ email: "ghost@example.com" });

    expect(known.status).toBe(202);
    expect(unknown.status).toBe(202);
    expect(known.body).toEqual(unknown.body);
    expect(outbox.map((m) => m.to)).toEqual(["exists@example.com"]);
  });

  it("resets the password, logs out other sessions and signs in with a new one", async () => {
    const user = await createUser("reset@example.com");
    await api().post("/api/auth/password/forgot").send({ email: "reset@example.com" });
    const token = lastTokenSentTo("reset@example.com", "reset-password");

    const res = await api().post("/api/auth/password/reset").send({ token, password: "a-brand-new-password" });

    expect(res.status).toBe(200);
    // The old session cookie no longer works...
    expect((await api().get("/api/orders").set("Cookie", user.cookie)).status).toBe(401);
    // ...the new one does, and so does the new password.
    expect((await api().get("/api/orders").set("Cookie", cookieFrom(res))).status).toBe(200);
    const login = await api().post("/api/auth/login").send({ email: "reset@example.com", password: "a-brand-new-password" });
    expect(login.status).toBe(200);
    const oldLogin = await api().post("/api/auth/login").send({ email: "reset@example.com", password: PASSWORD });
    expect(oldLogin.status).toBe(401);
  });

  it("accepts a reset token only once, even under concurrent use", async () => {
    await createUser("once@example.com");
    await api().post("/api/auth/password/forgot").send({ email: "once@example.com" });
    const token = lastTokenSentTo("once@example.com", "reset-password");

    const results = await Promise.all(
      Array.from({ length: 5 }, (_, i) => api().post("/api/auth/password/reset").send({ token, password: `password-${i}-xyz` }))
    );

    expect(results.filter((r) => r.status === 200)).toHaveLength(1);
  });

  it("validates the new password", async () => {
    const res = await api().post("/api/auth/password/reset").send({ token: "x", password: "short" });
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe("VALIDATION_FAILED");
    expect(res.body.error.details).toEqual([expect.objectContaining({ path: "password" })]);
  });
});

describe("rate limiting", () => {
  const limited = startServer({
    auth: { windowMs: 60_000, limit: 3 },
    checkout: { windowMs: 60_000, limit: 2 },
  });

  it("limits login attempts", async () => {
    const attempt = () => limited().post("/api/auth/login").send({ email: "x@example.com", password: "wrong-password" });
    const statuses = [];
    for (let i = 0; i < 5; i++) statuses.push((await attempt()).status);

    expect(statuses).toEqual([401, 401, 401, 429, 429]);
    const blocked = await attempt();
    expect(blocked.body.error.code).toBe("RATE_LIMITED");
    expect(blocked.headers["ratelimit-policy"]).toBeDefined();
  });

  it("limits checkout sessions per user", async () => {
    const { createProduct } = await import("./helpers");
    const productId = await createProduct({ stock: 100 });
    const a = await createUser();
    const b = await createUser();
    const checkout = (cookie: string) =>
      limited().post("/api/checkout/create-session").set("Cookie", cookie).send({ items: [{ productId, quantity: 1 }] });

    const statuses = [];
    for (let i = 0; i < 3; i++) statuses.push((await checkout(a.cookie)).status);
    expect(statuses).toEqual([200, 200, 429]);
    // Another user has their own budget.
    expect((await checkout(b.cookie)).status).toBe(200);
  });
});
