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

const app = express();

app.use(cors({ origin: env.corsOrigin, credentials: true }));
app.use(cookieParser());

// Stripe requires the raw request body to verify webhook signatures, so this
// route is registered before the global JSON body parser below.
app.post("/api/webhooks/stripe", express.raw({ type: "application/json" }), stripeWebhook);

app.use(express.json());

app.get("/api/health", (_req, res) => res.json({ ok: true }));

app.use("/api/auth", authRouter);
app.use("/api/products", productsRouter);
app.use("/api/checkout", checkoutRouter);
app.use("/api/orders", ordersRouter);
app.use("/api/admin", adminRouter);

app.use(errorHandler);

app.listen(env.port, () => {
  console.log(`Backend listening on http://localhost:${env.port}`);
});
