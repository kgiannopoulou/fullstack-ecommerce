import cookieParser from "cookie-parser";
import cors from "cors";
import express from "express";
import { env } from "./config/env";
import { errorHandler } from "./middleware/errorHandler";
import { adminRouter } from "./features/admin/routes";
import { authRouter } from "./features/auth/routes";
import { checkoutRouter } from "./features/checkout/routes";
import { stripeWebhook } from "./features/checkout/controller";
import { ordersRouter } from "./features/orders/routes";
import { productsRouter } from "./features/products/routes";

// Express app entry point. Wires up middleware and mounts each feature's
// router (auth, products, checkout, orders, admin) under /api/*. Route
// handlers themselves live in features/<name>/{routes,controller}.ts.
const app = express();

// credentials: true (server) + credentials: "include" (frontend fetches)
// is what allows the httpOnly auth cookie to travel between the frontend
// (localhost:3000) and this API (localhost:4000) despite being different
// ports/origins. `origin` must be an explicit URL, not "*", for that to work.
app.use(cors({ origin: env.corsOrigin, credentials: true }));
app.use(cookieParser());

// Stripe requires the raw request body to verify webhook signatures, so this
// route is registered before the global JSON body parser below.
app.post("/api/webhooks/stripe", express.raw({ type: "application/json" }), stripeWebhook);

// Parses JSON bodies for every other route. Registered after the webhook
// route above so it doesn't consume that route's raw body first.
app.use(express.json());

app.get("/api/health", (_req, res) => res.json({ ok: true }));

app.use("/api/auth", authRouter);
app.use("/api/products", productsRouter);
app.use("/api/checkout", checkoutRouter);
app.use("/api/orders", ordersRouter);
app.use("/api/admin", adminRouter);

// Must be registered last: Express treats any 4-argument middleware as an
// error handler, and errors only reach it if it comes after the routes
// that might throw.
app.use(errorHandler);

app.listen(env.port, () => {
  console.log(`Backend listening on http://localhost:${env.port}`);
});
