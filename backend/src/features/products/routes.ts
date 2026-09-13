import { Router } from "express";
import { getProductBySlug, listProducts } from "./controller";

export const productsRouter = Router();

productsRouter.get("/", listProducts);
productsRouter.get("/:slug", getProductBySlug);
