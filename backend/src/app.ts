import cookieParser from "cookie-parser";
import cors from "cors";
import express from "express";
import { env } from "./config/env";
import { errorHandler, notFoundHandler } from "./middleware/errorHandler";
import { DEFAULT_RATE_LIMITS, RateLimitOptions, authLimiter, checkoutLimiter } from "./middleware/rateLimit";
import { requestId } from "./middleware/requestId";
import { adminRouter } from "./features/admin/routes";
import { authRouter } from "./features/auth/routes";
import { checkoutRouter } from "./features/checkout/routes";
import { stripeWebhook } from "./features/checkout/controller";
import { ordersRouter } from "./features/orders/routes";
import { productsRouter } from "./features/products/routes";

export type AppOptions = { rateLimits?: RateLimitOptions };

// Builds the Express app without starting it, so the tests can drive the
// real middleware stack with supertest. index.ts calls this and listens.
// Mounts each feature's router (auth, products, checkout, orders, admin)
// under /api/*; route handlers live in features/<name>/{routes,controller}.ts.
export function createApp({ rateLimits = DEFAULT_RATE_LIMITS }: AppOptions = {}) {
  const app = express();
  app.disable("x-powered-by");
  // Behind Render/Fly-style proxies the client IP is in
  // X-Forwarded-For; TRUST_PROXY says how many hops to trust (see env.ts).
  app.set("trust proxy", env.trustProxy);

  app.use(requestId);

  // credentials: true (server) + credentials: "include" (frontend fetches)
  // is what allows the httpOnly auth cookie to travel between the frontend
  // (localhost:3000) and this API (localhost:4000) despite being different
  // ports/origins. `origin` must be an explicit URL, not "*", for that to work.
  app.use(cors({ origin: env.corsOrigin, credentials: true, exposedHeaders: ["X-Request-Id"] }));
  app.use(cookieParser());

  // Stripe requires the raw request body to verify webhook signatures, so this
  // route is registered before the global JSON body parser below.
  app.post("/api/webhooks/stripe", express.raw({ type: "application/json" }), stripeWebhook);

  // Parses JSON bodies for every other route. Registered after the webhook
  // route above so it doesn't consume that route's raw body first.
  app.use(express.json({ limit: "100kb" }));

  app.get("/api/health", (_req, res) => res.json({ ok: true }));

  app.use("/api/auth", authRouter(authLimiter(rateLimits.auth)));
  app.use("/api/products", productsRouter);
  app.use("/api/checkout", checkoutRouter(checkoutLimiter(rateLimits.checkout)));
  app.use("/api/orders", ordersRouter);
  app.use("/api/admin", adminRouter);

  app.use("/api", notFoundHandler);

  // Must be registered last: Express treats any 4-argument middleware as an
  // error handler, and errors only reach it if it comes after the routes
  // that might throw.
  app.use(errorHandler);

  return app;
}
