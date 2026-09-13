import { Router } from "express";
import { requireAuth } from "../../middleware/auth";
import { requireAdmin } from "../../middleware/requireAdmin";
import {
  createProduct,
  deleteProduct,
  getAdminProduct,
  listAdminProducts,
  updateProduct,
} from "./products.controller";
import { listAdminOrders, updateOrderStatus } from "./orders.controller";

export const adminRouter = Router();

// router.use() with no path applies these two middlewares to every route
// defined below in this file — so every /api/admin/* endpoint requires a
// signed-in admin, without repeating that on each route.
adminRouter.use(requireAuth, requireAdmin);

adminRouter.get("/products", listAdminProducts);
adminRouter.get("/products/:id", getAdminProduct);
adminRouter.post("/products", createProduct);
adminRouter.put("/products/:id", updateProduct);
adminRouter.delete("/products/:id", deleteProduct);

adminRouter.get("/orders", listAdminOrders);
adminRouter.patch("/orders/:id", updateOrderStatus);
