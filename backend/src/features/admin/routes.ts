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

adminRouter.use(requireAuth, requireAdmin);

adminRouter.get("/products", listAdminProducts);
adminRouter.get("/products/:id", getAdminProduct);
adminRouter.post("/products", createProduct);
adminRouter.put("/products/:id", updateProduct);
adminRouter.delete("/products/:id", deleteProduct);

adminRouter.get("/orders", listAdminOrders);
adminRouter.patch("/orders/:id", updateOrderStatus);
