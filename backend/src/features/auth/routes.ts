import { Router } from "express";
import { attachUserIfPresent } from "../../middleware/auth";
import { login, logout, me, signup } from "./controller";

export const authRouter = Router();

authRouter.post("/signup", signup);
authRouter.post("/login", login);
authRouter.post("/logout", logout);
authRouter.get("/me", attachUserIfPresent, me);
